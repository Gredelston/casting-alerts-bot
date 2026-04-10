import datetime
import unittest

import logic
import models


class TestLogic(unittest.TestCase):
    def test_find_unfilled_roles(self):
        today = datetime.date.today()
        show = models.Show(
            date=today + datetime.timedelta(days=10),
            cancelled=False,
            venue=models.Venue.LOUISVILLE_UNDERGROUND,
            host="John Doe",
            stage_manager="",
            greeter="",
            teams=["Team A", "Team B"],
        )

        # Deadline passed, but role filled (Host) -> No alert
        rule1 = models.CastingRule(
            role=models.Role.HOST,
            venues=[models.Venue.LOUISVILLE_UNDERGROUND],
            responsible_party="U123",
            deadline=datetime.timedelta(days=14),
        )

        # Deadline not passed yet (Stage Manager) -> No alert
        rule2 = models.CastingRule(
            role=models.Role.STAGE_MANAGER,
            venues=[models.Venue.LOUISVILLE_UNDERGROUND],
            responsible_party="U456",
            deadline=datetime.timedelta(days=7),
        )

        # Deadline passed, and role unfilled (Teams: needs 3, has 2) -> Alert
        rule3 = models.CastingRule(
            role=models.Role.TEAMS,
            venues=[models.Venue.LOUISVILLE_UNDERGROUND],
            responsible_party="U789",
            deadline=datetime.timedelta(days=14),
        )

        alerts = logic.find_unfilled_roles([show], [rule1, rule2, rule3])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].role, models.Role.TEAMS)
        self.assertEqual(alerts[0].responsible_party, "U789")


if __name__ == "__main__":
    unittest.main()
