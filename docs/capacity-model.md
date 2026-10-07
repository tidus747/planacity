# Work calendars and availability

The v0.4 development preview supports named work calendars, explicit per-person
assignments, and dated availability for the planning horizon. No default calendar is
assigned to existing plans or people; missing assignment means unknown, not zero.

## Desktop workflow

In People, choose **Work calendars...**, then Add. Enter a name and hours for all
seven weekdays, using 0 for non-working days. Add/Edit forms validate before
applying; cancelling a form leaves its draft unapplied. Closing the calendar
manager retains changes already confirmed in individual forms.

Select a person and choose **Assign calendar...**. Preview their nominal hours
for the horizon, then confirm, or select Not configured to clear the assignment.
Shared calendar edits update every assigned person's nominal hours. Deleting a
referenced calendar names the affected people and asks before clearing their
assignments. Removing a person also removes their assignment, not the calendar
or imported Person snapshots. All controls support keyboard navigation and both
appearances. Changes persist in projects and JSON backups.

Select a person and choose **Availability...** to add, edit, or delete dated
unavailability. Enter inclusive start/end dates (typed as YYYY-MM-DD or picked
from a calendar) and a share from 0 to 1: 1 means a full day, 0.5 half, and 0 none.
The share applies to each date's calendar hours, not a fixed 8-hour day.
No reason for the absence is requested. The live preview shows horizon totals
and overlapping periods/entry numbers matching the manager's list. Overlaps use
the largest share, not the sum;
combine distinct partial absences into one share if they should add up.

People starts at the plan horizon and also accepts explicit Day, Week, or custom
inclusive ranges. Its roster shows nominal, unavailable, available, reserved,
planning, allocated, signed remaining, and unplaced hours. The selected-person
table groups the same exact daily result by day, ISO week, or the complete selected
period. Status is always written as text as well as highlighted: overloaded,
incomplete, unknown, full, within capacity, no work, or no planning capacity.

The detail names every contributing reservation rule and dated task. Source
actions reopen the matching reservation or allocation editor. A period total is
marked Overloaded when any included date is overloaded, even if spare capacity on
other dates makes the period's signed total positive. Missing dates remain visible
as unplaced demand, and a missing calendar remains Unknown rather than zero.

Entries outside the selected range are retained; only intersecting dates
contribute. Clearing a calendar retains availability; reassigning one recalculates
it. Confirming an edit retains its ID, while cancellation leaves the draft
unapplied. Deleting a person asks before clearing their availability entries.
Imported snapshots remain unchanged. Program events are not yet modeled.

Schemas 1-3 open without availability; schemas 1-4 open without reservations.
Saving writes schema 10. Keep a backup
or use Save As if the file must remain readable in an older build.

Screenshots using an explicitly configured example schedule:

- Complete People capacity: [light](images/people-capacity-light.png),
  [dark](images/people-capacity-dark.png).
- People: [light](images/people-calendars-light.png),
  [dark](images/people-calendars-dark.png).
- Calendar editor: [light](images/calendar-editor-light.png),
  [dark](images/calendar-editor-dark.png).
- Availability editor: [light](images/availability-editor-light.png),
  [dark](images/availability-editor-dark.png).

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

## Shared dated capacity engine

`planning.capacity.calculate_dated_capacity` combines the existing canonical
inputs for any inclusive query period:

    Nominal calendar hours
    - Recorded personal unavailability
    = Available hours
    - Recurring reservations
    = Planning capacity
    - Scheduled allocated work
    = Remaining capacity

The result provides one `DatedCapacityDay` per queried date and person. Each day
retains exact nominal, unavailable, available, reserved, planning, allocated,
and signed remaining hours. Reservation and allocation breakdowns keep their
source UUIDs so later views can explain which duty or work item consumed the
hours. Negative planning or remaining hours are retained as overload, never
clamped to zero.

An allocation is distributed over its WorkItem's complete start/end window in
proportion to that person's positive planning capacity after reservations. The
complete window and complete anchored reservation periods are calculated first;
only then is the result clipped to the query. Concurrent allocations are summed
after distribution, so one allocation never silently moves because another uses
the same dates. Stored allocations, dates, estimates, and project files are not
changed.

Missing calendars, incomplete work dates, zero-capacity work windows, and
reservation occurrences without eligible days produce explicit `CapacityGap`
values. Their demand is not treated as zero. Known daily values remain available
alongside the gap, while `complete` prevents consumers from presenting an
incomplete result as a fully feasible plan. Queries requiring more than 100,000
person-days return one actionable incomplete result and no partial totals.

All public hour values use exact `Fraction` results derived from stored Decimal
inputs. No display rounding or caller Decimal context changes the total. Program
events are not yet a source because their domain model belongs to v0.5.

`planning.findings.planning_findings` turns this shared result and the canonical
effort rollups into calculated, non-persisted advice. Each finding has a stable
rule key, severity, affected work/person/source UUIDs, an optional date range,
an explanation, and a suggested action. Plan rows, selected-work details, and
allocation drafts consume the same snapshot. Overload findings include all
concurrent work and reservations for the affected person, even when a draft is
opened from only one task. They warn but do not block saving an incomplete plan.

## Capacity boundaries and follow-ups

The nominal-calendar and availability APIs remain smaller reusable calculations;
they do not independently claim remaining capacity. The shared engine is the
canonical integration boundary for findings and People/Overview totals. R05
exposes its gaps and overloads as reusable planning findings. R06 exposes the same
exact totals and source IDs in People. Overview projects those same results over
the fixed inclusive plan horizon, with known-person subtotals and explicit
coverage notes when any result is partial. Its topic view keeps scheduled
horizon allocations separate from whole-plan estimated leaf effort. Program
events remain a later input.

People WorkGroup filtering is a presentation over the same complete person
result. It never recalculates capacity from only the visible group. Whole-plan
positive allocations establish derived navigation associations; selected-range
scheduled and unplaced hours come from the shared engine and use one additive
reporting topic. A person's planning and remaining hours are never duplicated
across groups.

Program-event deductions follow in v0.5. They are not a prerequisite for showing
the currently entered meetings and front-office reservations consistently.
The recurring reservation API (#8) now consumes explicit daily capacity after
these deductions. Rules persist (#9), and the wizard (#10) previews saved calendars
and entered availability before reservations. Program-event deductions are not yet
modeled in the desktop; the preview labels that limitation. People then combines
the saved reservation result with dated allocations for the selected range.
Calendar and availability data remain unchanged in schema 10, while Jira hour
estimates and import baselines are unchanged. See
[recurring reservations](capacity-wizards.md).
The distribution and missing-data rules are defined in
[planning decisions](planning-decisions.md).

## Availability calculation API

The calculation foundation for [#60](https://github.com/tidus747/planacity/issues/60)
accepts explicit AvailabilityEvents for one person. Each event has an identity,
person UUID, inclusive PlanningHorizon, and unavailable fraction from 0 to 1.
For example, 0.5 removes half of each date's nominal hours; 1 removes all of them.
No 8-hour day or reason for the absence is inferred or stored. Fractions must be
finite Decimal values. ProgramPlan now stores these events, and People exposes
the calculation through its availability editor and horizon totals (#62).

```python
from datetime import date
from decimal import Decimal
from uuid import uuid4

from planacity.domain import AvailabilityEvent, PlanningHorizon, WorkCalendar
from planacity.planning.availability import availability_capacity

person_id = uuid4()
horizon = PlanningHorizon(date(2026, 9, 28), date(2026, 10, 4))
calendar = WorkCalendar(
    name="Explicit example",
    weekday_hours=tuple(Decimal(v) for v in ("6", "6", "6", "6", "6", "0", "0")),
)
absence = AvailabilityEvent(
    person_id=person_id,
    period=PlanningHorizon(date(2026, 9, 28), date(2026, 9, 29)),
    unavailable_fraction=Decimal("0.5"),
)
result = availability_capacity(calendar, horizon, person_id, (absence,))
assert result.nominal_hours == Decimal(30)
assert result.unavailable_hours == Decimal(6)
assert result.available_hours == Decimal(24)
assert not result.overlaps
```

### Overlaps and partial days

On each date, the strongest active unavailable fraction wins. A full-day holiday
and full-day leave therefore remove the date's hours once. Two half-day entries
also remove half, not all: without times, they may refer to the same half-day.
When separate partial absences should add up, supply one combined daily fraction
instead. This model describes availability limits, not additive appointments or
reserved duties. Time-of-day scheduling is outside this API.

Every interval with more than one positive-share event is returned in `overlaps`,
with its clipped dates and sorted event IDs. Even zero-hour calendar dates remain
visible in overlap reports. Zero-share entries have no effect and do not create
overlap warnings. Adjacent inclusive ranges do not overlap unless they share a
date. Inputs are never modified, and event order does not change the result.

Callers must supply only the requested person's events and explicitly resolve
their calendar. Duplicate event IDs and mismatched person references are rejected,
even outside the horizon. A missing calendar is an error, not zero capacity.
The result is available hours **before** program events, reservations, and
allocations; it must not be labelled remaining planning capacity.

### Range and precision

Only the intersection with the queried horizon contributes. The implementation
splits at event boundaries and counts weekdays within each interval, rather than
materializing every date. It handles date.min/date.max, leap days, variable hours,
working weekends, and calendars explicitly set to zero. Decimal precision covers
both the calendar hours and fraction, without rounding or changing the caller's
context. Availability cannot exceed nominal hours or reduce them below zero;
future over-reservation must still be reported rather than silently clamped.
