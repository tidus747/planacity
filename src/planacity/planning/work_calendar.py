"""Nominal calendar capacity, before availability and allocation calculations."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from planacity.domain import PlanningHorizon, WorkCalendar


@dataclass(frozen=True)
class NominalCapacity:
    """Gross hours and positive-hour dates; not remaining planning capacity."""

    total_hours: Decimal
    working_days: int
    calendar_days: int


def _weighted_hours(calendar: WorkCalendar, occurrences: tuple[int, ...]) -> Decimal:
    # Daily values are bounded by 24. Allow enough integer digits for the entire
    # horizon and retain every supplied fractional digit, regardless of the
    # caller's Decimal precision. No rounding/quantization is applied here.
    places = max(0, *(-int(value.as_tuple().exponent) for value in calendar.weekday_hours))
    with localcontext() as context:
        context.prec = max(28, places + len(str(24 * sum(occurrences))) + 1)
        return sum(
            (
                hours * count
                for hours, count in zip(calendar.weekday_hours, occurrences, strict=True)
            ),
            Decimal(0),
        )


def nominal_week_hours(calendar: WorkCalendar) -> Decimal:
    """Sum the explicit seven-day pattern; this does not define a day-unit conversion."""
    return _weighted_hours(calendar, (1,) * 7)


def nominal_capacity(calendar: WorkCalendar, horizon: PlanningHorizon) -> NominalCapacity:
    """Count an inclusive horizon in constant space/time over seven weekdays.

    A working day has strictly positive nominal hours. Holidays, leave, events,
    reservations, and allocations are deliberately absent from this result.
    No Person assignment or team total is inferred from a roster.
    """
    total_days = (horizon.end - horizon.start).days + 1
    weeks, remainder = divmod(total_days, 7)
    first = horizon.start.weekday()
    occurrences = tuple(weeks + int((weekday - first) % 7 < remainder) for weekday in range(7))
    working_days = sum(
        count for hours, count in zip(calendar.weekday_hours, occurrences, strict=True) if hours > 0
    )
    return NominalCapacity(_weighted_hours(calendar, occurrences), working_days, total_days)
