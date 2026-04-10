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

        return (
            f"Hey there! 👋 Just a quick heads-up that we're still missing {article}"
            f"*{alert.role.value}* for the upcoming show on *{formatted_date}* "
            f"at *{alert.show.venue.value}*. The ideal deadline for this was "
            f"*{formatted_deadline}*, so please update the casting sheet once "
            f"you get this sorted." + footer
        )

    message_lines = [
        "Hey there! 👋 Just a quick heads-up that we're still missing the following roles for upcoming shows:"
    ]

    for alert in alerts:
        formatted_date = alert.show.date.strftime("%B %d, %Y")
        formatted_deadline = alert.deadline.strftime("%B %d, %Y")
        article = "" if alert.role == Role.TEAMS else "a "

        message_lines.append(
            f"• {article}*{alert.role.value}* for the show on *{formatted_date}* "
            f"at *{alert.show.venue.value}* (deadline was *{formatted_deadline}*)"
        )

    message_lines.append("\nPlease update the casting sheet once you get this sorted.")

    return "\n".join(message_lines) + footer
