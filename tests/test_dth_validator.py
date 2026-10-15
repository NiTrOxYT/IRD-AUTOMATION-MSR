import os
import unittest
import tempfile
from pathlib import Path

from app.dth_automation.models import DthItemState
from app.dth_automation.validator import (
    normalize_categories,
    resolve_image_path,
    validate_channel_batch
)


class TestDthValidator(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        # Create a valid test image
        self.valid_img = self.test_dir / "dd.png"
        self.valid_img.write_bytes(b"\x89PNG\r\n\x1a\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_categories_mandatory_all(self):
        # When 'all' is missing from input, it must be added as first item
        cats, errors = normalize_categories("News, Sports")
        self.assertEqual(len(errors), 0)
        self.assertEqual(cats, ["all", "News", "Sports"])

    def test_normalize_categories_deduplication(self):
        # When 'all' is already present, no duplicate 'all' should exist
        cats, errors = normalize_categories("ALL, news, News, sports")
        self.assertEqual(len(errors), 0)
        self.assertEqual(cats, ["all", "news", "sports"])

    def test_normalize_categories_with_allowed_portal_list(self):
        portal_cats = ["all", "News", "Sports", "Movies"]
        cats, errors = normalize_categories("News, Movies", portal_cats)
        self.assertEqual(len(errors), 0)
        self.assertEqual(cats, ["all", "News", "Movies"])

        # Test unknown category
        cats_bad, errors_bad = normalize_categories("AlienCategory, News", portal_cats)
        self.assertEqual(len(errors_bad), 1)
        self.assertTrue("Unknown portal category 'AlienCategory'" in errors_bad[0])

    def test_resolve_image_path_success(self):
        path_str, errors = resolve_image_path("dd.png", str(self.test_dir))
        self.assertEqual(len(errors), 0)
        self.assertIsNotNone(path_str)
        self.assertTrue(Path(path_str).exists())

    def test_resolve_image_path_traversal_rejected(self):
        path_str, errors = resolve_image_path("../../escape.png", str(self.test_dir))
        self.assertIsNone(path_str)
        self.assertTrue(any("Path traversal" in e for e in errors))

    def test_resolve_image_path_url_rejected(self):
        path_str, errors = resolve_image_path("http://example.com/logo.png", str(self.test_dir))
        self.assertIsNone(path_str)
        self.assertTrue(any("Remote URL not allowed" in e for e in errors))

    def test_resolve_image_path_invalid_extension(self):
        path_str, errors = resolve_image_path("logo.exe", str(self.test_dir))
        self.assertIsNone(path_str)
        self.assertTrue(any("Unsupported image extension" in e for e in errors))

    def test_resolve_image_path_missing_file(self):
        path_str, errors = resolve_image_path("non_existent.png", str(self.test_dir))
        self.assertIsNone(path_str)
        self.assertTrue(any("Image file not found" in e for e in errors))

    def test_validate_channel_batch_clean(self):
        records = [
            {
                "row_number": 2,
                "channel_number": "101",
                "name": "DD National",
                "osd": "DD National",
                "image": "dd.png",
                "raw_categories": "News"
            }
        ]
        items, results = validate_channel_batch(records, image_dir=str(self.test_dir))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, DthItemState.READY)
        self.assertEqual(results[0].resolved_categories, ["all", "News"])

    def test_validate_channel_batch_duplicates_in_file(self):
        records = [
            {"row_number": 2, "channel_number": "101", "name": "Ch1", "osd": "Ch1", "image": "dd.png", "raw_categories": "News"},
            {"row_number": 3, "channel_number": "101", "name": "Ch2", "osd": "Ch2", "image": "dd.png", "raw_categories": "Sports"},
        ]
        items, results = validate_channel_batch(records, image_dir=str(self.test_dir))
        self.assertEqual(results[0].status, DthItemState.READY)
        self.assertEqual(results[1].status, DthItemState.INVALID)
        self.assertTrue(any("Duplicate channel number '101'" in e for e in results[1].errors))

    def test_validate_channel_batch_auto_selects_image_when_header_omitted(self):
        # Create a test logo in test directory
        test_logo = self.test_dir / "Sony MAX.png"
        test_logo.write_bytes(b"\x89PNG\r\n\x1a\n")

        records = [
            {
                "row_number": 2,
                "channel_number": "301",
                "name": "Sony MAX",
                "osd": "Sony MAX",
                "image": "",  # Empty, as parsed when image header is omitted
                "raw_categories": "Movies"
            }
        ]
        items, results = validate_channel_batch(records, image_dir=str(self.test_dir))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, DthItemState.READY)
        self.assertEqual(items[0].image, "Sony MAX.png")
        self.assertIsNotNone(items[0].resolved_image_path)
        self.assertTrue(str(items[0].resolved_image_path).endswith("Sony MAX.png"))


    def test_normalize_categories_single_category_only_with_multi_input(self):
        # Enforce rule: only 'all' and exactly one other relevant category
        cats, errors = normalize_categories("all, News, Regional, Hindi", allowed_categories=["all", "News", "Regional", "Sports"], single_category_only=True)
        self.assertEqual(len(errors), 0)
        self.assertEqual(cats, ["all", "News"])

    def test_infer_category_from_name_when_empty_categories(self):
        # Infers relevant category from channel name when raw category is only 'all' or empty
        cats_sports, errs = normalize_categories("all", allowed_categories=["all", "Sports", "News"], single_category_only=True, channel_name="Star Sports 1 HD")
        self.assertEqual(cats_sports, ["all", "Sports"])

        cats_movies, errs = normalize_categories("", allowed_categories=["all", "Movies", "News"], single_category_only=True, channel_name="Sony MAX HD")
        self.assertEqual(cats_movies, ["all", "Movies"])

        cats_news, errs = normalize_categories("", allowed_categories=["all", "News", "Entertainment"], single_category_only=True, channel_name="Aaj Tak")
        self.assertEqual(cats_news, ["all", "News"])


if __name__ == "__main__":
    unittest.main()

