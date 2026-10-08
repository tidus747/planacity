# Release procedure

Release tags identify reviewed commits on `main`. A branch name is not a release.
Use `v0.1.0` for Planning Foundation, `v0.2.0` for Jira Roundtrip, and
`v0.3.0` for Visual Planning. Current development is `0.4.0.dev0` with schema 11;
the v0.3.0 preparation below records the earlier schema 2 candidate. Never tag
the current v0.4 development commit as v0.3.0. Release approval must identify
the exact reviewed commit containing the intended version.

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
   git tag -a v0.3.0 -m "Planacity v0.3.0"
   git push origin v0.3.0
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

Historical preparation; use the current v0.3.0 notes for Visual Planning.

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

Historical preparation; use the current v0.3.0 notes for Visual Planning.

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

Package version `0.2.0` was prepared for Jira Roundtrip. Do not tag a current
Visual Planning commit as v0.1.0 or v0.2.0.

## v0.3.0 prepared notes

Package version `0.3.0` and the [Visual Planning notes](releases/v0.3.0.md) are
prepared for review. See the [validation record](v0.3-validation.md).
No tag or release is published by this preparation. Finalize the changelog date
in a reviewed commit before tagging the approved, tested `main` commit.
