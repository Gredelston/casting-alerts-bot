import datetime
import unittest
from unittest.mock import MagicMock

import slack_sdk.errors

import logic
import models
import spreadsheet


def _make_show(**kwargs) -> models.Show:
    defaults = dict(
        date=datetime.date(2026, 7, 8),
        cancelled=False,
        venue=models.Venue.THE_END,
        host="Jane Doe",
        stage_manager="",
        greeter="",
        teams=["Team Apple", "Team Banana"],
        theme="",
        host_cc_contact="Cody",
        guest_cc_contact="Steve",
    )
    defaults.update(kwargs)
    return models.Show(**defaults)


class TestFindDueFollowups(unittest.TestCase):
    def test_show_within_a_week_generates_both_followups(self):
        show = _make_show(date=datetime.date(2026, 7, 8))
        reminders = logic.find_due_followups([show], today=datetime.date(2026, 7, 1))
        self.assertEqual(
            [(r.kind, r.contact) for r in reminders],
            [
                (models.FollowUpKind.HOST, "Cody"),
                (models.FollowUpKind.GUEST_TEAMS, "Steve"),
            ],
        )

    def test_show_more_than_a_week_out_generates_no_followups(self):
        show = _make_show(date=datetime.date(2026, 7, 9))
        reminders = logic.find_due_followups([show], today=datetime.date(2026, 7, 1))
        self.assertEqual(reminders, [])

    def test_cancelled_show_generates_no_followups(self):
        show = _make_show(cancelled=True)
        reminders = logic.find_due_followups([show], today=datetime.date(2026, 7, 7))
        self.assertEqual(reminders, [])

    def test_missing_contact_skips_that_followup(self):
        show = _make_show(host_cc_contact="  ")
        reminders = logic.find_due_followups([show], today=datetime.date(2026, 7, 7))
        self.assertEqual([r.kind for r in reminders], [models.FollowUpKind.GUEST_TEAMS])


class TestFollowupFormatting(unittest.TestCase):
    def test_host_reminder_without_theme(self):
        reminder = models.FollowUpReminder(
            show=_make_show(theme=""),
            kind=models.FollowUpKind.HOST,
            contact="Cody",
        )
        result = models.format_followup_reminder(reminder, "<@U123>")
        self.assertIn("<@U123>", result)
        self.assertIn("Laughayette", result)
        self.assertIn("Jane Doe", result)
        self.assertIn("Host CC Contact", result)
        self.assertIn("Slack channel", result)
        self.assertNotIn("theme", result.lower())
        self.assertIn(":+1:", result)
        self.assertIn("Greg Edelston", result)

    def test_host_reminder_with_theme(self):
        reminder = models.FollowUpReminder(
            show=_make_show(theme="Pirates"),
            kind=models.FollowUpKind.HOST,
            contact="Cody",
        )
        result = models.format_followup_reminder(reminder, "<@U123>")
        self.assertIn("*Pirates*", result)
        self.assertIn("main ambassador", result)

    def test_guest_teams_reminder_laughayette(self):
        reminder = models.FollowUpReminder(
            show=_make_show(venue=models.Venue.THE_END),
            kind=models.FollowUpKind.GUEST_TEAMS,
            contact="Steve",
        )
        result = models.format_followup_reminder(reminder, "<@U456>")
        self.assertIn("<@U456>", result)
        self.assertIn("Guest Team CC Contact", result)
        self.assertIn("The End in Lafayette", result)
        self.assertIn("Team Apple, Team Banana", result)
        self.assertIn("6:55", result)
        self.assertIn("8:00", result)
        self.assertIn("social media handles", result)
        self.assertIn("promotional materials", result)
        self.assertIn(":+1:", result)
        self.assertIn("Greg Edelston", result)

    def test_guest_teams_reminder_improvarama(self):
        reminder = models.FollowUpReminder(
            show=_make_show(venue=models.Venue.LOUISVILLE_UNDERGROUND),
            kind=models.FollowUpKind.GUEST_TEAMS,
            contact="Steve",
        )
        result = models.format_followup_reminder(reminder, "<@U456>")
        self.assertIn("Improvarama", result)
        self.assertIn("the Louisville Underground", result)


class TestDispatchFollowups(unittest.TestCase):
    def setUp(self):
        self.show = _make_show()
        self.host_reminder = models.FollowUpReminder(
            show=self.show, kind=models.FollowUpKind.HOST, contact="Cody"
        )
        self.guest_reminder = models.FollowUpReminder(
            show=self.show, kind=models.FollowUpKind.GUEST_TEAMS, contact="Steve"
        )
        self.slack_client = MagicMock()
        self.slack_client.get_channel_id_by_name.return_value = "C123"
        self.slack_client.get_user_id_by_name.return_value = "U999"

    def _reminder_message(self, reminder, reactions=None, ts="1000.0"):
        message = {
            "ts": ts,
            "metadata": models.followup_metadata(reminder),
        }
        if reactions:
            message["reactions"] = reactions
        return message

    def test_posts_reminders_with_metadata(self):
        self.slack_client.fetch_channel_messages.return_value = []
        logic.dispatch_followups(
            [self.host_reminder, self.guest_reminder], self.slack_client
        )
        self.assertEqual(self.slack_client.post_message.call_count, 2)
        _, kwargs = self.slack_client.post_message.call_args_list[0]
        self.assertEqual(kwargs["conversation_id"], "C123")
        self.assertEqual(
            kwargs["metadata"], models.followup_metadata(self.host_reminder)
        )

    def test_acknowledged_reminder_is_skipped(self):
        self.slack_client.fetch_channel_messages.return_value = [
            self._reminder_message(
                self.host_reminder,
                reactions=[{"name": "+1", "users": ["U999"], "count": 1}],
            )
        ]
        logic.dispatch_followups(
            [self.host_reminder, self.guest_reminder], self.slack_client
        )
        self.assertEqual(self.slack_client.post_message.call_count, 1)
        _, kwargs = self.slack_client.post_message.call_args
        self.assertEqual(
            kwargs["metadata"], models.followup_metadata(self.guest_reminder)
        )

    def test_skin_tone_thumbsup_counts_as_ack(self):
        self.slack_client.fetch_channel_messages.return_value = [
            self._reminder_message(
                self.host_reminder,
                reactions=[{"name": "+1::skin-tone-3", "users": ["U9"], "count": 1}],
            )
        ]
        logic.dispatch_followups([self.host_reminder], self.slack_client)
        self.slack_client.post_message.assert_not_called()

    def test_other_reaction_does_not_count_as_ack(self):
        self.slack_client.fetch_channel_messages.return_value = [
            self._reminder_message(
                self.host_reminder,
                reactions=[{"name": "eyes", "users": ["U9"], "count": 1}],
            )
        ]
        logic.dispatch_followups([self.host_reminder], self.slack_client)
        self.assertEqual(self.slack_client.post_message.call_count, 1)

    def test_reminder_already_posted_today_is_skipped(self):
        now_ts = str(datetime.datetime.now(logic.LOCAL_TIMEZONE).timestamp())
        self.slack_client.fetch_channel_messages.return_value = [
            self._reminder_message(self.host_reminder, ts=now_ts)
        ]
        logic.dispatch_followups([self.host_reminder], self.slack_client)
        self.slack_client.post_message.assert_not_called()

    def test_reminder_posted_yesterday_is_reposted(self):
        yesterday = datetime.datetime.now(logic.LOCAL_TIMEZONE) - datetime.timedelta(
            days=1
        )
        self.slack_client.fetch_channel_messages.return_value = [
            self._reminder_message(self.host_reminder, ts=str(yesterday.timestamp()))
        ]
        logic.dispatch_followups([self.host_reminder], self.slack_client)
        self.assertEqual(self.slack_client.post_message.call_count, 1)

    def test_missing_scope_is_nonfatal(self):
        response = MagicMock()
        response.__getitem__.side_effect = {"error": "missing_scope"}.__getitem__
        self.slack_client.get_channel_id_by_name.side_effect = (
            slack_sdk.errors.SlackApiError("missing_scope", response)
        )
        logic.dispatch_followups([self.host_reminder], self.slack_client)
        self.slack_client.post_message.assert_not_called()

    def test_unknown_contact_falls_back_to_bold_name(self):
        self.slack_client.fetch_channel_messages.return_value = []
        self.slack_client.get_user_id_by_name.return_value = ""
        reminder = models.FollowUpReminder(
            show=self.show, kind=models.FollowUpKind.HOST, contact="Zelda"
        )
        logic.dispatch_followups([reminder], self.slack_client)
        _, kwargs = self.slack_client.post_message.call_args
        self.assertIn("*Zelda*", kwargs["message"])

    def test_short_contact_name_maps_to_full_slack_name(self):
        self.slack_client.fetch_channel_messages.return_value = []
        logic.dispatch_followups([self.host_reminder], self.slack_client)
        self.slack_client.get_user_id_by_name.assert_called_once_with(
            "Cody Esser", allow_none=True
        )


class TestParseShowsNewColumns(unittest.TestCase):
    HEADER = [
        "Date",
        "Cancelled?",
        "Venue",
        "Host",
        "Stage Manager",
        "Greeter",
        "Team Order",
    ]

    def test_parse_shows_without_new_columns(self):
        rows = [
            self.HEADER,
            ["2099-01-01", "FALSE", "The End", "Jane", "Sam", "Gil", "A\nB"],
        ]
        shows = spreadsheet.parse_shows(rows)
        self.assertEqual(len(shows), 1)
        self.assertEqual(shows[0].theme, "")
        self.assertEqual(shows[0].host_cc_contact, "")
        self.assertEqual(shows[0].guest_cc_contact, "")

    def test_parse_shows_with_new_columns(self):
        header = self.HEADER + ["Theme", "Host CC Contact", "Guest Team CC Contact"]
        rows = [
            header,
            [
                "2099-01-01",
                "FALSE",
                "The End",
                "Jane",
                "Sam",
                "Gil",
                "A\nB",
                "Pirates",
                "Cody",
                "Steve",
            ],
        ]
        shows = spreadsheet.parse_shows(rows)
        self.assertEqual(len(shows), 1)
        self.assertEqual(shows[0].theme, "Pirates")
        self.assertEqual(shows[0].host_cc_contact, "Cody")
        self.assertEqual(shows[0].guest_cc_contact, "Steve")


if __name__ == "__main__":
    unittest.main()
