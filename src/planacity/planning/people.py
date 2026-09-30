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


def remove_person(plan: ProgramPlan, person_id: UUID) -> ProgramPlan:
    """Remove a roster entry and its calendar assignment, preserving source snapshots."""
    plan.person(person_id)
    return replace(
        plan,
        people=tuple(person for person in plan.people if person.id != person_id),
        person_calendars=tuple(
            value for value in plan.person_calendars if value.person_id != person_id
        ),
    )
