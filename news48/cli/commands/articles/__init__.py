"""Articles sub-app - manage articles in the database (list, info)."""

import typer

articles_app = typer.Typer(help="Manage articles in the database.")

# Import sub-modules to register commands on articles_app
from ._browse import (
    article_categories,
    article_countries,
    article_related,
    patch_missing_cmd,
)
from ._crud import (
    article_content,
    article_info,
    delete_article_cmd,
    fail_article_cmd,
    list_articles,
    reset_article_cmd,
    update_article_cmd,
)
from ._factcheck import article_claims, check_article
from ._flags import breaking_article, feature_article

__all__ = ["articles_app"]
