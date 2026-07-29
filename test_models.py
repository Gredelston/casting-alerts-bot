import datetime
import unittest

import models


class TestModels(unittest.TestCase):
    def test_show_is_past(self):
        show = models.Show(
            date=datetime.date.today() - datetime.timedelta(days=1),
            cancelled=False,
            venue=models.Venue.LOUISVILLE_UNDERGROUND,
            host="",
            stage_manager="",
            greeter="",
            teams=[],
        )
        self.assertTrue(show.is_past())

        show.date = datetime.date.today()
        self.assertFalse(show.is_past())

        show.date = datetime.date.today() + datetime.timedelta(days=1)
        self.assertFalse(show.is_past())

    def test_is_placeholder_team(self):
        placeholders = [
            "",
            "  ",
            "Guest Team",
            "guest team (priority)",
            "Guest Team (Backup)",
            "Guest Team 2",
            "TBD",
            "TBA",
            "tbd (maybe The Nords?)",
            "?",
            "???",
            "Open",
            "Open Slot",
            "Placeholder",
        ]
        for label in placeholders:
            with self.subTest(label=label):
                self.assertTrue(models.is_placeholder_team(label))

        real_teams = [
            "The Nords",
            "Stranger Danger",
            "Guest Team Alpha Squad",  # A real name that merely starts with the phrase
            "Open Mic Knights",
        ]
        for name in real_teams:
            with self.subTest(name=name):
                self.assertFalse(models.is_placeholder_team(name))

    def test_real_teams_excludes_placeholders(self):
        show = models.Show(
            date=datetime.date.today(),
            cancelled=False,
            venue=models.Venue.THE_END,
            host="",
            stage_manager="",
            greeter="",
            teams=[
                "The Nords",
                "Guest Team (Priority)",
                " Stranger Danger ",
                "TBD",
                "",
            ],
        )
        self.assertEqual(show.real_teams(), ["The Nords", "Stranger Danger"])


if __name__ == "__main__":
    unittest.main()
