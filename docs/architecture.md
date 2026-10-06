# Architecture

The sections below record implemented behavior and its evolution. The next
implementation contract is in [planning decisions](planning-decisions.md), with
sequencing in the [roadmap](roadmap.md). Dependency enforcement, hierarchy
effort, dated capacity, and work-context services operate over schema 8 inputs.

The v0.1 application edits and persists a canonical plan, horizon, hierarchy,
people, estimates, dates, groups, and relationships. See
[domain-model.md](domain-model.md) and [project-file-format.md](project-file-format.md).

| Layer | Responsibility | Allowed dependencies |
| --- | --- | --- |
| `domain` | Canonical entities and intrinsic invariants | Python standard library |
| `planning` | Editing operations and cross-entity validation | Domain, standard library |
| `persistence` | SQLite project files and JSON backups | Domain, standard library |
| `document.py` | Open/save state and the last saved snapshot | Domain, persistence, standard library |
| `ui` | Qt views and model adapters; present validation errors | Document, domain, planning, persistence, PySide6 |
| `main.py` | Application startup | UI, PySide6 |

Use normal Python calls and Qt signals. Business rules belong below the UI;
validation must also apply to loading files and non-UI callers. The Plan
editor uses `QTreeView` and a `QAbstractItemModel` backed by the canonical model.
Do not keep separate editable copies of data for each view.

The domain validates complete immutable plan snapshots, including hierarchy
invariants. Planning operations create a candidate snapshot and return it only
after validation succeeds, preserving the original on errors. This keeps the
same invariants available to the future UI and file loaders without Qt imports.

## v0.1 decisions

- Use a `src` layout, setuptools, and Python 3.11+; PySide6 is the sole runtime
  dependency. Pytest, Ruff, mypy, and build are development tools.
- Keep the initial shell honest about unavailable functionality. Add actual
  editing and file actions as complete, tested increments.
- Organize the shell around a persistent sidebar (Overview, Plan, People, Import),
  project context, page headers, and a status bar. Plan uses resizable list/detail
  panels; People provides the team roster. Import is informational for v0.2. Do not
  derive domain assumptions such as quarters or single owners from UI references.
- Keep shared light/dark colors in `ui/theme.py` and empty-state layouts in
  `ui/pages.py`. Use Qt's local `QSettings` for the appearance preference, separate
  from project data; use the system appearance on first launch. Tests inject a
  temporary settings file so they do not overwrite user preferences.
- Use SQLite via `sqlite3` for local project persistence and `json` for backups.
  Schema 1 stores one validated JSON snapshot in a SQLite container. No ORM,
  database service, HTTP API, or cloud component is needed.
- Use canonical IDs and Python dates. A planning horizon is any valid date range.
  Parent/child hierarchy, WorkGroups, and relationships are distinct concepts.
- v0.1 people management does not need capacity calculations. If work assignment
  is introduced, it must use a separate Allocation entity supporting multiple
  people; do not add a single `WorkItem.owner` shortcut. Allocation editing and
  capacity accounting remain v0.4 work in this breakdown.
- Do not pre-create adapters, scenarios, calendar, reports, or milestone models.
  Add them when their roadmap release needs them.
- Astro is a static product site independent of the desktop. Node is needed only
  to develop/build the site. CI builds it for PRs and deploys the generated site
  from `main` after Python and website checks pass.

## Validation strategy

The skeleton tests navigation, theme switching and restoration, and a real Qt
startup/shutdown. Domain, persistence, and document tests cover invalid data and
failed writes. Selective Qt tests cover hierarchy, form validation, cancellation,
keyboard save, and close/reopen/continue. Native Windows GUI acceptance and visual
checks are recorded in [getting-started.md](getting-started.md).
Building a wheel checks Python packaging; a Windows installer remains later work.

One `Session` change signal connects the document to Overview, Plan, and People.
The Qt model holds a reference to the same immutable plan snapshot. Structural
changes use model reset notifications and restore selection/expansion by UUID;
cell edits use `dataChanged` so invalid drafts and the current editor stay intact.
File dialogs and confirmation prompts are presentation concerns; persistence and
dirty-state transitions are independently testable without Qt.

## Jira roundtrip

The `integrations/jira` adapter parses CSV and builds an immutable candidate plan.
The wizard commits that candidate only after validation and explicit confirmation.
`ImportSnapshot` and `ImportedWork` preserve source cells and baseline work in the
canonical model, without Jira API dependencies. Current roster entries and work
may change or be deleted without invalidating their original snapshots.

`planning/changes.py` computes differences; it never writes a baseline. CSV export
serializes the current hierarchy and carries original references, status, and
external people. Project schema 2 stores imports; schema 1 loads with none.
Mapping profiles are separate local files with no imported rows or people.

## Visual planning

`planning/timeline.py` is a read-only projection over the canonical plan. It
flattens hierarchy for display, calculates inclusive day coordinates, and carries
effective WorkGroup membership without copying editable state. Qt Timeline views
consume this projection and rebuild it when the shared `Session` changes.

Coordinates outside the horizon remain outside rather than changing stored dates.
Person grouping waits for Allocations in v0.4, and milestone markers wait for the
first-class Milestone model. The Timeline must not infer either concept from Jira
metadata or represent milestones as zero-duration work.

## Timeline scale coordinates

`planning/timeline_axis.py` calculates day, ISO-week, and calendar-month columns
without Qt or a list of every date. Partial first/last periods stay within the
planning horizon, including the supported minimum and maximum dates. Rendering
uses fractional bar spans within those periods; canonical dates never change.
The desktop stores `timeline/scale` in local QSettings, independently of projects.

`planning/timeline_view.py` filters individual rows and arranges them by canonical
hierarchy, Epic, or WorkGroup. Grouped rows retain the work UUID and add a section
UUID for stable display selection. Multiple WorkGroup memberships produce display
occurrences of the same work; summary counts deduplicate UUIDs.

`planning/plan_filters.py` reuses the Timeline predicates and inherited WorkGroup
membership, adding ancestor UUIDs for context. `ui/plan_filter_model.py` is a
Qt filtering proxy over the existing editable Plan model. Only matching rows
allow inline edits. Structural actions still use the canonical plan, so deletion
previews cover hidden descendants. Filtering after a cell commit is deferred
until the delegate closes; selection restoration uses work UUIDs. Filters never
enter the project or its imported snapshots.

`planning/work_context.py` atomically edits descriptions, ordered labels, and an
optional primary WorkGroup. Topic resolution walks to the nearest explicit
primary choice, then resolves a legacy Epic with exactly one WorkGroup. No group
is Ungrouped and several groups are Ambiguous until selected. Effective filter
membership combines the inherited Epic memberships with that one resolved topic
in canonical WorkGroup order; it does not persist copied membership on children.

`planning/dependency_validation.py` normalizes relationship direction and computes
cycle, incomplete-edge, and inclusive-date findings from the complete canonical
plan. The same validator guards relationship creation and every date setter. It
compares the original and candidate plan so legacy conflicts remain repairable,
while new cycles and new or worsened conflicts are rejected. Filters never reduce
the set of edges checked.

`planning/timeline_dependencies.py` consumes those shared findings and explains
unavailable endpoints. Its
orthogonal connector geometry is independently testable. The Qt schedule view
maps day coordinates to visible cells and draws arrows only when both actual
endpoints are on screen. Cross-section links use the first occurrence when no
shared section exists. None of these operations changes the canonical plan.

Timeline editing is separate from projection and painting. `timeline_resize.py`
in planning snaps period fractions to inclusive days and delegates validation to
`set_work_dates`. The UI holds the original immutable snapshot throughout a drag,
previews candidates, and applies once on release only if that snapshot is still
current. Escape and view changes discard the candidate. Invalid drops retain the
actionable dependency or date message while preserving the original plan. The
keyboard date form uses the same canonical setter and stale-snapshot check.

## Work-calendar foundation

Estimate presentation is plan-scoped through `EstimatePreferences`. The pure
`planning/estimate_units.py` service derives exact rational hour equivalents from
an explicit reference calendar. A day uses the mean of positive-hour weekdays;
a week uses their sum. The Plan model converts entry/display without modifying
stored hours on preference changes. Non-terminating displays are marked, and
editors fall back to exact hours to avoid writing back rounded display values.
Schema 6 stores only the unit and calendar reference. Jira mappings remain
independent, and schemas 1-5 default to hours without inferred conversion rates.

`domain/work_calendar.py` defines an immutable, explicit weekly hours pattern.
`planning/work_calendar.py` calculates nominal hours for an inclusive horizon in
constant space using seven weekday counts. It preserves Decimal precision without
modifying the caller's arithmetic context. ProgramPlan owns calendars and separate
PersonCalendar references. Schema 5 stores both collections, leaving imported
Person snapshots untouched. Schema 1/2 loads with empty collections. Lifecycle
services validate references and require explicit unassignment when deleting a
referenced calendar. The People view delegates editing and calculation to these services.
`domain/availability.py` defines person-specific unavailable shares without HR
reasons. `planning/availability.py` splits the horizon at event boundaries,
applies the strongest active fraction, and reports overlaps by stable event IDs.
It avoids expanding long horizons into daily lists and preserves exact Decimal
products. Callers supply an explicit calendar and one person's events; mismatched
references and duplicate IDs are rejected. ProgramPlan owns availability events;
schema 5 persists them and reads schemas 1-3 without inferred entries. Lifecycle
services preserve IDs and guard person deletion. People delegates previews and
totals to the planning layer, with validated date/share forms and stale-draft
protection. PlanningHorizon lives in a shared domain module to avoid a circular
dependency between ProgramPlan and its availability events. Program-event deductions, reservations,
and allocations remain separate inputs. See [the capacity model](capacity-model.md)
for the public API and limits.

## Recurring reservation calculation

`domain/reservations.py` defines fixed per-person duties and their anchored
recurrence. `planning/reservations.py` derives complete sprint periods and exact
shares from explicit daily capacity after availability and program events.
This input boundary keeps the engine independent of a future calendar/event UI.
It requires full-period data for correct proration, returns overlap/overload
details, and uses Fraction for non-terminating decimal shares. It never mutates
or persists generated occurrences. ProgramPlan owns reservation rules and schema 5
stores their exact Decimal inputs. Schemas 1-4 load without rules. The lifecycle
services in `reservation_settings.py` return validated immutable candidates and
preview them over explicit adjusted capacity. UI code can discard a candidate
without side effects. Person deletion requires explicit resolution of affected
rules; shared rules retain IDs and other people.

`reservation_preview.py` builds complete daily sprint inputs from assigned
calendars and recorded availability. Missing calendars and oversized previews
produce actionable errors. It explicitly excludes future program events and
allocations. `ui/reservations.py` implements the shared menu/People two-step
dialog: field drafts -> validated candidate and preview -> one confirmation.
Back invalidates the candidate, Cancel discards it, and a snapshot identity check
prevents stale confirmation from overwriting a changed plan. Editing and deletion
use the same lifecycle services as storage. Exact shares render as decimals when
terminating and fractions otherwise; display rounding never changes rule hours.

## Explicit work allocation foundation

`domain/allocation.py` defines explicit work/person effort links, independently
of ownership or external assignees. `planning/allocations.py` validates a candidate
tuple against a ProgramPlan and computes exact whole-work and per-person totals.
It retains unknown estimates and signed remaining effort rather than correcting
incomplete plans. Leaves provide effective estimates; containers recursively sum
their leaf estimates and allocations once. Stored container estimates remain
reference inputs and are never added to their derived totals.

ProgramPlan owns and validates allocations. Schema 7 persists exact hours and
stable IDs; schemas 1-6 load without inferred assignments. Lifecycle services in
`planning/allocation_settings.py` return validated immutable snapshots. The Plan
dialog stages edits until Save and rejects stale snapshots. Person/work deletion
requires explicit consent for affected allocations, including descendants. See
[the allocation model](allocation-model.md) for calculation semantics and limits.
New allocations target leaf work. A legacy direct container allocation stays
visible and counted until the user moves it to a newly named leaf or removes it.
The move preserves allocation IDs/hours and does not alter dates, groups,
relationships, imported baselines, or unrelated descendants.
