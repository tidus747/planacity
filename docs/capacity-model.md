# Work calendars and nominal capacity

The v0.4 calculation foundation defines explicit nominal working hours. It is a
Python domain API, not yet an editable or persisted desktop feature. No default
calendar is assigned to existing plans or people, and no capacity is inferred
from roster membership.

## Weekly pattern

`WorkCalendar` has a stable UUID, name, and an immutable tuple of seven Decimal
hour values ordered Monday through Sunday. All seven values must be supplied.
Zero means a non-working day. Positive values may differ by weekday; weekends
may be working days. Each value must be finite and between 0 and 24 inclusive.
Integers, floats, strings, missing entries, and invalid identities are rejected.

This represents nominal date-based hours, not shift start/end times or elapsed
time across timezone or daylight-saving transitions. Leave, holidays, and program
events will be separate inputs rather than hidden exceptions in this pattern.

```python
from datetime import date
from decimal import Decimal

from planacity.domain import PlanningHorizon, WorkCalendar
from planacity.planning.work_calendar import nominal_capacity, nominal_week_hours

calendar = WorkCalendar(
    name="Explicit example schedule",
    weekday_hours=tuple(Decimal(value) for value in ("6", "7.5", "0", "4.25", "2", "3", "1")),
)
horizon = PlanningHorizon(date(2026, 9, 28), date(2026, 10, 4))
result = nominal_capacity(calendar, horizon)
assert result.total_hours == Decimal("23.75")
assert result.working_days == 6
assert result.calendar_days == 7
assert nominal_week_hours(calendar) == Decimal("23.75")
```

The numbers above are supplied example inputs, not application defaults. Neither
an 8-hour day nor a 40-hour week is assumed. `hours_on(date)` returns the explicit
weekday value. A working-day count includes only dates with positive hours.

## Calculation and precision

Horizons are inclusive and may start on any weekday. The calculation counts full
weeks plus the remaining weekdays, requiring only seven counters regardless of
horizon length. It handles the complete supported date range without constructing
a list of dates or advancing beyond `date.max`.

Totals retain every fractional digit supplied in the calendar. A private Decimal
context has sufficient precision for the horizon total, without changing the
caller's context. No rounding or display quantization is performed. All-zero
calendars return zero hours and zero working days, not missing data.

`nominal_week_hours` reports the weekly total only. It does not define how an
estimate expressed in working days should be converted when days have different
lengths. Estimate unit settings in #39 must specify that convention explicitly.

## Capacity boundaries and follow-ups

Nominal capacity is the first input to the future calculation:

    Nominal calendar hours
    - Holidays and personal unavailability
    - Capacity-affecting program events
    - Reserved capacity
    = Planning capacity

Allocations then consume planning capacity. The current API does not calculate
remaining hours, overload, availability reductions, or team totals. These must
not be labelled as nominal capacity or inferred without explicit inputs.

Next slices must add calendar persistence, person/calendar assignment and editing,
then availability/event deductions with clear overlap rules. Recurring
reservations (#8), lifecycle (#9), and the wizard (#10) depend on those inputs.
The existing project schema, Jira hour estimates, and import baselines are
unchanged by this foundation. See [recurring reservations](capacity-wizards.md).
