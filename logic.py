#!/usr/bin/env python3

"""
Core business logic for the Casting Alerts Bot.

This module contains the purely functional rules of the application.
It compares scheduled shows against defined casting expectations and
deadlines to identify missing roles and generate actionable alerts.
"""

import collections
import datetime
import logging
import zoneinfo

import slack_sdk.errors

import models
import slack

logger = logging.getLogger(__name__)

LOCAL_TIMEZONE = zoneinfo.ZoneInfo("America/Denver")

CASTING_COMMITTEE_CHANNEL = "#casting-committee"

# How far in advance of a show the follow-up reminders begin.
FOLLOWUP_LEAD_TIME = datetime.timedelta(days=7)

# How far back to search #casting-committee for prior reminders and their
# acknowledgments. Comfortably covers the reminder window.
FOLLOWUP_LOOKBACK = datetime.timedelta(days=14)

# Short names used in the spreadsheet's CC Contact columns, mapped to the
# contacts' full names on Slack.
CC_CONTACT_FULL_NAMES = {
    "cody": "Cody Esser",
    "steve": "Steve Merrick",
    "greg": "Greg Edelston",
}


def find_unfilled_roles(
    upcoming_shows: list[models.Show], casting_rules: list[models.CastingRule]
) -> list[models.CastingAlert]:
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
    alerts: list[models.CastingAlert] = []
    for show in upcoming_shows:
        if show.cancelled:
            continue
        for rule in casting_rules:
            if show.venue not in rule.venues:
                continue
            deadline = show.date - rule.deadline
            if deadline > datetime.date.today():
                continue
            is_met: bool
            match rule.role:
                case models.Role.TEAMS:
                    is_met = len(show.teams) >= 3
                case models.Role.HOST:
                    is_met = bool(show.host.strip())
                case models.Role.STAGE_MANAGER:
                    is_met = bool(show.stage_manager.strip())
                case models.Role.GREETER:
                    is_met = bool(show.greeter.strip())
            if not is_met:
                alerts.append(
                    models.CastingAlert(
                        show=show,
                        role=rule.role,
                        responsible_party=rule.responsible_party,
                        deadline=deadline,
                    )
                )
    return alerts


def dispatch_alerts(
    alerts: list[models.CastingAlert],
    slack_client: slack.SlackClient,
) -> None:
    """Send all generated casting alerts to their responsible parties via Slack.

    Args:
        alerts: A list of CastingAlert objects representing missed deadlines.
        slack_client: An initialized SlackClient to handle message dispatching.
    """
    logger.info(f"Dispatching {len(alerts)} casting alerts...")
    alerts_by_party = collections.defaultdict(list)
    for alert in alerts:
        alerts_by_party[alert.responsible_party].append(alert)

    for responsible_party, party_alerts in alerts_by_party.items():
        # post_message automatically handles routing "#channels" vs "Real Names"
        slack_client.post_message(
            conversation_id=responsible_party,
            message=models.format_alerts(party_alerts),
        )
    logger.info("Finished dispatching alerts.")


def find_due_followups(
    upcoming_shows: list[models.Show],
    today: datetime.date,
) -> list[models.FollowUpReminder]:
    """Identify pre-show follow-ups whose reminder window has begun.

    A follow-up is due starting one week before the show. Shows without a
    CC contact listed for a given follow-up are skipped with a warning,
    since there is nobody to remind.

    Args:
        upcoming_shows: A list of future Show objects to evaluate.
        today: The current date.

    Returns:
        A list of FollowUpReminder objects for follow-ups within the window.
    """
    reminders: list[models.FollowUpReminder] = []
    for show in upcoming_shows:
        if show.cancelled:
            continue
        if show.date - today > FOLLOWUP_LEAD_TIME:
            continue
        for kind, contact in (
            (models.FollowUpKind.HOST, show.host_cc_contact),
            (models.FollowUpKind.GUEST_TEAMS, show.guest_cc_contact),
        ):
            if not contact.strip():
                logger.warning(
                    "Show on %s has no %s CC contact listed; skipping follow-up "
                    "reminder. Please fill it in on the casting spreadsheet.",
                    show.date,
                    kind.value,
                )
                continue
            reminders.append(
                models.FollowUpReminder(show=show, kind=kind, contact=contact)
            )
    logger.info("Found %d follow-up reminders in the window.", len(reminders))
    return reminders


def _followup_key(message: dict) -> tuple[str, str] | None:
    """Extract the (show_date, kind) key from a reminder message's metadata.

    Args:
        message: A Slack message dictionary from conversations.history.

    Returns:
        The (show_date, kind) key if the message is one of our follow-up
        reminders, otherwise None.
    """
    metadata = message.get("metadata") or {}
    if metadata.get("event_type") != models.FOLLOWUP_EVENT_TYPE:
        return None
    payload = metadata.get("event_payload") or {}
    show_date = payload.get("show_date")
    kind = payload.get("kind")
    if not show_date or not kind:
        return None
    return (show_date, kind)


def _is_acknowledged(message: dict) -> bool:
    """Check whether a Slack message has a :+1: reaction.

    Args:
        message: A Slack message dictionary from conversations.history.

    Returns:
        True if anyone reacted with :+1: (including skin-tone variants).
    """
    for reaction in message.get("reactions", []):
        if reaction["name"].split("::")[0] in ("+1", "thumbsup"):
            return True
    return False


def _contact_mention(contact: str, slack_client: slack.SlackClient) -> str:
    """Build the Slack mention text for a CC contact.

    Args:
        contact: The contact as listed in the spreadsheet (e.g. "Cody").
        slack_client: An initialized SlackClient for user lookups.

    Returns:
        A "<@USER_ID>" mention if the contact can be resolved to a Slack
        user, otherwise their name in bold.
    """
    full_name = CC_CONTACT_FULL_NAMES.get(contact.strip().lower(), contact.strip())
    user_id = slack_client.get_user_id_by_name(full_name, allow_none=True)
    if user_id:
        return f"<@{user_id}>"
    logger.warning("Could not find Slack user for CC contact '%s'.", full_name)
    return f"*{full_name}*"


def dispatch_followups(
    reminders: list[models.FollowUpReminder],
    slack_client: slack.SlackClient,
) -> None:
    """Post follow-up reminders to #casting-committee, respecting :+1: acks.

    Reads the channel's recent history to find previously-posted reminders
    (identified by message metadata). A reminder is skipped if any prior
    reminder for the same (show, kind) has a :+1: reaction, or if one was
    already posted today.

    Args:
        reminders: The follow-up reminders currently in their window.
        slack_client: An initialized SlackClient for channel operations.
    """
    if not reminders:
        logger.info("No follow-up reminders to dispatch.")
        return

    now = datetime.datetime.now(LOCAL_TIMEZONE)
    try:
        channel_id = slack_client.get_channel_id_by_name(CASTING_COMMITTEE_CHANNEL)
        slack_client.join_channel(channel_id)
        messages = slack_client.fetch_channel_messages(
            channel_id, oldest=(now - FOLLOWUP_LOOKBACK).timestamp()
        )
    except slack_sdk.errors.SlackApiError as e:
        if e.response["error"] == "missing_scope":
            logger.error(
                "Slack token is missing scopes needed for follow-up reminders "
                "(channels:read, channels:history, channels:join). Please add "
                "them to the Slack app and reinstall it. Skipping follow-ups. "
                "Error: %s",
                e,
            )
            return
        raise

    acknowledged: set[tuple[str, str]] = set()
    posted_today: set[tuple[str, str]] = set()
    for message in messages:
        key = _followup_key(message)
        if key is None:
            continue
        if _is_acknowledged(message):
            acknowledged.add(key)
        message_date = datetime.datetime.fromtimestamp(
            float(message["ts"]), tz=LOCAL_TIMEZONE
        ).date()
        if message_date == now.date():
            posted_today.add(key)

    for reminder in reminders:
        key = (reminder.show.date.isoformat(), reminder.kind.value)
        if key in acknowledged:
            logger.info("Follow-up %s already acknowledged with :+1:.", key)
            continue
        if key in posted_today:
            logger.info("Follow-up %s already posted today.", key)
            continue
        mention = _contact_mention(reminder.contact, slack_client)
        slack_client.post_message(
            conversation_id=channel_id,
            message=models.format_followup_reminder(reminder, mention),
            metadata=models.followup_metadata(reminder),
        )
    logger.info("Finished dispatching follow-up reminders.")
