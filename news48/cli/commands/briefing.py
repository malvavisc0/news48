"""Briefing command - structured news briefing."""

from news48.core.database.articles import (
    get_articles_paginated,
    get_topic_clusters,
    get_web_stats,
)

from ._common import emit_json, require_db


def briefing(
    hours: int = 48,
    limit: int = 10,
    output_json: bool = False,
) -> None:
    """Get a structured news briefing: top stories, trending topics, and stats.

    Examples:
        news48 briefing
        news48 briefing --hours 24 --limit 5 --json
    """
    require_db()

    stories, _ = get_articles_paginated(
        hours=hours, limit=limit, include_source=True, parsed=True
    )
    top_stories = [
        {
            "id": s["id"],
            "title": s["title"],
            "summary": s.get("summary"),
            "url": s["url"],
            "source_name": s.get("source_name") or s.get("feed_source_name"),
            "published_at": s.get("published_at"),
            "categories": s.get("categories"),
            "sentiment": s.get("sentiment"),
            "fact_check_status": s.get("fact_check_status"),
        }
        for s in stories
    ]

    clusters = get_topic_clusters(hours=hours, parsed=True)
    trending = [
        {
            "name": c["name"],
            "slug": c["slug"],
            "article_count": c["article_count"],
            "top_titles": [a["title"] for a in c.get("articles", [])[:3]],
        }
        for c in clusters[:8]
    ]

    stats_data = get_web_stats(hours=hours, parsed=True)
    stats = {
        "total_stories": stats_data.get("live_stories", 0),
        "sources": stats_data.get("sources", 0),
        "verified_count": stats_data.get("verified", 0),
        "hours_covered": hours,
    }

    data = {
        "top_stories": top_stories,
        "trending_topics": trending,
        "stats": stats,
    }

    if output_json:
        emit_json(data)
    else:
        print(f"News Briefing (last {hours}h)")
        print(
            f"  {stats['total_stories']} stories from "
            f"{stats['sources']} sources, "
            f"{stats['verified_count']} verified"
        )
        print()

        if top_stories:
            print("Top Stories:")
            for i, s in enumerate(top_stories, 1):
                fc = s.get("fact_check_status") or ""
                fc_tag = f" [{fc}]" if fc else ""
                print(f"  {i}. {s['title']}{fc_tag}")
                source = s.get("source_name") or "Unknown"
                print(f"     [{source}] {s['url']}")
            print()

        if trending:
            print("Trending Topics:")
            for t in trending:
                print(f"  - {t['name']} ({t['article_count']} articles)")
                for title in t.get("top_titles", []):
                    print(f"    * {title}")
            print()
