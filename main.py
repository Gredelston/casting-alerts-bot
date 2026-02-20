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
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Hardcoded spreadsheet ID.
SPREADSHEET_ID = "1sOcW4siUOLxd5Mt6WeOQ9vk05LZXDA6rHXulHcdQP4A"


def connect_to_sheets_service() -> discovery.Resource:
    """Authenticate with Google using Application Default Credentials.

    Locally: Uses GOOGLE_APPLICATION_CREDENTIALS env var.
    Cloud Run: Uses the attached Service Account automatically.
    """
    logger.info("Connecting to Google Sheets service...")
    scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']

    # google.auth.default() automatically looks for credentials in this order:
    # 1. GOOGLE_APPLICATION_CREDENTIALS env var.
    # 2. User credentials set up via `gcloud auth application-default login`.
    # 3. The Service Account attached to the Cloud Run instance.
    # Thus, for local use, we can use `gcloud auth application-default login`,
    # and for Cloud Run it should automatically use the service account.
    creds, project_id = google.auth.default(scopes=scopes)
    logging.debug(f"Connected to project {project_id}.")
    return discovery.build(
        'sheets',
        'v4',
        credentials=creds,
        cache_discovery=False,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Improv Boulder Production Alerts")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without sending external alerts",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.dry_run:
        logger.info("🔧 MODE: Dry Run (No alerts will be sent)")
    if args.debug:
        logger.setLevel(logging.DEBUG)

    sheets_service = connect_to_sheets_service()
    # TODO: Fetch casting data.
    # TODO: Fetch deadline config.
    # TODO: Identify late castings.
    # TODO: Initialize Slack client.
    # TODO: Send Slack messages.

    logger.info("Job completed successfully.")

if __name__ == "__main__":
    main()
