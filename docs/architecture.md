# Initial architecture

This document records the skeleton and the v0.1 boundaries. The canonical plan,
horizon, and work hierarchy are implemented; persistence remains a placeholder
and no project-file schema exists yet. See [domain-model.md](domain-model.md).

| Layer | Responsibility | Allowed dependencies |
| --- | --- | --- |
| `domain` | Canonical entities and intrinsic invariants | Python standard library |
| `planning` | Editing operations and cross-entity validation | Domain, standard library |
| `persistence` | SQLite project files and JSON backups | Domain, standard library |
| `ui` | Qt views and model adapters; present validation errors | Domain, planning, persistence, PySide6 |
| `main.py` | Application startup | UI, PySide6 |

Use normal Python calls and Qt signals. Business rules belong below the UI;
validation must also apply to loading files and non-UI callers. The future Plan
editor uses `QTreeView` and a `QAbstractItemModel` backed by the canonical model.
Do not keep separate editable copies of data for each view.

The domain validates complete immutable plan snapshots, including hierarchy
invariants. Planning operations create a candidate snapshot and return it only
after validation succeeds, preserving the original on errors. This keeps the
same invariants available to the future UI and file loaders without Qt imports.

## v0.1 decisions

- Use a `src` layout, setuptools, and Python 3.11+; PySide6 is the sole runtime
  dependency. Pytest, Ruff, mypy, and build are development tools.
- Keep the initial shell honest about unavailable functionality. Add actual
  editing and file actions as complete, tested increments.
- Organize the shell around a persistent sidebar (Overview, Plan, People, Import),
  project context, page headers, and a status bar. Plan and People use resizable
  list/detail panels. Import is an informational placeholder for v0.2. Do not
  derive domain assumptions such as quarters or single owners from UI references.
- Keep shared light/dark colors in `ui/theme.py` and empty-state layouts in
  `ui/pages.py`. Use Qt's local `QSettings` for the appearance preference, separate
  from project data; use the system appearance on first launch. Tests inject a
  temporary settings file so they do not overwrite user preferences.
- Use SQLite via `sqlite3` for local project persistence and `json` for backups.
  Decide and document the versioned file format in the storage issue. No ORM,
  database service, HTTP API, or cloud component is needed.
- Use canonical IDs and Python dates. A planning horizon is any valid date range.
  Parent/child hierarchy, WorkGroups, and relationships are distinct concepts.
- v0.1 people management does not need capacity calculations. If work assignment
  is introduced, it must use a separate Allocation entity supporting multiple
  people; do not add a single `WorkItem.owner` shortcut. Allocation editing and
  capacity accounting remain v0.4 work in this breakdown.
- Do not pre-create adapters, scenarios, calendar, reports, or milestone models.
  Add them when their roadmap release needs them.
- Astro is a static product site independent of the desktop. Node is needed only
  to develop/build the site. CI builds it for PRs and deploys the generated site
  from `main` after Python and website checks pass.

## Validation strategy

The skeleton tests navigation, theme switching and restoration, and a real Qt
startup/shutdown. Feature issues add
headless domain and persistence tests, including invalid input and failure paths.
The milestone finishes with a manual Windows create/edit/save/close/reopen check.
Building a wheel checks Python packaging; a Windows installer remains later work.
