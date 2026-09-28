# Changelog

Meaningful user-facing changes are recorded here. Planacity uses Semantic Versioning.

## [Unreleased]

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
