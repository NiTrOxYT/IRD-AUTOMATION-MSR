import os
import csv
import json
import logging
from typing import Dict, Any, List
from pathlib import Path

from app.config import REPORTS_DIR
from app.dth_automation.models import DthRunSummary, DthChannelExecutionResult

logger = logging.getLogger("DTH_ReportGenerator")


def export_dth_reports(run_summary: Dict[str, Any], channel_results: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Exports execution run reports to CSV and JSON formats.
    Returns: {"csv_path": str, "json_path": str}
    """
    dth_reports_dir = REPORTS_DIR / "dth"
    dth_reports_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_summary.get("id") or "preview"
    date_str = run_summary.get("run_date") or "today"
    base_filename = f"{date_str}_dth_run_{run_id}"

    csv_path = dth_reports_dir / f"{base_filename}.csv"
    json_path = dth_reports_dir / f"{base_filename}.json"

    # 1. Export JSON Report
    report_data = {
        "summary": run_summary,
        "channels": channel_results
    }
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(report_data, jf, indent=2)

    # 2. Export CSV Report
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as cf:
        writer = csv.writer(cf)
        # Header Metadata
        writer.writerow(["# DTH CHANNEL CONFIGURATION REPORT"])
        writer.writerow(["# Run ID", run_id])
        writer.writerow(["# Mode", run_summary.get("mode")])
        writer.writerow(["# Status", run_summary.get("status")])
        writer.writerow(["# Total Channels", run_summary.get("total_channels", 0)])
        writer.writerow(["# Successful", run_summary.get("successful_channels", 0)])
        writer.writerow(["# Skipped Duplicates", run_summary.get("skipped_duplicates", 0)])
        writer.writerow(["# Failed", run_summary.get("failed_channels", 0)])
        writer.writerow(["# Unknown", run_summary.get("unknown_channels", 0)])
        writer.writerow([])

        # Table Header
        writer.writerow([
            "Row Number",
            "Channel Number",
            "Channel Name",
            "OSD Text",
            "Categories",
            "Status",
            "Verified in Portal",
            "Duration (s)",
            "Reason / Error"
        ])

        for ch in channel_results:
            cats = ch.get("categories", [])
            cats_str = ", ".join(cats) if isinstance(cats, list) else str(cats)
            writer.writerow([
                ch.get("row_number", ""),
                ch.get("channel_number", ""),
                ch.get("name", ""),
                ch.get("osd", ""),
                cats_str,
                ch.get("status", ""),
                "YES" if ch.get("verified_in_portal") else "NO",
                f"{ch.get('duration_seconds', 0.0):.2f}",
                ch.get("error_reason", "")
            ])

    logger.info(f"[DTH] Reports exported successfully: {csv_path} and {json_path}")
    return {
        "csv_path": str(csv_path),
        "json_path": str(json_path)
    }
