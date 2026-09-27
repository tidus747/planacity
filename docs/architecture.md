# Initial architecture

The v0.1 application edits and persists a canonical plan, horizon, hierarchy,
people, estimates, dates, groups, and relationships. See
[domain-model.md](domain-model.md) and [project-file-format.md](project-file-format.md).

| Layer | Responsibility | Allowed dependencies |
| --- | --- | --- |
| `domain` | Canonical entities and intrinsic invariants | Python standard library |
| `planning` | Editing operations and cross-entity validation | Domain, standard library |
| `persistence` | SQLite project files and JSON backups | Domain, standard library |
| `document.py` | Open/save state and the last saved snapshot | Domain, persistence, standard library |
| `ui` | Qt views and model adapters; present validation errors | Document, domain, planning, persistence, PySide6 |
| `main.py` | Application startup | UI, PySide6 |

Use normal Python calls and Qt signals. Business rules belong below the UI;
validation must also apply to loading files and non-UI callers. The Plan
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
  Schema 1 stores one validated JSON snapshot in a SQLite container. No ORM,
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
startup/shutdown. Domain, persistence, and document tests cover invalid data and
failed writes. Selective Qt tests cover hierarchy, form validation, cancellation,
keyboard save, and close/reopen/continue. Native Windows GUI acceptance and visual
checks are recorded in [getting-started.md](getting-started.md).
Building a wheel checks Python packaging; a Windows installer remains later work.

One `Session` change signal connects the document to Overview, Plan, and People.
The Qt model holds a reference to the same immutable plan snapshot. Structural
changes use model reset notifications and restore selection/expansion by UUID;
cell edits use `dataChanged` so invalid drafts and the current editor stay intact.
File dialogs and confirmation prompts are presentation concerns; persistence and
dirty-state transitions are independently testable without Qt.
