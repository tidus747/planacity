# Changelog

Meaningful user-facing changes are recorded here. Planacity uses Semantic Versioning.

## [Unreleased]

### Added

- Plan estimate entry/display in hours, days, or weeks from Planning -> Estimate
  units. Choose an explicit reference work calendar; stored hours and Jira units
  remain unchanged. Repeating display conversions are marked and edit as exact hours.
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

### Changed

- Development continues as 0.4.0.dev0. Projects and backups now save as schema 6
  to retain calendars, availability, reservation rules, and estimate preferences.
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
