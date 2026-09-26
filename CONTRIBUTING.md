# Contributing

Read the [architecture](docs/architecture.md) and [v0.1 breakdown](docs/v0.1-issues.md)
before starting. Pick one focused issue.
The current milestone is Planning Foundation; keep later features out of its PRs.

## Branch and pull request workflow

Use [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow):

1. Update `main` with `git pull --ff-only`.
2. Create a short-lived `feature/<name>`, `fix/<name>`, or `docs/<name>` branch.
3. Make focused commits and push the branch.
4. Open a pull request targeting `main` and wait for all CI checks to pass.
5. After maintainer approval, squash merge the PR and delete the remote feature branch.

Keep `main` ready to build; do not push directly to it. A long-lived `develop`
branch is unnecessary at this stage. Release tags use Semantic Versioning, such
as `v0.1.0`, and are created only for approved releases.

The CI workflow builds the website for every PR. After a merge to `main`, the
same workflow publishes it to GitHub Pages only if both Python and website checks
pass. Pull requests never publish the site.

## Implementation and validation

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

Use only fictional or sanitized examples. Do not commit corporate planning data,
credentials, or personal HR information. Do not rewrite public Git history.
Merges, release tags, releases, and publication require maintainer approval.
