"""Calendar lifecycle and explicit person assignments over immutable snapshots."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import PersonCalendar, ProgramPlan, WorkCalendar


def add_calendar(plan: ProgramPlan, calendar: WorkCalendar) -> ProgramPlan:
    return replace(plan, work_calendars=(*plan.work_calendars, calendar))


def update_calendar(plan: ProgramPlan, calendar: WorkCalendar) -> ProgramPlan:
    plan.work_calendar(calendar.id)
    return replace(
        plan,
        work_calendars=tuple(
            calendar if current.id == calendar.id else current for current in plan.work_calendars
        ),
    )


def assign_calendar(plan: ProgramPlan, person_id: UUID, calendar_id: UUID | None) -> ProgramPlan:
    plan.person(person_id)
    remaining = tuple(value for value in plan.person_calendars if value.person_id != person_id)
    if calendar_id is not None:
        plan.work_calendar(calendar_id)
        remaining += (PersonCalendar(person_id=person_id, calendar_id=calendar_id),)
    # Canonical roster order keeps repeated assignment deterministic.
    by_person = {value.person_id: value for value in remaining}
    return replace(
        plan, person_calendars=tuple(by_person[p.id] for p in plan.people if p.id in by_person)
    )


def remove_calendar(plan: ProgramPlan, calendar_id: UUID, *, unassign: bool = False) -> ProgramPlan:
    plan.work_calendar(calendar_id)
    referenced = [value for value in plan.person_calendars if value.calendar_id == calendar_id]
    if referenced and not unassign:
        raise ValueError(
            "This calendar is assigned to people. Confirm clearing those assignments first."
        )
    return replace(
        plan,
        work_calendars=tuple(value for value in plan.work_calendars if value.id != calendar_id),
        person_calendars=tuple(
            value for value in plan.person_calendars if value.calendar_id != calendar_id
        ),
    )
