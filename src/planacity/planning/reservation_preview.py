"""Desktop preview inputs from explicit calendars and recorded availability only."""

from datetime import date

from planacity.domain import PlanningHorizon, ProgramPlan
from planacity.planning.availability import availability_capacity
from planacity.planning.reservation_settings import preview_reservations
from planacity.planning.reservations import (
    CapacityDay,
    PersonCapacity,
    ReservationCapacity,
    reservation_periods,
)

MAX_PREVIEW_DAYS = 100_000


def preview_plan_reservations(plan: ProgramPlan) -> tuple[ReservationCapacity, ...]:
    """Build complete sprint inputs; never infer calendars or missing event data.

    This preview covers recorded availability, not program events or allocations.
    Limit daily expansion for responsive desktop use, with an explicit error.
    """
    selected = {person for rule in plan.reservation_rules for person in rule.person_ids}
    if ((plan.horizon.end - plan.horizon.start).days + 1) * len(selected) > MAX_PREVIEW_DAYS:
        raise ValueError(
            "Preview exceeds 100,000 person-days. Shorten the horizon or select fewer people."
        )
    assignments = {a.person_id: a.calendar_id for a in plan.person_calendars}
    missing = [p.name for p in plan.people if p.id in selected and p.id not in assignments]
    if missing:
        raise ValueError(
            "Assign a work calendar before previewing reservations for: " + ", ".join(missing)
        )
    ranges = {}
    for person in plan.people:
        if person.id not in selected:
            continue
        first, last = plan.horizon.start, plan.horizon.end
        for rule in plan.reservation_rules:
            if person.id in rule.person_ids:
                periods = reservation_periods(rule, plan.horizon)
                if periods:
                    first = min(first, periods[0].start)
                    last = max(last, periods[-1].end)
        ranges[person.id] = PlanningHorizon(first, last)
    total_days = sum((period.end - period.start).days + 1 for period in ranges.values())
    if total_days > MAX_PREVIEW_DAYS:
        raise ValueError(
            "Preview exceeds 100,000 person-days. Shorten the horizon or sprint interval, "
            "or select fewer people. No changes have been applied."
        )
    capacities = []
    for person_id, period in ranges.items():
        calendar = plan.work_calendar(assignments[person_id])
        events = tuple(e for e in plan.availability_events if e.person_id == person_id)
        days = []
        for ordinal in range(period.start.toordinal(), period.end.toordinal() + 1):
            day = date.fromordinal(ordinal)
            result = availability_capacity(calendar, PlanningHorizon(day, day), person_id, events)
            days.append(CapacityDay(day, result.available_hours))
        capacities.append(PersonCapacity(person_id, tuple(days)))
    return preview_reservations(plan, tuple(capacities))
