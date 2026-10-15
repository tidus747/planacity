"""Immutable lifecycle operations for shared program-calendar events."""

from dataclasses import replace
from uuid import UUID

from planacity.domain import CalendarEvent, ProgramPlan


def calendar_event(plan: ProgramPlan, event_id: UUID) -> CalendarEvent:
    """Return one shared event without exposing tuple-search details to callers."""
    if not isinstance(event_id, UUID):
        raise ValueError("Calendar event ID must be a UUID.")
    try:
        return next(event for event in plan.calendar_events if event.id == event_id)
    except StopIteration as error:
        raise ValueError(f"Calendar event {event_id} does not exist in this plan.") from error


def add_calendar_event(plan: ProgramPlan, event: CalendarEvent) -> ProgramPlan:
    if any(existing.id == event.id for existing in plan.calendar_events):
        raise ValueError("Calendar event IDs must be unique within a plan.")
    return replace(plan, calendar_events=(*plan.calendar_events, event))


def update_calendar_event(plan: ProgramPlan, event: CalendarEvent) -> ProgramPlan:
    if not any(existing.id == event.id for existing in plan.calendar_events):
        raise ValueError(f"Calendar event {event.id} does not exist in this plan.")
    return replace(
        plan,
        calendar_events=tuple(
            event if existing.id == event.id else existing for existing in plan.calendar_events
        ),
    )


def remove_calendar_event(plan: ProgramPlan, event_id: UUID) -> ProgramPlan:
    if not isinstance(event_id, UUID):
        raise ValueError("Calendar event ID must be a UUID.")
    if not any(event.id == event_id for event in plan.calendar_events):
        raise ValueError(f"Calendar event {event_id} does not exist in this plan.")
    return replace(
        plan,
        calendar_events=tuple(event for event in plan.calendar_events if event.id != event_id),
    )
