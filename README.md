# Planacity

**Plan the work. Respect the capacity.**

Open-source program planning for engineering teams. Desktop-first, local-first,
and offline-capable. Planning data stays local by default.

## Current status

This repository is the initial **v0.1 — Planning Foundation** skeleton, not a
finished planning application. It includes a launchable PySide6 shell with a left
sidebar, Overview cards, Plan and People workspaces with resizable details panels,
and an Import roadmap page, plus development checks and a small static website.
Creating, editing, saving, and reopening plans are still planned work.

Switch between **Light** and **Dark** at the bottom of the sidebar or through
**View → Appearance**. The choice is saved locally for the next launch. The first
launch uses the system appearance when Qt can detect it. Use **Ctrl+1–4** or the
View menu to switch pages. The Import page describes planned v0.2 work; capacity
remains planned for v0.4. Empty workspaces contain no fabricated planning data.

The v0.1 goal is to build a small Program Plan manually, close Planacity, reopen it,
and continue working. See the [issue breakdown](docs/v0.1-issues.md) for the work
needed to reach that goal. Jira, timelines, capacity calculations, and other later
roadmap features are outside this skeleton.

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
- `tests/`: application smoke tests; domain tests will accompany each feature.
- `docs/`: [architecture](docs/architecture.md) and [v0.1 issues](docs/v0.1-issues.md).
- `examples/`: sample-program brief, pending the project file format.
- `website/`: standalone Astro Home and Roadmap pages; see its [README](website/README.md).
- `.github/`: CI and contribution templates.

## License

See [LICENSE](LICENSE) for the GNU General Public License v3.0.
