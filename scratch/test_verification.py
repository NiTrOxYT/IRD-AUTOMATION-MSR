import os
import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database.db import init_db, get_all_sites, add_site, delete_site
from app.database.seed import seed_default_sites_if_empty
from app.security.credentials import encrypt_password, decrypt_password
from app.csv_analyzer.analyzer import analyze_action_point_csv
from app.reports.report_generator import export_reports

class TestIRDSyncAutomation(unittest.TestCase):

    def setUp(self):
        init_db()
        seed_default_sites_if_empty()

    def test_database_and_sites(self):
        sites = get_all_sites()
        self.assertGreaterEqual(len(sites), 21, "Database should contain at least 21 initial sites.")
        fnb = sites[0]
        self.assertEqual(fnb.name, "FNB")
        self.assertEqual(fnb.launcher_button, "FNB")

    def test_dpapi_credentials(self):
        plain = "MySecretP@ssw0rd123!"
        enc = encrypt_password(plain)
        self.assertNotEqual(plain, enc)
        dec = decrypt_password(enc)
        self.assertEqual(plain, dec)

    def test_csv_analyzer_no_action(self):
        test_csv = Path(__file__).parent / "test_no_action.csv"
        with open(test_csv, "w", encoding="utf-8") as f:
            f.write("Header 1, Header 2\nLine 2 info\nNo Action Point\nLine 4 info\n")

        res = analyze_action_point_csv(str(test_csv))
        self.assertEqual(res["action_point_status"], "NO ACTION POINT")
        self.assertEqual(res["third_line"], "No Action Point")

        if test_csv.exists():
            test_csv.unlink()

    def test_csv_analyzer_action_found(self):
        test_csv = Path(__file__).parent / "test_action_found.csv"
        with open(test_csv, "w", encoding="utf-8") as f:
            f.write("Header 1, Header 2\nLine 2 info\nItem 102 Needs Action\nLine 4 info\n")

        res = analyze_action_point_csv(str(test_csv))
        self.assertEqual(res["action_point_status"], "ACTION POINT FOUND")
        self.assertEqual(res["third_line"], "Item 102 Needs Action")

        if test_csv.exists():
            test_csv.unlink()

    def test_report_export(self):
        run_data = {
            "run": {
                "run_date": "2026-08-25",
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
                    "third_line_text": "No Action Point",
                    "duration_seconds": 12.4,
                    "retry_count": 0
                },
                {
                    "site_name": "Site 02",
                    "status": "COMPLETED",
                    "action_point_status": "ACTION POINT FOUND",
                    "third_line_text": "Action Required: Price Updated",
                    "duration_seconds": 15.1,
                    "retry_count": 1
                }
            ]
        }
        res_paths = export_reports(run_data)
        self.assertTrue(os.path.exists(res_paths["txt"]))
        self.assertTrue(os.path.exists(res_paths["csv"]))
        self.assertTrue(os.path.exists(res_paths["xlsx"]))
        self.assertTrue(os.path.exists(res_paths["json"]))

if __name__ == "__main__":
    unittest.main()
