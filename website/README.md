# Planacity website

Static Astro product site, independent of the Python desktop application.
Home and Roadmap are intentionally explicit about the project's early status.

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

## Publishing

In the repository's **Settings → Pages → Build and deployment**, select
**GitHub Actions** as the source (one-time setup).

The shared CI workflow builds the site on pull requests. Merges to `main` publish
the generated `website/dist` artifact only after both Python and website checks
pass. Deployment runs in the `github-pages` environment; feature branches and pull
requests cannot deploy. The workflow can also be run manually on `main` to retry
a deployment. No application release or tag is created by website publishing.

The published address is `https://tidus747.github.io/planacity/`. Verify both the
home page and `/planacity/roadmap/` after the first successful deployment.

References: [Astro setup](https://docs.astro.build/en/install-and-setup/) and
[GitHub Pages configuration](https://docs.astro.build/en/guides/deploy/github/).
