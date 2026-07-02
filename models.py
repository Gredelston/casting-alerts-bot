#!/usr/bin/env python3

"""
Core data structures and domain models for the Casting Alerts Bot.

This module defines the classes, enums, and exceptions used to represent
the fundamental concepts of the application, including improv shows, venues,
casting rules, and triggered alerts. It is designed to be free of external
API dependencies.
"""

import dataclasses
import datetime
import enum
import logging

logger = logging.getLogger(__name__)


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
        theme: The show's theme, if any.
        host_cc_contact: The casting committee member responsible for
            following up with the host before the show.
        guest_cc_contact: The casting committee member responsible for
            following up with the guest teams before the show.
    """

    date: datetime.date
    cancelled: bool
    venue: Venue
    host: str
    stage_manager: str
    greeter: str
    teams: list[str]
    theme: str = ""
    host_cc_contact: str = ""
    guest_cc_contact: str = ""

    def is_past(self) -> bool:
        """Check whether a show occurred in the past.

        Returns:
            True if the show's date is strictly before today, False otherwise.
        """
        return self.date < datetime.date.today()


SHOW_BRANDS = {
    Venue.THE_END: "Laughayette",
    Venue.LOUISVILLE_UNDERGROUND: "Improvarama",
}

VENUE_DIRECTIONS = {
    Venue.THE_END: "The End in Lafayette",
    Venue.LOUISVILLE_UNDERGROUND: "the Louisville Underground",
}


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


class ShowParsingError(ValueError):
    """Raised when show data cannot be parsed from the casting spreadsheet."""


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


class FollowUpKind(enum.StrEnum):
    """The kinds of pre-show follow-ups a casting committee member performs."""

    HOST = "host"
    GUEST_TEAMS = "guest_teams"


@dataclasses.dataclass
class FollowUpReminder:
    """A reminder for a casting committee member to follow up before a show.

    Attributes:
        show: The upcoming show that needs a human follow-up.
        kind: Which follow-up is needed (host or guest teams).
        contact: The casting committee member responsible for the follow-up,
            as listed in the spreadsheet (e.g. "Cody").
    """

    show: Show
    kind: FollowUpKind
    contact: str


# Identifies this bot's follow-up reminder messages in Slack message metadata,
# so later runs can find them and check for :+1: acknowledgments.
FOLLOWUP_EVENT_TYPE = "cc_followup_reminder"


def followup_metadata(reminder: FollowUpReminder) -> dict:
    """Build the Slack message metadata that identifies a follow-up reminder.

    Args:
        reminder: The follow-up reminder being posted.

    Returns:
        A metadata dict suitable for chat.postMessage, uniquely identifying
        the (show, kind) pair so future runs can detect acknowledgments.
    """
    return {
        "event_type": FOLLOWUP_EVENT_TYPE,
        "event_payload": {
            "show_date": reminder.show.date.isoformat(),
            "kind": reminder.kind.value,
        },
    }


def _followup_footer() -> str:
    return (
        "\n\nOnce you've reached out, please react to this message with a "
        ":+1: and I'll stop reminding you.\n\n"
        "🤖 _If you have any issues with this automation, please contact "
        "Greg Edelston._"
    )


def _show_brand(show: Show) -> str:
    return SHOW_BRANDS.get(show.venue, show.venue.value)


def _venue_directions(show: Show) -> str:
    return VENUE_DIRECTIONS.get(show.venue, show.venue.value)


def format_host_followup_reminder(reminder: FollowUpReminder, mention: str) -> str:
    """Write the #casting-committee reminder to follow up with a show's host.

    Args:
        reminder: The follow-up reminder to format.
        mention: Slack mention text for the responsible contact (e.g.
            "<@U123ABC>", or a plain name if the user couldn't be resolved).

    Returns:
        The full Slack message text, including a copyable sample message.
    """
    show = reminder.show
    brand = _show_brand(show)
    formatted_date = show.date.strftime("%A, %B %-d")
    host = show.host.strip() or "(host TBD)"

    todo_lines = ["• Confirm they're still available to host the show"]
    sample_theme = ""
    if show.theme.strip():
        todo_lines.append(
            f"• Make sure they know the show's theme is *{show.theme.strip()}*, "
            f"that they're our main ambassador for the theme, and ask them to "
            f"find some ways to incorporate it into their hosting"
        )
        sample_theme = (
            f" Also, this show's theme is *{show.theme.strip()}* — as host, "
            f"you're our main ambassador for the theme, so we'd love for you "
            f"to find some fun ways to work it into your hosting!"
        )
    todo_lines.append(
        "• Remind them that all the info they need is in the show's Slack channel"
    )

    sample = (
        f"> Hey {host}! Just checking in ahead of {brand} on {formatted_date} — "
        f"are you still good to host?{sample_theme} All the info you need is in "
        f"the show's Slack channel. Thanks so much! 🎉"
    )

    return (
        f"👋 Hey {mention}! *{brand}* on *{formatted_date}* is one week out "
        f"(or less), and you're the Host CC Contact. Please reach out to our "
        f"host, *{host}*, to:\n" + "\n".join(todo_lines) + "\n\n"
        f"Here's a sample message you're welcome to copy:\n{sample}"
        + _followup_footer()
    )


def format_guest_teams_followup_reminder(
    reminder: FollowUpReminder, mention: str
) -> str:
    """Write the #casting-committee reminder to follow up with guest teams.

    Args:
        reminder: The follow-up reminder to format.
        mention: Slack mention text for the responsible contact (e.g.
            "<@U123ABC>", or a plain name if the user couldn't be resolved).

    Returns:
        The full Slack message text, including a copyable sample message.
    """
    show = reminder.show
    brand = _show_brand(show)
    where = _venue_directions(show)
    formatted_date = show.date.strftime("%A, %B %-d")
    teams = [t.strip() for t in show.teams if t.strip()]
    teams_text = ", ".join(teams) if teams else "(no teams listed yet)"

    todo_lines = [
        "• Confirm they're ready for the show",
        f"• Confirm the where & when: {where}; call time is generally 6:55 PM "
        f"for the 8:00 showtime, but arriving a bit later is OK if they'd prefer",
        "• Ask them to remind us of their social media handles so we can tag "
        "them in our promotional posts",
        "• Offer to send them some promotional materials they can use in "
        "their own social posts",
    ]

    sample = (
        f"> Hey folks! Looking forward to having you at {brand} at {where} on "
        f"{formatted_date}! A few things:\n"
        f"> 1. Are you all set for the show? Call time is generally 6:55 PM "
        f"for the 8:00 showtime — if you'd prefer to arrive a bit later, "
        f"that's totally fine, just let us know.\n"
        f"> 2. Could you remind us of your social media handles so we can tag "
        f"you in our promotional posts?\n"
        f"> 3. We'd be happy to send you some promotional materials you can "
        f"use in your own social posts — just say the word!\n"
        f"> See you soon! 🎉"
    )

    return (
        f"👋 Hey {mention}! *{brand}* on *{formatted_date}* is one week out "
        f"(or less), and you're the Guest Team CC Contact. Please reach out "
        f"to the guest teams ({teams_text}) to:\n" + "\n".join(todo_lines) + "\n\n"
        f"Here's a sample message you're welcome to copy:\n{sample}"
        + _followup_footer()
    )


def format_followup_reminder(reminder: FollowUpReminder, mention: str) -> str:
    """Write the #casting-committee reminder message for a follow-up.

    Args:
        reminder: The follow-up reminder to format.
        mention: Slack mention text for the responsible contact.

    Returns:
        The full Slack message text for the reminder's kind.
    """
    match reminder.kind:
        case FollowUpKind.HOST:
            return format_host_followup_reminder(reminder, mention)
        case FollowUpKind.GUEST_TEAMS:
            return format_guest_teams_followup_reminder(reminder, mention)


def format_alerts(alerts: list[CastingAlert]) -> str:
    """Write a friendly message to send the responsible party via Slack for one or more alerts."""
    if not alerts:
        return ""

    config_url = "https://docs.google.com/spreadsheets/d/1sOcW4siUOLxd5Mt6WeOQ9vk05LZXDA6rHXulHcdQP4A/edit?gid=1914067327#gid=1914067327"
    footer = (
        f"\n\n⚙️ _Note: You can configure deadlines and who gets tagged on the "
        f"<{config_url}|Alerts Config tab> of the performance casting spreadsheet._\n"
        f"❓ _If you need any help, feel free to reach out to Greg Edelston._\n\n"
        f"Thanks! 💖"
    )

    if len(alerts) == 1:
        alert = alerts[0]
        formatted_date = alert.show.date.strftime("%B %d, %Y")
        formatted_deadline = alert.deadline.strftime("%B %d, %Y")
        article = "" if alert.role == Role.TEAMS else "a "

        msg = (
            f"Hey there! 👋 Just a quick heads-up that we're still missing {article}"
            f"*{alert.role.value}* for the upcoming show on *{formatted_date}* "
            f"at *{alert.show.venue.value}*. The ideal deadline for this was "
            f"*{formatted_deadline}*."
        )

        if alert.role == Role.TEAMS:
            cast_teams = [t.strip() for t in alert.show.teams if t.strip()]
            if cast_teams:
                msg += f" (Currently cast: {', '.join(cast_teams)})"

        return (
            msg + " Please update the casting sheet once you get this sorted." + footer
        )

    message_lines = [
        "Hey there! 👋 Just a quick heads-up that we're still missing the following roles for upcoming shows:"
    ]

    for alert in alerts:
        formatted_date = alert.show.date.strftime("%B %d, %Y")
        formatted_deadline = alert.deadline.strftime("%B %d, %Y")
        article = "" if alert.role == Role.TEAMS else "a "

        extra_info = ""
        if alert.role == Role.TEAMS:
            cast_teams = [t.strip() for t in alert.show.teams if t.strip()]
            if cast_teams:
                extra_info = f" (Currently cast: {', '.join(cast_teams)})"

        message_lines.append(
            f"• {article}*{alert.role.value}* for the show on *{formatted_date}* "
            f"at *{alert.show.venue.value}* (deadline was *{formatted_deadline}*){extra_info}"
        )

    message_lines.append("\nPlease update the casting sheet once you get this sorted.")

    return "\n".join(message_lines) + footer
