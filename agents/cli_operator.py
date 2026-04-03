"""CLI Operator agent entry point.

A news48 pipeline worker agent that controls the CLI, monitors the system,
troubleshoots issues, and verifies information via web search.
"""

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
        create_plan,
        fetch_webpage_content,
        get_system_info,
        perform_web_search,
        read_file,
        run_shell_command,
        update_plan,
    )

    agent = FunctionAgent(
        name="CLI Operator",
        description=(
            "A news48 pipeline worker agent that controls the pipeline "
            "via CLI commands, monitors system health, troubleshoots "
            "failures, and verifies information via web search. "
            "Operates in four roles: Pipeline Operator, System Monitor, "
            "Troubleshooter, and Fact Checker."
        ),
        llm=OpenAILike(
            model="enfuse/smol-tools-4b-32k",
            api_base=api_base,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        tools=[
            run_shell_command,
            read_file,
            perform_web_search,
            fetch_webpage_content,
            get_system_info,
            create_plan,
            update_plan,
        ],
        system_prompt=load_agent_instructions("cli-operator"),
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
                    f"System error while executing tool: {event.tool_name}."
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

    asyncio.run(main(user_prompt="show system stats"))
