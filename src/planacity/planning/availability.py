"""Exact availability before program events, reservations, and allocations."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from uuid import UUID

from planacity.domain import CalendarEvent, PlanningHorizon, WorkCalendar
from planacity.domain.availability import AvailabilityEvent
from planacity.planning.work_calendar import nominal_capacity


@dataclass(frozen=True)
class AvailabilityOverlap:
    """Reviewable overlap, including dates that may have no nominal hours."""

    period: PlanningHorizon
    event_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class AvailableCapacity:
    """Calendar hours minus unavailability only, not remaining planning capacity."""

    nominal_hours: Decimal
    unavailable_hours: Decimal
    available_hours: Decimal
    overlaps: tuple[AvailabilityOverlap, ...]


def availability_capacity(
    calendar: WorkCalendar,
    horizon: PlanningHorizon,
    person_id: UUID,
    events: tuple[AvailabilityEvent, ...],
    shared_events: tuple[CalendarEvent, ...] = (),
) -> AvailableCapacity:
    """Apply the strongest unavailable share on each date, without double counting.

    Callers must explicitly select one person's events and calendar. Shared
    calendar events apply to every person. Duplicate IDs within either event
    collection and mismatched personal events are rejected, even outside the horizon.
    Distinct partial-day absences cannot be summed without time-of-day data;
    callers must supply a combined daily share when that is their intent.

    Split only at event boundaries, not at every date. Ordinal end sentinels
    support date.max without constructing an out-of-range date.
    """
    if not isinstance(calendar, WorkCalendar) or not isinstance(horizon, PlanningHorizon):
        raise ValueError("Supply an explicit work calendar and planning horizon.")
    if not isinstance(person_id, UUID):
        raise ValueError("Person ID must be a UUID.")
    if not isinstance(events, tuple) or any(not isinstance(e, AvailabilityEvent) for e in events):
        raise ValueError("Availability events must be a tuple of AvailabilityEvent objects.")
    if len({event.id for event in events}) != len(events):
        raise ValueError("Availability event IDs must be unique.")
    if any(event.person_id != person_id for event in events):
        raise ValueError("All availability events must reference the requested person.")
    if not isinstance(shared_events, tuple) or any(
        not isinstance(event, CalendarEvent) for event in shared_events
    ):
        raise ValueError("Shared events must be a tuple of CalendarEvent objects.")
    if len({event.id for event in shared_events}) != len(shared_events):
        raise ValueError("Calendar event IDs must be unique.")

    first, stop = horizon.start.toordinal(), horizon.end.toordinal() + 1
    starts: dict[int, list[tuple[tuple[bool, UUID], Decimal]]] = {}
    ends: dict[int, list[tuple[bool, UUID]]] = {}
    reductions = tuple(
        (False, event.id, event.period, event.unavailable_fraction) for event in events
    ) + tuple((True, event.id, event.period, event.unavailable_fraction) for event in shared_events)
    for shared, event_id, period, unavailable_fraction in reductions:
        start = max(first, period.start.toordinal())
        end = min(stop, period.end.toordinal() + 1)
        key = (shared, event_id)
        if start < end and unavailable_fraction > 0:
            starts.setdefault(start, []).append((key, unavailable_fraction))
            ends.setdefault(end, []).append(key)
    boundaries = sorted({first, stop, *starts, *ends})
    active: dict[tuple[bool, UUID], Decimal] = {}
    overlaps: list[AvailabilityOverlap] = []

    # Products retain the sum of calendar/fraction decimal places. The total
    # cannot exceed 24 hours per date. Do not inherit the caller's precision.
    hour_places = max(0, *(-int(h.as_tuple().exponent) for h in calendar.weekday_hours))
    fraction_places = max(
        [0, *(-int(reduction[3].as_tuple().exponent) for reduction in reductions)]
    )
    with localcontext() as context:
        context.prec = max(28, hour_places + fraction_places + len(str(24 * (stop - first))) + 1)
        nominal = nominal_capacity(calendar, horizon).total_hours
        unavailable = Decimal(0)
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            for key in ends.get(start, ()):
                active.pop(key)
            for key, fraction in starts.get(start, ()):
                active[key] = fraction
            if not active:
                continue
            period = PlanningHorizon(date.fromordinal(start), date.fromordinal(end - 1))
            fraction = max(active.values())
            unavailable += nominal_capacity(calendar, period).total_hours * fraction
            if len(active) > 1:
                overlaps.append(
                    AvailabilityOverlap(
                        period,
                        tuple(sorted((key[1] for key in active), key=str)),
                    )
                )
        return AvailableCapacity(nominal, unavailable, nominal - unavailable, tuple(overlaps))
