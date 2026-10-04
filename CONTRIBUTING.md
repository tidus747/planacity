# Contributing

Read the [architecture](docs/architecture.md), [current roadmap](docs/roadmap.md),
and [planning decisions](docs/planning-decisions.md) before starting.
The current target is v0.4 Team & Capacity. Pick one focused issue from the next
roadmap wave; GitHub Issues track live status. Keep later features out of the PR.

## Branch and pull request workflow

Use [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow):

1. Start with a focused GitHub issue, or promote the selected roadmap slice to
   an issue before implementation begins.
2. Update `main` with `git pull --ff-only`.
3. Create a short-lived `feature/<name>`, `fix/<name>`, or `docs/<name>` branch.
4. Make focused commits and push the branch.
5. Open one pull request for that outcome, link or close the issue, and wait for
   all CI checks to pass.
6. After maintainer approval, squash merge the PR and delete the remote branch.

Keep `main` ready to build; do not push directly to it. A long-lived `develop`
branch is unnecessary at this stage. Release tags use Semantic Versioning, such
as `v0.1.0`, and are created only for approved releases.

This issue -> branch -> pull request -> CI -> maintainer approval sequence is the
default for planned features, fixes, and documentation changes. Keep each change
small enough to review as one coherent outcome. When the package version changes,
update the prominent version badge and status in `README.md` in the same pull
request.

The CI workflow builds the website for every PR. After a merge to `main`, the
same workflow publishes it to GitHub Pages only if both Python and website checks
pass. Pull requests never publish the site.

## Implementation and validation

Use ordinary keyboard punctuation in authored text: hyphens, straight quotes,
`...`, and `->` if a text arrow is needed. Avoid decorative Unicode punctuation.
Preserve accents in names and language, and preserve user/imported data exactly.

Follow the setup and check commands in [README.md](README.md). Use type hints and
small, explicit functions. Keep domain entities and planning rules independent of
Qt. Use the standard library for SQLite and JSON; avoid infrastructure or
abstractions without a current need.

Add tests for domain behavior and data integrity. Use UI tests selectively.
Run Ruff, mypy, pytest, and the package build before opening a PR; build the Astro
site for website changes. CI checks Windows and Linux with Python 3.11 and 3.13.

Describe the problem, resulting behavior, validation, and limitations in the PR.
Update documentation and the Unreleased changelog for user-facing changes.
Keep commits focused, for example `feat(plan): add work item hierarchy`.

### Reviewable implementation slices

Use the [implementation queue](docs/implementation-queue.md) to select one ready
slice. Check live issue/PR status before starting; a pending PR is not a completed
prerequisite. Record acceptance criteria and non-goals before implementation.
Do not bundle adjacent roadmap features just because they touch the same screen.

For visible UI or website changes, include real screenshots in the PR. Show both
themes when appearance is affected and before/after views for visual fixes.
Use a short recording or reproducible steps for interactions that a still image
cannot establish. Include the platform and fictional dataset. Use attachments
or commit-pinned links so images remain available after branch deletion.
Keep the evidence focused on the changed behavior; screenshots do not replace
tests or keyboard checks. Do not require images for nonvisual or docs-only work.

For documentation-only changes, check links, consistency, and the diff; runtime
tests and builds are unnecessary unless an executable/configuration file changes.
CI remains the integration gate. Update website feature claims only when the
corresponding functionality has actually shipped.

Use only fictional or sanitized examples. Do not commit corporate planning data,
credentials, or personal HR information. Do not rewrite public Git history.
Merges, release tags, releases, and publication require maintainer approval.
