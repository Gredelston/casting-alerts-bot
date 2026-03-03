#!/usr/bin/env python3

"""
Slack API integration module.

This module provides the `SlackClient` class, which wraps the official 
`slack_sdk.WebClient` to handle user lookups, workspace queries, and 
message dispatching. It includes a dry-run feature to prevent accidental 
notifications during testing and local development.
"""

import functools
import logging
import os
import re
from typing import Any

import slack_sdk
import slack_sdk.errors

logger = logging.getLogger(__name__)


class SlackClient:
    """A wrapper for slack_sdk.WebClient actions.

    Provides simplified methods for looking up Slack users and sending messages,
    while supporting a dry-run mode to prevent actual messages from being sent
    during testing.
    """

    def __init__(self, dry_run: bool) -> None:
        """Initialize the SlackClient.

        Args:
            dry_run: If True, blocks actual external notifications from being
                sent to Slack.
        """
        # Initialize the WebClient.
        # Technically the token param is optional, but passing it explicitly
        # makes errors more obvious.
        self._client = slack_sdk.WebClient(token=self._get_token())
        self._dry_run = dry_run

    @staticmethod
    def _get_token() -> str:
        """Fetch the SLACK_BOT_TOKEN from environment variables.

        Returns:
            The Slack bot token string.

        Raises:
            KeyError: If the SLACK_BOT_TOKEN environment variable is not found.
            ValueError: If the SLACK_BOT_TOKEN environment variable is
                mistakenly wrapped in quotes.
        """
        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            raise KeyError(f"Missing env var SLACK_BOT_TOKEN. Env: {os.env}")
        if token.startswith('"') or token.startswith("'"):
            raise ValueError(
                f"SLACK_BOT_TOKEN is incorrectly wrapped in quotes. Literal value: {token}"
            )
        return token

    @functools.cached_property
    def _all_users(self) -> list[dict[str, Any]]:
        """Get a full list of all Slack users in the workspace.

        Returns:
            A list of dictionaries, each representing a single user, fetched
            from the Slack API.
        """
        users = []
        cursor = None
        logger.debug("Fetching list of all Slack users...")
        while True:
            response = self._client.users_list(cursor=cursor)
            if response["members"]:
                users.extend(response["members"])
            if response["response_metadata"]["next_cursor"]:
                cursor = next_cursor
            else:
                break
        logger.debug("Found %d Slack users.", len(users))
        return users

    def get_user_id_by_name(self, name: str, allow_none: bool = False) -> str:
        """Look up a user ID by their full name.

        Args:
            name: The full real name of the Slack user to look up.
            allow_none: If True, returns an empty string when no user is found
                instead of raising an exception.

        Returns:
            The Slack user ID matching the given name, or an empty string if
            allow_none is True and no user is found.

        Raises:
            ValueError: If no user is found (and allow_none is False), or if
                multiple users are found with the given name.
        """
        logger.debug("Searching for Slack user with name '%s'...", name)
        user_id = ""
        for user in self._all_users:
            if user["profile"]["real_name"] != name:
                continue
            if user_id:
                raise ValueError(
                    f"Two Slack users found with name '{name}': {user_id}, {user['id']}"
                )
            user_id = user["id"]
        if user_id:
            logger.debug("Found Slack user ID %s for user '%s'.", user_id, name)
            return user_id
        if not allow_none:
            raise ValueError("No Slack user found with name '{name}'")
        logger.debug(
            "No Slack user found with name '%s', but allowing due to allow_none."
        )
        return ""

    def get_user_id_by_email(self, email: str) -> str:
        """Look up a user ID by their registered email address.

        Args:
            email: The registered email address associated with the Slack user.

        Returns:
            The Slack user ID matching the given email address.
        """
        logger.debug("Looking up Slack user by email: %s", email)
        response = self._client.users_lookupByEmail(email=email)
        user_id = response["user"]["id"]
        logger.debug("Found Slack user ID: %s", user_id)
        return user_id

    def post_message(self, conversation_id: str, message: str) -> None:
        """Send a message to the specified user.

        Args:
            conversation_id: The channel name, channel ID, user ID, user email,
                or user's full name to post a message to.
            message: The exact text message to post.

        Raises:
            ValueError: If the conversation_id cannot be interpreted or resolved
                to a valid Slack user or channel.
        """
        if re.fullmatch(r"[UW][A-Z0-9]{8,}", conversation_id):
            logger.debug("Conversation ID '%s' looks like a user ID.", conversation_id)
        elif re.fullmatch(r"[CG][A-Z0-9]{8,}", conversation_id):
            logger.debug(
                "Conversation ID '%s' looks like a channel ID.", conversation_id
            )
        elif re.fullmatch(r"#[a-z0-9-]+", conversation_id):
            logger.debug(
                "Conversation ID '%s' looks like a channel name.", conversation_id
            )
        elif re.fullmatch(r"\S+@\S+.\S+", conversation_id):
            logger.debug(
                "Conversation ID '%s' looks like an email address. Converting to user ID.",
                conversation_id,
            )
            conversation_id = self.get_user_id_by_email(conversation_id)
        else:
            logger.debug(
                "Conversation ID '%s' does not match a regular format. Attempting to find user with that name...",
                conversation_id,
            )
            conversation_id = self.get_user_id_by_name(conversation_id, allow_none=True)
            if not conversation_id:
                raise ValueError(
                    "Could not interpret Slack conversation ID: conversation_id"
                )
        if self._dry_run:
            logger.info("Skipping Slack message for dry run.")
            logger.info(f"Target conversation: {conversation_id}")
            logger.info(f"Message: '''{message}'''")
            return
        logger.debug(
            f"Attempting to send Slack message to conversation {conversation_id}..."
        )
        self._client.chat_postMessage(channel=conversation_id, text=message)
        logger.info(f"Sent message to {conversation_id}: '''{message}'''")
