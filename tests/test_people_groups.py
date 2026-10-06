"""People WorkGroup associations remain derived and additive."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from fractions import Fraction

from planacity.domain import (
    Allocation,
    Person,
    PersonCalendar,
    PlanningHorizon,
    ProgramPlan,
    WorkCalendar,
    WorkGroup,
    WorkItem,
    WorkItemType,
)
from planacity.planning.capacity_breakdown import calculate_capacity_breakdown
from planacity.planning.people_groups import (
    AMBIGUOUS_KEY,
    NO_ASSIGNED_WORK_KEY,
    UNGROUPED_KEY,
    calculate_people_groups,
)

MONDAY = date(2026, 10, 5)
WEEK = PlanningHorizon(MONDAY, date(2026, 10, 11))


def plan_with_people_groups() -> ProgramPlan:
    first, second, idle = (Person(name=name) for name in ("Alex", "Alex", "Robin"))
    calendar = WorkCalendar(
        name="Engineering",
        weekday_hours=tuple(Decimal(value) for value in ("8", "8", "8", "8", "8", "0", "0")),
    )
    epic = WorkItem(title="Platform", kind=WorkItemType.EPIC)
    alpha = WorkGroup(name="Alpha", epic_ids=(epic.id,))
    beta = WorkGroup(name="Beta", epic_ids=(epic.id,))
    gamma = WorkGroup(name="Gamma")
    unused = WorkGroup(name="Unused")
    shared = WorkItem(
        title="Shared integration",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        estimate_hours=Decimal(11),
        start=MONDAY,
        end=MONDAY,
    )
    override = WorkItem(
        title="Firmware override",
        kind=WorkItemType.TASK,
        parent_id=epic.id,
        primary_group_id=gamma.id,
        estimate_hours=Decimal(6),
        start=date(2026, 10, 6),
        end=date(2026, 10, 6),
    )
    undated = WorkItem(
        title="Undated follow-up",
        kind=WorkItemType.TASK,
        estimate_hours=Decimal(4),
    )
    zero = WorkItem(
        title="Zero placeholder",
        kind=WorkItemType.TASK,
        primary_group_id=unused.id,
        estimate_hours=Decimal(1),
        start=MONDAY,
        end=MONDAY,
    )
    return ProgramPlan(
        name="People groups",
        horizon=WEEK,
        people=(first, second, idle),
        work_items=(epic, shared, override, undated, zero),
        work_groups=(alpha, beta, gamma, unused),
        work_calendars=(calendar,),
        person_calendars=tuple(
            PersonCalendar(person_id=person.id, calendar_id=calendar.id)
            for person in (first, second, idle)
        ),
        allocations=(
            Allocation(work_item_id=shared.id, person_id=first.id, hours=Decimal(8)),
            Allocation(work_item_id=shared.id, person_id=second.id, hours=Decimal(3)),
            Allocation(work_item_id=override.id, person_id=first.id, hours=Decimal(6)),
            Allocation(work_item_id=undated.id, person_id=first.id, hours=Decimal(4)),
            Allocation(work_item_id=zero.id, person_id=idle.id, hours=Decimal(0)),
        ),
    )


def test_associations_use_positive_allocations_and_all_effective_context() -> None:
    plan = plan_with_people_groups()
    result = calculate_people_groups(plan, calculate_capacity_breakdown(plan, WEEK))
    first = result.person(plan.people[0].id)
    second = result.person(plan.people[1].id)
    idle = result.person(plan.people[2].id)

    assert tuple(value.label for value in first.associations) == (
        "Alpha",
        "Ambiguous group",
        "Beta",
        "Gamma",
        "Ungrouped",
    )
    assert tuple(value.label for value in second.associations) == (
        "Alpha",
        "Ambiguous group",
        "Beta",
    )
    assert tuple(value.key for value in idle.associations) == (NO_ASSIGNED_WORK_KEY,)
    assert tuple(value.person_id for value in result.people) == (
        plan.people[1].id,
        plan.people[0].id,
        plan.people[2].id,
    )
    assert first.matches(f"group:{plan.work_groups[0].id}")
    assert first.matches(UNGROUPED_KEY)
    assert second.matches(AMBIGUOUS_KEY)
    assert not idle.matches(f"group:{plan.work_groups[3].id}")
    assert "Unused" not in tuple(value.label for value in result.filters)


def test_topic_hours_are_additive_and_keep_range_demand_separate() -> None:
    plan = plan_with_people_groups()
    result = calculate_people_groups(plan, calculate_capacity_breakdown(plan, WEEK))
    person = result.person(plan.people[0].id)

    assert tuple(topic.label for topic in person.topics) == (
        "Ambiguous group",
        "Gamma",
        "Ungrouped",
    )
    ambiguous, gamma, ungrouped = person.topics
    assert (ambiguous.whole_plan_hours, ambiguous.scheduled_hours, ambiguous.unplaced_hours) == (
        Fraction(8),
        Fraction(8),
        Fraction(),
    )
    assert (gamma.whole_plan_hours, gamma.scheduled_hours, gamma.unplaced_hours) == (
        Fraction(6),
        Fraction(6),
        Fraction(),
    )
    assert (
        ungrouped.whole_plan_hours,
        ungrouped.scheduled_hours,
        ungrouped.unplaced_hours,
    ) == (Fraction(4), Fraction(), Fraction(4))
    assert tuple(value.label for value in gamma.context_groups) == (
        "Alpha",
        "Beta",
        "Gamma",
    )
    assert sum((topic.whole_plan_hours for topic in person.topics), Fraction()) == 18
    assert sum((topic.scheduled_hours for topic in person.topics), Fraction()) == 14
    assert sum((topic.unplaced_hours for topic in person.topics), Fraction()) == 4


def test_whole_plan_associations_survive_a_range_with_no_scheduled_work() -> None:
    plan = plan_with_people_groups()
    wednesday = PlanningHorizon(date(2026, 10, 7), date(2026, 10, 7))

    result = calculate_people_groups(plan, calculate_capacity_breakdown(plan, wednesday)).person(
        plan.people[0].id
    )

    assert sum((topic.whole_plan_hours for topic in result.topics), Fraction()) == 18
    assert sum((topic.scheduled_hours for topic in result.topics), Fraction()) == 0
    assert sum((topic.unplaced_hours for topic in result.topics), Fraction()) == 4
    assert tuple(value.label for value in result.associations) == (
        "Alpha",
        "Ambiguous group",
        "Beta",
        "Gamma",
        "Ungrouped",
    )


def test_removed_groups_leave_no_stale_filter_or_association_identity() -> None:
    plan = plan_with_people_groups()
    removed = {group.id for group in plan.work_groups}
    changed = replace(
        plan,
        work_groups=(),
        work_items=tuple(replace(item, primary_group_id=None) for item in plan.work_items),
    )

    result = calculate_people_groups(changed, calculate_capacity_breakdown(changed, WEEK))

    assert all(
        association.group_id not in removed
        for person in result.people
        for association in person.associations
    )
    assert tuple(value.key for value in result.filters) == (
        UNGROUPED_KEY,
        NO_ASSIGNED_WORK_KEY,
    )
