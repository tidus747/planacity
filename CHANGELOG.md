# Changelog

Meaningful user-facing changes are recorded here. Planacity uses Semantic Versioning.

## [Unreleased]

### Added

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
