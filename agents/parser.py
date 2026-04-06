"""News parser agent module.

Provides a factory for the NewsParserAgent, a LlamaIndex FunctionAgent that
extracts structured article data from raw HTML pages and updates articles
directly via CLI commands.
"""

from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.instructions import load_agent_instructions


def get_agent() -> FunctionAgent:
    """Create and configure the News Parser Agent.

    Self-manages LLM creation from environment variables (PARSER_* with
    fallback to generic vars).

    Returns:
        A configured FunctionAgent ready for article parsing.
    """
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import read_file, run_shell_command

    return FunctionAgent(
        name="NewsParser",
        description=(
            "Parses HTML article pages and updates articles directly via CLI. "
            "Extracts structured data from news websites and saves to DB."
        ),
        tools=[run_shell_command, read_file],
        llm=OpenAILike(
            model=model,
            api_base=api_base,
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=True,
        ),
        system_prompt=load_agent_instructions("parser"),
        streaming=True,
        verbose=False,
        # No output_cls — agent uses CLI tools to update articles
    )


async def run(task: str):
    """Run the News Parser Agent with a task prompt.

    Parses a single article. The task must contain article information
    (ID, title, HTML file path, URL) so the agent knows what to parse.

    Args:
        task: Task prompt containing article details for parsing.

    Returns:
        The final text response from the agent.
    """
    return await run_agent(get_agent, task)
