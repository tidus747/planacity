# Recurring capacity reservations

Available in the v0.4 Team & Capacity development preview. The two-step wizard
uses the calculation API (#8) and schema 5 rules (#9). It previews before applying
any change. The desktop preview uses explicit work calendars and recorded
availability only. Program events and work allocations are not deducted here;
the preview clearly labels its remaining hours as before those inputs.

The [work-calendar calculation foundation](capacity-model.md) is implemented for
review in [#56](https://github.com/tidus747/planacity/issues/56). It accepts an
explicit seven-day pattern and calculates nominal hours only. Calendar storage,
assignment, and editing are implemented for review in #58. The unavailable-share
calculation and overlap reports follow in #60, with persisted editing in #62.
The engine can consume explicit daily capacity after any upstream deductions.
The desktop adapter currently supplies saved calendar hours minus recorded
availability, including dates outside the horizon needed for complete sprints.
It does not infer program-event deductions. Existing plans have no default calendar.

## Purpose and entry point

Reserve time for recurring duties before allocating delivery work. Examples:

- Each selected person reserves 6 hours for meetings every two-week sprint.
- A selected front-office person reserves 12 hours each sprint for support.

Use `Planning -> Reserve capacity...` in the top menu, plus a `Reserve capacity`
button in People. Both open the same wizard. Controls support light/dark appearance,
Tab navigation, Space to check people, and typed ISO dates or calendar pickers.
The command is disabled without an open plan. Commit or correct an active Plan
cell edit before opening the wizard from the menu.

## Wizard steps

1. Name the reservation: Meetings, Front office, or a custom name.
2. Select people. Enter hours per person per period. Show that 6 hours for three
   people reserves 18 team hours; it is not a shared pool of 6 hours.
3. Set the sprint anchor date, length in weeks, and effective start/end dates.
   Two weeks is an editable default. A plan's horizon remains an arbitrary date
   range; sprints are a recurrence option, not the plan's fundamental unit.
4. Preview each affected period and person: available hours before reservation,
   reserved hours, and remaining planning capacity. Show boundary periods,
   overlaps, and reservations that exceed available hours before applying.
5. Confirm once to save the rule. Cancel leaves the plan unchanged. Reopening
   and editing a rule replaces its effect; it must not generate duplicates.

The first page also has a Rule selector. Choose an existing rule to edit it, or
choose **Preview deletion** to see the plan without it. Confirm applies the
deletion; Back or Cancel does not. Confirm is unavailable until Preview succeeds.
If the plan changes while the dialog is open, reopen it to avoid overwriting
newer edits. Closing the wizard without Confirm leaves all drafts unapplied.

The preview shows all stored rules, not just the edited duty, so combined overlaps
and overloads are visible. Assign a calendar to every referenced person first.
Missing calendars or complete-period data block a save preview. Deletion remains
possible when other rules cannot be calculated, with the limitation shown.
Rules outside the current horizon remain stored and are identified in the preview.
Zero eligible days produce Unknown remaining hours; overloads stay negative.
Use Back to revise a rule, or confirm it with those risks visible.

To keep the desktop responsive, previews are limited to 100,000 person-days,
including full-sprint padding. Larger previews ask you to shorten the horizon or
interval, or select fewer people. This is a preview limit, not a file-format limit.
People's table continues to show availability before reservations; its rule count
points to this wizard for reservation totals. Saving/reopening retains the rules.

Real screenshots: [configure light](images/reservation-wizard-light.png),
[configure dark](images/reservation-wizard-dark.png),
[preview light](images/reservation-preview-light.png),
[preview dark](images/reservation-preview-dark.png).

Start with fixed hours per period. Percentage reservations, automatic front-office
rotation, and complex calendar recurrence can be separate later enhancements.
Initially, users can select different people in separate effective date ranges.

## Data and calculation rules

A reservation is separate from a WorkItem, Allocation, and absence. It reserves
capacity without creating task estimates or assigning project work. Reference
people by stable UUIDs. Removing a referenced person must require an explicit
resolution. The confirmation names affected rules. Shared rules retain other
people and their identities; rules left with no people are removed. Calendar
removal retains the rules, since missing capacity is not equivalent to zero.

Store one rule with a stable ID, person IDs, label, hours per person, recurrence
anchor/interval, and effective dates. Derive occurrences deterministically for
the requested horizon; do not persist a growing list of duplicate events.

Calculate capacity in this order:

    Calendar hours - unavailability - capacity-affecting events
    - recurring reservations = planning capacity

Allocations consume planning capacity. Duties recorded as reservations must not
also be deducted as calendar events or project allocations. Explain this in the
wizard and show overlapping reservations; never silently merge or discard them.

Distribute each period's hours equally across the person's positive-capacity
days in that complete period, then include only dates within the effective range
and queried horizon. A partially available day counts as one eligible day, so its
share may exceed its available hours; this is reported as a daily overload.
Full-day leave, holidays, and events with zero remaining capacity are not eligible.
Boundary totals are prorated by eligible-day count, not calendar duration or hours.

Rule hours remain exact Decimal values. Derived shares use standard-library
Fraction values: a 1-hour duty over three eligible days is exactly 1/3 hour per
day, without rounding drift. No display rounding is fed back into calculations.
Negative remaining hours are preserved. A period with zero eligible days has
unknown reserved hours and marks the person's remaining total unknown, rather
than pretending the duty was successfully reserved as zero. The occurrence still
reports the full requested hours for review.

## Calculation API (#8)

`ReservationRule` contains a stable ID, name, distinct person IDs, positive
Decimal hours per person, date anchor, positive integer interval in weeks, and
inclusive effective dates. Anchors align sprints in both directions; effective
dates determine when the rule is active. Occurrences are derived, never persisted.

`reserve_capacity(rules, horizon, capacities)` accepts explicit `PersonCapacity`
inputs. Each contains `CapacityDay` records with date and Decimal available hours
from 0 to 24, **after** unavailability and capacity-affecting events and **before**
reservations or allocations. A known non-working day must be supplied as zero;
missing capacity is an error. Every selected person must have an input, including
people whose rule is outside the current query. Duplicate rules, people, or daily
dates are rejected. Supplied inputs remain unchanged.

Provide every queried date and every complete relevant sprint, even outside the
effective range or query. `reservation_periods(rule, horizon)` returns those full
sprints for the caller. A full sprint extending beyond date.min/date.max is
rejected with an actionable error; missing dates are never assigned guessed hours.

The result contains one `ReservationCapacity` per supplied person, including
daily available/reserved/remaining hours and per-rule occurrences. `overlaps`
identifies days with multiple applied rules, while `overloaded_days` reports
negative daily remaining capacity even when the horizon total is positive.
Rules are additive and never automatically deduplicated by name or dates.
The caller must avoid recording a duty again as an event or allocation.

```python
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from uuid import uuid4

from planacity.domain import PlanningHorizon, ReservationRule
from planacity.planning.reservations import CapacityDay, PersonCapacity, reserve_capacity

person = uuid4()
start = date(2026, 1, 5)
week = PlanningHorizon(start, start + timedelta(days=6))
duty = ReservationRule(
    name="Meetings",
    person_ids=(person,),
    hours_per_person=Decimal(6),
    anchor=start,
    interval_weeks=1,
    effective=week,
)
# Explicit example inputs, already adjusted for any availability/events.
capacity = PersonCapacity(
    person,
    tuple(CapacityDay(start + timedelta(days=i), Decimal(6 if i < 5 else 0)) for i in range(7)),
)
result = reserve_capacity((duty,), week, (capacity,))[0]
assert result.reserved_hours == Fraction(6)
assert result.remaining_hours == Fraction(24)
```

This is a pure domain/calculation API. ProgramPlan now stores the rules in
schema 5, while People still shows availability before reservations. The API does
not fetch calendars, create program events, assign work, or enable a menu command.
The wizard uses a separate desktop adapter and retains these boundaries explicitly.

## Persistence and lifecycle (#9)

`ProgramPlan.reservation_rules` contains the canonical rules. SQLite and JSON
round-trip IDs, selected people, dates, intervals, and exact Decimal hours.
Schemas 1-4 load without rules; saving upgrades to schema 8. Keep a backup or
use Save As if an older build must still read the plan.

`add_reservation`, `update_reservation`, and `remove_reservation` return validated
candidate plans without mutating the original. Updating replaces the same ID in
the same position; it cannot silently create a missing rule. Preview a candidate
with `preview_reservations(candidate, capacities)` before applying it. Cancelling
discards it, and failed validation/preview leaves the original untouched. Removing
a rule removes only its own contribution on the next calculation. Jira baselines
and exports are unchanged. Generated occurrences are never persisted or appended
on reopen, edit, or preview. The wizard exposes this workflow in #10.

## Trackable implementation slices

0. **[Work-calendar foundation (#56)](https://github.com/tidus747/planacity/issues/56):**
   Explicit weekly hours and exact nominal-capacity calculations, independent of
   Qt and persistence. Calendar storage/assignment/editing follows in #58;
   availability calculation follows in #60 and persisted editing in #62.
   Reservation inputs must include any applicable program-event deductions.
1. **[Reservation rules and calculations (#8)](https://github.com/tidus747/planacity/issues/8):** Validate recurrence, hours and person
   references. Test full/partial periods, non-Monday anchors, leap years, leave,
   holidays, zero availability, overlapping rules, and deterministic expansion.
2. **[Persistence and lifecycle (#9)](https://github.com/tidus747/planacity/issues/9):** Round-trip rule identities and precision in
   SQLite/JSON. Edit and remove without duplicate deductions. Resolve person
   deletion and show preview before replacing an existing rule.
3. **[Capacity wizard (#10)](https://github.com/tidus747/planacity/issues/10):** Add the menu/People entry points, accessible forms,
   preview and confirmation, with selective UI tests for cancellation, edits,
   validation, and both themes.

These slices depend on the v0.4 calendar and capacity baseline. Jira CSV in v0.2
must continue to map external people to the same canonical Person identities.

The slices above describe the implemented foundation. Future integration into
People, Overview, and Team Timeline is ordered in the [current roadmap](roadmap.md).
