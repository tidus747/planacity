# Recurring capacity reservations

Planned for v0.4, Team & Capacity. This is a design and issue breakdown, not a
feature available in the current desktop preview. The v0.1 people roster is a
prerequisite; calendars, allocations, persistence, and capacity calculations
must be ready before this wizard becomes an enabled command.

## Purpose and entry point

Reserve time for recurring duties before allocating delivery work. Examples:

- Each selected person reserves 6 hours for meetings every two-week sprint.
- A selected front-office person reserves 12 hours each sprint for support.

Use `Planning -> Reserve capacity...` in the top menu, plus a `Reserve capacity`
button in People & Capacity. Both open the same wizard. Preserve light/dark
appearance and keyboard navigation; use normal form controls and explicit units.
Do not add a nonfunctional menu entry to the current shell.

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

Start with fixed hours per period. Percentage reservations, automatic front-office
rotation, and complex calendar recurrence can be separate later enhancements.
Initially, users can select different people in separate effective date ranges.

## Data and calculation rules

A reservation is separate from a WorkItem, Allocation, and absence. It reserves
capacity without creating task estimates or assigning project work. Reference
people by stable UUIDs. Removing a referenced person must require an explicit
resolution once reservations are implemented; v0.1 currently has no references.

Store one rule with a stable ID, person IDs, label, hours per person, recurrence
anchor/interval, and effective dates. Derive occurrences deterministically for
the requested horizon; do not persist a growing list of duplicate events.

Calculate capacity in this order:

    Calendar hours - unavailability - capacity-affecting events
    - recurring reservations = planning capacity

Allocations consume planning capacity. Duties recorded as reservations must not
also be deducted as calendar events or project allocations. Explain this in the
wizard and show overlapping reservations; never silently merge or discard them.

Before implementing calculations, define partial-period behavior explicitly.
Recommended initial rule: distribute period hours across the person's eligible
working days in that complete period, then include only dates within the
effective range and queried horizon. Show prorated boundary totals in preview.
Keep exact decimal arithmetic, document rounding, flag zero eligible days, and
report negative remaining capacity instead of hiding it by clamping to zero.

## Trackable implementation slices

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
