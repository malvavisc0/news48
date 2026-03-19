"""LLM configuration utilities."""

from llama_index.llms.openai_like import OpenAILike


def get_llm(
    model: str, api_base: str, api_key: str, context_window: int
) -> OpenAILike:
    """Create and configure an OpenAI-like LLM instance.

    Args:
        model: The model name to use.
        api_base: The base URL for the API.
        api_key: The API key for authentication.
        context_window: The context window size for the model.

    Returns:
        A configured OpenAILike LLM instance.
    """
    return OpenAILike(
        model=model,
        api_base=api_base,
        api_key=api_key,
        context_window=context_window,
        is_chat_model=True,
        is_function_calling_model=True,
    )
