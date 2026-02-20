#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from typing import Any

import google.auth
from googleapiclient import discovery

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
    # TODO: Initialize Slack client.
    # TODO: Send Slack messages.

    logger.info("Job completed successfully.")


if __name__ == "__main__":
    main()
