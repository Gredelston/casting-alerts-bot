#!/usr/bin/env python3

import argparse
import dataclasses
import datetime
import enum
import functools
import logging
import re
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
CONFIG_TAB_NAME = "AlertConfigs"


class Venue(enum.StrEnum):
    """Venues where improv shows are performed."""

    LOUISVILLE_UNDERGROUND = "Louisville Underground"
    FULL_CYCLE = "Full Cycle"
    THE_END = "The End"


@dataclasses.dataclass
class Show:
    """Represents a scheduled improv show and its casting details.

    Attributes:
        date: The scheduled date of the show.
        cancelled: Whether the show has been officially cancelled.
        venue: The venue where the show will take place.
        host: The assigned host for the show.
        stage_manager: The assigned stage manager.
        greeter: The assigned greeter/door person.
        teams: A list of improv teams scheduled to perform.
    """

    date: datetime.date
    cancelled: bool
    venue: Venue
    host: str
    stage_manager: str
    greeter: str
    teams: list[str]

    def is_past(self) -> bool:
        """Check whether a show occurred in the past.

        Returns:
            True if the show's date is strictly before today, False otherwise.
        """
        return self.date < datetime.date.today()


class ShowParsingError(ValueError):
    """Raised when show data cannot be parsed from the casting spreadsheet."""


class Role(enum.StrEnum):
    """Different roles need to be cast for each show."""

    TEAMS = "Teams"
    HOST = "Host"
    STAGE_MANAGER = "Stage Manager"
    GREETER = "Greeter"


@dataclasses.dataclass
class CastingRule:
    """An expectation of who should cast which role, and by when.

    Attributes:
        role: The specific casting role this rule applies to.
        venues: A list of venues where this rule is applicable.
        responsible_party: The name of the person or group responsible for
            ensuring the role is cast.
        deadline: The time duration before the show date by which the role
            must be cast.
    """

    role: Role
    venues: list[Venue]
    responsible_party: str
    deadline: str


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


@dataclasses.dataclass
class CastingAlert:
    """Instance of a role that should have been cast by a deadline, but has not.

    Attributes:
        show: The specific show that is missing a casted role.
        role: The role that remains unfilled.
        responsible_party: The person or group responsible for casting the role.
        deadline: The date by which the role was supposed to be cast.
    """

    show: Show
    role: Role
    responsible_party: str
    deadline: datetime.datetime


def get_sheets_client() -> discovery.Resource:
    """Authenticate and build the Google Sheets service client.

    Uses Google Application Default Credentials to authenticate.

    Returns:
        A Google Sheets API service resource object.
    """
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


def read_sheet_rows(
    sheets_service: discovery.Resource,
    spreadsheet_id: str,
    range_name: str,
) -> list[list[str]]:
    """Retrieve all spreadsheet values from a specific range or tab.

    Args:
        sheets_service: The authenticated Google Sheets API resource.
        spreadsheet_id: The ID of the Google Spreadsheet to read from.
        range_name: The A1 notation of the range or tab name to fetch.

    Returns:
        A list of lists, where each inner list represents a row of string
        values from the spreadsheet.
    """
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
    """Parse raw spreadsheet rows into Show objects.

    Args:
        casting_data: A list of rows (lists of strings) retrieved from the
            casting spreadsheet. The first row must be the header.

    Returns:
        A list of Show objects parsed from the raw data.

    Raises:
        ShowParsingError: If there is an issue parsing a future show's data.
    """
    header_row = casting_data[0]
    date_col_idx = header_row.index("Date")
    cancelled_col_idx = header_row.index("Cancelled?")
    venue_col_idx = header_row.index("Venue")
    host_col_idx = header_row.index("Host")
    stage_manager_col_idx = header_row.index("Stage Manager")
    greeter_col_idx = header_row.index("Greeter")
    teams_col_idx = header_row.index("Team Order")
    shows: list[Show] = []
    for row in casting_data[1:]:
        if not row[date_col_idx]:
            continue
        while len(row) < len(header_row):
            row.append("")
        date = datetime.date.fromisoformat(row[date_col_idx])
        try:
            shows.append(
                Show(
                    date=datetime.date.fromisoformat(row[date_col_idx]),
                    cancelled=row[cancelled_col_idx] == "TRUE",
                    venue=Venue(row[venue_col_idx]),
                    host=row[host_col_idx],
                    stage_manager=row[stage_manager_col_idx],
                    greeter=row[greeter_col_idx],
                    teams=row[teams_col_idx].split("\n"),
                )
            )
        except Exception as e:
            if date < datetime.date.today():
                logger.warning("Error parsing show in the past: %s", e)
            else:
                raise ShowParsingError(date) from e
    return shows


def fetch_upcoming_shows(
    sheets_service: discovery.Resource,
) -> list[Show]:
    """Fetche and parse upcoming shows from the Performance Casting spreadsheet.

    Args:
        sheets_service: The authenticated Google Sheets API resource.

    Returns:
        A list of Show objects representing shows occurring today or in the
        future.

    Raises:
        ShowParsingError: If no data is found, no shows can be parsed, or if
            no upcoming shows exist in the parsed data.
    """
    casting_data = read_sheet_rows(
        sheets_service,
        SPREADSHEET_ID,
        CASTING_TAB_NAME,
    )
    if not casting_data:
        logger.warning(
            "No data found in '%s' (or tab does not exist).",
            CASTING_TAB_NAME,
        )
        return []
    logging.info(
        "Fetched %d rows from '%s'.",
        len(casting_data),
        CASTING_TAB_NAME,
    )

    shows = parse_shows(casting_data)
    if not shows:
        raise ShowParsingError(
            f"Failed to parse any shows from raw data: {casting_data}."
        )
    logger.info("Parsed %d shows.", len(shows))

    upcoming_shows = [show for show in shows if not show.is_past()]
    if not upcoming_shows:
        raise ShowParsingError(f"No upcoming shows found. All shows: {shows}")
    logger.info("Found %d upcoming shows.", len(upcoming_shows))
    return upcoming_shows


def parse_duration_string(input_string: str) -> datetime.timedelta:
    """Parse a string like '1 month' or '2 weeks' into a timedelta.

    Args:
        input_string: The duration string to parse (e.g., '3 days', '1 week').

    Returns:
        A datetime.timedelta object representing the parsed duration. Months
        are approximated as 30 days.

    Raises:
        ValueError: If the string format cannot be parsed or the unit is
            unrecognized.
    """
    m = re.fullmatch(r"(\d+)\s*([A-Za-z]+)", input_string.strip())
    if not m:
        raise ValueError(f"Could not parse deadline string: {input_string}")
    amount = int(m.group(1))
    unit = m.group(2)
    match unit.lower():
        case "day" | "days":
            return datetime.timedelta(days=amount)
        case "week" | "weeks":
            return datetime.timedelta(weeks=amount)
        case "month" | "months":
            # Months have an inconsistent length, so timedelta doesn't support them.
            # Let's just approximate at 30 days.
            return datetime.timedelta(days=30 * amount)
        case _:
            raise ValueError(
                f"Unrecognized unit '{unit}' in deadline string '{input_string}'."
            )


def fetch_casting_rules(
    sheets_service: discovery.Resource,
) -> list[CastingRule]:
    """Fetch and parse casting rules from the AlertConfigs spreadsheet.

    Args:
        sheets_service: The authenticated Google Sheets API resource.

    Returns:
        A list of CastingRule objects dictating roles, venues, and casting
        deadlines.

    Raises:
        ValueError: If no data is found in the configs tab or if alerting
            configs are not properly defined.
    """
    rows = read_sheet_rows(
        sheets_service,
        SPREADSHEET_ID,
        CONFIG_TAB_NAME,
    )
    if rows:
        logging.info(
            "Successfully fetched %d rows from '%s'.",
            len(rows),
            CONFIG_TAB_NAME,
        )
    else:
        raise ValueError(f"No data found in spreadsheet tab '{CONFIG_TAB_NAME}'")
    header_row = rows[0]
    role_col_idx = header_row.index("Role")
    venues_col_idx = header_row.index("Venue(s)")
    responsible_party_col_idx = header_row.index("Who's responsible?")
    deadline_col_idx = header_row.index("Deadline")
    casting_rules: list[CastingRule] = []
    venue_map = {
        "All Shows": [Venue.LOUISVILLE_UNDERGROUND, Venue.THE_END],
        "Improvarama Only": [Venue.LOUISVILLE_UNDERGROUND],
        "Laughayette Only": [Venue.THE_END],
    }
    for row in rows[1:]:
        casting_rules.append(
            CastingRule(
                role=Role(row[role_col_idx]),
                venues=venue_map[row[venues_col_idx]],
                responsible_party=row[responsible_party_col_idx],
                deadline=parse_duration_string(row[deadline_col_idx]),
            )
        )
    logger.info("Parsed %d casting rules.", len(casting_rules))
    if not casting_rules:
        raise ValueError("Alerting configs not defined")
    return casting_rules


def find_unfilled_roles(
    upcoming_shows: list[Show], casting_rules: list[CastingRule]
) -> list[CastingAlert]:
    """Identify roles that should have been cast but remain unfilled.

    Evaluates upcoming shows against the specified casting rules to determine
    if any deadlines have been missed for required roles.

    Args:
        upcoming_shows: A list of future Show objects to evaluate.
        casting_rules: A list of CastingRule objects detailing casting
            expectations.

    Returns:
        A list of CastingAlert objects for each missed casting deadline.
    """
    alerts: list[CastingAlert] = []
    for show in upcoming_shows:
        for rule in casting_rules:
            if show.venue not in rule.venues:
                continue
            deadline = show.date - rule.deadline
            if deadline > datetime.date.today():
                continue
            is_met: bool
            match rule.role:
                case Role.TEAMS:
                    is_met = len(show.teams) >= 3
                case Role.HOST:
                    is_met = bool(show.host.strip())
                case Role.STAGE_MANAGER:
                    is_met = bool(show.stage_manager.strip())
                case Role.GREETER:
                    is_met = bool(show.greeter.strip())
            if not is_met:
                alerts.append(
                    CastingAlert(
                        show=show,
                        role=rule.role,
                        responsible_party=rule.responsible_party,
                        deadline=deadline,
                    )
                )
    return alerts


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        An argparse.Namespace object containing the parsed arguments.
    """
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


def main():
    """Execute the main routine for the Casting Alerts Bot.

    Authenticates with Google Sheets, retrieves show and rule data, identifies
    unfilled roles based on missed deadlines, and handles notification alerts.
    """
    args = parse_args()

    if args.dry_run:
        logger.info("🔧 MODE: Dry Run (No alerts will be sent)")
    if args.debug:
        logger.setLevel(logging.DEBUG)

    sheets_service = get_sheets_client()
    upcoming_shows = fetch_upcoming_shows(sheets_service)
    casting_rules = fetch_casting_rules(sheets_service)

    slack_client = SlackClient(dry_run=args.dry_run)
    slack_client.post_message("Greg Edelston", "Hello, world!")

    alerts = find_unfilled_roles(upcoming_shows, casting_rules)
    for alert in alerts:
        print(alert)
    # TODO: Send Slack messages.

    logger.info("Job completed successfully.")


if __name__ == "__main__":
    main()
