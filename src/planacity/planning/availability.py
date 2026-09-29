"""Exact availability before program events, reservations, and allocations."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from uuid import UUID

from planacity.domain import PlanningHorizon, WorkCalendar
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
) -> AvailableCapacity:
    """Apply the strongest unavailable share on each date, without double counting.

    Callers must explicitly select one person's events and calendar. Duplicate
    event IDs and mismatched people are rejected, even outside the horizon.
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

    first, stop = horizon.start.toordinal(), horizon.end.toordinal() + 1
    starts: dict[int, list[AvailabilityEvent]] = {}
    ends: dict[int, list[UUID]] = {}
    for event in events:
        start = max(first, event.period.start.toordinal())
        end = min(stop, event.period.end.toordinal() + 1)
        if start < end and event.unavailable_fraction > 0:
            starts.setdefault(start, []).append(event)
            ends.setdefault(end, []).append(event.id)
    boundaries = sorted({first, stop, *starts, *ends})
    active: dict[UUID, AvailabilityEvent] = {}
    overlaps: list[AvailabilityOverlap] = []

    # Products retain the sum of calendar/fraction decimal places. The total
    # cannot exceed 24 hours per date. Do not inherit the caller's precision.
    hour_places = max(0, *(-int(h.as_tuple().exponent) for h in calendar.weekday_hours))
    fraction_places = max(
        [0, *(-int(event.unavailable_fraction.as_tuple().exponent) for event in events)]
    )
    with localcontext() as context:
        context.prec = max(28, hour_places + fraction_places + len(str(24 * (stop - first))) + 1)
        nominal = nominal_capacity(calendar, horizon).total_hours
        unavailable = Decimal(0)
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            for identifier in ends.get(start, ()):
                active.pop(identifier)
            for event in starts.get(start, ()):
                active[event.id] = event
            if not active:
                continue
            period = PlanningHorizon(date.fromordinal(start), date.fromordinal(end - 1))
            fraction = max(event.unavailable_fraction for event in active.values())
            unavailable += nominal_capacity(calendar, period).total_hours * fraction
            if len(active) > 1:
                overlaps.append(AvailabilityOverlap(period, tuple(sorted(active, key=str))))
        return AvailableCapacity(nominal, unavailable, nominal - unavailable, tuple(overlaps))
