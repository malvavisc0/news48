"""Doctor command — quick health check of all external services."""

import asyncio
import json
import os
import time
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from ._common import emit_json


def _check_env_vars() -> dict:
    """Check required and optional environment variables."""
    required = {
        "DATABASE_URL": "MySQL connection string",
        "BYPARR_API_URL": "Byparr headless browser API",
        "API_BASE": "LLM API base URL",
        "API_KEY": "LLM API key",
        "MODEL": "LLM model identifier",
    }
    required_extra = {
        "REDIS_URL": "Redis for Dramatiq message broker",
        "SEARXNG_URL": "SearXNG for fact-checker evidence search",
        "CONTEXT_WINDOW": "LLM context window size",
    }
    optional = {
        "SMTP_HOST": "SMTP for sentinel email alerts",
    }

    results = []
    for var, desc in required.items():
        val = os.getenv(var)
        results.append(
            {
                "name": var,
                "description": desc,
                "configured": bool(val),
                "required": True,
                "value_preview": _mask_value(var, val) if val else None,
            }
        )
    for var, desc in required_extra.items():
        val = os.getenv(var)
        results.append(
            {
                "name": var,
                "description": desc,
                "configured": bool(val),
                "required": True,
                "value_preview": _mask_value(var, val) if val else None,
            }
        )
    for var, desc in optional.items():
        val = os.getenv(var)
        results.append(
            {
                "name": var,
                "description": desc,
                "configured": bool(val),
                "required": False,
                "value_preview": _mask_value(var, val) if val else None,
            }
        )

    all_required_ok = all(r["configured"] for r in results if r["required"])
    return {
        "name": "Environment",
        "status": "ok" if all_required_ok else "error",
        "checks": results,
    }


def _mask_value(var: str, val: str | None) -> str | None:
    """Return a masked preview of sensitive values."""
    if not val:
        return None
    if var in (
        "API_KEY",
        "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "SMTP_PASS",
    ):
        if len(val) > 8:
            return val[:4] + "****" + val[-4:]
        return "****"
    if len(val) > 60:
        return val[:57] + "..."
    return val


def _check_database() -> dict:
    """Check MySQL database connectivity and health."""
    try:
        from news48.core.database import check_database_health

        health = check_database_health()
        if health.get("is_connected"):
            return {
                "name": "Database (MySQL)",
                "status": "ok",
                "details": {
                    "size_mb": health.get("db_size_mb", 0),
                    "integrity_ok": health.get("integrity_ok", False),
                    "tables": health.get("table_counts", {}),
                },
            }
        return {
            "name": "Database (MySQL)",
            "status": "error",
            "error": health.get("error", "Connection failed"),
        }
    except Exception as exc:
        return {
            "name": "Database (MySQL)",
            "status": "error",
            "error": str(exc),
        }


def _check_redis() -> dict:
    """Check Redis connectivity."""
    try:
        from news48.core.config import Redis as RedisConfig

        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        import redis as redis_lib

        client = redis_lib.from_url(url, socket_connect_timeout=5)
        info = client.info("server")
        client.close()
        return {
            "name": "Redis",
            "status": "ok",
            "details": {
                "version": info.get("redis_version", "unknown"),
                "url": url,
            },
        }
    except Exception as exc:
        return {
            "name": "Redis",
            "status": "error",
            "error": str(exc),
            "suggestion": "Ensure Redis is running. In Docker: check redis service. Locally: redis-cli ping",
        }


async def _check_byparr_async() -> dict:
    """Check Byparr service connectivity."""
    url = os.getenv("BYPARR_API_URL", "")
    if not url:
        return {
            "name": "Byparr",
            "status": "skipped",
            "error": "BYPARR_API_URL not set",
        }
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url.rstrip("/") + "/health")
            if resp.status_code == 200:
                return {
                    "name": "Byparr",
                    "status": "ok",
                    "details": {"url": url},
                }
            return {
                "name": "Byparr",
                "status": "error",
                "error": f"HTTP {resp.status_code}",
                "details": {"url": url},
            }
    except Exception as exc:
        return {
            "name": "Byparr",
            "status": "error",
            "error": str(exc),
            "details": {"url": url},
            "suggestion": "Ensure Byparr is running. In Docker: check byparr service.",
        }


async def _check_searxng_async() -> dict:
    """Check SearXNG service connectivity."""
    url = os.getenv("SEARXNG_URL", "")
    if not url:
        return {
            "name": "SearXNG",
            "status": "skipped",
            "error": "SEARXNG_URL not set",
        }
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url.rstrip("/") + "/healthz")
            if resp.status_code == 200:
                return {
                    "name": "SearXNG",
                    "status": "ok",
                    "details": {"url": url},
                }
            # Some SearXNG versions don't have /healthz, try /
            resp2 = await client.get(url.rstrip("/") + "/")
            if resp2.status_code == 200:
                return {
                    "name": "SearXNG",
                    "status": "ok",
                    "details": {"url": url},
                }
            return {
                "name": "SearXNG",
                "status": "error",
                "error": f"HTTP {resp.status_code}",
                "details": {"url": url},
            }
    except Exception as exc:
        return {
            "name": "SearXNG",
            "status": "error",
            "error": str(exc),
            "details": {"url": url},
            "suggestion": "Ensure SearXNG is running. In Docker: check searxng service.",
        }


async def _check_llm_async() -> dict:
    """Check LLM API (llama.cpp) connectivity."""
    api_base = os.getenv("API_BASE", "")
    model = os.getenv("MODEL", "")
    if not api_base:
        return {
            "name": "LLM API (llama.cpp)",
            "status": "skipped",
            "error": "API_BASE not set",
        }
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_base.rstrip("/") + "/models")
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                model_ids = [m.get("id", "unknown") for m in models]
                return {
                    "name": "LLM API (llama.cpp)",
                    "status": "ok",
                    "details": {
                        "url": api_base,
                        "configured_model": model,
                        "available_models": model_ids,
                    },
                }
            return {
                "name": "LLM API (llama.cpp)",
                "status": "error",
                "error": f"HTTP {resp.status_code}",
                "details": {"url": api_base},
            }
    except Exception as exc:
        return {
            "name": "LLM API (llama.cpp)",
            "status": "error",
            "error": str(exc),
            "details": {"url": api_base},
            "suggestion": "Ensure llama.cpp is running. In Docker: check llamacpp service. For external LLM: verify API_BASE is reachable.",
        }


def _run_async_checks() -> list[dict]:
    """Run all async health checks sequentially."""
    results = []

    loop = asyncio.new_event_loop()
    try:
        results.append(loop.run_until_complete(_check_byparr_async()))
        results.append(loop.run_until_complete(_check_searxng_async()))
        results.append(loop.run_until_complete(_check_llm_async()))
    finally:
        loop.close()

    return results


def _render_text(all_results: list[dict]) -> None:
    """Render doctor results as a rich table."""
    console = Console()
    console.print()
    console.print("[bold]news48 doctor[/bold] — service health check")
    console.print()

    status_icons = {
        "ok": "[bold green]✓[/bold green]",
        "error": "[bold red]✗[/bold red]",
        "skipped": "[dim]⊘[/dim]",
    }

    for section in all_results:
        icon = status_icons.get(section["status"], "?")
        name = section["name"]
        console.print(f"  {icon}  [bold]{name}[/bold]")

        if section["status"] == "ok" and "details" in section:
            details = section["details"]
            for k, v in details.items():
                if isinstance(v, dict):
                    console.print(f"       [dim]{k}:[/dim]")
                    for tk, tv in v.items():
                        console.print(f"         {tk}: {tv}")
                elif isinstance(v, list):
                    console.print(
                        f"       [dim]{k}:[/dim] {', '.join(str(i) for i in v)}"
                    )
                else:
                    console.print(f"       [dim]{k}:[/dim] {v}")

        if section["status"] == "error" and "checks" not in section:
            err = section.get("error", "Unknown error")
            console.print(f"       [red]{err}[/red]")
            suggestion = section.get("suggestion")
            if suggestion:
                console.print(f"       [yellow]→ {suggestion}[/yellow]")

        if section["status"] == "skipped":
            err = section.get("error", "Skipped")
            console.print(f"       [dim]{err}[/dim]")

        # Show env var details for Environment section
        if section["name"] == "Environment" and "checks" in section:
            for chk in section["checks"]:
                var_icon = (
                    "✓" if chk["configured"] else ("✗" if chk["required"] else "⊘")
                )
                style = (
                    "green"
                    if chk["configured"]
                    else ("red" if chk["required"] else "dim")
                )
                req_tag = (
                    " [dim](required)[/dim]"
                    if chk["required"]
                    else " [dim](optional)[/dim]"
                )
                val = chk.get("value_preview")
                val_str = f" = {val}" if val else ""
                console.print(
                    f"       [{style}]{var_icon}[/{style}] {chk['name']}{req_tag}{val_str}"
                )

        console.print()

    # Summary
    errors = sum(1 for r in all_results if r["status"] == "error")
    oks = sum(1 for r in all_results if r["status"] == "ok")
    skipped = sum(1 for r in all_results if r["status"] == "skipped")

    if errors == 0:
        console.print(
            f"[bold green]All checks passed[/bold green] ({oks} ok, {skipped} skipped)"
        )
    else:
        console.print(
            f"[bold red]{errors} issue(s) found[/bold red] "
            f"({oks} ok, {errors} error, {skipped} skipped)"
        )
    console.print()


def doctor(
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON for scripting",
    ),
) -> None:
    """Quick health check of all external services.

    Checks: environment variables, MySQL database, Redis, Byparr,
    SearXNG, and LLM API (llama.cpp).
    """
    all_results: list[dict[str, Any]] = []

    # 1. Environment variables
    all_results.append(_check_env_vars())

    # 2. Database
    all_results.append(_check_database())

    # 3. Redis
    all_results.append(_check_redis())

    # 4. Async checks (Byparr, SearXNG, LLM)
    all_results.extend(_run_async_checks())

    if output_json:
        emit_json({"checks": all_results})
    else:
        _render_text(all_results)
