"""Explicit splits, incomplete plans, stable references, and exact hour summaries."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest

from planacity.domain import (
    Allocation,
    Person,
    PlanningHorizon,
    ProgramPlan,
    WorkItem,
    WorkItemType,
)
from planacity.persistence.codec import dumps
from planacity.planning.allocations import summarize_allocations, validate_allocations


@pytest.fixture
def plan():
    epic = WorkItem(title="Integration", kind=WorkItemType.EPIC, estimate_hours=Decimal(100))
    task = WorkItem(
        title="Bench", kind=WorkItemType.TASK, parent_id=epic.id, estimate_hours=Decimal(100)
    )
    unknown = WorkItem(title="Follow-up", kind=WorkItemType.TASK)
    return ProgramPlan(
        name="Split effort",
        horizon=PlanningHorizon(date(2026, 10, 1), date(2026, 12, 31)),
        work_items=(epic, task, unknown),
        people=(Person(name="Alex"), Person(name="Sam")),
    )


def allocation(plan, hours, *, person=0, work=1):
    return Allocation(
        work_item_id=plan.work_items[work].id,
        person_id=plan.people[person].id,
        hours=Decimal(hours),
    )


def test_split_work_preserves_inputs_identity_and_sibling_order(plan):
    allocations = (allocation(plan, "60"), allocation(plan, "40", person=1))
    before = dumps(plan)
    summary = summarize_allocations(plan, allocations)
    assert summary.work[1].allocated_hours == 100
    assert summary.work[1].remaining_hours == 0
    assert not summary.work[1].unassigned
    assert [p.allocated_hours for p in summary.people] == [60, 40]
    assert [w.work_item_id for w in summary.work] == [w.id for w in plan.work_items]
    assert [p.person_id for p in summary.people] == [p.id for p in plan.people]
    assert summary == summarize_allocations(plan, tuple(reversed(allocations)))
    assert allocations[0].hours == 60 and allocations[1].hours == 40
    assert dumps(plan) == before
    with pytest.raises(FrozenInstanceError):
        allocations[0].hours = Decimal(0)
    with pytest.raises(FrozenInstanceError):
        summary.work[1].remaining_hours = Decimal(1)


@pytest.mark.parametrize("hours,remaining", [("50", "50"), ("100", "0"), ("130.5", "-30.5")])
def test_under_and_over_allocation_are_visible_not_rescaled(plan, hours, remaining):
    entries = (allocation(plan, hours),)
    validate_allocations(plan, entries)
    result = summarize_allocations(plan, entries).work[1]
    assert result.allocated_hours == Decimal(hours)
    assert result.remaining_hours == Decimal(remaining)
    assert result.estimate_hours == 100


def test_unknown_estimate_and_zero_hours_are_distinct(plan):
    entries = (allocation(plan, "0"), allocation(plan, "12", work=2))
    result = summarize_allocations(plan, entries)
    assert result.work[1].unassigned and result.work[1].remaining_hours == 100
    assert result.work[2].missing_estimate and result.work[2].remaining_hours is None
    assert not result.work[2].unassigned
    zero = replace(plan, work_items=(replace(plan.work_items[0], estimate_hours=Decimal(0)),))
    empty = summarize_allocations(zero, ())
    assert empty.work[0].remaining_hours == 0
    assert not empty.work[0].missing_estimate
    assert empty.work[0].unassigned


def test_hierarchy_rollups_do_not_clip_dates_or_double_count_container_estimates(plan):
    task = replace(plan.work_items[1], start=date(2027, 1, 1), end=date(2027, 1, 5))
    plan = replace(plan, work_items=(plan.work_items[0], task, plan.work_items[2]))
    result = summarize_allocations(plan, (allocation(plan, "25"), allocation(plan, "10", work=0)))
    epic, child, unknown = result.work
    assert epic.entered_estimate_hours == 100
    assert epic.known_estimate_hours == 100
    assert epic.estimate_hours == 100
    assert epic.direct_allocated_hours == 10
    assert epic.descendant_allocated_hours == 25
    assert epic.allocated_hours == 35
    assert epic.remaining_hours is None
    assert epic.mixed_level_effort and epic.incomplete
    assert child.allocated_hours == 25 and child.remaining_hours == 75
    assert unknown.missing_estimate_count == 1 and unknown.remaining_hours is None
    assert result.people[0].allocated_hours == 35
    assert result.people[1].allocated_hours == 0


def test_nested_rollup_reports_known_subtotal_missing_leaves_and_exact_allocations(plan):
    epic, task, unknown = plan.work_items
    known = WorkItem(
        title="Known leaf",
        kind=WorkItemType.SUBTASK,
        parent_id=task.id,
        estimate_hours=Decimal("60"),
    )
    missing = WorkItem(title="Unknown leaf", kind=WorkItemType.SUBTASK, parent_id=task.id)
    other = replace(unknown, parent_id=epic.id, estimate_hours=Decimal("40"))
    plan = replace(
        plan,
        work_items=(replace(epic, estimate_hours=Decimal("150")), task, known, missing, other),
    )
    entries = (
        Allocation(work_item_id=known.id, person_id=plan.people[0].id, hours=Decimal("20")),
        Allocation(work_item_id=other.id, person_id=plan.people[1].id, hours=Decimal("40")),
    )
    result = summarize_allocations(plan, entries)
    by_id = {summary.work_item_id: summary for summary in result.work}
    epic_summary = by_id[epic.id]
    task_summary = by_id[task.id]
    assert epic_summary.entered_estimate_hours == 150
    assert epic_summary.known_estimate_hours == 100
    assert epic_summary.estimate_hours is None
    assert epic_summary.missing_estimate_count == 1
    assert epic_summary.leaf_count == 3
    assert epic_summary.allocated_hours == 60
    assert epic_summary.direct_allocation_count == 0
    assert epic_summary.descendant_allocation_count == 2
    assert task_summary.entered_estimate_hours == 100
    assert task_summary.known_estimate_hours == 60
    assert task_summary.missing_estimate_count == 1
    assert task_summary.allocated_hours == 20
    assert [person.allocated_hours for person in result.people] == [20, 40]


def test_long_fractional_hours_and_negative_difference_are_exact_under_low_precision(plan):
    first = allocation(plan, "10000000000000000000000000000.00000000000000000000000000001")
    second = allocation(plan, "0.00000000000000000000000000002", person=1)
    with localcontext() as context:
        context.prec = 3
        result = summarize_allocations(plan, (first, second))
        assert context.prec == 3
        assert result.work[1].allocated_hours == Decimal(
            "10000000000000000000000000000.00000000000000000000000000003"
        )
        assert result.work[1].remaining_hours == Decimal(
            "-9999999999999999999999999900.00000000000000000000000000003"
        )


@pytest.mark.parametrize(
    "hours",
    [None, 1, 1.5, True, "1", Decimal("-1"), Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity")],
)
def test_allocation_requires_explicit_finite_nonnegative_decimal(plan, hours):
    with pytest.raises(ValueError, match="finite, non-negative Decimal"):
        Allocation(work_item_id=plan.work_items[0].id, person_id=plan.people[0].id, hours=hours)


@pytest.mark.parametrize("field", ["id", "work_item_id", "person_id"])
def test_all_ids_must_be_uuids(plan, field):
    with pytest.raises(ValueError, match="UUID"):
        replace(allocation(plan, "1"), **{field: "not-a-uuid"})


@pytest.mark.parametrize("field", ["work_item_id", "person_id"])
def test_unknown_references_are_errors(plan, field):
    with pytest.raises(ValueError, match="unknown"):
        summarize_allocations(plan, (replace(allocation(plan, "1"), **{field: uuid4()}),))


def test_duplicate_ids_and_pairs_are_errors_even_with_zero_hours(plan):
    first = allocation(plan, "0")
    with pytest.raises(ValueError, match="Duplicate allocation ID"):
        summarize_allocations(plan, (first, replace(first, person_id=plan.people[1].id)))
    with pytest.raises(ValueError, match="same work/person pair"):
        summarize_allocations(plan, (first, replace(first, id=uuid4())))


@pytest.mark.parametrize("entries", [None, [], (object(),)])
def test_candidate_collection_requires_immutable_typed_values(plan, entries):
    with pytest.raises(ValueError, match="tuple of Allocation"):
        summarize_allocations(plan, entries)


def test_empty_plan_and_empty_allocations_are_supported(plan):
    result = summarize_allocations(plan, ())
    assert all(w.unassigned for w in result.work)
    assert all(p.allocated_hours == 0 for p in result.people)
    empty = summarize_allocations(replace(plan, people=(), work_items=()), ())
    assert empty.work == empty.people == ()
