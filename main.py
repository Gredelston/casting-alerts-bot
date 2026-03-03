#!/usr/bin/env python3

"""
Main entry point and orchestrator for the Casting Alerts Bot.

This script ties together the configuration, Google Sheets client, Slack 
client, and core logic. It handles command-line argument parsing (such 
as enabling debug logging or dry-run mode), coordinates data fetching, 
evaluates unfilled roles, and dispatches the resulting notifications.
"""

import argparse
import logging
import os

import spreadsheet
import slack
import logic

# Configure logging for Cloud Run (structured text)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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

    sheets_client = spreadsheet.get_sheets_client()
    upcoming_shows = spreadsheet.fetch_upcoming_shows(sheets_client)
    casting_rules = spreadsheet.fetch_casting_rules(sheets_client)

    slack_client = slack.SlackClient(dry_run=args.dry_run)
    slack_client.post_message("Greg Edelston", "Hello, world!")

    alerts = logic.find_unfilled_roles(upcoming_shows, casting_rules)
    for alert in alerts:
        print(alert.message)
    # TODO: Send Slack messages.

    logger.info("Job completed successfully.")


if __name__ == "__main__":
    main()
