"""People and editable estimates/dates retain user information across operations."""

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from planacity.domain import Person, PlanningHorizon, ProgramPlan, WorkItem, WorkItemType
from planacity.planning.people import add_person, remove_person, rename_person
from planacity.planning.work_items import (
    set_work_dates,
    set_work_estimate,
    work_outside_horizon,
)


@pytest.fixture
def plan() -> ProgramPlan:
    return ProgramPlan(
        name="Aurora",
        horizon=PlanningHorizon(date(2026, 1, 1), date(2026, 1, 31)),
        work_items=(WorkItem(title="Build bench", kind=WorkItemType.TASK),),
    )


def test_roster_lifecycle_keeps_ids_order_and_work(plan: ProgramPlan) -> None:
    first, second = Person(name="  Iv\u00e1n  "), Person(name="Sam")
    added = add_person(add_person(plan, first), second)
    renamed = rename_person(added, first.id, "Alex")
    removed = remove_person(renamed, first.id)
    assert first.id != second.id
    assert added.person(first.id).name == "  Iv\u00e1n  "
    assert renamed.people == (replace(first, name="Alex"), second)
    assert removed.people == (second,)
    assert plan.people == ()
    assert removed.work_items == plan.work_items
    assert removed.id == plan.id


@pytest.mark.parametrize("name", ["", " \t", None, 42])
def test_person_rejects_invalid_names(name: object) -> None:
    with pytest.raises(ValueError, match="non-blank"):
        Person(name=name)


def test_roster_validates_ids_and_collections(plan: ProgramPlan) -> None:
    with pytest.raises(ValueError, match="UUID"):
        Person(name="Sam", id="external-user")
    person = Person(name="Sam")
    populated = add_person(plan, person)
    with pytest.raises(ValueError, match="unique"):
        add_person(populated, replace(person, name="Another name"))
    for invalid in ([person], ("Sam",)):
        with pytest.raises(ValueError, match="tuple of Person"):
            replace(plan, people=invalid)
    same_name = add_person(populated, Person(name="Sam"))
    assert len(same_name.people) == 2
    with pytest.raises(ValueError, match="does not exist"):
        rename_person(populated, uuid4(), "New name")
    with pytest.raises(ValueError, match="does not exist"):
        remove_person(populated, uuid4())
    assert populated.people == (person,)


@pytest.mark.parametrize("hours", [None, Decimal(0), Decimal("0.125"), Decimal("123456.789")])
def test_estimate_round_trip_preserves_precision_and_identity(
    plan: ProgramPlan, hours: Decimal | None
) -> None:
    original = plan.work_items[0]
    changed = set_work_estimate(plan, original.id, hours)
    assert changed.work_items[0].estimate_hours == hours
    assert changed.work_items[0].id == original.id
    assert original.estimate_hours is None
    assert set_work_estimate(changed, original.id, None).work_items[0] == original


@pytest.mark.parametrize(
    "hours",
    [
        Decimal("-0.01"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        True,
        1,
        0.1,
        "1.5",
    ],
)
def test_invalid_estimate_does_not_replace_valid_plan(plan: ProgramPlan, hours: object) -> None:
    original = plan.work_items[0]
    with pytest.raises(ValueError, match="Estimate"):
        set_work_estimate(plan, original.id, hours)
    assert plan.work_items == (original,)


@pytest.mark.parametrize(
    ("start", "end", "outside"),
    [
        (None, None, False),
        (date(2026, 1, 1), date(2026, 1, 31), False),
        (date(2026, 1, 2), date(2026, 1, 2), False),
        (date(2026, 1, 15), None, False),
        (None, date(2026, 1, 15), False),
        (date(2025, 12, 31), None, True),
        (None, date(2026, 2, 1), True),
        (date(2025, 12, 1), date(2025, 12, 2), True),
        (date(2026, 2, 1), date(2026, 2, 2), True),
        (date(2025, 12, 1), date(2026, 2, 1), True),
    ],
)
def test_partial_and_outside_dates_are_preserved_and_reported(
    plan: ProgramPlan, start: date | None, end: date | None, outside: bool
) -> None:
    item = plan.work_items[0]
    changed = set_work_dates(plan, item.id, start=start, end=end)
    updated = changed.work_item(item.id)
    assert (updated.start, updated.end) == (start, end)
    assert work_outside_horizon(changed) == ((updated,) if outside else ())
    assert set_work_dates(changed, item.id, start=None, end=None).work_items == (item,)


@pytest.mark.parametrize("invalid", ["2026-01-01", datetime(2026, 1, 1), 1])
@pytest.mark.parametrize("field", ["start", "end"])
def test_dates_reject_implicit_conversions(plan: ProgramPlan, invalid: object, field: str) -> None:
    dates = {"start": None, "end": None}
    dates[field] = invalid
    with pytest.raises(ValueError, match="date without a time"):
        set_work_dates(plan, plan.work_items[0].id, **dates)


def test_reversed_dates_and_unknown_edits_are_atomic(plan: ProgramPlan) -> None:
    item = plan.work_items[0]
    with pytest.raises(ValueError, match="on or after"):
        set_work_dates(plan, item.id, start=date(2026, 1, 2), end=date(2026, 1, 1))
    with pytest.raises(ValueError, match="does not exist"):
        set_work_estimate(plan, uuid4(), Decimal(1))
    with pytest.raises(ValueError, match="does not exist"):
        set_work_dates(plan, uuid4(), start=None, end=None)
    assert plan.work_items == (item,)
