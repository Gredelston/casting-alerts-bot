import datetime
import unittest
from unittest.mock import MagicMock

import models
import logic


class TestAlerts(unittest.TestCase):
    def setUp(self):
        self.show1 = models.Show(
            date=datetime.date(2026, 5, 1),
            cancelled=False,
            venue=models.Venue.LOUISVILLE_UNDERGROUND,
            host="",
            stage_manager="",
            greeter="",
            teams=[],
        )
        self.show2 = models.Show(
            date=datetime.date(2026, 5, 2),
            cancelled=False,
            venue=models.Venue.THE_END,
            host="",
            stage_manager="",
            greeter="",
            teams=[],
        )

    def test_format_alerts_empty(self):
        self.assertEqual(models.format_alerts([]), "")

    def test_format_alerts_single(self):
        alert = models.CastingAlert(
            show=self.show1,
            role=models.Role.HOST,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 15),
        )
        result = models.format_alerts([alert])
        self.assertIn("missing a *Host*", result)
        self.assertIn("May 01, 2026", result)
        self.assertIn("Louisville Underground", result)
        self.assertNotIn("•", result)  # Should not use bullet points
        self.assertIn("Thanks! 💖", result)

    def test_format_alerts_multiple(self):
        alert1 = models.CastingAlert(
            show=self.show1,
            role=models.Role.HOST,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 15),
        )
        alert2 = models.CastingAlert(
            show=self.show2,
            role=models.Role.TEAMS,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 16),
        )
        result = models.format_alerts([alert1, alert2])
        self.assertIn("missing the following roles", result)
        self.assertIn("• a *Host*", result)
        self.assertIn("• *Teams*", result)
        self.assertIn("May 01, 2026", result)
        self.assertIn("Louisville Underground", result)
        self.assertIn("May 02, 2026", result)
        self.assertIn("The End", result)
        self.assertIn("Thanks! 💖", result)

    def test_format_alerts_single_teams(self):
        show_with_teams = models.Show(
            date=datetime.date(2026, 5, 1),
            cancelled=False,
            venue=models.Venue.LOUISVILLE_UNDERGROUND,
            host="",
            stage_manager="",
            greeter="",
            teams=["Team Apple", "Team Banana"],
        )
        alert = models.CastingAlert(
            show=show_with_teams,
            role=models.Role.TEAMS,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 15),
        )
        result = models.format_alerts([alert])
        self.assertIn("missing *Teams*", result)
        self.assertIn("Currently cast: Team Apple, Team Banana", result)

    def test_format_alerts_multiple_teams(self):
        show_with_teams = models.Show(
            date=datetime.date(2026, 5, 2),
            cancelled=False,
            venue=models.Venue.THE_END,
            host="",
            stage_manager="",
            greeter="",
            teams=["Team Cherry"],
        )
        alert1 = models.CastingAlert(
            show=self.show1,
            role=models.Role.HOST,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 15),
        )
        alert2 = models.CastingAlert(
            show=show_with_teams,
            role=models.Role.TEAMS,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 16),
        )
        result = models.format_alerts([alert1, alert2])
        self.assertIn(
            "• *Teams* for the show on *May 02, 2026* at *The End* (deadline was *April 16, 2026*) (Currently cast: Team Cherry)",
            result,
        )

    def test_dispatch_alerts(self):
        slack_client = MagicMock()

        alert1 = models.CastingAlert(
            show=self.show1,
            role=models.Role.HOST,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 15),
        )
        alert2 = models.CastingAlert(
            show=self.show2,
            role=models.Role.TEAMS,
            responsible_party="U123",
            deadline=datetime.datetime(2026, 4, 16),
        )
        alert3 = models.CastingAlert(
            show=self.show1,
            role=models.Role.STAGE_MANAGER,
            responsible_party="U456",
            deadline=datetime.datetime(2026, 4, 15),
        )

        logic.dispatch_alerts([alert1, alert2, alert3], slack_client)

        self.assertEqual(slack_client.post_message.call_count, 2)

        # Verify U123 got a combined message
        slack_client.post_message.assert_any_call(
            conversation_id="U123", message=models.format_alerts([alert1, alert2])
        )

        # Verify U456 got a single message
        slack_client.post_message.assert_any_call(
            conversation_id="U456", message=models.format_alerts([alert3])
        )


if __name__ == "__main__":
    unittest.main()
