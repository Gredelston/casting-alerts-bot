import os
import unittest
from unittest.mock import patch

import slack


def _make_client() -> slack.SlackClient:
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test"}):
        with patch("slack.slack_sdk.WebClient"):
            return slack.SlackClient(dry_run=True)


class TestGetToken(unittest.TestCase):
    def test_missing_token_raises_key_error(self):
        env = {k: v for k, v in os.environ.items() if k != "SLACK_BOT_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(KeyError):
                slack.SlackClient._get_token()

    def test_quoted_token_raises_value_error(self):
        with patch.dict(os.environ, {"SLACK_BOT_TOKEN": '"xoxb-test"'}):
            with self.assertRaises(ValueError):
                slack.SlackClient._get_token()


class TestAllUsersPagination(unittest.TestCase):
    def test_follows_pagination_cursor(self):
        client = _make_client()
        client._client.users_list.side_effect = [
            {
                "members": [{"id": "U1"}],
                "response_metadata": {"next_cursor": "abc"},
            },
            {
                "members": [{"id": "U2"}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
        self.assertEqual([u["id"] for u in client._all_users], ["U1", "U2"])
        second_call = client._client.users_list.call_args_list[1]
        self.assertEqual(second_call.kwargs["cursor"], "abc")


class TestGetUserIdByName(unittest.TestCase):
    def test_no_match_raises_with_name_in_message(self):
        client = _make_client()
        client._client.users_list.side_effect = [
            {
                "members": [{"id": "U1", "profile": {"real_name": "Someone Else"}}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
        with self.assertRaisesRegex(ValueError, "Jane Doe"):
            client.get_user_id_by_name("Jane Doe")


class TestPostMessage(unittest.TestCase):
    def test_unresolvable_conversation_raises_with_id_in_message(self):
        client = _make_client()
        client._client.users_list.side_effect = [
            {
                "members": [{"id": "U1", "profile": {"real_name": "Someone Else"}}],
                "response_metadata": {"next_cursor": ""},
            },
        ]
        with self.assertRaisesRegex(ValueError, "Total Gibberish"):
            client.post_message("Total Gibberish", "hello")


if __name__ == "__main__":
    unittest.main()
