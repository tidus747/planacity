"""Reusable advisory findings over effort and shared dated capacity."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import uuid4

from planacity.domain import (
    Allocation,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    ReservationRule,
    WorkCalendar,
    WorkItem,
    WorkItemType,
)
from planacity.planning.findings import (
    FindingRule,
    FindingSeverity,
    findings_for_work,
    planning_findings,
)

MONDAY = date(2026, 10, 5)
FRIDAY = date(2026, 10, 9)
TWO_WEEKS = PlanningHorizon(MONDAY, date(2026, 10, 16))


def calendar(*hours: str) -> WorkCalendar:
    values = hours or ("8", "8", "8", "8", "8", "0", "0")
    return WorkCalendar(name="Engineering", weekday_hours=tuple(Decimal(v) for v in values))


def configured_plan(
    items: tuple[WorkItem, ...],
    allocations: tuple[Allocation, ...] = (),
    *,
    people: tuple[Person, ...] | None = None,
    horizon: PlanningHorizon = TWO_WEEKS,
) -> ProgramPlan:
    roster = people or (Person(name="Alex"),)
    work_calendar = calendar()
    return ProgramPlan(
        name="Finding example",
        horizon=horizon,
        work_items=items,
        people=roster,
        work_calendars=(work_calendar,),
        person_calendars=tuple(
            PersonCalendar(person_id=person.id, calendar_id=work_calendar.id) for person in roster
        ),
        allocations=allocations,
    )


def test_legacy_100_hour_split_keeps_exact_demand_and_adds_resolution_finding():
    alex, sam = Person(name="Alex"), Person(name="Sam")
    task = WorkItem(
        title="Integration",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(100),
        start=TWO_WEEKS.start,
        end=TWO_WEEKS.end,
    )
    alex_share = Allocation(work_item_id=task.id, person_id=alex.id, hours=Decimal(60))
    sam_share = Allocation(work_item_id=task.id, person_id=sam.id, hours=Decimal(40))
    plan = configured_plan((task,), (alex_share, sam_share), people=(alex, sam))

    findings = planning_findings(plan)

    rules = {finding.rule_key for finding in findings}
    assert FindingRule.UNRESOLVED_ASSIGNMENT in rules
    assert not {
        FindingRule.ALLOCATION_MISMATCH,
        FindingRule.UNALLOCATED_WORK,
        FindingRule.OVERLOAD,
    }.intersection(rules)
    unresolved = next(
        finding for finding in findings if finding.rule_key == FindingRule.UNRESOLVED_ASSIGNMENT
    )
    assert unresolved.person_ids == tuple(sorted((alex.id, sam.id), key=str))
    assert unresolved.source_ids == tuple(sorted((alex_share.id, sam_share.id), key=str))
    assert planning_findings(plan) == findings


def test_missing_inputs_and_unallocated_work_have_stable_actionable_fields():
    unknown = WorkItem(title="Unknown", kind=WorkItemType.TASK)
    unallocated = WorkItem(
        title="Ready",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(5),
        start=MONDAY,
        end=MONDAY,
    )
    person = Person(name="Alex")
    plan = ProgramPlan(
        name="Incomplete",
        horizon=TWO_WEEKS,
        work_items=(unknown, unallocated),
        people=(person,),
    )

    findings = planning_findings(plan)
    by_rule = {finding.rule_key: finding for finding in findings}

    assert by_rule[FindingRule.MISSING_WORK_DATES].work_item_ids == (unknown.id,)
    assert by_rule[FindingRule.MISSING_ESTIMATE].work_item_ids == (unknown.id,)
    assert by_rule[FindingRule.UNALLOCATED_WORK].work_item_ids == (unallocated.id,)
    missing_calendar = by_rule[FindingRule.MISSING_CALENDAR]
    assert missing_calendar.person_ids == (person.id,)
    assert missing_calendar.date_range == plan.horizon
    assert missing_calendar.severity == FindingSeverity.WARNING
    assert missing_calendar.explanation and missing_calendar.suggested_action


def test_concurrent_work_creates_one_person_overload_relevant_to_both_tasks():
    person = Person(name="Alex")
    first = WorkItem(
        title="First",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(8),
        start=MONDAY,
        end=MONDAY,
    )
    second = replace(first, id=uuid4(), title="Second")
    allocations = (
        Allocation(work_item_id=first.id, person_id=person.id, hours=Decimal(8)),
        Allocation(work_item_id=second.id, person_id=person.id, hours=Decimal(8)),
    )
    plan = configured_plan(
        (first, second),
        allocations,
        people=(person,),
        horizon=PlanningHorizon(MONDAY, MONDAY),
    )

    overload = next(
        finding for finding in planning_findings(plan) if finding.rule_key == FindingRule.OVERLOAD
    )

    assert overload.severity == FindingSeverity.ERROR
    assert overload.work_item_ids == tuple(sorted((first.id, second.id), key=str))
    assert overload.source_ids == tuple(sorted((entry.id for entry in allocations), key=str))
    assert overload.date_range == plan.horizon
    assert "overloaded by 8 h" in overload.explanation
    assert "All concurrent work" in overload.explanation
    assert overload in findings_for_work(plan, planning_findings(plan), first.id)
    assert overload in findings_for_work(plan, planning_findings(plan), second.id)


def test_mismatch_hierarchy_and_unplaced_capacity_remain_separate_rules():
    person = Person(name="Alex")
    parent = WorkItem(title="Program", kind=WorkItemType.EPIC)
    child = WorkItem(
        title="Build",
        kind=WorkItemType.TASK,
        parent_id=parent.id,
        estimate_hours=Decimal(10),
        start=MONDAY,
        end=FRIDAY,
    )
    entries = (
        Allocation(work_item_id=parent.id, person_id=person.id, hours=Decimal(2)),
        Allocation(work_item_id=child.id, person_id=person.id, hours=Decimal(3)),
    )
    zero_calendar = calendar("0", "0", "0", "0", "0", "0", "0")
    plan = configured_plan((parent, child), entries, people=(person,))
    plan = replace(
        plan,
        work_calendars=(zero_calendar,),
        person_calendars=(PersonCalendar(person_id=person.id, calendar_id=zero_calendar.id),),
    )

    findings = planning_findings(plan)
    rules = {finding.rule_key for finding in findings}

    assert FindingRule.ALLOCATION_MISMATCH in rules
    assert FindingRule.HIERARCHY_EFFORT in rules
    assert FindingRule.NO_PLANNING_CAPACITY in rules
    hierarchy = next(f for f in findings if f.rule_key == FindingRule.HIERARCHY_EFFORT)
    assert hierarchy.title == "Mixed hierarchy effort"


def test_unresolved_reservation_is_related_to_the_persons_allocated_work():
    person = Person(name="Alex")
    task = WorkItem(
        title="Task",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(2),
        start=MONDAY,
        end=MONDAY,
    )
    allocation = Allocation(work_item_id=task.id, person_id=person.id, hours=Decimal(2))
    empty = calendar("0", "0", "0", "0", "0", "0", "0")
    rule = ReservationRule(
        name="Support",
        person_ids=(person.id,),
        hours_per_person=Decimal(3),
        anchor=MONDAY,
        interval_weeks=1,
        effective=PlanningHorizon(MONDAY, MONDAY),
    )
    plan = ProgramPlan(
        name="Reservations",
        horizon=PlanningHorizon(MONDAY, MONDAY),
        work_items=(task,),
        people=(person,),
        work_calendars=(empty,),
        person_calendars=(PersonCalendar(person_id=person.id, calendar_id=empty.id),),
        reservation_rules=(rule,),
        allocations=(allocation,),
    )

    finding = next(
        value
        for value in planning_findings(plan)
        if value.rule_key == FindingRule.UNRESOLVED_RESERVATION
    )

    assert finding.work_item_ids == (task.id,)
    assert finding.person_ids == (person.id,)
    assert finding.source_ids == (rule.id,)
