import os
import unittest
from pathlib import Path

from app.dth_automation.logo_matcher import ChannelLogoMatcher, DEFAULT_CHANNEL_LOGOS_DIR
from app.dth_automation.validator import resolve_image_path, validate_channel_batch
from app.dth_automation.models import DthItemState


class TestDthLogoMatcher(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher = ChannelLogoMatcher()
        cls.logo_dir = DEFAULT_CHANNEL_LOGOS_DIR

    def test_hd_vs_sd_differentiation(self):
        """Ensures SD channels receive SD logos and HD channels receive HD logos."""
        # 1. &flix SD vs HD
        p_sd, fn_sd, _, _ = self.matcher.find_best_logo("&flix", logo_dir=str(self.logo_dir))
        p_hd, fn_hd, _, _ = self.matcher.find_best_logo("&flix HD", logo_dir=str(self.logo_dir))
        self.assertIsNotNone(fn_sd)
        self.assertIsNotNone(fn_hd)
        self.assertFalse("hd" in fn_sd.lower())
        self.assertTrue("hd" in fn_hd.lower())

        # 2. Aaj Tak SD vs HD
        p_sd, fn_sd, _, _ = self.matcher.find_best_logo("Aaj Tak", logo_dir=str(self.logo_dir))
        p_hd, fn_hd, _, _ = self.matcher.find_best_logo("Aaj Tak HD", logo_dir=str(self.logo_dir))
        self.assertIsNotNone(fn_sd)
        self.assertIsNotNone(fn_hd)
        self.assertFalse("hd" in fn_sd.lower())
        self.assertTrue("hd" in fn_hd.lower())

        # 3. Star Sports 1 SD vs HD
        p_sd, fn_sd, _, _ = self.matcher.find_best_logo("Star Sports 1", logo_dir=str(self.logo_dir))
        p_hd, fn_hd, _, _ = self.matcher.find_best_logo("Star Sports 1 HD", logo_dir=str(self.logo_dir))
        self.assertIsNotNone(fn_sd)
        self.assertIsNotNone(fn_hd)
        self.assertFalse("hd" in fn_sd.lower())
        self.assertTrue("hd" in fn_hd.lower())

    def test_regional_language_specificity(self):
        """Ensures regional logos (Tamil, Telugu, Hindi) are only given to language-specific channels."""
        # Star Sports 1 (national) must not get Tamil logo
        _, fn_nat, _, _ = self.matcher.find_best_logo("Star Sports 1", logo_dir=str(self.logo_dir))
        self.assertFalse("tamil" in fn_nat.lower())
        self.assertFalse("hindi" in fn_nat.lower())

        # Star Sports 1 Tamil HD must get Tamil logo
        _, fn_tamil, _, _ = self.matcher.find_best_logo("Star Sports 1 Tamil HD", logo_dir=str(self.logo_dir))
        self.assertTrue("tamil" in fn_tamil.lower())
        self.assertTrue("hd" in fn_tamil.lower())

    def test_numeral_preservation(self):
        """Ensures distinct numbers like Ten 1, Ten 2, Ten 3, Sports18 2, Sports18 3 are preserved."""
        _, fn1, _, _ = self.matcher.find_best_logo("Sony Sports Ten 1", logo_dir=str(self.logo_dir))
        _, fn2, _, _ = self.matcher.find_best_logo("Sony Sports Ten 2", logo_dir=str(self.logo_dir))
        _, fn3, _, _ = self.matcher.find_best_logo("Sony Sports Ten 3", logo_dir=str(self.logo_dir))
        _, fn4, _, _ = self.matcher.find_best_logo("Sony Sports Ten 4", logo_dir=str(self.logo_dir))

        self.assertTrue("1" in fn1)
        self.assertTrue("2" in fn2)
        self.assertTrue("3" in fn3)
        self.assertTrue("4" in fn4)

        # Sports18
        _, fn_s2, _, _ = self.matcher.find_best_logo("Sports18 2", logo_dir=str(self.logo_dir))
        _, fn_s3, _, _ = self.matcher.find_best_logo("Sports18 3", logo_dir=str(self.logo_dir))
        self.assertTrue("2" in fn_s2)
        self.assertTrue("3" in fn_s3)

    def test_clean_file_preference(self):
        """Clean base filenames are preferred over indexed variants (_1, _(k))."""
        _, fn_10, _, _ = self.matcher.find_best_logo("10TV", logo_dir=str(self.logo_dir))
        self.assertEqual(fn_10.lower(), "10tv.png")

        _, fn_zb, _, _ = self.matcher.find_best_logo("Zee Bangla", logo_dir=str(self.logo_dir))
        self.assertTrue("zee" in fn_zb.lower() and "bangla" in fn_zb.lower())

    def test_validator_integration_with_logo_selection(self):
        """validate_channel_batch automatically selects logos for batch records."""
        records = [
            {
                "row_number": 2,
                "channel_number": "101",
                "name": "DD National",
                "osd": "DD National",
                "image": "",
                "raw_categories": "News"
            },
            {
                "row_number": 3,
                "channel_number": "102",
                "name": "Star Sports 1 HD",
                "osd": "Star Sports 1 HD",
                "image": "",
                "raw_categories": "Sports"
            }
        ]
        items, results = validate_channel_batch(records)
        self.assertEqual(len(items), 2)
        self.assertEqual(results[0].status, DthItemState.READY)
        self.assertEqual(results[1].status, DthItemState.READY)
        self.assertIsNotNone(items[0].resolved_image_path)
        self.assertIsNotNone(items[1].resolved_image_path)
        self.assertTrue(Path(items[0].resolved_image_path).exists())
        self.assertTrue(Path(items[1].resolved_image_path).exists())
        self.assertTrue("hd" in items[1].image.lower())


if __name__ == "__main__":
    unittest.main()
