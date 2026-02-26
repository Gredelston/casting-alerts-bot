#!/usr/bin/env python3

import argparse
import dataclasses
import datetime
import enum
import logging
import os
import sys
from typing import Any

import google.auth
from googleapiclient import discovery
import slack_sdk
import slack_sdk.errors

# Configure logging for Cloud Run (structured text)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Hardcoded spreadsheet info.
SPREADSHEET_ID = "1sOcW4siUOLxd5Mt6WeOQ9vk05LZXDA6rHXulHcdQP4A"
CASTING_TAB_NAME = "Casting Info"
CONFIG_TAB_NAME = "AlertsConfig"


class ShowLocation(enum.StrEnum):
    LOUISVILLE_UNDERGROUND = "Louisville Underground"
    FULL_CYCLE = "Full Cycle"
    THE_END = "The End"


@dataclasses.dataclass
class Show:
    date: datetime.date
    cancelled: bool
    location: ShowLocation
    host: str
    stage_manager: str
    greeter: str
    teams: list[str]

    def is_past(self) -> bool:
        """Check whether a show occurred in the past."""
        return self.date < datetime.date.today()


class ShowParsingError(ValueError):
    """Raised when we fail to parse show data from the casting spreadsheet."""


class SlackClient:
    """A wrapper for slack_sdk.WebClient actions."""

    def __init__(self, dry_run: bool) -> None:
        # Initialize the WebClient.
        # Technically the token param is optional, but passing it explicitly
        # makes errors more obvious.
        self._client = slack_sdk.WebClient(token=self._get_token())
        self._dry_run = dry_run

    @staticmethod
    def _get_token() -> str:
        """Fetch the SLACK_BOT_TOKEN from env vars.

        Raises:
            KeyError: If the env var is not found.
            ValueError: If the env var is mistakenly wrapped in quotes.
        """
        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            raise KeyError(f"Missing env var SLACK_BOT_TOKEN. Env: {os.env}")
        if token.startswith('"') or token.startswith("'"):
            raise ValueError(
                f"SLACK_BOT_TOKEN is incorrectly wrapped in quotes. Literal value: {token}"
            )
        return token

    def get_user_id_by_email(self, email: str) -> str:
        """Look up a user ID by their registered email address."""
        logger.debug("Looking up Slack user by email: %s", email)
        response = self._client.users_lookupByEmail(email=email)
        user_id = response["user"]["id"]
        logger.debug("Found Slack user ID: %s", user_id)
        return user_id

    def send_message(self, user_id: str, message: str) -> None:
        """Send a message to the specified user.

        Raises:
            ValueError: If user_id doesn't look like a user ID.
        """
        if "@" in user_id:
            raise ValueError(f"User ID {user_id} looks like an email address.")
        elif "#" in user_id:
            raise ValueError(f"User ID {user_id} looks like a channel name.")
        if self._dry_run:
            logger.info("Skipping Slack message for dry run.")
            logger.info(f"Target user: {user_id}")
            logger.info(f"Message: '''{message}'''")
            return
        logger.debug(f"Attempting to send Slack message to user {user_id}...")
        self._client.chat_postMessage(channel=user_id, text=message)
        logger.info(f"Sent message to user {user_id}: '''{message}'''")


def connect_to_sheets_service() -> discovery.Resource:
    """Authenticate with Google using Application Default Credentials."""
    logger.info("Connecting to Google Sheets service...")
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    # google.auth.default() automatically looks for credentials in this order:
    # 1. GOOGLE_APPLICATION_CREDENTIALS env var.
    # 2. User credentials set up via `gcloud auth application-default login`.
    # 3. The Service Account attached to the Cloud Run instance.
    # Thus, for local use, we can use `gcloud auth application-default login`,
    # and for Cloud Run it should automatically use the service account.
    creds, project_id = google.auth.default(scopes=scopes)
    logging.debug(f"Connected to project {project_id}.")
    return discovery.build(
        "sheets",
        "v4",
        credentials=creds,
        cache_discovery=False,
    )


def fetch_sheet_values(
    sheets_service: discovery.Resource,
    spreadsheet_id: str,
    range_name: str,
) -> list[list[str]]:
    """Retrieve all spreadsheet values from a specific range or tab."""
    logger.debug(
        "Attempting to fetch range %s from spreadsheet %s",
        range_name,
        spreadsheet_id,
    )
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        )
        .execute()
    )
    return result.get("values", [])


def parse_shows(casting_data: list[list[str]]) -> list[Show]:
    header_row = casting_data[0]
    date_column = header_row.index("Date")
    cancelled_column = header_row.index("Cancelled?")
    location_column = header_row.index("Location")
    host_column = header_row.index("Host")
    stage_manager_column = header_row.index("Stage Manager")
    greeter_column = header_row.index("Greeter")
    teams_column = header_row.index("Team Order")
    shows: list[Show] = []
    for row in casting_data[1:]:
        if not row[date_column]:
            continue
        while len(row) < len(header_row):
            row.append("")
        date = datetime.date.fromisoformat(row[date_column])
        try:
            shows.append(
                Show(
                    date=datetime.date.fromisoformat(row[date_column]),
                    cancelled=row[cancelled_column] == "TRUE",
                    location=ShowLocation(row[location_column]),
                    host=row[host_column],
                    stage_manager=row[stage_manager_column],
                    greeter=row[greeter_column],
                    teams=row[teams_column].split("\n"),
                )
            )
        except Exception as e:
            if date < datetime.date.today():
                logger.warning("Error parsing show in the past: %s", e)
            else:
                raise ShowParsingError(date) from e
    return shows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Improv Boulder Production Alerts")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending external alerts",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug-level logging."
    )
    return parser.parse_args()


def send_hello_world_via_slack(slack_client: SlackClient, user_email: str) -> None:
    """Send a test DM to the specified email address."""
    user_id = slack_client.get_user_id_by_email(user_email)
    slack_client.send_message(user_id, "Hello, world!")


def main():
    args = parse_args()

    if args.dry_run:
        logger.info("🔧 MODE: Dry Run (No alerts will be sent)")
    if args.debug:
        logger.setLevel(logging.DEBUG)

    sheets_service = connect_to_sheets_service()

    casting_data = fetch_sheet_values(
        sheets_service,
        SPREADSHEET_ID,
        CASTING_TAB_NAME,
    )
    if casting_data:
        logging.info(
            "Successfully fetched %d rows from '%s'.",
            len(casting_data),
            CASTING_TAB_NAME,
        )
    else:
        logger.warning(
            "No data found in '%s' (or tab does not exist).",
            CASTING_TAB_NAME,
        )

    shows = parse_shows(casting_data)
    if shows:
        logger.info("Successfully parsed %d shows.", len(shows))
    else:
        raise ShowParsingError("Failed to parse any shows.")

    upcoming_shows = [show for show in shows if not show.is_past()]
    if upcoming_shows:
        logger.info("Upcoming shows: %d", len(upcoming_shows))
        for i, show in enumerate(upcoming_shows):
            logger.info("%d.\t%s", i + 1, show)
    else:
        raise ShowParsingError("No upcoming shows found.")

    config_data = fetch_sheet_values(
        sheets_service,
        SPREADSHEET_ID,
        CONFIG_TAB_NAME,
    )
    if config_data:
        logging.info(
            "Successfully fetched %d rows from '%s'.",
            len(config_data),
            CONFIG_TAB_NAME,
        )
    else:
        logger.warning(
            "No data found in '%s' (or tab does not exist).",
            CONFIG_TAB_NAME,
        )
    # TODO: Identify late castings.
    slack_client = SlackClient(dry_run=args.dry_run)
    send_hello_world_via_slack(slack_client, "gredelston@gmail.com")
    # TODO: Send Slack messages.

    logger.info("Job completed successfully.")


if __name__ == "__main__":
    main()
