# Changelog

Meaningful user-facing changes are recorded here. Planacity uses Semantic Versioning.

## [Unreleased]

### Added

- Selective Jira CSV export with explicit flat and external-system hierarchy
  workflows. Genuine Jira keys remain separate from deterministic export-local
  Work item IDs, new work keeps a blank Jira key, and parent-first hierarchy
  export blocks excluded or missing parents instead of emitting dangling links.
  Per-row selection affects only the generated CSV, while versioned profiles
  retain the workflow and optional identity columns without storing work data.
- Stable Timeline visual identity. Scheduled bars use deterministic WorkGroup
  colors in coordinated light/dark palettes, with named neutral styles for
  Ungrouped and Ambiguous group work. Epic brackets, rounded Task bars, and slim
  Subtask bars distinguish work types without relying on color, while the named
  accessible legend and item details remain authoritative when colors collide.
- Complete Operation Moon Heist v0.4 demonstration with deterministic IDs and
  dates, five fictional people, four WorkGroups, single-person leaf assignments,
  calendars, availability, reservations, priorities, descriptions, fork/join
  dependencies, and a preserved Jira CSV baseline. The tested clean plan includes
  236 h of feasible work, exact capacity totals, a guided walkthrough, and real
  Overview, Plan, People, and Timeline captures in both appearances. The legacy
  Aurora migration example remains unchanged.
- Compact one-person assignment editing in the Plan inspector and Work allocations
  dialog. A leaf can have an owner with optional explicit capacity hours;
  reassignment preserves the sole Allocation ID, while blank hours explicitly
  removes capacity demand without clearing ownership. Epics expose a feature owner
  without hours, containers show their derived contributor team, and legacy
  multi-person leaves retain every row plus their explicit consolidation workflow.
- Canonical optional assignees for every work item. Epic assignees are feature
  owners without capacity demand; executable Tasks and Subtasks align their sole
  Allocation person when allocation ownership is edited. Jira import preserves
  mapped ownership without inventing hours, Changes reports assignee edits, and
  export preserves unchanged source identities while requiring explicit Jira
  identities for changed or new ownership. Display names are never guessed.
- Explicit consolidation for legacy multi-person leaves. Choose one existing
  Allocation to keep, preview the exact combined hours, removed IDs, whole-plan
  person loads, and resulting findings, then confirm atomically. Cancel keeps the
  complete draft unchanged; estimates, dates, dependencies, hierarchy, imports,
  and schema 10 remain untouched. The preview warns that genuine collaboration
  should be split into separately assigned work so capacity and Jira ownership
  are not misattributed.
- Single-person assignment transitions for executable leaf work. New leaves
  accept zero or one explicit Allocation, while legacy multi-person leaves keep
  every ID and exact hour, remain saveable and editable, and receive an
  actionable resolution finding. Reassignment preserves the existing Allocation;
  no estimate, dependency, Jira baseline, or file schema is rewritten.
- Explicit Jira CSV priority mapping. Map each distinct source label to a
  canonical priority or visible Unset state, reuse it in versioned profiles, and
  preserve the original source text in the imported baseline. Export previews
  show preserved, edited, unresolved, and blank results while configurable,
  unique target labels keep Jira instance conventions explicit.
- Optional canonical work priority with Highest, High, Medium, Low, Lowest, and
  an explicit Unset state. Edit priority inline or in the transactional Plan
  inspector, combine it with existing filters, and sort siblings from highest
  to lowest while preserving selection. Text labels and distinct icons remain
  readable in both appearances; priority never changes scheduling or capacity.
- Derived WorkGroup associations in People. Filter the one-row-per-person roster
  by positive whole-plan allocation context, then inspect reporting topics,
  associated work, whole-plan hours, selected-range scheduled hours, and unplaced
  demand. Ungrouped, Ambiguous group, and No assigned work remain explicit while
  filtered capacity continues to include all competing work.
- Compact Overview analysis for the fixed plan horizon. Compare planning
  capacity, scheduled work, remaining hours, and unplaced demand by person;
  review scheduled or estimated leaf effort by reporting topic; and reconcile
  nominal time, unavailability, named reservations, work, and remaining time.
  Native charts have exact accessible table peers and keep overload, unknown,
  and incomplete states explicit.
- Transactional work inspector in Plan. Edit a selected item's title,
  description, ordered labels, primary reporting topic, dates, and leaf estimate
  as one draft with Apply/Cancel. Selection and navigation changes offer
  Save/Discard/Cancel, while allocations, dependencies, findings, derived effort,
  and imported baseline values remain visible as read-only context.
- Persist plain-text descriptions, ordered labels, and an optional primary
  WorkGroup on work items. Reporting-topic resolution inherits the nearest
  explicit choice, classifies legacy single-group work, and keeps Ungrouped and
  Ambiguous cases explicit. Existing Plan and Timeline WorkGroup filters include
  this effective context without rewriting Epic memberships.
- Complete People capacity breakdown for an explicit day, week, plan horizon, or
  custom range. Roster and selected-person views reconcile named reservations and
  dated work with planning capacity, signed remaining hours, overload states, and
  unplaced demand. Source actions open the matching reservation or allocation
  editor, while unknown inputs remain visible instead of becoming free capacity.
- Actionable planning findings in Plan rows, selected-work details, and allocation
  drafts. Missing calendars, dates, estimates and assignments, allocation
  mismatches, hierarchy effort, unplaced demand, and overloads use the same
  current-plan capacity calculation. Findings remain advisory, so incomplete or
  overloaded drafts can still be saved and corrected incrementally.

- Shared dated capacity calculation across each person's calendar, recorded
  availability, recurring reservations, and scheduled work allocations. Exact
  daily and selected-period results retain overloads, source breakdowns, and
  explicit unplaced-demand gaps without changing plan data.
- Hierarchy effort rollups in Plan. Leaf estimates form read-only Epic and Task
  totals, with known subtotals and missing-estimate counts. Allocation summaries
  count each assignment once and identify direct container effort. Existing
  container estimates remain reference values, and an explicit resolution action
  moves direct effort to a new leaf without changing allocation IDs or hours.
- Product website with real application captures, a getting-started guide,
  responsive light/dark appearance, and the current implementation roadmap.
- Work allocations in Plan: store explicit hours separately from estimates and
  review allocated/remaining effort and missing estimates. Save applies the draft;
  Cancel discards it. Work/person deletion previews affected allocations, including
  hidden descendants. Imported baselines remain unchanged.
- Plan estimate entry/display in hours, days, or weeks from Planning -> Estimate
  units. Choose an explicit reference work calendar; stored hours and Jira units
  remain unchanged. Repeating display conversions are marked and edit as exact hours.
- Plan filters for title, work type, WorkGroup, and schedule state, matching
  Timeline. Matching descendants retain marked ancestor context; a count and
  Clear filters action explain the view. Deletion previews include hidden work.
- Recurring capacity wizard from Planning and People for meetings, front-office
  duties, or named reservations. Preview per-person/per-sprint hours, proration,
  overlaps, and overloads before confirming creation, edits, or deletion.
  The preview uses work calendars and recorded availability; program events and
  work allocations are not yet included.
- Dated availability editing in People with keyboard entry, calendar pickers,
  live totals, and explicit overlap previews. Entries persist with the plan;
  available hours are shown before program events, reservations, and allocations.
- Named work calendars with explicit weekday hours, per-person assignments,
  and nominal horizon hours in People, before leave, events, or reservations.

### Fixed

- Estimate units explains when a reference calendar is needed and offers calendar
  setup directly in the dialog. Calendar and unit drafts apply together with OK;
  Cancel discards both. Calendars without working hours are clearly identified.

### Changed

- Dependency links now reject new cycles and fully dated conflicts. Plan and
  Timeline date edits reject only new or worsened conflicts, with affected work
  and permitted boundaries; legacy conflicts and incomplete edges remain visible
  and repairable without automatic rescheduling.
- Development continues as 0.4.0.dev0. Projects and backups now save as schema 11
  to retain canonical work assignees alongside original imported identity and
  priority text, work context, calendars, availability, reservations, preferences,
  and allocations. Schemas 1-10 open with assignees unset; schemas 1-9 open with
  empty source-priority text; schemas 1-8 open with priority unset; schemas 1-7
  open with empty work context; schemas 1-6 open without inferred allocations.
  Schemas 1-5 open with estimates displayed in hours; keep a backup or use Save As
  for older builds.
- Removing a person now identifies affected reservation rules before confirmation.
  Shared rules retain their other people; rules left empty are removed.

## [0.3.0] - Release candidate

### Added

- Resize Timeline bar edges with day snapping, a date/duration preview, and
  cancellation. Edit dates with the keyboard or calendar without changing effort
  hours, dependent work, or the imported baseline.
- Timeline grouping by hierarchy, Epic, or WorkGroup, with title, type,
  WorkGroup, and schedule-state filters and explicit ungrouped sections.
- Directional dependency arrows with readable relationship details, filter and
  schedule explanations, and cycle detection. Arrows never change dates.
- Day, week, and month Timeline scales with calendar-aligned periods, preserved
  selection and visible dates, and a remembered local scale preference.
- A read-only desktop Timeline with aligned hierarchy labels, scheduled bars,
  partial and unscheduled states, synchronized scrolling, and stable selection.
- Calendar pickers for planning-horizon dates and optional work item start and
  end dates, while retaining ISO keyboard entry and clearable optional dates.
- Use the supplied Planacity mark as the desktop window icon and the full
  wordmark in the application sidebar.

### Changed

- Match planning-horizon and inline date calendars to the active Planacity light
  or dark appearance, including navigation, hover, focus, and selected dates.

### Fixed

- Restore readable calendar date numbers and weekday headers in both appearances
  by keeping spreadsheet padding out of date-picker cells.

- Give the hosted Python process a Planacity identity so Windows can display the
  runtime icon instead of grouping it under Python.
- Initialize the Planacity icon at application startup and use the exact
  maintainer-supplied mark and wordmark assets.
- Reject ambiguous mapping profiles with duplicate JSON fields, preserving the
  current wizard mapping instead of silently replacing settings such as estimate units.

## [0.2.0] - Release candidate

### Added

- Jira CSV import with explicit field, type, and people mapping, validation,
  preview, and reusable local mapping profiles.
- Preserved imported baselines and original CSV cells in projects and backups.
- Jira CSV export with configurable column labels, estimate units, and dates.
- Changes view for added, modified, and removed work; external references in Plan.
- Fictional Jira CSV example and import/export guides.

### Changed

- Project schema 2 retains source baselines; existing schema 1 files remain readable.
  Saving upgrades the file, so keep a backup before returning to v0.1.

## [0.1.0] - Release candidate

### Added

- Create Program Plans with arbitrary planning horizons and editable metadata.
- Edit Epic/Task/Subtask hierarchy, estimates in hours, and dates in the Plan view;
  manage a people roster, WorkGroups, and relationships.
- Save and reopen local SQLite projects, with Save As and unsaved-change protection.
- Export and restore versioned JSON backups without losing IDs or decimal precision.
- Fictional Aurora example, getting-started guide, and screenshots of both appearances.

- Dedicated locations for desktop and website graphics, with a packaged starter
  application icon and theme-aware navigation SVGs.

- Initial desktop preview with Overview, Plan, People, and Import sidebar
  navigation, overview cards, and resizable work/detail panels.
  Import describes planned v0.2 functionality.
- Light and dark appearances, switchable from the sidebar or View menu, with the
  preference remembered locally between launches.
- Initial Home and Roadmap website sources describing the Planning Foundation target.
- GitHub Pages deployment of the website after successful checks on `main`.

### Changed

- Use ordinary keyboard punctuation in the application, website, and documentation.

### Fixed

- Invalid calendar dates stay in the editor with guidance to use YYYY-MM-DD.
