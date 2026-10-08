# Planning Foundation domain model

The planning foundation provides a canonical model and editing API independent of
Qt, file formats, and external tools. The desktop editor and versioned local
project/backup adapters use these APIs.

## Entities

ProgramPlan also owns `EstimatePreferences`: an Hours/Days/Weeks unit and an
optional reference WorkCalendar ID. Days and weeks require positive calendar
hours. This schema 6 preference never changes WorkItem or imported baseline
estimates, which remain exact Decimal hours. See [estimate units](estimate-units.md).

| Entity | Fields | Rules |
| --- | --- | --- |
| `PlanningHorizon` | `start`, `end` | Inclusive dates; end cannot precede start |
| `ProgramPlan` | `id`, `name`, `description`, `horizon`, `work_items`, `people`, `work_groups`, `relationships` | Valid immutable collections and references |
| `WorkItem` | `id`, `title`, `kind`, `parent_id`, `assignee_id`, `estimate_hours`, `start`, `end`, `description`, `labels`, `primary_group_id`, `priority` | Valid hierarchy, optional roster assignee, estimates, dates, context, and priority |
| `Person` | `id`, `name` | Non-blank name; unique ID within the roster |
| `WorkGroup` | `id`, `name`, `epic_ids` | Named group of existing Epics |
| `Relationship` | `id`, `source_id`, `target_id`, `kind` | Existing distinct endpoints; no duplicate links |
| `ImportedWork` | `item`, `external_reference`, `external_person`, `person`, `status`, `external_priority` | Immutable source baseline and original integration text |

IDs are Python `uuid.UUID` values. Constructors generate UUIDs by default and
accept explicit UUIDs when reconstructing existing data. Editing preserves IDs.
Future storage adapters must convert serialized IDs to UUIDs explicitly.

Dates are `datetime.date` values, without time or timezone. A horizon can be a
single day, cross a year boundary, or cover any other ordered date range.
Constructors reject strings and datetimes instead of guessing conversions.

Names, titles, and descriptions preserve supplied characters and whitespace.
Validation checks for blank names but never trims user text. Duplicate titles
are allowed because references use IDs rather than names.

## Hierarchy

- Epics are root items.
- Tasks may be roots or children of Epics.
- Subtasks require a Task parent.
- IDs must be unique within a plan. Parent references must resolve in that plan.
- Self-parenting, cycles, and invalid parent types are rejected.

A plan stores an immutable tuple of work items. Filtering that tuple by parent
defines sibling order. Physical tuple order does not require parents to precede
children, allowing a future loader to resolve a complete snapshot before validation.
`plan.children()` returns roots; `plan.children(parent_id)` returns direct children.
`plan.work_item(item_id)` retrieves an item or raises an actionable `ValueError`.

WorkGroups and relationships are separate concepts, not extra hierarchy levels.
Canonical ownership is the optional `WorkItem.assignee_id`; capacity demand stays
in separate Allocations. An Epic assignee is a feature owner and does not add
capacity demand. New executable leaves accept zero or one Allocation, whose person
is aligned with the assignee by planning services. Legacy multi-person leaves keep
every allocation and receive a calculated resolution finding.

## Work context and reporting topics

WorkItem descriptions are plain text. Labels are ordered non-blank strings with
no leading/trailing whitespace and no case-insensitive duplicates. Their spelling
and order are preserved. They are metadata, not additive reporting dimensions.

`primary_group_id` is optional and must identify a WorkGroup in the same plan.
`planning/work_context.py` edits all three context fields atomically. A work
item's reporting topic is its nearest explicit primary group in the hierarchy.
Without one, exactly one WorkGroup membership on the containing Epic resolves a
legacy topic; none is Ungrouped and several are Ambiguous. Standalone Tasks can
select a primary group directly, and a child can override its ancestor.

Effective WorkGroup filters combine inherited Epic memberships with the resolved
primary group. This keeps historical multi-group organization while giving future
additive reports one topic or an explicit exception bucket. No memberships are
copied into descendants. Removing a referenced WorkGroup requires confirmation
and clears only explicit primary references; work and other groups are preserved.

People WorkGroup associations are also derived rather than stored. A positive
Allocation associates its Person with every effective context group on that
work. Additive hour reporting uses only the resolved primary topic or the
Ungrouped/Ambiguous bucket. A Person with several groups still has one roster
identity and one capacity total; zero-hour allocations create no association.

## Work priority

`WorkItem.priority` is optional and accepts only Highest, High, Medium, Low, or
Lowest. `None` is the explicit Unset state, not Medium. Priority belongs to the
individual item and is never inherited from an ancestor. It does not affect
dates, effort rollups, dependencies, capacity, person load, or future
critical-path calculations.

`planning/work_context.set_work_priority` returns one validated immutable plan
candidate. `update_work_details` includes the same value in the inspector's
single atomic draft. The Plan proxy filters exact priority values, including
Unset, and can stably order siblings Highest through Lowest with Unset last.

## Editing

Entities are frozen dataclasses. Each operation in `planning/work_items.py`
returns a validated new `ProgramPlan`. The caller adopts it only after success.
A failed operation raises `ValueError` and leaves the original snapshot intact.

| Operation | Behavior |
| --- | --- |
| `add_work_item` | Append after existing siblings; validate all references |
| `rename_work_item` | Change the title, preserving ID, parent, and position |
| `set_work_priority` | Set or clear one explicit priority without changing other planning inputs |
| `update_work_details` | Validate title, context, priority, leaf estimate, and dates into one candidate snapshot |
| `move_work_item` | Append under the new parent, preserving the item's descendants |
| `remove_work_item` | Remove a leaf; reject descendants unless explicitly confirmed |

Moving to the current parent is a no-op. Moving a Task moves its Subtasks through
their unchanged parent IDs and preserves their sibling order. Passing `None` as
the new parent makes a Task a root; Subtasks cannot become roots.

Subtree deletion requires `delete_descendants=True`, which must be a boolean.
The future UI must show what will be removed and ask the user before passing it.
Deleting a group of items does not reorder the surviving items.

Removing referenced work also requires `remove_references=True` (a boolean).
Without it, the operation reports the affected relationship and group-membership
counts and leaves the plan unchanged. Confirmed removal drops those references,
including references to descendants, and preserves surviving work and groups.

## People, estimates and dates

`planning/people.py` provides `add_person`, `rename_person`, and `remove_person`.
Names may repeat; IDs identify people. Renaming preserves identity and roster
order. Removing a person requires explicit consent for affected assignees,
availability, reservation rules, and allocations. Confirmed removal clears
current assignee references without changing imported baselines. Surviving
records retain their IDs.

`estimate_hours` is `decimal.Decimal | None`. `None` means unknown; `Decimal(0)`
means an explicit zero-hour estimate. Fractional precision is preserved, with no
rounding. Negative/non-finite values, floats, strings, and booleans are rejected.
Future UI/import adapters must parse human input into Decimal explicitly.
`set_work_estimate(plan, item_id, Decimal("1.25"))` changes the estimate;
passing `None` clears it. A leaf's entered value is its effective estimate. A
container's effective estimate is the recursive sum of its descendant leaves and
is read-only in Plan. Unknown leaves produce a known subtotal plus a missing count;
an explicit zero remains known. A container's entered/imported value stays stored
as reference data and is not added to the rollup or written over.

`set_work_dates(plan, item_id, start=..., end=...)` sets or clears both optional
dates atomically. A start-only or end-only item is valid. When both are known,
end must be on or after start. Dates outside the horizon are preserved.
`work_outside_horizon(plan)` returns affected items in order for the editor
to display; it never invents missing dates, clamps values, or shifts other work.

## WorkGroups and relationships

`planning/structure.py` provides group add/rename/remove operations and
`set_group_epics` to replace ordered membership. Groups contain Epics directly;
an Epic can appear in multiple groups. Tasks remain under their canonical Epic.
Removing a group removes its memberships and preserves all work and links. If it
is an explicit primary topic, removal first requires confirmation and clears only
those references.

`add_relationship` and `remove_relationship` manage explicit links:

- `A related_to B` is symmetric. Reversing it is a duplicate.
- `A depends_on B` means B is the prerequisite of A.
- `A blocks B` means A is the prerequisite of B. It duplicates `B depends_on A`.

Duplicate IDs, equivalent duplicate links, self-links, and missing endpoints are
rejected. A related link and a dependency between the same items can coexist.
New dependency cycles are rejected. A new fully dated link is also rejected when
its predecessor does not finish before its successor starts. Existing imported or
legacy cycles and date conflicts remain loadable and appear as calculated findings
so the user can repair them; partial edges remain explicitly unevaluated.

`planning/dependency_validation.py` is the shared source for direction, cycle,
and inclusive-date checks. Plan and Timeline date operations allow an existing
conflict to be preserved or reduced, but reject a new or larger conflict on every
incoming and outgoing edge. Clearing a required date is allowed and makes the
edge unevaluated. Unrelated existing conflicts never block a repair. No operation
automatically moves dependent work, clamps a date, or changes the imported baseline.
Hierarchy cycles remain hard domain errors.

```python
from datetime import date

from planacity.domain import PlanningHorizon, ProgramPlan, WorkItem, WorkItemType
from planacity.planning.work_items import add_work_item

plan = ProgramPlan(
    name="Aurora Test Bench",
    horizon=PlanningHorizon(date(2026, 5, 13), date(2026, 6, 24)),
)
epic = WorkItem(title="Integration", kind=WorkItemType.EPIC)
plan = add_work_item(plan, epic)
task = WorkItem(title="Build bench", kind=WorkItemType.TASK, parent_id=epic.id)
plan = add_work_item(plan, task)
assert plan.children(epic.id) == (task,)
```

Automatic scheduling and capacity remain future work. Storage is documented in
[project-file-format.md](project-file-format.md). Run domain tests with
`python -m pytest tests/domain`;
neither these tests nor the model require importing Qt.

## Work calendars (v0.4 development)

ProgramPlan contains named WorkCalendars and separate PersonCalendar references.
A calendar has an ID, name, and seven explicit Decimal weekday hours. An
assignment links one roster Person to one calendar; a calendar may be shared.
Imported Person snapshots do not contain these assignments and remain unchanged.
People shows nominal, unavailable, and available horizon hours, before program
events, reservations, or allocations. See the
[capacity model](capacity-model.md) for lifecycle rules and future deductions.

AvailabilityEvent is an immutable calculation input with a stable UUID, person
reference, inclusive period, and Decimal unavailable fraction. It records no
absence reason. Overlaps use the strongest daily fraction and return reviewable
periods and event IDs. ProgramPlan owns the events, validates their roster
references, and persists them in schema 5. People edits them while preserving IDs.
Person removal requires explicit confirmation to remove associated entries.
The [availability API](capacity-model.md#availability-calculation-api)
documents these boundaries and the partial-day interpretation.

## Recurring reservations (v0.4 calculation API)

ReservationRule is a separate domain entity for fixed hours per selected person
per anchored sprint. It is not a WorkItem, Allocation, or AvailabilityEvent.
The calculation API consumes explicit daily capacity and derives occurrences.
ProgramPlan stores rules in schema 5 and validates their roster references.
Lifecycle services return immutable candidates for preview before confirmation;
edits preserve IDs and order. Removing a person requires explicit resolution:
retain shared rules for remaining people and delete rules left empty.
The reservation wizard previews a candidate before applying it once on confirmation.
The desktop adapter supplies saved calendars and availability; it does not infer
program-event deductions or work allocations.
See [recurring reservations](capacity-wizards.md#calculation-api-8) for proration
and zero-capacity rules.

## Timeline projection (v0.3)

`planning/timeline.py` derives immutable rows from a complete `ProgramPlan` for
visualization. Rows keep work IDs, hierarchy depth, sibling order, original
dates, and effective WorkGroup memberships. Tasks and Subtasks inherit the
memberships of their containing Epic. A resolved primary group is also included,
so standalone Tasks and deliberate child overrides can be filtered without
changing hierarchy or legacy memberships.

Day coordinates are zero-based from the inclusive planning-horizon start. They
may be negative or extend past the horizon, making outside work visible without
changing or clamping its dates. A scheduled same-day item has duration one.
Start-only, end-only, and unscheduled work remain explicit states; the projection
never invents missing dates. This module has no Qt or Jira dependency.

## Imported baselines (v0.2)

`ProgramPlan.imports` holds immutable `ImportSnapshot` sources. Each snapshot
contains original headers and cells plus `ImportedWork` records with original
WorkItems, external references, status, source priority text, and person identity
snapshots. Schema 10 stores source priority separately from the canonical mapped
`WorkItem.priority`, so an unresolved custom Jira label can remain Unset without
being lost or silently interpreted as Medium.
The imported person mapping sets the current and baseline `WorkItem.assignee_id`
to the matched roster person. It does not create an Allocation or invent capacity
hours. The exact external person text and Person snapshot remain provenance.

Baseline references need not exist in current work or the current roster after
local deletion. The baseline validates its own original hierarchy independently.
Computed Changes compares that original work with current work by stable UUID.

## Allocations

ProgramPlan owns an immutable tuple of Allocation values: `id`, `work_item_id`,
`person_id`, and finite non-negative Decimal `hours`. Work and people must exist;
IDs and work/person pairs are unique. Schema 7 persists these values. Lifecycle
services preserve identity; deletion requires explicit consent for references.
Summaries recursively count each allocation ID once. They separate direct and
descendant hours, and mark legacy container allocations as incomplete or
mixed-level effort instead of discarding them. New allocations must target leaves.
When allocated leaf work gains its first child, the user must move its entered
estimate and allocations to a leaf or cancel. `resolve_container_effort` offers
the same explicit repair for existing container allocations.
See [work allocations](allocation-model.md) for summary rules and desktop editing.
