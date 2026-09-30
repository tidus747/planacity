# Planacity

**Plan the work. Respect the capacity.**

Open-source program planning for engineering teams. Desktop-first, local-first,
and offline-capable. Planning data stays local by default.

## Current status

The source preview includes the **v0.1 planning foundation**, **v0.2 Jira roundtrip**,
and the developing **v0.3 Visual Planning** milestone. Create, edit, save, and reopen
local Program Plans. It includes a hierarchical Plan editor, a people roster,
WorkGroups, relationships, estimates in hours, optional dates, and JSON backups.
See [Getting started](docs/getting-started.md) for the complete workflow and example.

The Python [domain model](docs/domain-model.md) now supports Program Plans,
flexible horizons, validated Epic/Task/Subtask editing, a people roster, exact
hour estimates, optional dates, WorkGroups, and basic relationships. The desktop
editor and local files use this same validated model.

Switch between **Light** and **Dark** at the bottom of the sidebar or through
**View -> Appearance**. The choice is saved locally for the next launch. The first
launch uses the system appearance when Qt can detect it. Use **Ctrl+1-6** or the
View menu to switch pages: Overview, Plan, Timeline, People, Import, and Changes.
Import supports Jira CSV mapping, preview, saved profiles, and CSV export;
People supports explicit calendars and nominal horizon hours. Availability,
allocations, and recurring reservations remain planned for v0.4.
New workspaces start empty; a fictional example is
available separately in `examples/aurora.planacity.json`.

Manual planning and Jira CSV roundtrip are implemented. The Timeline shows work
using the same canonical plan, with scales, grouping, filters, and dependency
arrows. Drag bar edges or use Edit dates to adjust dates without changing effort
hours. Development now targets v0.4 Team & Capacity. Read the
[import guide](docs/jira-import.md) and [export guide](docs/jira-export.md).
Completed-version issue drafts have been retired; GitHub Issues and Milestones
retain their history. See [calendar setup](docs/capacity-model.md) for the current
workflow and remaining capacity work.
No stable packaged release is published yet.

The v0.3.0 source candidate has [prepared release notes](docs/releases/v0.3.0.md)
and a [validation record](docs/v0.3-validation.md). Publication requires a reviewed
main commit, passing CI, and a separately approved release.
Current source is `0.4.0.dev0` and saves schema 3. Schema 1/2 files open without
inferred calendars; keep a backup or use Save As for compatibility with v0.3 or earlier.

## Run from source

Use Python 3.11 or newer. Windows is the initial desktop target.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m planacity
```

On Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m planacity
```

The installed `planacity` command also launches the desktop shell. Dependency
installation requires network access; running the desktop application does not.
There is no installer or stable release yet.

## Development

With the virtual environment activated:

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
python -m build
```

Tests use Qt's offscreen platform. Linux may need `libegl1` and `libopengl0`
installed, as in CI. See [CONTRIBUTING.md](CONTRIBUTING.md) for workflow guidance.

## Repository

- `src/planacity/`: desktop entry point, UI, and boundaries for domain, planning,
  and persistence code.
- `tests/`: domain, persistence, document-state, and selective Qt interaction tests.
- `docs/`: [architecture](docs/architecture.md), release issue breakdowns, and
  user guidance.
- `examples/`: fictional Aurora program, loadable through Restore JSON backup.
- `website/`: standalone Astro Home and Roadmap pages; see its [README](website/README.md).
- `.github/`: CI and contribution templates.
- `assets/`: editable design originals; desktop runtime graphics belong in
  `src/planacity/resources/icons/` and `src/planacity/resources/images/`.
- `website/public/icons/` and `website/public/images/`: static website graphics.

## License

See [LICENSE](LICENSE) for the GNU General Public License v3.0.
