"""CLI commands package."""

from .agents import agents_app
from .articles import articles_app
from .briefing import briefing
from .cleanup import cleanup_app
from .doctor import doctor
from .download import download
from .feeds import feeds_app
from .fetch import fetch
from .fetches import fetches_app
from .lessons import lessons_app
from .parse import parse
from .plans import plans_app
from .search import search_app
from .seed import seed
from .stats import stats

__all__ = [
    "agents_app",
    "articles_app",
    "briefing",
    "cleanup_app",
    "doctor",
    "download",
    "feeds_app",
    "fetch",
    "fetches_app",
    "lessons_app",
    "parse",
    "plans_app",
    "search_app",
    "seed",
    "stats",
]
