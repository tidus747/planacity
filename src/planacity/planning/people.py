"""Roster operations preserve identities, order, and the original plan snapshot."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import Person, ProgramPlan


def add_person(plan: ProgramPlan, person: Person) -> ProgramPlan:
    return replace(plan, people=(*plan.people, person))


def rename_person(plan: ProgramPlan, person_id: UUID, name: str) -> ProgramPlan:
    updated = replace(plan.person(person_id), name=name)
    return replace(
        plan, people=tuple(updated if person.id == person_id else person for person in plan.people)
    )


def remove_person(
    plan: ProgramPlan,
    person_id: UUID,
    *,
    remove_availability: bool = False,
    remove_reservations: bool = False,
    remove_allocations: bool = False,
) -> ProgramPlan:
    """Remove a person; availability, reservations and allocations need consent.

    Shared reservations keep their IDs and other people. Rules with no remaining
    people are removed rather than retained as invalid, empty rules.
    """
    plan.person(person_id)
    if type(remove_allocations) is not bool:
        raise ValueError("Confirming allocation removal requires an explicit boolean.")
    if not remove_allocations and any(a.person_id == person_id for a in plan.allocations):
        raise ValueError("Confirm removing this person's work allocations first.")
    if not remove_availability and any(e.person_id == person_id for e in plan.availability_events):
        raise ValueError("Confirm removing this person's availability entries first.")
    if not remove_reservations and any(person_id in r.person_ids for r in plan.reservation_rules):
        raise ValueError("Confirm removing this person from their reservation rules first.")
    return replace(
        plan,
        people=tuple(person for person in plan.people if person.id != person_id),
        allocations=tuple(a for a in plan.allocations if a.person_id != person_id),
        person_calendars=tuple(
            value for value in plan.person_calendars if value.person_id != person_id
        ),
        availability_events=tuple(e for e in plan.availability_events if e.person_id != person_id),
        reservation_rules=tuple(
            replace(rule, person_ids=tuple(p for p in rule.person_ids if p != person_id))
            if person_id in rule.person_ids
            else rule
            for rule in plan.reservation_rules
            if rule.person_ids != (person_id,)
        ),
    )
