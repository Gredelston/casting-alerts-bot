#!/usr/bin/env python3

"""
Google Sheets API integration and data parsing module.

This module handles authentication with Google Workspace via Application 
Default Credentials. It provides functions to fetch raw spreadsheet data 
and parse those rows into the domain models (Shows and Casting Rules) 
required by the bot's core logic.
"""

import datetime
import logging
import re

import google.auth
from googleapiclient import discovery

import models

SPREADSHEET_ID = "1sOcW4siUOLxd5Mt6WeOQ9vk05LZXDA6rHXulHcdQP4A"
CASTING_TAB_NAME = "Casting Info"
CONFIG_TAB_NAME = "Alert Configs"

logger = logging.getLogger(__name__)


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


def parse_shows(casting_data: list[list[str]]) -> list[models.Show]:
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
    shows: list[models.Show] = []
    for row in casting_data[1:]:
        if not row[date_col_idx]:
            continue
        while len(row) < len(header_row):
            row.append("")
        date = datetime.date.fromisoformat(row[date_col_idx])
        try:
            shows.append(
                models.Show(
                    date=datetime.date.fromisoformat(row[date_col_idx]),
                    cancelled=row[cancelled_col_idx] == "TRUE",
                    venue=models.Venue(row[venue_col_idx]),
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
                raise models.ShowParsingError(date) from e
    return shows


def fetch_upcoming_shows(
    sheets_service: discovery.Resource,
) -> list[models.Show]:
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
        raise models.ShowParsingError(
            f"Failed to parse any shows from raw data: {casting_data}."
        )
    logger.info("Parsed %d shows.", len(shows))

    upcoming_shows = [show for show in shows if not show.is_past()]
    if not upcoming_shows:
        raise models.ShowParsingError(f"No upcoming shows found. All shows: {shows}")
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
) -> list[models.CastingRule]:
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
    casting_rules: list[models.CastingRule] = []
    venue_map = {
        "All Shows": [models.Venue.LOUISVILLE_UNDERGROUND, models.Venue.THE_END],
        "Improvarama Only": [models.Venue.LOUISVILLE_UNDERGROUND],
        "Laughayette Only": [models.Venue.THE_END],
    }
    for row in rows[1:]:
        casting_rules.append(
            models.CastingRule(
                role=models.Role(row[role_col_idx]),
                venues=venue_map[row[venues_col_idx]],
                responsible_party=row[responsible_party_col_idx],
                deadline=parse_duration_string(row[deadline_col_idx]),
            )
        )
    logger.info("Parsed %d casting rules.", len(casting_rules))
    if not casting_rules:
        raise ValueError("Alerting configs not defined")
    return casting_rules
