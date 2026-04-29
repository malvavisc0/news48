# NOTE: Do NOT import parser here — parser imports llama_index which is only
# available in the worker image (extra cli). The web image only has extra web.
# Use lazy imports where needed:
#   from news48.core.agents.parser import run as run_parser

__all__: list[str] = []
