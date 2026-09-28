# Planning Foundation domain model

V01-02 through V01-05 provide a small canonical model and editing API independent of
Qt, file formats, and external tools. The desktop editor and versioned local
project/backup adapters use these APIs.

## Entities

| Entity | Fields | Rules |
| --- | --- | --- |
| `PlanningHorizon` | `start`, `end` | Inclusive dates; end cannot precede start |
| `ProgramPlan` | `id`, `name`, `description`, `horizon`, `work_items`, `people`, `work_groups`, `relationships` | Valid immutable collections and references |
| `WorkItem` | `id`, `title`, `kind`, `parent_id`, `estimate_hours`, `start`, `end` | Valid hierarchy, estimates and optional dates |
| `Person` | `id`, `name` | Non-blank name; unique ID within the roster |
| `WorkGroup` | `id`, `name`, `epic_ids` | Named group of existing Epics |
| `Relationship` | `id`, `source_id`, `target_id`, `kind` | Existing distinct endpoints; no duplicate links |

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
Assignment will use separate Allocations when implemented; no single owner field
is introduced here.

## Editing

Entities are frozen dataclasses. Each operation in `planning/work_items.py`
returns a validated new `ProgramPlan`. The caller adopts it only after success.
A failed operation raises `ValueError` and leaves the original snapshot intact.

| Operation | Behavior |
| --- | --- |
| `add_work_item` | Append after existing siblings; validate all references |
| `rename_work_item` | Change the title, preserving ID, parent, and position |
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
order. Removing a person currently affects only the roster. Future Allocations
and recurring reservations must explicitly handle references before allowing
removal; there are no capacity or assignment fields yet.

`estimate_hours` is `decimal.Decimal | None`. `None` means unknown; `Decimal(0)`
means an explicit zero-hour estimate. Fractional precision is preserved, with no
rounding. Negative/non-finite values, floats, strings, and booleans are rejected.
Future UI/import adapters must parse human input into Decimal explicitly.
`set_work_estimate(plan, item_id, Decimal("1.25"))` changes the estimate;
passing `None` clears it. Parent estimates are independent, not computed rollups.

`set_work_dates(plan, item_id, start=..., end=...)` sets or clears both optional
dates atomically. A start-only or end-only item is valid. When both are known,
end must be on or after start. Dates outside the horizon are preserved.
`work_outside_horizon(plan)` returns affected items in order for the editor
to display; it never invents missing dates, clamps values, or shifts other work.

## WorkGroups and relationships

`planning/structure.py` provides group add/rename/remove operations and
`set_group_epics` to replace ordered membership. Groups contain Epics directly;
an Epic can appear in multiple groups. Tasks remain under their canonical Epic.
Removing a group removes its memberships and preserves all work and links.

`add_relationship` and `remove_relationship` manage explicit links:

- `A related_to B` is symmetric. Reversing it is a duplicate.
- `A depends_on B` means B is the prerequisite of A.
- `A blocks B` means A is the prerequisite of B. It duplicates `B depends_on A`.

Duplicate IDs, equivalent duplicate links, self-links, and missing endpoints are
rejected. A related link and a dependency between the same items can coexist.
Dependency cycles are recorded without scheduling or risk analysis in v0.1;
hierarchy cycles are always rejected. Adding a link never changes dates, hours,
or parentage. Future scheduling/validation must report dependency cycles rather
than traverse them indefinitely.

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

## Timeline projection (v0.3)

`planning/timeline.py` derives immutable rows from a complete `ProgramPlan` for
visualization. Rows keep work IDs, hierarchy depth, sibling order, original
dates, and effective WorkGroup memberships. Tasks and Subtasks inherit the
memberships of their containing Epic; standalone Tasks remain ungrouped.

Day coordinates are zero-based from the inclusive planning-horizon start. They
may be negative or extend past the horizon, making outside work visible without
changing or clamping its dates. A scheduled same-day item has duration one.
Start-only, end-only, and unscheduled work remain explicit states; the projection
never invents missing dates. This module has no Qt or Jira dependency.

## Imported baselines (v0.2)

`ProgramPlan.imports` holds immutable `ImportSnapshot` sources. Each snapshot
contains original headers and cells plus `ImportedWork` records with original
WorkItems, external references, status, and person identity snapshots.
The imported person mapping does not make `WorkItem.owner` part of the model and
does not represent an Allocation. Capacity and allocation editing remain v0.4.

Baseline references need not exist in current work or the current roster after
local deletion. The baseline validates its own original hierarchy independently.
Computed Changes compares that original work with current work by stable UUID.
