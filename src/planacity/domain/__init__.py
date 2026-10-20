"""Canonical planning entities; independent of Qt and external tools."""

from planacity.domain.allocation import Allocation
from planacity.domain.availability import AvailabilityEvent
from planacity.domain.calendar_event import CalendarEvent, CalendarEventKind
from planacity.domain.models import (
    Person,
    PlanningHorizon,
    ProgramPlan,
    Relationship,
    RelationshipType,
    WorkGroup,
    WorkItem,
    WorkItemType,
    WorkPriority,
)
from planacity.domain.reservation_coverage import (
    ReservationCoverage,
    validate_reservation_coverage_references,
)
from planacity.domain.reservations import ReservationRule
from planacity.domain.sprint import Sprint, SprintAssignment
from planacity.domain.work_calendar import PersonCalendar, WorkCalendar

__all__ = [
    "Allocation",
    "ReservationRule",
    "ReservationCoverage",
    "Sprint",
    "SprintAssignment",
    "AvailabilityEvent",
    "CalendarEvent",
    "CalendarEventKind",
    "Person",
    "PersonCalendar",
    "PlanningHorizon",
    "ProgramPlan",
    "Relationship",
    "RelationshipType",
    "WorkGroup",
    "WorkCalendar",
    "WorkItem",
    "WorkPriority",
    "WorkItemType",
    "validate_reservation_coverage_references",
]
