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
