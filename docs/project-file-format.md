# Project files and JSON backups (schema 9)

Planacity stores each Program Plan in a local `.planacity` SQLite file. No server
or external database is involved. The application validates the entire document
before making it editable. File extensions are a convenience, not validation.

## SQLite container

- `PRAGMA application_id = 0x504C414E` identifies Planacity.
- `PRAGMA user_version = 9` is the schema version.
- The only application table is `document` with `id INTEGER PRIMARY KEY
  CHECK(id=1)` and `payload TEXT NOT NULL`.
- Exactly one row, ID 1, contains the complete versioned JSON document below.

The application edits complete immutable plan snapshots, so a single
document payload keeps its SQLite storage and backup representations identical.
There is no partial entity loading or database-side scheduling. A normalized
schema can be introduced through an explicit migration if future query needs
justify it; changing the representation requires a new schema version.

Saving writes a sibling temporary database inside a SQLite transaction, closes
it, then atomically replaces the destination. A failed transaction or replacement
preserves the previous file. Opening uses SQLite read-only mode and cannot create
a missing file. Saving over an existing project first validates its format;
foreign, corrupt, and unsupported-version files are not overwritten.

## JSON document

Top-level fields: `format` (`"planacity"`), `schema_version` (`9`), and `plan`.

`plan` contains `id`, `name`, `description`, `horizon`, `work_items`, `people`,
`work_groups`, `relationships`, `imports`, `work_calendars`, `person_calendars`,
`availability_events`, `reservation_rules`, `estimate_preferences`, and `allocations`.
Fields match [the domain model](domain-model.md).

Each work item stores its existing identity, hierarchy, estimate, and dates plus
plain-text `description`, ordered `labels`, nullable `primary_group_id`, and
nullable `priority`. Priority is one of `highest`, `high`, `medium`, `low`, or
`lowest`; null is an explicit Unset state and is not interpreted as Medium.
Labels are non-blank canonical strings without leading/trailing whitespace and
are unique ignoring case. A primary group must exist in the same current plan.
Imported baseline WorkItems use the same representation, but editing current work
does not rewrite baseline values or raw source rows.

Each work calendar stores `id`, `name`, and seven `weekday_hours` Decimal strings,
Monday through Sunday. Each person/calendar assignment stores `person_id` and
`calendar_id`. Both must reference existing plan entities; one person may have
only one calendar. Imported Person snapshots remain separate and unchanged.

Each availability event stores `id`, `person_id`, an inclusive `period` with
`start`/`end`, and `unavailable_fraction` as a Decimal string from 0 to 1.
IDs must be unique and people must exist in the roster. Entries may extend beyond
the horizon; they are retained unchanged. No absence reason is stored.

Each reservation rule stores `id`, `name`, `person_ids`, `hours_per_person` as a
positive Decimal string, `anchor` as an ISO date, `interval_weeks` as a positive
integer, and `effective` with inclusive `start`/`end`. Person references must exist
and be distinct and non-empty. Rule IDs are unique. Only rules are stored, never
generated occurrences, Fraction results, or cached deductions. Rule order and
selected-person order are preserved.

`estimate_preferences` stores `unit` (`hours`, `days`, or `weeks`) and
`calendar_id` (a calendar UUID or null for hours). Days and weeks require an
existing calendar with positive working hours. Conversion factors derive from
that calendar, never from person assignments or an implicit default. Work and
imported baseline estimates remain Decimal hours; rounded display values and
computed conversion factors are not persisted.

Each allocation stores `id`, `work_item_id`, `person_id`, and `hours` as a
finite non-negative Decimal string. References must exist in current work and
the roster. IDs and work/person pairs must be unique. Order and precision survive
save and restore. No computed totals or inferred Jira assignments are stored.

- UUIDs are strings. Identity is preserved on load, save, and backup restore.
- Dates are ISO `YYYY-MM-DD` strings, without timestamps or timezones.
- Estimates are decimal strings such as `"4.25"`, retaining precision. `null`
  means unknown; `"0"` means an explicit zero estimate.
- Optional parent, start and end values are `null` when unset.
- Arrays preserve work, sibling, person, group-membership, and relationship order.
- All declared fields are required, including empty arrays and optional nulls.
- Unknown/missing fields, duplicate JSON keys, invalid references, invalid entity
  values, and unsupported versions are errors. No fields are silently ignored.
- In SQLite projects, `PRAGMA user_version` and the embedded JSON
  `schema_version` must match. A mixed-version file is rejected as corrupt.

See [the complete fictional example](../examples/aurora.planacity.json).
Text is UTF-8; supplied characters and whitespace are preserved.

## Backup workflow and recovery

`File -> Export JSON backup...` writes through a sibling temporary file, flushes
it, then atomically replaces the chosen backup. It does not mark an unsaved plan
as saved or change the active project path. The active SQLite project cannot be
used as the backup destination.

`File -> Restore JSON backup...` validates first and opens an unsaved document.
Normal Save/Discard/Cancel protection applies to the previous plan. Save the
restored plan to a `.planacity` file to continue working. A failed restore leaves
the current document intact. Keep backups separately from the working project.

Schema 1 files are read with an empty imports collection. Schema 1 and 2 files
open without calendars or assignments; no default hours are invented. Opening
does not modify the file. Schemas 1-3 open with empty availability collections.
Schemas 1-4 open without reservation rules; schema 4 retains its availability.
Schemas 1-5 open with Hours and no estimate reference calendar.
Schemas 1-6 open with no allocations; no assignments are inferred.
Schemas 1-7 open with empty work descriptions, labels, and primary groups.
Schemas 1-8 open with work priority unset. Imported baseline WorkItems follow
the same migration without inventing a source priority.
Saving writes schema 9; older builds cannot open the upgraded file. Keep a
backup or use Save As before upgrading.
Unsupported versions require a compatible application; do not edit version fields
to bypass validation. Concurrent editing of one project is not supported.

## External planning assistants (proposed)

The [versioned guide proposal](agent-assisted-planning.md) uses JSON backups as
the external editing boundary, never the SQLite file. A matching guide would
describe the installed writer schema and preserve identities and source data.
This is future product work: current Restore validates a document and opens an
unsaved copy; it does not compare it with the original or guarantee feasibility.

## Imported source snapshots

Each entry in `imports` contains a UUID, source name, original headers, raw rows,
and one record per row. Records contain the original WorkItem, external
reference, external person, mapped Person snapshot (or null), and original status.
Headers may repeat; every row must match their width. Baseline work forms its own
validated hierarchy. References and work IDs cannot be duplicated across sources.
Baseline records remain valid when current work or roster entries are removed.
The baseline is never rewritten by editing or exporting the current plan.
