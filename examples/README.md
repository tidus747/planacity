# Aurora Test Bench

This fictional program demonstrates the v0.1 planning workflow. All names and
work are invented; it contains no real company or customer data.

Use File -> Restore JSON backup... and select aurora.planacity.json. It opens
as an unsaved copy. Save it to a new .planacity file before continuing.

The example includes two Epics, Tasks and Subtasks, a three-person roster, a
WorkGroup, relationships, fractional hour estimates, and optional dates. Missing
estimates/dates are intentional. The roster does not imply work allocations.

See [Getting started](../docs/getting-started.md) for the full workflow.

## Jira roundtrip sample

`jira-aurora.csv` is a fictional Jira-style export for v0.2. Choose Import,
keep comma delimiter, use seconds and ISO dates, and explicitly match or create
the two example people. Repeated Labels columns demonstrate source preservation.
See [the import guide](../docs/jira-import.md) and
[the export guide](../docs/jira-export.md).
