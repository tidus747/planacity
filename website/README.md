# Planacity website

Static Astro product site, independent of the Python desktop application.
Product, Get started, and Roadmap are explicit about the project's early status.

## Design and content

The site uses an original Astro/CSS layout inspired by the clean product and
documentation navigation of [CelestialDocs](https://github.com/HYP3R00T/CelestialDocs).
The full template is not installed or vendored: React, Tailwind, and an Astro
major-version migration are unnecessary for these three static pages. No new
runtime dependency, remote font, analytics, or external rendering service is used.

`src/layouts/Page.astro` owns navigation, metadata, and the appearance switch.
`src/styles/site.css` defines responsive layouts and light/dark tokens.
`src/components/AppScreenshot.astro` displays existing app captures in the selected
appearance. Source captures come from `../docs/images/`; the logo comes from
`../src/planacity/resources/images/`. Astro emits their base-prefixed asset URLs.
These are project-owned assets; no CelestialDocs code or artwork was copied.

The site follows system appearance initially, then saves an explicit choice in
local storage. Storage being unavailable does not block the switch. Without
JavaScript, system colors, navigation, and all content remain available.

Keep the roadmap aligned with `../docs/roadmap.md` and GitHub Issues. Label
preview-only functionality honestly; do not offer an installer until one exists.
The detailed workflow guides remain in repository Markdown to avoid duplicating
the whole documentation collection.

Use Node.js 22.12+ (Node 22 LTS is used in CI):

```sh
cd website
npm ci
npm run dev
npm run build
npm run preview
```

Open the local URL printed by Astro, including `/planacity/`. Output is written
to `dist/`. The configuration targets `https://tidus747.github.io/planacity/`;
update `site` and `base` for a different repository or custom domain.
Internal links include the configured base path.

Put static website icons in `public/icons/` and other graphics in `public/images/`.
Reference them using `import.meta.env.BASE_URL` so they also work under the
repository's `/planacity/` path. Desktop assets live separately in
`src/planacity/resources/`; editable design originals belong in `assets/`.

## Publishing

In the repository's **Settings -> Pages -> Build and deployment**, select
**GitHub Actions** as the source (one-time setup).

If a separate `pages build and deployment` run fails with "Invalid YAML front
matter" in an `.astro` file, check that source setting. The branch-based Pages
builder uses Jekyll, which cannot build Astro source files. Keep the existing
Actions workflow as the publisher; do not change Astro front matter to YAML.
After correcting the source, run `CI` manually on `main` and verify its
`deploy-pages` job. Historical failed Jekyll runs remain visible in Actions.

The shared CI workflow builds the site on pull requests. Merges to `main` publish
the generated `website/dist` artifact only after both Python and website checks
pass. Deployment runs in the `github-pages` environment; feature branches and pull
requests cannot deploy. The workflow can also be run manually on `main` to retry
a deployment. No application release or tag is created by website publishing.

The published address is `https://tidus747.github.io/planacity/`. Verify the
home page, `/planacity/docs/`, and `/planacity/roadmap/` after deployment.

Before review, check those three routes at desktop and mobile widths, keyboard
navigation, appearance persistence across pages/reloads, system-default colors,
and behavior without JavaScript or local storage. Inspect all screenshots and
verify there is no page-wide horizontal overflow or missing asset. The build
must work with the repository base path, not just at `/`.

Review captures: [light](../docs/images/website-light.png) and
[dark](../docs/images/website-dark.png). These show the real rendered website,
not a design mockup.

References: [Astro setup](https://docs.astro.build/en/install-and-setup/) and
[GitHub Pages configuration](https://docs.astro.build/en/guides/deploy/github/).
