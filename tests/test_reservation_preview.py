"""Daily adapter includes complete sprints and never invents missing calendars."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from test_calendar_settings import calendar_plan

from planacity.domain import AvailabilityEvent, PlanningHorizon, ReservationRule
from planacity.planning.reservation_preview import preview_plan_reservations


def preview_plan():
    plan = calendar_plan()
    rule = ReservationRule(
        name="Meetings",
        person_ids=(plan.people[0].id,),
        hours_per_person=Decimal(1),
        anchor=plan.horizon.start,
        interval_weeks=1,
        effective=plan.horizon,
    )
    return replace(plan, reservation_rules=(rule,))


def test_preview_uses_complete_sprints_and_availability_outside_query():
    plan = preview_plan()
    absence = AvailabilityEvent(
        person_id=plan.people[0].id,
        period=PlanningHorizon(date(2026, 9, 28), date(2026, 9, 28)),
        unavailable_fraction=Decimal(1),
    )
    plan = replace(
        plan,
        availability_events=(absence,),
        horizon=PlanningHorizon(date(2026, 9, 29), date(2026, 9, 29)),
    )
    result = preview_plan_reservations(plan)[0]
    assert result.occurrences[0].eligible_days == 4
    assert result.reserved_hours == Fraction(1, 4)
    assert result.remaining_hours == Fraction(19, 20)
    assert preview_plan_reservations(plan) == (result,)


def test_missing_calendar_is_actionable_and_no_rules_needs_no_calendar():
    plan = replace(preview_plan(), person_calendars=())
    with pytest.raises(ValueError, match="Alex"):
        preview_plan_reservations(plan)
    assert preview_plan_reservations(replace(plan, reservation_rules=())) == ()


def test_preview_limit_is_explicit_and_does_not_expand_full_date_range():
    plan = replace(preview_plan(), horizon=PlanningHorizon(date.min, date.max))
    with pytest.raises(ValueError, match="100,000"):
        preview_plan_reservations(plan)


def test_zero_availability_is_unresolved_and_overlaps_remain_visible():
    from uuid import uuid4

    plan = preview_plan()
    rule = plan.reservation_rules[0]
    duplicate = replace(rule, id=uuid4(), name="Support", hours_per_person=Decimal(10))
    plan = replace(plan, reservation_rules=(rule, duplicate))
    result = preview_plan_reservations(plan)[0]
    assert len(result.overlaps) == 5
    assert result.remaining_hours == -5
    absent = AvailabilityEvent(
        person_id=plan.people[0].id, period=plan.horizon, unavailable_fraction=Decimal(1)
    )
    assert (
        preview_plan_reservations(replace(plan, availability_events=(absent,)))[0].remaining_hours
        is None
    )
