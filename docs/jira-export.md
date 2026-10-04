# Export Jira CSV

Choose **Import -> Export Jira CSV...**. Review the output column labels,
estimate units, and date format, then select a `.csv` destination. The delimiter
comes from the Import page. Existing-file replacement uses the file dialog's
confirmation. The active project cannot be replaced with a CSV export.

Export includes:

- Original external issue keys for imported work; blank keys for new work.
- Unique sequential row IDs, with parents before children and Parent referring
  to those row IDs.
- Canonical Epic, Task, and Sub-task types, title, estimate, and planned dates.
- Original external assignees and statuses for imported work.

Hours are exported as seconds by default. The column labels can be changed to
match your Jira configuration. Jira's importer requires its own field mapping,
date configuration, permissions, and validation. Review its preview before
applying changes. Planacity does not upload anything to Jira.

Hierarchy rollups do not replace stored export values. A container's exported
estimate is its entered/imported reference value, not its computed leaf total.
Derived totals remain visible in Plan and allocation summaries, so an export
never silently rewrites Jira effort or its imported baseline.

Atlassian documents numeric IDs for CSV hierarchy, parent-first row ordering,
seconds for Original Estimate, and issue keys for updating existing issues in
its [CSV import guide](https://support.atlassian.com/jira-cloud-administration/docs/import-data-from-a-csv-file/).
Different Jira configurations may require different mappings.

## Boundaries

This export sends the agreed work structure. It omits WorkGroups, relationships,
roster-only people, and unmapped source columns. Those stay in the local project
and JSON backup. It is not a complete project backup. The initial exporter uses
canonical types even when an external type was mapped differently on import.

Removed work is omitted from the CSV; this does not delete issues in Jira.
New work receives its real external key only after Jira creates the issue.
Export does not rewrite the source snapshot or clear the Changes view.

CSV cells retain user text, including formula-like strings. Import the file
directly into Jira; if inspecting it in spreadsheet software, import columns as
text to avoid spreadsheet interpretation changing the data.
