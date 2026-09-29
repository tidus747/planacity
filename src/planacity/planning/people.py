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
    plan: ProgramPlan, person_id: UUID, *, remove_availability: bool = False
) -> ProgramPlan:
    """Remove a person and calendar link; availability removal needs explicit consent."""
    plan.person(person_id)
    if not remove_availability and any(e.person_id == person_id for e in plan.availability_events):
        raise ValueError("Confirm removing this person's availability entries first.")
    return replace(
        plan,
        people=tuple(person for person in plan.people if person.id != person_id),
        person_calendars=tuple(
            value for value in plan.person_calendars if value.person_id != person_id
        ),
        availability_events=tuple(e for e in plan.availability_events if e.person_id != person_id),
    )
