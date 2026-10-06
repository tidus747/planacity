"""Read-only Overview projections over canonical capacity and work context."""

from dataclasses import dataclass
from fractions import Fraction
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.capacity import CapacityGap, CapacityGapKind
from planacity.planning.capacity_breakdown import (
    CapacityLoadState,
    calculate_capacity_breakdown,
)
from planacity.planning.work_context import TopicState, resolve_topic


@dataclass(frozen=True)
class OverviewPerson:
    """One roster identity with exact horizon capacity values."""

    person_id: UUID
    name: str
    planning_hours: Fraction | None
    scheduled_hours: Fraction | None
    remaining_hours: Fraction | None
    unplaced_hours: Fraction
    state: CapacityLoadState
    gap_messages: tuple[str, ...]


@dataclass(frozen=True)
class OverviewTopic:
    """One additive reporting topic or explicit exception bucket."""

    key: str
    group_id: UUID | None
    label: str
    state: TopicState
    scheduled_hours: Fraction
    unplaced_hours: Fraction
    estimated_leaf_hours: Fraction
    leaf_count: int
    missing_estimate_count: int


@dataclass(frozen=True)
class OverviewReservation:
    """Placed reservation hours for one stable rule identity."""

    rule_id: UUID
    name: str
    hours: Fraction


@dataclass(frozen=True)
class OverviewCapacity:
    """Known-roster subtotals with unresolved demand kept separate."""

    known_people: int
    total_people: int
    nominal_hours: Fraction | None
    unavailable_hours: Fraction | None
    available_hours: Fraction | None
    reservations: tuple[OverviewReservation, ...]
    reserved_hours: Fraction | None
    planning_hours: Fraction | None
    scheduled_hours: Fraction | None
    remaining_hours: Fraction | None
    unplaced_hours: Fraction

    @property
    def partial(self) -> bool:
        return self.known_people != self.total_people


@dataclass(frozen=True)
class OverviewAnalysis:
    """All compact Overview modes calculated from one immutable plan snapshot."""

    period: PlanningHorizon
    people: tuple[OverviewPerson, ...]
    topics: tuple[OverviewTopic, ...]
    capacity: OverviewCapacity
    coverage: tuple[str, ...]


@dataclass
class _TopicTotals:
    key: str
    group_id: UUID | None
    label: str
    state: TopicState
    scheduled_hours: Fraction = Fraction()
    unplaced_hours: Fraction = Fraction()
    estimated_leaf_hours: Fraction = Fraction()
    leaf_count: int = 0
    missing_estimate_count: int = 0


def _topic(plan: ProgramPlan, work_item_id: UUID) -> tuple[str, UUID | None, str, TopicState]:
    resolution = resolve_topic(plan, work_item_id)
    if resolution.group_id is not None:
        group = plan.work_group(resolution.group_id)
        return f"group:{group.id}", group.id, group.name, TopicState.RESOLVED
    if resolution.state == TopicState.AMBIGUOUS:
        return "ambiguous", None, "Ambiguous group", TopicState.AMBIGUOUS
    return "ungrouped", None, "Ungrouped", TopicState.UNGROUPED


def _totals_for(
    totals: dict[str, _TopicTotals], plan: ProgramPlan, work_item_id: UUID
) -> _TopicTotals:
    key, group_id, name, state = _topic(plan, work_item_id)
    if key not in totals:
        totals[key] = _TopicTotals(key, group_id, name, state)
    return totals[key]


def _ordered_topics(
    plan: ProgramPlan, totals: dict[str, _TopicTotals]
) -> tuple[OverviewTopic, ...]:
    order = {f"group:{group.id}": index for index, group in enumerate(plan.work_groups)}

    def sort_key(value: _TopicTotals) -> tuple[int, int, str]:
        if value.group_id is not None:
            return (0, order[value.key], value.label.casefold())
        return (1, 0 if value.state == TopicState.UNGROUPED else 1, value.label.casefold())

    return tuple(
        OverviewTopic(
            value.key,
            value.group_id,
            value.label,
            value.state,
            value.scheduled_hours,
            value.unplaced_hours,
            value.estimated_leaf_hours,
            value.leaf_count,
            value.missing_estimate_count,
        )
        for value in sorted(totals.values(), key=sort_key)
    )


def _unplaced_work_gaps(gaps: tuple[CapacityGap, ...]) -> tuple[CapacityGap, ...]:
    result = []
    seen: set[UUID] = set()
    for gap in gaps:
        if gap.work_item_id is None or gap.hours is None:
            continue
        if gap.source_id is not None:
            if gap.source_id in seen:
                continue
            seen.add(gap.source_id)
        result.append(gap)
    return tuple(result)


def _optional_total(values: tuple[Fraction | None, ...]) -> Fraction | None:
    known = tuple(value for value in values if value is not None)
    if not known and values:
        return None
    return sum(known, Fraction())


def _known_total(people: tuple[OverviewPerson, ...], attribute: str) -> Fraction | None:
    return _optional_total(tuple(getattr(person, attribute) for person in people))


def _coverage(
    plan: ProgramPlan,
    people: tuple[OverviewPerson, ...],
    topics: tuple[OverviewTopic, ...],
    gaps: tuple[CapacityGap, ...],
    unplaced_hours: Fraction,
) -> tuple[str, ...]:
    messages = [
        "Includes work calendars, recorded availability, recurring reservations, and work "
        "allocations. Program events are not yet included."
    ]
    known = sum(person.planning_hours is not None for person in people)
    if not people:
        messages.append("No people are in the roster; capacity totals are empty.")
    elif known != len(people):
        messages.append(
            f"{known} of {len(people)} people have known capacity. Displayed capacity sums are "
            "known-person subtotals, not complete team totals."
        )
    else:
        messages.append(f"Capacity is known for all {len(people)} roster people.")

    allocated_people = {
        allocation.person_id for allocation in plan.allocations if allocation.hours > 0
    }
    messages.append(
        f"{len(allocated_people)} of {len(plan.people)} people have positive planned work "
        "allocations in the complete plan."
    )
    if unplaced_hours:
        messages.append(
            f"{unplaced_hours} h of work or reservation demand could not be placed; positive "
            "remaining capacity is provisional."
        )

    missing_estimates = sum(topic.missing_estimate_count for topic in topics)
    if missing_estimates:
        messages.append(
            f"{missing_estimates} leaf work item(s) have no estimate and are excluded from the "
            "known estimated-effort subtotal."
        )
    missing_dates = sum(
        1
        for item in plan.work_items
        if not plan.children(item.id) and (item.start is None or item.end is None)
    )
    if missing_dates:
        messages.append(
            f"{missing_dates} leaf work item(s) have incomplete dates; their allocations cannot "
            "be treated as scheduled horizon work."
        )
    positive_allocated_work = {
        allocation.work_item_id for allocation in plan.allocations if allocation.hours > 0
    }
    unallocated = sum(
        1
        for item in plan.work_items
        if not plan.children(item.id)
        and item.estimate_hours is not None
        and item.estimate_hours > 0
        and item.id not in positive_allocated_work
    )
    if unallocated:
        messages.append(
            f"{unallocated} estimated leaf work item(s) have no positive allocation; free "
            "capacity does not prove that all required work fits."
        )
    outside = sum(
        1
        for item in plan.work_items
        if not plan.children(item.id)
        and item.start is not None
        and item.end is not None
        and (item.end < plan.horizon.start or item.start > plan.horizon.end)
    )
    if outside:
        messages.append(
            f"{outside} dated leaf work item(s) are outside the plan horizon and contribute no "
            "scheduled hours to this analysis period."
        )
    query_messages = tuple(
        dict.fromkeys(gap.message for gap in gaps if gap.kind == CapacityGapKind.QUERY_LIMIT)
    )
    messages.extend(query_messages)
    return tuple(messages)


def calculate_overview_analysis(plan: ProgramPlan) -> OverviewAnalysis:
    """Project all Overview modes for the inclusive plan horizon without mutation."""
    breakdown = calculate_capacity_breakdown(plan, plan.horizon)
    people = tuple(
        OverviewPerson(
            person.person_id,
            plan.person(person.person_id).name,
            person.planning_hours,
            person.allocated_hours,
            person.remaining_hours,
            person.unplaced_hours,
            person.state,
            tuple(dict.fromkeys(gap.message for gap in person.gaps)),
        )
        for person in breakdown.people
    )

    topic_totals: dict[str, _TopicTotals] = {}
    for item in plan.work_items:
        if plan.children(item.id):
            continue
        topic = _totals_for(topic_totals, plan, item.id)
        topic.leaf_count += 1
        if item.estimate_hours is None:
            topic.missing_estimate_count += 1
        else:
            topic.estimated_leaf_hours += Fraction(item.estimate_hours)

    for person in breakdown.capacity.people:
        for day in person.days:
            for entry in day.allocations:
                _totals_for(topic_totals, plan, entry.work_item_id).scheduled_hours += entry.hours

    for gap in _unplaced_work_gaps(breakdown.capacity.all_gaps):
        assert gap.work_item_id is not None and gap.hours is not None
        _totals_for(topic_totals, plan, gap.work_item_id).unplaced_hours += gap.hours

    topics = _ordered_topics(plan, topic_totals)
    reservation_totals: dict[UUID, Fraction] = {
        rule.id: Fraction() for rule in plan.reservation_rules
    }
    for person in breakdown.capacity.people:
        for reservation_entry in person.reservation_breakdown:
            reservation_totals[reservation_entry.rule_id] += reservation_entry.hours
    reservations = tuple(
        OverviewReservation(rule.id, rule.name, reservation_totals[rule.id])
        for rule in plan.reservation_rules
    )
    known_people = sum(person.planning_hours is not None for person in people)
    unplaced = sum((person.unplaced_hours for person in people), Fraction())
    capacity = OverviewCapacity(
        known_people,
        len(people),
        _optional_total(tuple(person.nominal_hours for person in breakdown.people)),
        _optional_total(tuple(person.unavailable_hours for person in breakdown.people)),
        _optional_total(tuple(person.available_hours for person in breakdown.people)),
        reservations,
        _optional_total(tuple(person.reserved_hours for person in breakdown.people)),
        _known_total(people, "planning_hours"),
        _known_total(people, "scheduled_hours"),
        _known_total(people, "remaining_hours"),
        unplaced,
    )
    return OverviewAnalysis(
        plan.horizon,
        people,
        topics,
        capacity,
        _coverage(plan, people, topics, breakdown.capacity.all_gaps, unplaced),
    )
