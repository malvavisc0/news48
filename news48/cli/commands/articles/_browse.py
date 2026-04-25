"""Article browse CLI commands: categories, countries, related, patch-missing."""

import json

import typer

from news48.core.database import get_article_by_id

from .._common import emit_error, emit_json, require_db
from . import articles_app


@articles_app.command(name="categories")
def article_categories(
    hours: int = typer.Option(48, "--hours", help="Time window in hours"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List active news categories with article counts."""
    require_db()

    from news48.core.database.articles import get_all_categories

    categories = get_all_categories(hours=hours, parsed=True)

    data = {"hours": hours, "categories": categories}

    if output_json:
        emit_json(data)
    else:
        print(f"Categories (last {hours}h):")
        for c in categories:
            print(f"  {c['name']} ({c['article_count']} articles)")


@articles_app.command(name="countries")
def article_countries(
    hours: int = typer.Option(48, "--hours", help="Time window in hours"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List countries mentioned in recent articles with article counts."""
    require_db()

    from news48.core.database.articles import get_all_countries

    countries = get_all_countries(hours=hours, parsed=True)

    data = {"hours": hours, "countries": countries}

    if output_json:
        emit_json(data)
    else:
        print(f"Countries (last {hours}h):")
        for c in countries:
            print(f"  {c['name']} ({c['article_count']} articles)")


@articles_app.command(name="related")
def article_related(
    article_id: int = typer.Argument(..., help="Article ID"),
    limit: int = typer.Option(5, "--limit", "-l", help="Max related articles"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show related articles based on shared categories/tags."""
    require_db()

    from news48.core.database.articles import get_related_articles

    article = get_article_by_id(article_id)
    if not article:
        emit_error(f"Article not found: {article_id}", as_json=output_json)

    related = get_related_articles(article_id, limit=limit, parsed=True)

    data = {
        "article_id": article_id,
        "article_title": article["title"],
        "total": len(related),
        "related": [
            {
                "id": r["id"],
                "title": r["title"],
                "url": r["url"],
                "source_name": r.get("source_name") or r.get("feed_source_name"),
                "published_at": r.get("published_at"),
                "categories": r.get("categories"),
                "fact_check_status": r.get("fact_check_status"),
            }
            for r in related
        ],
    }

    if output_json:
        emit_json(data)
    else:
        title = article["title"] or "Untitled"
        print(f"Related to: {title} (ID: {article_id})")
        print(f"  {len(related)} related articles:")
        for r in related:
            source = r.get("source_name") or r.get("feed_source_name") or "Unknown"
            fc = r.get("fact_check_status") or ""
            fc_tag = f" [{fc}]" if fc else ""
            print(f"  - [{source}] {r['title']}{fc_tag}")
            print(f"    {r['url']}")


@articles_app.command(name="patch-missing")
def patch_missing_cmd(
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum articles to patch"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Patch parsed articles that are missing required fields."""
    import asyncio

    require_db()

    from news48.core.database.articles import get_articles_with_missing_fields

    candidates = get_articles_with_missing_fields(limit=limit)
    if not candidates:
        data = {"patched": 0, "failed": 0, "total": 0, "results": []}
        if output_json:
            emit_json(data)
        else:
            print("No articles with missing fields found")
        return

    async def _patch_all() -> dict:
        from news48.core.config import Parser

        sem = asyncio.Semaphore(Parser.concurrency)
        results = []

        async def _patch_one(article: dict) -> dict:
            async with sem:
                return await _patch_article_fields(article)

        results = await asyncio.gather(*(_patch_one(a) for a in candidates))
        patched = sum(1 for r in results if r.get("success"))
        failed = sum(1 for r in results if not r.get("success"))
        return {
            "patched": patched,
            "failed": failed,
            "total": len(candidates),
            "results": list(results),
        }

    data = asyncio.run(_patch_all())

    if output_json:
        emit_json(data)
    else:
        print(
            f"Patched {data['patched']} of {data['total']} "
            f"articles, {data['failed']} failed"
        )


async def _patch_article_fields(article: dict) -> dict:
    """Extract and update only the missing fields for one article."""
    from os import getenv

    from llama_index.llms.openai_like import OpenAILike

    from news48.core.database.articles import patch_article_fields

    missing = article.get("missing", [])
    if not missing:
        return {
            "id": article["id"],
            "success": True,
            "skipped": True,
            "reason": "no missing fields",
        }

    content = article.get("content") or ""
    if not content.strip():
        return {
            "id": article["id"],
            "success": False,
            "error": "No content available",
        }

    fields_desc = ", ".join(missing)
    prompt = (
        "Extract the following fields from the article content below. "
        "Return ONLY a JSON object with these keys: "
        f"{fields_desc}\n\n"
        "Field formats:\n"
        "- summary: 40-420 chars, 1-3 sentences, start with substantive "
        "content (never 'This article...')\n"
        "- categories: comma-separated from: world, politics, business, "
        "technology, science, health, sports, travel, entertainment, others\n"
        "- sentiment: positive, negative, or neutral\n"
        "- tags: comma-separated lowercase, 2-8 tags\n\n"
        "Return ONLY valid JSON, no markdown.\n\n"
        f"Article content:\n{content[:8000]}"
    )

    api_base = getenv("API_BASE", "")
    api_key = getenv("API_KEY", "")
    model = getenv("MODEL", "")

    if not api_base:
        return {"id": article["id"], "success": False, "error": "No API_BASE"}

    try:
        llm = OpenAILike(
            model=model,
            api_base=api_base,
            api_key=api_key,
            is_chat_model=True,
            is_function_calling_model=False,
        )
        response = await llm.acomplete(prompt)
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        extracted = json.loads(raw)

        kwargs = {}
        if "summary" in missing and extracted.get("summary"):
            kwargs["summary"] = extracted["summary"]
        if "categories" in missing and extracted.get("categories"):
            kwargs["categories"] = extracted["categories"]
        if "sentiment" in missing and extracted.get("sentiment"):
            kwargs["sentiment"] = extracted["sentiment"]
        if "tags" in missing and extracted.get("tags"):
            kwargs["tags"] = extracted["tags"]

        if not kwargs:
            return {
                "id": article["id"],
                "success": False,
                "error": "LLM returned empty fields",
            }

        patch_article_fields(article["id"], **kwargs)
        return {
            "id": article["id"],
            "success": True,
            "patched_fields": list(kwargs.keys()),
        }

    except json.JSONDecodeError as e:
        return {
            "id": article["id"],
            "success": False,
            "error": f"LLM returned invalid JSON: {e}",
        }
    except Exception as e:
        return {
            "id": article["id"],
            "success": False,
            "error": str(e),
        }
