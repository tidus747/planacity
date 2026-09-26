# Desktop assets

- `icons/`: the application icon (`app.svg`) and navigation icons.
- `images/`: runtime illustrations and other desktop graphics.

These folders are included in Python wheels and source distributions. Load them
with `importlib.resources` rather than paths relative to the working directory.
The starter application mark can be replaced with the final logo in `icons/app.svg`.
Navigation SVGs use `currentColor` so the UI can render them in either theme.

Put large editable originals in the repository's `assets/` folder. Keep runtime
assets small; document their source and license when adding third-party graphics.
