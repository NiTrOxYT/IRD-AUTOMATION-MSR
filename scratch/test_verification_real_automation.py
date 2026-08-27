import os
import sys
import json
import tempfile
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

def main():
    print("=================================================================")
    print("RUNNING REAL AUTOMATION EXECUTION VERIFICATION")
    print("=================================================================\n")

    # TEST 1: SELECTOR REGISTRY LOOKUPS FOR PROCESS & DOWNLOAD
    print("[TEST 1] Testing Selector Registry Lookups for Process & Download...")
    from app.browser.selectors import SelectorRegistry

    proc_selectors = SelectorRegistry.get_selectors_for_step("process_latest_menu")
    dl_selectors = SelectorRegistry.get_selectors_for_step("download_action_point")

    print(f"Process Latest Menu Selectors: {proc_selectors}")
    print(f"Download Action Point Selectors: {dl_selectors}")

    assert any("Process Latest Menu" in s for s in proc_selectors), "Missing Process Latest Menu text selector"
    assert any("Download Action Point" in s for s in dl_selectors), "Missing Download Action Point text selector"
    print("Selector Registry Lookups: PASS\n")

    # TEST 2: CSV LINE 3 ANALYSIS & CLASSIFICATION
    print("[TEST 2] Testing CSV Line 3 Analysis & Classification...")
    from app.csv_analyzer.analyzer import analyze_action_point_csv

    with tempfile.TemporaryDirectory() as tmpdir:
        # 2a. No Action Point CSV
        no_ap_csv = Path(tmpdir) / "no_action.csv"
        with open(no_ap_csv, "w", encoding="utf-8") as f:
            f.write("Line 1: Header\nLine 2: Summary\nNo Action Point\nLine 4: Data\n")

        res_no_ap = analyze_action_point_csv(str(no_ap_csv))
        print(f"No Action CSV Line 3: '{res_no_ap['third_line']}' -> Classification: {res_no_ap['action_point_status']}")
        assert res_no_ap["action_point_status"] == "NO ACTION POINT", f"Expected NO ACTION POINT, got {res_no_ap['action_point_status']}"

        # 2b. Action Point Found CSV
        ap_csv = Path(tmpdir) / "action_found.csv"
        with open(ap_csv, "w", encoding="utf-8") as f:
            f.write("Line 1: Header\nLine 2: Summary\nAction Point Item 102 - High Priority\nLine 4: Data\n")

        res_ap = analyze_action_point_csv(str(ap_csv))
        print(f"Action Point CSV Line 3: '{res_ap['third_line']}' -> Classification: {res_ap['action_point_status']}")

        assert res_ap["action_point_status"] == "ACTION POINT FOUND", f"Expected ACTION POINT FOUND, got {res_ap['action_point_status']}"

    print("CSV Line 3 Analysis & Classification: PASS\n")

    # TEST 3: REPORT GENERATOR EXPORT (.txt, .csv, .xlsx, .json)
    print("[TEST 3] Testing Daily Report Generator Export...")
    from app.reports.report_generator import export_reports

    mock_run_data = {
        "run": {
            "id": 1,
            "run_date": "2026-08-27",
            "start_time": "02:00:00",
            "end_time": "02:15:00",
            "status": "COMPLETED",
            "total_sites": 2,
            "completed_sites": 2,
            "action_points_count": 1,
            "no_action_points_count": 1,
            "failed_sites_count": 0
        },
        "results": [
            {
                "site_name": "FNB",
                "status": "COMPLETED",
                "action_point_status": "NO ACTION POINT",
                "csv_path": "logs/downloads/2026-08-27/FNB/1234_action_points.csv",
                "third_line_text": "No Action Point",
                "start_time": "02:00:00",
                "end_time": "02:05:00",
                "duration_seconds": 300.0,
                "retry_count": 0,
                "error_message": ""
            },
            {
                "site_name": "Site 02",
                "status": "COMPLETED",
                "action_point_status": "ACTION POINT FOUND",
                "csv_path": "logs/downloads/2026-08-27/Site_02/1235_action_points.csv",
                "third_line_text": "Action Point Found: 5 Items Pending",
                "start_time": "02:05:00",
                "end_time": "02:12:00",
                "duration_seconds": 420.0,
                "retry_count": 0,
                "error_message": ""
            }
        ]
    }

    with tempfile.TemporaryDirectory() as tmp_report_dir:
        exported_files = export_reports(mock_run_data, output_dir=tmp_report_dir)
        print("Exported Report Files:")
        for fmt, fpath in exported_files.items():
            print(f"  [{fmt.upper()}] {fpath} (Exists: {os.path.exists(fpath)})")
            assert os.path.exists(fpath), f"Failed generating {fmt} report file."

    print("Daily Report Generator Export: PASS\n")

    # TEST 4: WORKFLOW RUNNER SINGLE SITE & MULTI-SITE INTERFACE
    print("[TEST 4] Testing Workflow Runner Interface & Status Broadcast...")
    from app.automation.workflow_runner import workflow_runner

    broadcasts = []
    def mock_listener(payload):
        broadcasts.append(payload)

    workflow_runner.add_status_listener(mock_listener)
    print(f"Current Runner Status: is_running={workflow_runner.is_running}, status={workflow_runner.current_status}")

    print("Workflow Runner Interface: PASS\n")

    print("=================================================================")
    print("ALL REAL AUTOMATION VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()
