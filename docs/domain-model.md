# Planning Foundation domain model

V01-02 and V01-03 provide a small canonical model and editing API independent of
Qt, file formats, and external tools. These APIs are implemented; the desktop
editor and persistence are separate upcoming issues.

## Entities

| Entity | Fields | Rules |
| --- | --- | --- |
| `PlanningHorizon` | `start`, `end` | Inclusive dates; end cannot precede start |
| `ProgramPlan` | `id`, `name`, `description`, `horizon`, `work_items` | Non-blank name and a valid hierarchy |
| `WorkItem` | `id`, `title`, `kind`, `parent_id` | Non-blank title and a supported kind |

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

WorkGroups and relationships will be separate concepts, not extra hierarchy
levels. Assignment will use separate Allocations when implemented; no single
owner field is introduced here.

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

No project-file schema, scheduling, estimates, people, capacity, or imports are
implemented by these two issues. Run their tests with `python -m pytest tests/domain`;
neither these tests nor the model require importing Qt.
