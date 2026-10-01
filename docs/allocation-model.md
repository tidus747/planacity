# Work allocation foundation

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

This API is not yet a desktop allocation workflow. Allocations are not stored in
ProgramPlan or project files by this foundation. Persistence, migration, editing,
and explicit deletion previews are tracked together in
[#71](https://github.com/tidus747/planacity/issues/71). Capacity load and overload
comparisons require a separate scheduling policy and remain later v0.4 work.
