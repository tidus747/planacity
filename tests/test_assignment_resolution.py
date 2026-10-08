"""Explicit legacy consolidation previews exact, atomic plan candidates."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest

from planacity.domain import (
    Allocation,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    WorkCalendar,
    WorkItem,
    WorkItemType,
)
from planacity.persistence.codec import dumps, loads
from planacity.planning.assignment_policy import assignment_policy_conflicts
from planacity.planning.assignment_resolution import preview_assignment_consolidation
from planacity.planning.findings import FindingRule
from planacity.planning.work_items import resolve_container_effort

DAY = date(2026, 10, 5)


def legacy_plan() -> ProgramPlan:
    alex = Person(name="Alex")
    sam = Person(name="Sam")
    task = WorkItem(
        title="Integration",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(10),
        start=DAY,
        end=DAY,
    )
    support = WorkItem(
        title="Support",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(2),
        start=DAY,
        end=DAY,
    )
    calendar = WorkCalendar(
        name="Engineering",
        weekday_hours=tuple(Decimal(value) for value in ("8", "0", "0", "0", "0", "0", "0")),
    )
    return ProgramPlan(
        name="Legacy consolidation",
        horizon=PlanningHorizon(DAY, DAY),
        people=(alex, sam),
        work_items=(task, support),
        work_calendars=(calendar,),
        person_calendars=(
            PersonCalendar(person_id=alex.id, calendar_id=calendar.id),
            PersonCalendar(person_id=sam.id, calendar_id=calendar.id),
        ),
        allocations=(
            Allocation(work_item_id=task.id, person_id=alex.id, hours=Decimal(6)),
            Allocation(work_item_id=task.id, person_id=sam.id, hours=Decimal(4)),
            Allocation(work_item_id=support.id, person_id=alex.id, hours=Decimal(2)),
        ),
    )


def test_preview_preserves_survivor_sums_hours_and_reports_whole_plan_loads() -> None:
    plan = legacy_plan()
    survivor, removed, unrelated = plan.allocations
    before = dumps(plan)

    preview = preview_assignment_consolidation(plan, survivor.work_item_id, survivor.id)

    assert preview.surviving_allocation_id == survivor.id
    assert preview.removed_allocation_ids == (removed.id,)
    assert preview.total_hours == 10
    assert preview.candidate.allocations == (
        replace(survivor, hours=Decimal(10)),
        unrelated,
    )
    assert [(change.before_hours, change.after_hours) for change in preview.person_loads] == [
        (Decimal(8), Decimal(12)),
        (Decimal(4), Decimal(0)),
    ]
    assert [change.delta_hours for change in preview.person_loads] == [
        Decimal(4),
        Decimal(-4),
    ]
    assert FindingRule.UNRESOLVED_ASSIGNMENT in {
        finding.rule_key for finding in preview.before_findings
    }
    assert FindingRule.UNRESOLVED_ASSIGNMENT not in {
        finding.rule_key for finding in preview.after_findings
    }
    assert FindingRule.OVERLOAD in {finding.rule_key for finding in preview.after_findings}
    assert dumps(plan) == before
    assert preview.candidate.work_item(survivor.work_item_id).assignee_id == survivor.person_id
    assert preview.candidate.work_items[1:] == plan.work_items[1:]
    assert preview.candidate.imports is plan.imports


def test_preview_uses_exact_decimal_sum_with_zero_hours_and_unknown_estimate() -> None:
    plan = legacy_plan()
    task = replace(plan.work_items[0], estimate_hours=None, start=None, end=None)
    first = replace(
        plan.allocations[0],
        hours=Decimal("1.00000000000000000000000000001"),
    )
    second = replace(plan.allocations[1], hours=Decimal("0.00000000000000000000000000002"))
    robin = Person(name="Robin")
    zero = Allocation(work_item_id=task.id, person_id=robin.id, hours=Decimal(0))
    plan = replace(
        plan,
        people=(*plan.people, robin),
        person_calendars=(
            *plan.person_calendars,
            PersonCalendar(person_id=robin.id, calendar_id=plan.work_calendars[0].id),
        ),
        work_items=(task, plan.work_items[1]),
        allocations=(first, second, zero),
    )

    with localcontext() as context:
        context.prec = 3
        preview = preview_assignment_consolidation(plan, task.id, first.id)
        assert context.prec == 3
        assert preview.total_hours == Decimal("1.00000000000000000000000000003")
        assert preview.candidate.allocations[0].hours == preview.total_hours
        assert zero.id in preview.removed_allocation_ids


def test_preview_requires_a_legacy_leaf_and_one_of_its_existing_allocations() -> None:
    plan = legacy_plan()
    task, support = plan.work_items

    with pytest.raises(ValueError, match="does not have multiple assignments"):
        preview_assignment_consolidation(plan, support.id, plan.allocations[2].id)
    with pytest.raises(ValueError, match="existing allocations"):
        preview_assignment_consolidation(plan, task.id, uuid4())

    parent = WorkItem(title="Program", kind=WorkItemType.EPIC)
    child = replace(task, parent_id=parent.id)
    container_plan = replace(plan, work_items=(parent, child, support))
    with pytest.raises(ValueError, match="container"):
        preview_assignment_consolidation(container_plan, parent.id, plan.allocations[0].id)


def test_transferred_legacy_parent_effort_can_be_previewed_without_losing_ids() -> None:
    plan = legacy_plan()
    parent = WorkItem(title="Program", kind=WorkItemType.EPIC, estimate_hours=Decimal(10))
    child = replace(plan.work_items[1], parent_id=parent.id)
    entries = tuple(
        replace(allocation, work_item_id=parent.id) for allocation in plan.allocations[:2]
    )
    legacy = replace(plan, work_items=(parent, child), allocations=entries)
    transferred = resolve_container_effort(legacy, parent.id, "Program coordination")
    leaf = transferred.work_items[-1]

    preview = preview_assignment_consolidation(transferred, leaf.id, entries[1].id)

    assert preview.surviving_allocation_id == entries[1].id
    assert preview.removed_allocation_ids == (entries[0].id,)
    assert preview.candidate.allocations[0].id == entries[1].id
    assert preview.candidate.allocations[0].hours == 10
    assert preview.candidate.work_item(leaf.id).assignee_id == entries[1].person_id
    assert assignment_policy_conflicts(preview.candidate) == ()
    assert loads(dumps(preview.candidate)) == preview.candidate
