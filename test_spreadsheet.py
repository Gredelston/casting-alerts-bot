import datetime
import unittest

import spreadsheet


class TestSpreadsheet(unittest.TestCase):
    def test_parse_duration_string(self):
        self.assertEqual(
            spreadsheet.parse_duration_string("1 day"), datetime.timedelta(days=1)
        )
        self.assertEqual(
            spreadsheet.parse_duration_string("3 days"), datetime.timedelta(days=3)
        )
        self.assertEqual(
            spreadsheet.parse_duration_string("1 week"), datetime.timedelta(weeks=1)
        )
        self.assertEqual(
            spreadsheet.parse_duration_string("2 weeks"), datetime.timedelta(weeks=2)
        )
        self.assertEqual(
            spreadsheet.parse_duration_string("1 month"), datetime.timedelta(days=30)
        )
        self.assertEqual(
            spreadsheet.parse_duration_string("6 months"), datetime.timedelta(days=180)
        )

    def test_parse_duration_string_invalid(self):
        with self.assertRaises(ValueError):
            spreadsheet.parse_duration_string("1 year")
        with self.assertRaises(ValueError):
            spreadsheet.parse_duration_string("days")


if __name__ == "__main__":
    unittest.main()
