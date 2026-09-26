import unittest

from localization import get_text


class LocalizationTests(unittest.TestCase):
    def test_returns_english_translation_by_default(self):
        self.assertEqual(get_text("app_title"), "Biashara Bookkeeper")

    def test_returns_kiswahili_translation(self):
        self.assertEqual(get_text("app_title", "sw"), "Mweka Hazina wa Biashara")

    def test_falls_back_to_english_for_unknown_language_or_key(self):
        self.assertEqual(get_text("app_title", "fr"), "Biashara Bookkeeper")
        self.assertEqual(get_text("not_a_translation"), "not_a_translation")

    def test_formats_translation_values(self):
        self.assertEqual(get_text("processing_error", error="bad input"), "Processing Error: bad input")


if __name__ == "__main__":
    unittest.main()