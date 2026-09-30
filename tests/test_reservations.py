"""Anchored duties, exact proration, explicit capacity, and visible planning risks."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import UUID, uuid4

import pytest

from planacity.domain import AvailabilityEvent, PlanningHorizon, WorkCalendar
from planacity.domain.reservations import ReservationRule
from planacity.planning.availability import availability_capacity
from planacity.planning.reservations import (
    CapacityDay,
    PersonCapacity,
    reservation_periods,
    reserve_capacity,
)

PERSON = UUID("5c5e78a9-0a0b-4c3e-a59a-a1710d8554af")
START = date(2024, 2, 28)  # Wednesday, with leap day in the first sprint.
SPRINT = PlanningHorizon(START, date(2024, 3, 12))


def rule(**fields):
    values = dict(
        name="Meetings",
        person_ids=(PERSON,),
        hours_per_person=Decimal(6),
        anchor=START,
        interval_weeks=2,
        effective=SPRINT,
    )
    values.update(fields)
    return ReservationRule(**values)


def capacity(person=PERSON, period=SPRINT, hours="6"):
    return PersonCapacity(
        person,
        tuple(
            CapacityDay(
                date.fromordinal(day),
                Decimal(hours) if date.fromordinal(day).weekday() < 5 else Decimal(0),
            )
            for day in range(period.start.toordinal(), period.end.toordinal() + 1)
        ),
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"id": "invalid"},
        {"name": " "},
        {"name": None},
        {"person_ids": ()},
        {"person_ids": [PERSON]},
        {"person_ids": (PERSON, PERSON)},
        {"person_ids": ("bad",)},
        {"hours_per_person": 6},
        {"hours_per_person": "6"},
        {"hours_per_person": True},
        {"hours_per_person": Decimal("NaN")},
        {"hours_per_person": Decimal("sNaN")},
        {"hours_per_person": Decimal("Infinity")},
        {"hours_per_person": Decimal(0)},
        {"hours_per_person": Decimal(-1)},
        {"anchor": datetime(2024, 2, 28)},
        {"interval_weeks": 0},
        {"interval_weeks": -1},
        {"interval_weeks": True},
        {"interval_weeks": 1.5},
        {"effective": None},
    ],
)
def test_rule_validation(fields):
    with pytest.raises(ValueError):
        rule(**fields)


@pytest.mark.parametrize(
    "hours", [1, None, Decimal(-1), Decimal(25), Decimal("NaN"), Decimal("Infinity")]
)
def test_invalid_capacity_values(hours):
    with pytest.raises(ValueError):
        CapacityDay(START, hours)


def test_immutable_rule_preserves_supplied_name_and_identity():
    duty = rule(name="  Meetings / support  ")
    assert duty.name == "  Meetings / support  "
    assert isinstance(duty.id, UUID)
    assert replace(duty, hours_per_person=Decimal(8)).id == duty.id
    with pytest.raises(FrozenInstanceError):
        duty.name = "Changed"


def test_non_monday_anchor_leap_day_and_periods_before_anchor():
    duty = rule(effective=PlanningHorizon(date(2024, 2, 1), date(2024, 4, 1)))
    assert reservation_periods(duty, SPRINT) == (SPRINT,)
    query = PlanningHorizon(date(2024, 2, 27), START)
    periods = reservation_periods(duty, query)
    assert periods == (PlanningHorizon(date(2024, 2, 14), date(2024, 2, 27)), SPRINT)
    assert reservation_periods(rule(), PlanningHorizon(date(2025, 1, 1), date(2025, 1, 2))) == ()


def test_hours_are_per_person_and_do_not_change_inputs():
    other = uuid4()
    duty = rule(person_ids=(PERSON, other))
    inputs = (capacity(), capacity(other))
    before = repr((duty, inputs))
    result = reserve_capacity((duty,), SPRINT, inputs)
    assert len(result) == 2
    assert sum((r.reserved_hours for r in result), Fraction()) == 12
    assert all(r.reserved_hours == 6 and r.remaining_hours == 54 for r in result)
    assert all(r.occurrences[0].eligible_days == 10 for r in result)
    assert repr((duty, inputs)) == before
    assert reserve_capacity((duty,), SPRINT, tuple(reversed(inputs))) == result


def test_partial_effective_range_and_query_use_complete_period_denominator():
    duty = rule(effective=PlanningHorizon(date(2024, 3, 1), SPRINT.end))
    query = PlanningHorizon(START, date(2024, 3, 4))
    result = reserve_capacity((duty,), query, (capacity(),))[0]
    assert result.reserved_hours == Fraction(6, 5)  # Friday and Monday, 2/10 of 6 h.
    occurrence = result.occurrences[0]
    assert (occurrence.eligible_days, occurrence.included_days) == (10, 2)
    assert occurrence.included_period == PlanningHorizon(date(2024, 3, 1), date(2024, 3, 4))
    assert result.days[0].reserved_hours == 0


def test_leave_holiday_and_program_event_adjustments_are_applied_before_reservations():
    calendar = WorkCalendar(
        name="Explicit calendar", weekday_hours=(Decimal(6),) * 5 + (Decimal(0),) * 2
    )
    leave = AvailabilityEvent(
        person_id=PERSON, period=PlanningHorizon(START, START), unavailable_fraction=Decimal(1)
    )
    holiday = replace(leave, id=uuid4())  # Same date as leave: unavailable once.
    adjusted = []
    for original in capacity().days:
        day = original.day
        available = availability_capacity(
            calendar, PlanningHorizon(day, day), PERSON, (leave, holiday)
        ).available_hours
        # Explicit upstream event deductions: a full-day event and a partial-day event.
        if day == date(2024, 2, 29):
            available = Decimal(0)
        if day == date(2024, 3, 1):
            available = Decimal(2)
        adjusted.append(CapacityDay(day, available))
    result = reserve_capacity((rule(),), SPRINT, (PersonCapacity(PERSON, tuple(adjusted)),))[0]
    assert result.occurrences[0].eligible_days == 8
    assert result.reserved_hours == 6
    assert result.days[0].reserved_hours == result.days[1].reserved_hours == 0
    assert result.days[2].reserved_hours == Fraction(3, 4)
    assert result.remaining_hours == 38  # 7 * 6 + 2 available, minus 6 reserved.


def test_overlaps_add_and_negative_daily_capacity_is_not_hidden_by_positive_total():
    first, second = (
        rule(hours_per_person=Decimal(40)),
        rule(name="Support", hours_per_person=Decimal(30)),
    )
    result = reserve_capacity((second, first), SPRINT, (capacity(),))[0]
    assert result.reserved_hours == 70
    assert result.remaining_hours == -10
    assert len(result.overlaps) == len(result.overloaded_days) == 10
    assert set(result.overlaps[0].rule_ids) == {first.id, second.id}
    assert reserve_capacity((first, second), SPRINT, (capacity(),)) == (result,)


def test_partial_capacity_days_get_equal_shares_with_visible_daily_overload():
    original = capacity()
    values = (replace(original.days[0], available_hours=Decimal("0.1")), *original.days[1:])
    result = reserve_capacity((rule(),), SPRINT, (PersonCapacity(PERSON, values),))[0]
    assert result.remaining_hours > 0
    assert result.overloaded_days[0].remaining_hours == Fraction(-1, 2)


def test_no_eligible_days_is_unresolved_not_a_successful_zero_reservation():
    result = reserve_capacity((rule(),), SPRINT, (capacity(hours="0"),))[0]
    assert result.occurrences[0].reserved_hours is None
    assert result.occurrences[0].requested_hours == 6
    assert result.occurrences[0].eligible_days == 0
    assert result.remaining_hours is None


def test_query_without_eligible_days_can_still_have_a_valid_full_period():
    query = PlanningHorizon(date(2024, 3, 2), date(2024, 3, 3))
    result = reserve_capacity((rule(),), query, (capacity(),))[0]
    assert result.reserved_hours == result.remaining_hours == 0
    assert result.occurrences[0].eligible_days == 10
    assert result.occurrences[0].included_days == 0


def test_fractional_shares_are_exact_and_queries_add_back_to_full_period():
    values = tuple(
        replace(d, available_hours=Decimal(1) if i < 3 else Decimal(0))
        for i, d in enumerate(capacity().days)
    )
    inputs = (PersonCapacity(PERSON, values),)
    duty = rule(hours_per_person=Decimal("1.00000000000000000000000000001"))
    with localcontext() as context:
        context.prec = 2
        full = reserve_capacity((duty,), SPRINT, inputs)[0]
        assert full.days[0].reserved_hours == Fraction(duty.hours_per_person) / 3
        total = sum(
            (
                reserve_capacity((duty,), PlanningHorizon(d.day, d.day), inputs)[0].reserved_hours
                for d in values
            ),
            Fraction(),
        )
        assert full.reserved_hours == total == Fraction(duty.hours_per_person)
        assert context.prec == 2


def test_missing_capacity_outside_query_is_not_assumed_zero():
    query = PlanningHorizon(START, START)
    with pytest.raises(ValueError, match="complete sprint period"):
        reserve_capacity((rule(),), query, (PersonCapacity(PERSON, capacity().days[:1]),))
    with pytest.raises(ValueError, match="Missing capacity"):
        reserve_capacity((), SPRINT, (PersonCapacity(PERSON, ()),))


def test_reject_duplicate_or_mismatched_inputs():
    duty = rule()
    with pytest.raises(ValueError, match="Reservation IDs"):
        reserve_capacity((duty, duty), SPRINT, (capacity(),))
    with pytest.raises(ValueError, match="person IDs"):
        reserve_capacity((duty,), SPRINT, (capacity(), capacity()))
    with pytest.raises(ValueError, match="explicit daily capacity"):
        reserve_capacity((duty,), SPRINT, ())
    with pytest.raises(ValueError, match="unique"):
        PersonCapacity(PERSON, capacity().days * 2)
    with pytest.raises(ValueError):
        PersonCapacity("bad", ())
    with pytest.raises(ValueError):
        PersonCapacity(PERSON, (None,))
    with pytest.raises(ValueError):
        CapacityDay(datetime(2024, 2, 28), Decimal(6))
    for rules, horizon, people in (
        ([], SPRINT, ()),
        ((None,), SPRINT, ()),
        ((), None, ()),
        ((), SPRINT, []),
        ((), SPRINT, (None,)),
    ):
        with pytest.raises(ValueError):
            reserve_capacity(rules, horizon, people)


def test_date_limits_and_no_partial_denominator_at_supported_boundary():
    for start in (date.min, date.max - timedelta(days=6)):
        period = PlanningHorizon(start, start + timedelta(days=6))
        duty = rule(anchor=start, interval_weeks=1, effective=period)
        result = reserve_capacity((duty,), period, (capacity(period=period),))[0]
        assert result.reserved_hours == 6
    for day in (date.min, date.max):
        duty = rule(
            anchor=day + timedelta(days=1) if day == date.min else day,
            interval_weeks=1,
            effective=PlanningHorizon(day, day),
        )
        with pytest.raises(ValueError, match="outside supported dates"):
            reservation_periods(duty, duty.effective)


def test_editing_and_removing_rules_recomputes_without_accumulating_occurrences():
    duty = rule()
    initial = reserve_capacity((duty,), SPRINT, (capacity(),))
    assert reserve_capacity((duty,), SPRINT, (capacity(),)) == initial
    updated = replace(duty, hours_per_person=Decimal(3))
    assert reserve_capacity((updated,), SPRINT, (capacity(),))[0].reserved_hours == 3
    removed = reserve_capacity((), SPRINT, (capacity(),))[0]
    assert removed.reserved_hours == 0
    assert removed.remaining_hours == 60


def test_multiple_sprints_each_keep_their_own_eligible_day_denominator():
    horizon = PlanningHorizon(START, SPRINT.end + timedelta(days=14))
    duty = rule(effective=horizon)
    original = capacity(period=horizon)
    values = tuple(
        replace(day, available_hours=Decimal(0))
        if day.day == SPRINT.end + timedelta(days=1)
        else day
        for day in original.days
    )
    result = reserve_capacity((duty,), horizon, (PersonCapacity(PERSON, values),))[0]
    assert len(result.occurrences) == 2
    assert [o.eligible_days for o in result.occurrences] == [10, 9]
    assert result.reserved_hours == 12
    assert result.days[0].reserved_hours == Fraction(3, 5)
    assert result.days[15].reserved_hours == Fraction(2, 3)
