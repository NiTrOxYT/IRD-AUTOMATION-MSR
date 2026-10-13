import os
import unittest
import tempfile
from pathlib import Path
import openpyxl

from app.dth_automation.models import (
    DthItemState,
    DthRunState,
    DthExecutionMode,
    ChannelItem,
    ChannelValidationResult
)
from app.dth_automation.file_parser import parse_dth_file


class TestDthModelsAndParser(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_models_state_enums(self):
        self.assertEqual(DthItemState.READY.value, "READY")
        self.assertEqual(DthItemState.SKIPPED_DUPLICATE.value, "SKIPPED_DUPLICATE")
        self.assertEqual(DthRunState.IN_PROGRESS.value, "IN_PROGRESS")
        self.assertEqual(DthExecutionMode.DRY_RUN.value, "DRY_RUN")

    def test_channel_item_serialization(self):
        item = ChannelItem(
            row_number=2,
            channel_number="007",
            name="Spy TV",
            osd="Spy TV",
            image="spy.png",
            categories=["all", "Movies"],
            raw_categories="all, Movies"
        )
        self.assertEqual(item.channel_number, "007")
        self.assertEqual(item.categories, ["all", "Movies"])

    def test_parse_valid_csv(self):
        csv_file = self.test_dir / "valid.csv"
        csv_file.write_text(
            "channel_number,name,osd,image,categories\n"
            "001,News Now,News Now,news.png,\"all, News\"\n"
            "102,Sports Max,Sports,sports.png,\"Sports\"\n",
            encoding="utf-8"
        )
        records, errors = parse_dth_file(str(csv_file))
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["channel_number"], "001")
        self.assertEqual(records[0]["name"], "News Now")
        self.assertEqual(records[0]["row_number"], 2)
        self.assertEqual(records[1]["channel_number"], "102")
        self.assertEqual(records[1]["row_number"], 3)

    def test_parse_utf8_bom_csv(self):
        csv_file = self.test_dir / "bom.csv"
        content = "channel_number,name,osd,image,categories\n101,DD1,DD1,dd.png,all\n"
        csv_file.write_bytes(content.encode("utf-8-sig"))

        records, errors = parse_dth_file(str(csv_file))
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["channel_number"], "101")

    def test_parse_csv_header_aliases(self):
        csv_file = self.test_dir / "aliases.csv"
        csv_file.write_text(
            "Channel No,Channel Name,OSD Text,Logo,Category\n"
            "55,BBC,BBC,bbc.png,News\n",
            encoding="utf-8"
        )
        records, errors = parse_dth_file(str(csv_file))
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["channel_number"], "55")
        self.assertEqual(records[0]["name"], "BBC")
        self.assertEqual(records[0]["image"], "bbc.png")

    def test_parse_csv_missing_headers(self):
        csv_file = self.test_dir / "missing_header.csv"
        csv_file.write_text(
            "channel_number,name,osd\n"
            "101,Test,Test\n",
            encoding="utf-8"
        )
        records, errors = parse_dth_file(str(csv_file))
        self.assertEqual(len(records), 0)
        self.assertTrue(any("Missing required columns" in e for e in errors))

    def test_parse_valid_xlsx(self):
        xlsx_file = self.test_dir / "valid.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["channel_number", "name", "osd", "image", "categories"])
        ws.append(["050", "Music India", "Music", "music.png", "Music, all"])
        wb.save(str(xlsx_file))

        records, errors = parse_dth_file(str(xlsx_file))
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["channel_number"], "050")
        self.assertEqual(records[0]["name"], "Music India")

    def test_reject_unsupported_extension(self):
        bad_file = self.test_dir / "data.txt"
        bad_file.write_text("dummy", encoding="utf-8")
        records, errors = parse_dth_file(str(bad_file))
        self.assertEqual(len(records), 0)
        self.assertTrue(any("Unsupported file format" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
