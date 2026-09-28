# Desktop assets

- `icons/`: theme-aware navigation icons.
- `images/`: the Planacity application mark, wordmark, and other desktop graphics.

These folders are included in Python wheels and source distributions. Load them
with `importlib.resources` rather than paths relative to the working directory.
Navigation SVGs use `currentColor` so the UI can render them in either theme.

The Planacity mark and wordmark were supplied by the project maintainer. They are
shown on a consistent light surface so the original wordmark remains readable in
both desktop appearances.

Put large editable originals in the repository's `assets/` folder. Keep runtime
assets small; document their source and license when adding third-party graphics.
