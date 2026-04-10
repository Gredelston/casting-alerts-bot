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


if __name__ == "__main__":
    unittest.main()
