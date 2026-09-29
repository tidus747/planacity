# Release procedure

Release tags identify reviewed commits on `main`. A branch name is not a release.
Use `v0.1.0` for Planning Foundation and `v0.2.0` for Jira Roundtrip.

1. Prepare the version in `pyproject.toml`, changelog, documentation, and notes in
   a pull request. Run lint, formatting, typing, tests, package and website builds.
2. Review the complete milestone and its acceptance checks. Merge only with
   maintainer approval. Wait for CI on the resulting `main` commit to pass.
3. Record that exact commit and obtain approval to publish the release. Do not
   tag a feature branch or assume that approval to merge also approves release.
4. From a clean checkout, fetch and fast-forward `main`. Confirm its commit is
   the approved, tested commit, then create an annotated tag:

   ```sh
   git switch main
   git pull --ff-only
   git rev-parse HEAD
   git tag -a v0.1.0 -m "Planacity v0.1.0"
   git push origin v0.1.0
   ```

5. Build from the tagged commit with `python -m build`. Create a GitHub Release
   using the existing tag, the reviewed notes, wheel, and source distribution.
   Clearly state that these are Python packages, not standalone installers.
   Verify installing the wheel and launching `python -m planacity` in a fresh
virtual environment before attaching the artifacts.
   The running Windows application sets a Planacity process identity and window
   icon. A desktop icon for the executable itself requires the future standalone
   Windows package to embed an `.ico` resource.
6. Verify the published release and links. Never move a published tag; fixes get
   a new patch version. Start the next development version in a separate PR.

## v0.1.0 prepared notes

Planacity can create, edit, save, and reopen a small Program Plan locally.

- Structure Epics, Tasks, and Subtasks with estimates in hours and planned dates.
- Manage people, WorkGroups, and basic relationships.
- Save SQLite projects and export or restore JSON backups.
- Switch between light and dark appearances.
- Explore the fictional Aurora program using the getting-started guide.

Requires Python 3.11+ and PySide6. Windows is the initial desktop target; CI also
checks Linux. No standalone installer is included. Jira CSV roundtrip is planned
for v0.2; capacity calculations and recurring reservations remain future work.

Publication is pending. Replace the changelog's release-candidate label with the
actual release date in the reviewed release commit before tagging it.

## v0.2.0 prepared notes

Bring Jira work into a local Program Plan, edit its structure, and export the
agreed plan as CSV.

- Map columns, work types, estimates, dates, and external people with a preview.
- Reuse local mapping profiles.
- Preserve original source cells and baseline work in saved projects and backups.
- Review added, modified, and removed work in Changes.
- Export Jira CSV with configurable column labels, estimate units, and dates.

Schema 1 projects remain readable. Saving writes schema 2; keep an original backup
if you need to return to v0.1. Status and external assignees are preserved, not
editable. Exports omit unmapped columns, WorkGroups, and relationships; JSON
backups retain the full plan. Jira APIs, reconciliation, capacity, and standalone
installers remain deferred. No release has been published by this preparation.

Package version `0.2.0` is prepared. Before publishing, finalize the changelog date
in a reviewed commit. Run the same release checks, then tag the approved `main`
commit using `v0.2.0` in the commands above. A v0.1.0 tag is optional if the first
public release will be v0.2.0; never tag the same v0.2 commit as both versions.
