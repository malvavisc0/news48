"""News parser agent module.

Provides a factory for the NewsParserAgent, a LlamaIndex FunctionAgent that
extracts structured article data from raw HTML pages and updates articles
directly via CLI commands.
"""

from os import getenv

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai_like import OpenAILike

from agents._run import run_agent
from agents.skills import compose_agent_instructions


def get_agent(task_context: dict | None = None) -> FunctionAgent:
    """Create and configure the News Parser Agent.

    Args:
        task_context: Dict with keys for conditional skill loading.
            If None, uses empty context (all core skills loaded).
    """
    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")
    if not api_base:
        raise ValueError("Missing API_BASE env.")

    from agents.tools import read_file, run_shell_command

    ctx = task_context or {}

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
        system_prompt=compose_agent_instructions("parser", ctx),
        streaming=True,
        verbose=False,
    )


async def run(task: str, task_context: dict | None = None):
    """Run the News Parser Agent with a task prompt.

    Parses a single article. The task must contain article information
    (ID, title, HTML file path, URL) so the agent knows what to parse.

    Args:
        task: Task prompt containing article details for parsing.
        task_context: Optional dict for conditional skill loading.

    Returns:
        The final text response from the agent.
    """
    return await run_agent(lambda: get_agent(task_context), task)
