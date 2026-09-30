"""Availability limits, overlap visibility, exact arithmetic, and date boundaries."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from random import Random
from uuid import UUID, uuid4

import pytest

from planacity.domain import PlanningHorizon, WorkCalendar
from planacity.domain.availability import AvailabilityEvent
from planacity.planning.availability import availability_capacity

PERSON = UUID("cb4d4aa5-30dc-4a6a-a4b1-a566194fbaaf")
MONDAY = date(2026, 9, 28)
WEEK = PlanningHorizon(MONDAY, date(2026, 10, 4))
CALENDAR = WorkCalendar(
    name="Explicit week",
    weekday_hours=tuple(Decimal(v) for v in ("6", "7.5", "0", "4.25", "2", "3", "1")),
)


def event(start=MONDAY, end=MONDAY, fraction="1", **kwargs):
    return AvailabilityEvent(
        person_id=PERSON,
        period=PlanningHorizon(start, end),
        unavailable_fraction=Decimal(fraction),
        **kwargs,
    )


@pytest.mark.parametrize(
    "fraction",
    [
        None,
        1,
        0.5,
        True,
        "0.5",
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-0.01"),
        Decimal("1.01"),
    ],
)
def test_reject_invalid_shares(fraction):
    with pytest.raises(ValueError, match="fraction"):
        AvailabilityEvent(person_id=PERSON, period=WEEK, unavailable_fraction=fraction)


@pytest.mark.parametrize("fields", [{"id": "bad"}, {"person_id": None}, {"period": None}])
def test_reject_invalid_identity_and_period(fields):
    with pytest.raises(ValueError):
        replace(event(), **fields)


def test_date_range_validation_and_immutable_identity():
    value = event()
    assert isinstance(value.id, UUID)
    assert replace(value, unavailable_fraction=Decimal("0.5")).id == value.id
    with pytest.raises(FrozenInstanceError):
        value.person_id = uuid4()
    with pytest.raises(ValueError):
        event(start=date(2026, 10, 1), end=MONDAY)
    with pytest.raises(ValueError):
        event(start=datetime(2026, 9, 28))


def test_no_events_and_explicit_zero_share_leave_nominal_unchanged():
    expected = availability_capacity(CALENDAR, WEEK, PERSON, ())
    actual = availability_capacity(CALENDAR, WEEK, PERSON, (event(fraction="0"),))
    assert actual == expected
    assert (actual.nominal_hours, actual.unavailable_hours, actual.available_hours) == (
        Decimal("23.75"),
        Decimal(0),
        Decimal("23.75"),
    )
    assert not actual.overlaps


def test_full_and_partial_absence_use_each_dates_explicit_hours():
    events = (event(), event(date(2026, 9, 29), date(2026, 10, 4), "0.5"))
    result = availability_capacity(CALENDAR, WEEK, PERSON, events)
    assert result.unavailable_hours == Decimal("14.875")
    assert result.available_hours == Decimal("8.875")
    assert result.nominal_hours == result.unavailable_hours + result.available_hours
    assert not result.overlaps


def test_overlap_uses_strongest_share_and_preserves_reviewable_ids():
    half = event(MONDAY, date(2026, 10, 1), "0.5")
    full = event(date(2026, 9, 29), date(2026, 10, 2))
    other = event(date(2026, 9, 29), date(2026, 9, 29), "0.25")
    events = (half, full, other)
    result = availability_capacity(CALENDAR, WEEK, PERSON, events)
    assert result.unavailable_hours == Decimal("16.75")
    assert result.available_hours == Decimal(7)
    assert len(result.overlaps) == 2
    assert result.overlaps[0].period == PlanningHorizon(date(2026, 9, 29), date(2026, 9, 29))
    assert result.overlaps[0].event_ids == tuple(sorted((e.id for e in events), key=str))
    assert result.overlaps[1].period == PlanningHorizon(date(2026, 9, 30), date(2026, 10, 1))
    assert availability_capacity(CALENDAR, WEEK, PERSON, tuple(reversed(events))) == result


def test_two_partial_absences_are_limits_not_additive_duties():
    result = availability_capacity(
        CALENDAR, WEEK, PERSON, (event(fraction="0.5"), event(fraction="0.5"))
    )
    assert result.unavailable_hours == 3
    assert len(result.overlaps) == 1


def test_clips_events_and_ignores_outside_horizon():
    events = (
        event(date.min, MONDAY),
        event(date(2026, 10, 4), date.max),
        event(date(2026, 10, 5), date.max),
    )
    result = availability_capacity(CALENDAR, WEEK, PERSON, events)
    assert result.unavailable_hours == 7
    assert not result.overlaps


def test_adjacent_events_do_not_overlap():
    result = availability_capacity(
        CALENDAR, WEEK, PERSON, (event(), event(date(2026, 9, 29), date(2026, 9, 29)))
    )
    assert result.unavailable_hours == Decimal("13.5")
    assert not result.overlaps


def test_zero_calendar_hours_are_not_negative_but_overlaps_remain_visible():
    calendar = replace(CALENDAR, weekday_hours=(Decimal(0),) * 7)
    result = availability_capacity(calendar, WEEK, PERSON, (event(), event()))
    assert result.nominal_hours == result.unavailable_hours == result.available_hours == 0
    assert len(result.overlaps) == 1


@pytest.mark.parametrize("day", [date.min, date.max, date(2024, 2, 29)])
def test_single_date_boundaries_and_leap_day(day):
    result = availability_capacity(CALENDAR, PlanningHorizon(day, day), PERSON, (event(day, day),))
    assert result.unavailable_hours == CALENDAR.hours_on(day)
    assert result.available_hours == 0


def test_entire_supported_range_does_not_expand_dates(monkeypatch):
    import planacity.planning.availability as module

    calls = []
    original = module.nominal_capacity

    def counted(calendar, horizon):
        calls.append(horizon)
        return original(calendar, horizon)

    monkeypatch.setattr(module, "nominal_capacity", counted)
    horizon = PlanningHorizon(date.min, date.max)
    result = availability_capacity(CALENDAR, horizon, PERSON, (event(date.min, date.max),))
    assert result.available_hours == 0
    assert len(calls) == 2


def test_high_precision_is_independent_of_callers_decimal_context():
    hours = Decimal("1.123456789012345678901234567890123456789")
    fraction = Decimal("0.123456789012345678901234567890123456789")
    calendar = replace(CALENDAR, weekday_hours=(hours,) * 7)
    absence = event(MONDAY, WEEK.end, str(fraction))
    with localcontext() as context:
        context.prec = 120
        expected_nominal = hours * 7
        expected_unavailable = expected_nominal * fraction
        expected_available = expected_nominal - expected_unavailable
    with localcontext() as context:
        context.prec = 2
        result = availability_capacity(calendar, WEEK, PERSON, (absence,))
        assert context.prec == 2
    assert result.nominal_hours == expected_nominal
    assert result.unavailable_hours == expected_unavailable
    assert result.available_hours == expected_available


@pytest.mark.parametrize(
    "events",
    [
        [event()],
        (None,),
        (event(id=PERSON), event(id=PERSON)),
        (replace(event(), person_id=uuid4()),),
    ],
)
def test_reject_invalid_collections_duplicate_ids_and_other_people(events):
    with pytest.raises(ValueError):
        availability_capacity(CALENDAR, WEEK, PERSON, events)


def test_missing_calendar_or_person_is_not_zero_capacity():
    for calendar, horizon, person in (
        (None, WEEK, PERSON),
        (CALENDAR, None, PERSON),
        (CALENDAR, WEEK, None),
    ):
        with pytest.raises(ValueError):
            availability_capacity(calendar, horizon, person, ())


def test_interval_calculation_matches_daily_reference_for_varied_overlaps():
    random = Random(41)
    start = date(2024, 2, 20)
    horizon = PlanningHorizon(start, start + timedelta(days=49))
    for _ in range(40):
        events = []
        for _ in range(12):
            first = random.randrange(-10, 60)
            events.append(
                event(
                    start + timedelta(days=first),
                    start + timedelta(days=first + random.randrange(0, 20)),
                    random.choice(("0", "0.25", "0.5", "1")),
                )
            )
        expected = Decimal(0)
        for offset in range(50):
            day = start + timedelta(days=offset)
            fraction = max(
                (e.unavailable_fraction for e in events if e.period.start <= day <= e.period.end),
                default=Decimal(0),
            )
            expected += CALENDAR.hours_on(day) * fraction
        result = availability_capacity(CALENDAR, horizon, PERSON, tuple(events))
        assert result.unavailable_hours == expected
        assert result.available_hours >= 0
