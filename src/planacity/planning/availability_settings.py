"""Immutable availability lifecycle and roster capacity queries."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import AvailabilityEvent, ProgramPlan
from planacity.planning.availability import AvailableCapacity, availability_capacity


def availability_event(plan: ProgramPlan, event_id: UUID) -> AvailabilityEvent:
    for event in plan.availability_events:
        if event.id == event_id:
            return event
    raise ValueError("Availability entry does not exist in this plan.")


def add_availability(plan: ProgramPlan, event: AvailabilityEvent) -> ProgramPlan:
    return replace(plan, availability_events=(*plan.availability_events, event))


def update_availability(plan: ProgramPlan, event: AvailabilityEvent) -> ProgramPlan:
    previous = availability_event(plan, event.id)
    if event.person_id != previous.person_id:
        raise ValueError("An availability edit cannot change its person.")
    return replace(
        plan,
        availability_events=tuple(
            event if current.id == event.id else current for current in plan.availability_events
        ),
    )


def remove_availability(plan: ProgramPlan, event_id: UUID) -> ProgramPlan:
    availability_event(plan, event_id)
    return replace(
        plan,
        availability_events=tuple(
            event for event in plan.availability_events if event.id != event_id
        ),
    )


def person_availability(plan: ProgramPlan, person_id: UUID) -> AvailableCapacity | None:
    """Unknown without a calendar; entries remain stored until one is assigned."""
    plan.person(person_id)
    assignment = next((a for a in plan.person_calendars if a.person_id == person_id), None)
    if assignment is None:
        return None
    return availability_capacity(
        plan.work_calendar(assignment.calendar_id),
        plan.horizon,
        person_id,
        tuple(e for e in plan.availability_events if e.person_id == person_id),
    )
