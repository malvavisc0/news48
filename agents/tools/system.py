"""System information tool."""

import os
import platform
import sys
from datetime import datetime, timezone

from agents.tools._helpers import _safe_json


def get_system_info() -> str:
    """Get system and runtime environment information.

    ## When to Use
    Use this tool when you need to know about the execution environment,
    such as Python version, platform details, or current time. Useful for
    debugging or adapting behavior to the runtime environment.

    ## Why to Use
    - Check Python version compatibility
    - Determine operating system for platform-specific logic
    - Get current time for timestamp generation
    - Find working directory or home directory paths
    - Check news48 service configuration status
    - Diagnose environment-related issues

    ## Returns
    JSON with:
    - `result.working_directory`: Current working directory
    - `result.python_executable`: Path to Python interpreter
    - `result.python_version`: Version string (e.g., "3.11.4")
    - `result.platform`: OS name (Linux, Darwin, Windows)
    - `result.platform_release`: OS release version
    - `result.default_shell`: Default shell path
    - `result.home_directory`: Home directory path
    - `result.current_datetime`: UTC timestamp
    - `result.local_datetime`: Local timestamp
    - `result.architecture`: Machine architecture (x86_64, etc.)
    - `result.news48.database_path`: Configured database path
    - `result.news48.database_exists`: Whether the database file exists
    - `result.news48.database_size_mb`: Database file size in MB
    - `result.news48.env_configured`: Whether .env file exists
    - `result.news48.byparr_configured`: Whether BYPARR_API_URL is set
    - `result.news48.searxng_configured`: Whether SEARXNG_URL is set
    - `result.news48.api_base_configured`: Whether API_BASE is set
    """
    try:
        news48_info = _get_news48_info()

        result = {
            "working_directory": os.getcwd(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "default_shell": os.getenv("SHELL", "/bin/bash"),
            "home_directory": os.getenv("HOME", ""),
            "current_datetime": datetime.now(timezone.utc).isoformat(),
            "local_datetime": datetime.now().isoformat(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "news48": news48_info,
        }
        return _safe_json({"result": result, "error": ""})
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})


def _get_news48_info() -> dict:
    """Gather news48-specific configuration and status info.

    Returns:
        A dict with news48 service status information.
    """
    from sqlalchemy import text

    from database.connection import SessionLocal

    info = {
        "database_url": None,
        "database_connected": False,
        "database_size_mb": 0.0,
        "env_configured": False,
        "byparr_configured": False,
        "searxng_configured": False,
        "api_base_configured": False,
    }

    # Check .env file
    env_path = os.path.join(os.getcwd(), ".env")
    info["env_configured"] = os.path.isfile(env_path)

    # Check environment variables
    info["byparr_configured"] = bool(os.getenv("BYPARR_API_URL"))
    info["searxng_configured"] = bool(os.getenv("SEARXNG_URL"))
    info["api_base_configured"] = bool(os.getenv("API_BASE"))

    # Check database connectivity and size
    try:
        from config import Database as DbConfig

        info["database_url"] = DbConfig.url
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            info["database_connected"] = True

            # MySQL-specific health: table status for size
            rows = session.execute(text("SHOW TABLE STATUS")).fetchall()
            total_size = sum((r.Data_length or 0) + (r.Index_length or 0) for r in rows)
            info["database_size_mb"] = round(total_size / (1024 * 1024), 2)
    except Exception:
        pass

    return info
