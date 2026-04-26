"""Articles sub-app - manage articles in the database (list, info)."""

import typer

articles_app = typer.Typer(help="Manage articles in the database.")

# Import sub-modules to register commands on articles_app
from ._browse import (  # noqa: E402
    article_categories,
    article_countries,
    article_related,
    patch_missing_cmd,
)
from ._crud import (  # noqa: E402
    article_content,
    article_info,
    delete_article_cmd,
    fail_article_cmd,
    list_articles,
    reset_article_cmd,
    update_article_cmd,
)
from ._factcheck import article_claims, check_article  # noqa: E402
from ._flags import breaking_article, feature_article  # noqa: E402

__all__ = [
    "articles_app",
    "article_categories",
    "article_countries",
    "article_related",
    "patch_missing_cmd",
    "article_content",
    "article_info",
    "delete_article_cmd",
    "fail_article_cmd",
    "list_articles",
    "reset_article_cmd",
    "update_article_cmd",
    "article_claims",
    "check_article",
    "breaking_article",
    "feature_article",
]
