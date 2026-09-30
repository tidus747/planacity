"""Explicit calendars and exact gross capacity without Qt or persistence."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from uuid import UUID

import pytest

from planacity.domain import PlanningHorizon, WorkCalendar
from planacity.planning.work_calendar import nominal_capacity, nominal_week_hours


def calendar(*hours):
    return WorkCalendar(
        name="Variable week", weekday_hours=tuple(Decimal(value) for value in hours)
    )


def test_calendar_has_stable_identity_and_explicit_weekday_order():
    identifier = UUID("5ad14961-1dc3-4429-af47-1c4d9b60c471")
    values = tuple(Decimal(n) for n in range(7))
    work = WorkCalendar(id=identifier, name="  Calendario de Rubén  ", weekday_hours=values)
    assert work.id == identifier
    assert work.name == "  Calendario de Rubén  "
    assert work.weekday_hours is values
    for weekday in range(7):
        assert work.hours_on(date(2026, 9, 28) + timedelta(days=weekday)) == values[weekday]
    with pytest.raises(FrozenInstanceError):
        work.name = "Changed"
    with pytest.raises(ValueError, match="without a time"):
        work.hours_on(datetime(2026, 9, 28))


@pytest.mark.parametrize(
    "hours",
    [
        (),
        (Decimal(8),) * 6,
        (Decimal(8),) * 8,
        [Decimal(8)] * 7,
        (8,) * 7,
        (8.0,) * 7,
        ("8",) * 7,
        (True,) * 7,
        (None,) * 7,
        (Decimal("NaN"),) * 7,
        (Decimal("sNaN"),) * 7,
        (Decimal("Infinity"),) * 7,
        (Decimal("-0.01"),) * 7,
        (Decimal("24.01"),) * 7,
    ],
)
def test_invalid_weekday_patterns_are_rejected(hours):
    with pytest.raises(ValueError):
        WorkCalendar(name="Invalid", weekday_hours=hours)


@pytest.mark.parametrize("fields", [{"name": " "}, {"name": None}, {"id": "not-a-uuid"}])
def test_invalid_identity_or_name_is_rejected(fields):
    values = {"name": "Named", "weekday_hours": (Decimal(0),) * 7}
    values.update(fields)
    with pytest.raises(ValueError):
        WorkCalendar(**values)


def test_no_implicit_workweek_or_daily_hours():
    work = calendar("6", "7.5", "0", "4.25", "2", "3", "1")
    horizon = PlanningHorizon(date(2026, 9, 28), date(2026, 10, 4))
    result = nominal_capacity(work, horizon)
    assert result.total_hours == nominal_week_hours(work) == Decimal("23.75")
    assert (result.working_days, result.calendar_days) == (6, 7)
    weekend = nominal_capacity(work, PlanningHorizon(date(2026, 10, 3), date(2026, 10, 4)))
    assert weekend.total_hours == Decimal(4)
    assert weekend.working_days == 2


@pytest.mark.parametrize(
    "start,length",
    [
        (date(2024, 2, 26), 7),
        (date(2024, 2, 29), 1),
        (date(2025, 12, 29), 15),
        (date.min, 17),
        (date(9999, 12, 15), 17),
    ]
    + [
        (date(2026, 9, 28) + timedelta(days=weekday), length)
        for weekday in range(7)
        for length in (1, 6, 7, 8, 19)
    ],
)
def test_partial_periods_match_independent_daily_accumulation(start, length):
    work = calendar("1.25", "0", "3.5", "0.75", "0", "6", "0")
    horizon = PlanningHorizon(start, start + timedelta(days=length - 1))
    daily = [work.hours_on(start + timedelta(days=offset)) for offset in range(length)]
    expected = sum(daily, Decimal(0))
    result = nominal_capacity(work, horizon)
    assert result.total_hours == expected
    assert result.working_days == sum(hours > 0 for hours in daily)
    assert result.calendar_days == length
    assert nominal_capacity(work, horizon) == result


def test_zero_calendar_and_full_supported_date_range():
    horizon = PlanningHorizon(date.min, date.max)
    zero = nominal_capacity(calendar(*("0",) * 7), horizon)
    assert zero.total_hours == 0 and zero.working_days == 0
    all_days = nominal_capacity(calendar(*("24",) * 7), horizon)
    assert all_days.calendar_days == all_days.working_days == 3652059
    assert all_days.total_hours == Decimal(3652059) * 24


def test_arithmetic_retains_fractional_precision_and_does_not_change_caller_context():
    work = calendar("7.123456789012345678901234567890", "0", "0", "0", "0", "0", "0")
    horizon = PlanningHorizon(date(2026, 9, 28), date(2026, 10, 11))
    with localcontext() as context:
        context.prec = 3
        assert nominal_week_hours(work) == work.weekday_hours[0]
        assert nominal_capacity(work, horizon).total_hours == Decimal(
            "14.246913578024691357802469135780"
        )
        assert context.prec == 3
    assert work.weekday_hours[0] == Decimal("7.123456789012345678901234567890")
