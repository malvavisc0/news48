import json
from os import getenv

from dotenv import load_dotenv
from llama_index.core.agent.workflow import (
    AgentStream,
    FunctionAgent,
    ToolCall,
    ToolCallResult,
)
from llama_index.llms.openai_like import OpenAILike
from loguru import logger

from agents.instructions import load_agent_instructions


async def main(user_prompt: str):
    load_dotenv()

    api_base = getenv("API_BASE", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import (
        add_plan_step,
        create_execution_plan,
        fetch_webpage_content,
        get_execution_plan,
        get_file_content,
        get_file_info,
        get_system_info,
        list_directory,
        perform_web_search,
        read_file_chunk,
        remove_plan_step,
        reorder_plan_steps,
        replace_plan_step,
        run_shell_command,
        update_plan_step,
    )

    agent = FunctionAgent(
        name="Operator",
        description=(
            "A general-purpose Operator agent that can take arbitrary user "
            "tasks, inspect available context, use tools to gather evidence, "
            "execute actions, and maintain an explicit execution plan through "
            "planner tools."
        ),
        llm=OpenAILike(
            model="enfuse/smol-tools-4b-32k",
            api_base=api_base,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        tools=[
            add_plan_step,
            create_execution_plan,
            fetch_webpage_content,
            get_execution_plan,
            get_file_content,
            get_file_info,
            get_system_info,
            list_directory,
            perform_web_search,
            read_file_chunk,
            remove_plan_step,
            reorder_plan_steps,
            replace_plan_step,
            run_shell_command,
            update_plan_step,
        ],
        system_prompt=load_agent_instructions("operator"),
        verbose=False,
        streaming=True,
    )
    handler = agent.run(user_msg=user_prompt, max_iterations=500)

    # handle streaming output
    async for event in handler.stream_events():
        if isinstance(event, ToolCall):
            logger.info(
                f"Executing tool: {event.tool_name}. "
                f"Reason: {event.tool_kwargs.get('reason', 'Unknown')}"
            )
        elif isinstance(event, ToolCallResult):
            if event.tool_output.is_error:
                logger.info(
                    f"System error while executing tool: {event.tool_name}.-"
                )
                continue
            output: dict = json.loads(event.tool_output.raw_output)
            error = output.get("error", None)
            if error:
                logger.info(
                    f"Unsuccessfully execution of the tool: {event.tool_name}."
                    f" Error: {error}."
                )
                continue
            logger.info(f"Completed execution of tool: {event.tool_name}.")
        elif isinstance(event, AgentStream):
            print(event.delta, end="", flush=True)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main(user_prompt=("Who is Elon Musk")))
