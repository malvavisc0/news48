"""Sentinel report writing tool."""

import json
from datetime import datetime, timezone

import config

from ._helpers import _safe_json


def write_sentinel_report(
    status: str,
    metrics: str,
    alerts: str,
    recommendations: str,
) -> str:
    """Write a structured sentinel health report
    to data/monitor/latest-report.json.

    ## When to Use
    Call this tool at the end of every sentinel cycle to persist your
    findings.  The report is consumed by the executor
    (to decide plan priority) and future sentinel cycles.

    ## Parameters
    - `status` (str): Overall status — one of HEALTHY, WARNING, CRITICAL
    - `metrics` (str): JSON string of metric key-value pairs, e.g.
      ``{"feeds_total": 40, "download_backlog": 12, "parse_backlog": 5,
      "download_failures": 2, "parse_failures": 1, "parsed": 30}``
    - `alerts` (str): JSON array of alert strings, e.g.
      ``["Download backlog exceeds warning threshold (52 > 50)"]``
      Use ``[]`` when there are no alerts.
    - `recommendations` (str): JSON array of recommendation strings, e.g.
      ``["Run news48 download --limit 100 to clear backlog"]``
      Use ``[]`` when there are no recommendations.

    ## Returns
    JSON with:
    - `result`: Confirmation message with file path
    - `error`: Empty on success, or error description
    """
    try:
        # Parse the JSON strings from the LLM
        try:
            metrics_dict = json.loads(metrics) if metrics else {}
        except json.JSONDecodeError:
            metrics_dict = {"raw": metrics}

        try:
            alerts_list = json.loads(alerts) if alerts else []
        except json.JSONDecodeError:
            alerts_list = [alerts] if alerts else []

        try:
            recs_list = json.loads(recommendations) if recommendations else []
        except json.JSONDecodeError:
            recs_list = [recommendations] if recommendations else []

        # Validate status
        valid_statuses = {"HEALTHY", "WARNING", "CRITICAL"}
        if status.upper() not in valid_statuses:
            status = "HEALTHY"
        else:
            status = status.upper()

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "metrics": metrics_dict,
            "alerts": alerts_list,
            "recommendations": recs_list,
        }

        config.MONITOR_DIR.mkdir(parents=True, exist_ok=True)
        report_path = config.MONITOR_DIR / "latest-report.json"
        report_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        return _safe_json(
            {
                "result": (f"Report written to {report_path}" f" (status={status})"),
                "error": "",
            }
        )
    except Exception as exc:
        return _safe_json(
            {
                "result": "",
                "error": f"Failed to write report: {exc}",
            }
        )
