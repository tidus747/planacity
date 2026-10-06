"""Derived People associations and additive topic hours."""

from dataclasses import dataclass
from fractions import Fraction
from uuid import UUID

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.capacity_breakdown import CapacityBreakdown
from planacity.planning.work_context import TopicState, effective_group_ids, resolve_topic

UNGROUPED_KEY = "ungrouped"
AMBIGUOUS_KEY = "ambiguous"
NO_ASSIGNED_WORK_KEY = "no_assigned_work"


@dataclass(frozen=True)
class GroupAssociation:
    """One navigation label derived from positively allocated work."""

    key: str
    label: str
    group_id: UUID | None = None


@dataclass(frozen=True)
class TopicWorkItem:
    """One allocated work item and its whole-plan/range hours."""

    work_item_id: UUID
    title: str
    context_groups: tuple[GroupAssociation, ...]
    whole_plan_hours: Fraction
    scheduled_hours: Fraction
    unplaced_hours: Fraction


@dataclass(frozen=True)
class PersonTopic:
    """One additive reporting topic for a person's positive allocations."""

    key: str
    label: str
    state: TopicState
    group_id: UUID | None
    context_groups: tuple[GroupAssociation, ...]
    work_items: tuple[TopicWorkItem, ...]
    whole_plan_hours: Fraction
    scheduled_hours: Fraction
    unplaced_hours: Fraction


@dataclass(frozen=True)
class PersonGroupProjection:
    """Whole-plan associations and selected-range additive hours for one person."""

    person_id: UUID
    person_name: str
    associations: tuple[GroupAssociation, ...]
    topics: tuple[PersonTopic, ...]

    def matches(self, association_key: str) -> bool:
        return not association_key or any(
            association.key == association_key for association in self.associations
        )


@dataclass(frozen=True)
class PeopleGroupProjection:
    """Deterministic People rows for one capacity interval."""

    period: PlanningHorizon
    people: tuple[PersonGroupProjection, ...]
    filters: tuple[GroupAssociation, ...]

    def person(self, person_id: UUID) -> PersonGroupProjection:
        for person in self.people:
            if person.person_id == person_id:
                return person
        raise ValueError(f"Person {person_id} does not exist in this group projection.")


@dataclass
class _WorkTotals:
    work_item_id: UUID
    title: str
    context_groups: tuple[GroupAssociation, ...]
    whole_plan_hours: Fraction = Fraction()
    scheduled_hours: Fraction = Fraction()
    unplaced_hours: Fraction = Fraction()


@dataclass
class _TopicTotals:
    key: str
    label: str
    state: TopicState
    group_id: UUID | None
    work: dict[UUID, _WorkTotals]


def _group_association(plan: ProgramPlan, group_id: UUID) -> GroupAssociation:
    group = plan.work_group(group_id)
    return GroupAssociation(f"group:{group.id}", group.name, group.id)


def _context_groups(plan: ProgramPlan, work_item_id: UUID) -> tuple[GroupAssociation, ...]:
    groups = [
        _group_association(plan, group_id) for group_id in effective_group_ids(plan, work_item_id)
    ]
    resolution = resolve_topic(plan, work_item_id)
    if resolution.state == TopicState.UNGROUPED:
        groups.append(GroupAssociation(UNGROUPED_KEY, "Ungrouped"))
    elif resolution.state == TopicState.AMBIGUOUS:
        groups.append(GroupAssociation(AMBIGUOUS_KEY, "Ambiguous group"))
    return _ordered_associations(groups)


def _topic(plan: ProgramPlan, work_item_id: UUID) -> tuple[str, str, TopicState, UUID | None]:
    resolution = resolve_topic(plan, work_item_id)
    if resolution.group_id is not None:
        group = plan.work_group(resolution.group_id)
        return f"group:{group.id}", group.name, TopicState.RESOLVED, group.id
    if resolution.state == TopicState.AMBIGUOUS:
        return AMBIGUOUS_KEY, "Ambiguous group", TopicState.AMBIGUOUS, None
    return UNGROUPED_KEY, "Ungrouped", TopicState.UNGROUPED, None


def _ordered_associations(
    associations: list[GroupAssociation],
) -> tuple[GroupAssociation, ...]:
    unique = {association.key: association for association in associations}
    return tuple(
        sorted(
            unique.values(),
            key=lambda value: (value.label.casefold(), value.key),
        )
    )


def _scheduled_by_allocation(breakdown: CapacityBreakdown, person_id: UUID) -> dict[UUID, Fraction]:
    person = next(
        (value for value in breakdown.capacity.people if value.person_id == person_id),
        None,
    )
    if person is None:
        return {}
    return {entry.allocation_id: entry.hours for entry in person.allocation_breakdown}


def _unplaced_by_allocation(breakdown: CapacityBreakdown, person_id: UUID) -> dict[UUID, Fraction]:
    person = next(
        (value for value in breakdown.capacity.people if value.person_id == person_id),
        None,
    )
    if person is None:
        return {}
    totals: dict[UUID, Fraction] = {}
    for gap in person.gaps:
        if gap.source_id is None or gap.work_item_id is None or gap.hours is None:
            continue
        totals[gap.source_id] = totals.get(gap.source_id, Fraction()) + gap.hours
    return totals


def _person_projection(
    plan: ProgramPlan,
    breakdown: CapacityBreakdown,
    person_id: UUID,
) -> PersonGroupProjection:
    person = plan.person(person_id)
    scheduled = _scheduled_by_allocation(breakdown, person_id)
    unplaced = _unplaced_by_allocation(breakdown, person_id)
    topics: dict[str, _TopicTotals] = {}
    associations: list[GroupAssociation] = []
    for allocation in plan.allocations:
        if allocation.person_id != person_id or allocation.hours <= 0:
            continue
        item = plan.work_item(allocation.work_item_id)
        context = _context_groups(plan, item.id)
        associations.extend(context)
        key, topic_label, state, group_id = _topic(plan, item.id)
        if key not in topics:
            topics[key] = _TopicTotals(key, topic_label, state, group_id, {})
        topic = topics[key]
        if item.id not in topic.work:
            topic.work[item.id] = _WorkTotals(item.id, item.title, context)
        work = topic.work[item.id]
        work.whole_plan_hours += Fraction(allocation.hours)
        work.scheduled_hours += scheduled.get(allocation.id, Fraction())
        work.unplaced_hours += unplaced.get(allocation.id, Fraction())

    if not associations:
        associations.append(GroupAssociation(NO_ASSIGNED_WORK_KEY, "No assigned work"))
    ordered_associations = _ordered_associations(associations)
    item_order = {item.id: index for index, item in enumerate(plan.work_items)}
    topic_rows = []
    for topic in sorted(topics.values(), key=lambda value: (value.label.casefold(), value.key)):
        work_items = tuple(
            TopicWorkItem(
                work.work_item_id,
                work.title,
                work.context_groups,
                work.whole_plan_hours,
                work.scheduled_hours,
                work.unplaced_hours,
            )
            for work in sorted(
                topic.work.values(), key=lambda value: item_order[value.work_item_id]
            )
        )
        topic_context = _ordered_associations(
            [association for work in work_items for association in work.context_groups]
        )
        topic_rows.append(
            PersonTopic(
                topic.key,
                topic.label,
                topic.state,
                topic.group_id,
                topic_context,
                work_items,
                sum((work.whole_plan_hours for work in work_items), Fraction()),
                sum((work.scheduled_hours for work in work_items), Fraction()),
                sum((work.unplaced_hours for work in work_items), Fraction()),
            )
        )
    return PersonGroupProjection(
        person.id,
        person.name,
        ordered_associations,
        tuple(topic_rows),
    )


def calculate_people_groups(
    plan: ProgramPlan, breakdown: CapacityBreakdown
) -> PeopleGroupProjection:
    """Derive associations without changing People, work, allocations, or capacity."""
    people = tuple(_person_projection(plan, breakdown, person.id) for person in plan.people)
    people = tuple(
        sorted(
            people,
            key=lambda person: (
                person.associations[0].key == NO_ASSIGNED_WORK_KEY,
                tuple(value.label.casefold() for value in person.associations),
                person.person_name.casefold(),
                str(person.person_id),
            ),
        )
    )
    used = {association.key for person in people for association in person.associations}
    group_filters = [
        _group_association(plan, group.id)
        for group in plan.work_groups
        if f"group:{group.id}" in used
    ]
    special_filters = [
        GroupAssociation(key, label)
        for key, label in (
            (UNGROUPED_KEY, "Ungrouped"),
            (AMBIGUOUS_KEY, "Ambiguous group"),
            (NO_ASSIGNED_WORK_KEY, "No assigned work"),
        )
        if key in used
    ]
    return PeopleGroupProjection(
        breakdown.period,
        people,
        (*_ordered_associations(group_filters), *special_filters),
    )
