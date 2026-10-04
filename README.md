<p align="center">
  <img
    src="src/planacity/resources/images/planacity-wordmark.png"
    alt="Planacity"
    width="620"
  >
</p>

<p align="center">
  <strong>Plan the work. Respect the capacity.</strong><br>
  Open-source program planning for engineering teams.
</p>

<p align="center">
  <a href="https://github.com/tidus747/planacity/actions/workflows/ci.yml">
    <img alt="CI" src="https://github.com/tidus747/planacity/actions/workflows/ci.yml/badge.svg?branch=main">
  </a>
  <img alt="Development version 0.4.0.dev0" src="https://img.shields.io/badge/version-0.4.0.dev0-075985">
  <img alt="Python 3.11 or newer" src="https://img.shields.io/badge/python-3.11%2B-3776AB">
  <a href="LICENSE">
    <img alt="GPL 3.0 license" src="https://img.shields.io/badge/license-GPL--3.0-6f42c1">
  </a>
</p>

<p align="center">
  <a href="docs/getting-started.md">Getting started</a> |
  <a href="docs/roadmap.md">Roadmap</a> |
  <a href="https://tidus747.github.io/planacity/">Website</a> |
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

## What is Planacity?

Planacity is a desktop planning workspace for engineering managers, program
managers, and technical leads. It brings planned work, dates, dependencies,
people, and available capacity into one local workspace so teams can build a
realistic plan before committing it to execution tools such as Jira.

The application is desktop-first, local-first, and offline-capable. It requires
no account, cloud service, or external database, and planning data stays local by
default.

## What you can do today

- Build and save Program Plans with Epics, Tasks, Subtasks, WorkGroups, people,
  relationships, estimates, and optional dates.
- Enter estimates in hours, days, or weeks while preserving exact stored hours.
- Import Jira CSV files through reusable mappings, keep a baseline, review
  changes, and export the agreed structure back to CSV.
- Explore work on a Timeline with day, week, and month scales, grouping, filters,
  dependency arrows, and direct date editing.
- Define personal work calendars and availability, reserve recurring capacity,
  and split work estimates into explicit allocations.
- Use light or dark appearance and keyboard navigation across the main views.

See the [getting-started guide](docs/getting-started.md) for the complete workflow
and load the fictional `examples/aurora.planacity.json` plan to explore the app.

## Current development status

| | Current state |
| --- | --- |
| Source version | `0.4.0.dev0` |
| Active milestone | v0.4 - Team & Capacity |
| Project file schema | 7 |
| Distribution | Source preview - no stable installer yet |

The v0.1 planning foundation and v0.2 Jira roundtrip are implemented. The v0.3
Visual Planning source candidate has
[prepared release notes](docs/releases/v0.3.0.md), but publication still requires
an approved release. Development now targets the shared capacity calculations,
validation, and planning context needed for v0.4.

Current reservation previews do not yet deduct program events or work
allocations, and the app does not yet calculate remaining team capacity. The
[implementation roadmap](docs/roadmap.md) and
[implementation queue](docs/implementation-queue.md) describe the ordered work;
GitHub Issues and Milestones are the live status.

Project files from schemas 1-6 remain supported. Schemas 1-5 open in hours, and
schemas 1-6 open without inferred allocations. Keep a backup or use Save As when
opening a project with an older build.

## Run from source

Planacity requires Python 3.11 or newer. Windows is the initial desktop target.

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

The installed `planacity` command also launches the desktop application.
Installing dependencies requires network access; running Planacity does not.

## Documentation

- [Getting started](docs/getting-started.md) - create, edit, save, and explore a
  plan.
- [Jira import](docs/jira-import.md) and [Jira export](docs/jira-export.md) - the
  CSV roundtrip workflow.
- [Estimate units](docs/estimate-units.md) - conversion and precision rules.
- [Calendar and capacity model](docs/capacity-model.md) - calendars,
  availability, and current limitations.
- [Allocations](docs/allocation-model.md) and
  [capacity wizards](docs/capacity-wizards.md) - distribute effort and reserve
  recurring capacity.
- [Architecture](docs/architecture.md) and [domain model](docs/domain-model.md) -
  technical design and core concepts.
- [Roadmap](docs/roadmap.md) and
  [planning decisions](docs/planning-decisions.md) - release direction and scoped
  design decisions.

## Development

With the virtual environment activated:

```sh
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
python -m build
```

Tests use Qt's offscreen platform. Linux may need `libegl1` and `libopengl0`, as
configured in CI. See [CONTRIBUTING.md](CONTRIBUTING.md) for the issue, branch,
pull request, review, and validation workflow.

## Repository layout

- `src/planacity/` - application, domain, planning, persistence, and UI code.
- `tests/` - domain, persistence, planning, and selective Qt interaction tests.
- `docs/` - user guidance, architecture, roadmap, and release records.
- `examples/` - sanitized fictional plans.
- `website/` - lightweight Astro product and documentation website.
- `.github/` - CI and contribution templates.
- `assets/` - editable design originals; runtime graphics live under
  `src/planacity/resources/`.

## License

Planacity is released under the [GNU General Public License v3.0](LICENSE).
