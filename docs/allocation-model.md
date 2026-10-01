# Work allocations

An `Allocation` is an explicit link between one WorkItem and one Person, with
its own UUID and finite, non-negative Decimal hours. Several people can share
one task, such as 60 hours for Alex and 40 hours for Sam on a 100-hour task.
It is separate from work ownership, Jira assignees, and personal availability.

The v0.4 calculation foundation in [#70](https://github.com/tidus747/planacity/issues/70)
provides `domain.allocation.Allocation` and the pure
`planning.allocations.validate_allocations` / `summarize_allocations` functions.
Pass a ProgramPlan and an immutable tuple of candidate allocations. References
must exist in the plan. Allocation IDs and work/person pairs must be unique;
edit an existing allocation instead of adding another entry for the same pair.

The summary returns all work and people in canonical plan/roster order. It sums
only explicitly allocated hours. For each work item:

- `allocated_hours` is the exact sum of its allocations.
- `remaining_hours` is estimate minus allocated hours, or None for an unknown
  estimate. A negative value identifies allocation beyond the estimate.
- `missing_estimate` identifies unknown estimates, separately from zero.
- `unassigned` means no positive effort has been allocated. A zero-hour entry is
  retained as explicit data but does not make work positively allocated.

Partial allocation, allocation beyond an estimate, and work without an estimate
are allowed so incomplete plans remain visible. The calculation never changes
estimates, rescales allocations, assigns imported users, or rewrites baselines.
Decimal totals retain all input precision even under a low caller precision.

Parent and child work are independent. Their estimates and allocations do not
inherit or roll up automatically. Allocating effort at both levels counts both
explicit entries; decide which work represents the effort being planned.
Dates outside the horizon do not discard allocations from these whole-work
totals. No calendar-hour defaults, date distribution, capacity comparison, or
individual performance measure is implied.

## Edit allocations in Plan

Select a work item, then choose **Work allocations...** in Selected work.
Add a roster member and explicit hours, or select an existing row to Edit or
Remove it. Hours remain hours even when Plan displays estimates in days or weeks.
Save applies the complete draft. Cancel or Escape discards it. Use Tab to move
between controls and Alt+A / Alt+E / Alt+R for allocation actions.

The summary reports estimate, allocated effort, and remaining effort for this
work. Missing estimates and allocations exceeding the estimate remain visible.
These totals do not compare against calendar capacity or distribute work by date.

Deletion of a person or work item previews affected allocations and requires
confirmation. Deleting a parent includes hidden descendants. Surviving allocation
IDs remain stable. Jira assignees never create allocations automatically, and
allocation edits do not change imported baselines or Jira CSV effort units.

ProgramPlan stores allocations in schema 7 SQLite projects and JSON backups.
Schemas 1-6 load with an empty collection. Keep an original backup or use Save As
if an older build must still open the project.

![Work allocations in light appearance](images/work-allocations-light.png)
![Work allocations in dark appearance](images/work-allocations-dark.png)

For a quick evaluation, split a 100-hour task into 60 and 40 hours, save and reopen,
then edit one entry and cancel. Check that the saved totals remain unchanged.
Capacity load and overload comparisons require a scheduling policy and remain
separate work.
