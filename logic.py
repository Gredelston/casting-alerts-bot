#!/usr/bin/env python3

"""
Core business logic for the Casting Alerts Bot.

This module contains the purely functional rules of the application. 
It compares scheduled shows against defined casting expectations and 
deadlines to identify missing roles and generate actionable alerts.
"""

import datetime
import logging

import models


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
