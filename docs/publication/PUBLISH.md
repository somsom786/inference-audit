# Publish the approved snapshot

The release uses [somsom786/inference-audit](https://github.com/somsom786/inference-audit) and the [project site](https://somsom786.github.io/inference-audit/). Keep the repository link in `docs/publication/SITE_INSTALL.md` and the canonical site URL in `scripts/publication/build_site_pages.py` and `public/index.html` in sync with hosting settings.

1. Review the claims ledger and the `repository/` folder in the staged release. Create a GitHub repository under the approved account. Use the curated snapshot as a fresh Git working tree with the intended contributor identity. Retain the private working history and research archives locally.
2. Commit the approved snapshot, push the default branch and create a `v0.2.1` tag. Draft a GitHub Release using the staged release notes. Attach the original wheel, source ZIP and site ZIP with their SHA-256 files.
3. Serve the contents of the approved site's `public/` directory at the root of a Pages deployment. If using the standard branch-based Pages setting, create a `gh-pages` branch from the static site files and configure Pages to use that branch's root. The `.nojekyll` file is included.
4. Check the deployed subpath, metadata, sample audit, source link and downloadable checksums. Publish the draft release after those checks pass.

[GitHub Pages publishing sources](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) · [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

The staging script uses a new output directory and scans selected source files and the original wheel:

```powershell
python scripts/publication/build_site_pages.py
python scripts/publication/validate_publication.py
python scripts/publication/stage_publication.py --output dist/publication/approved-0.2.1
```

For the final deployment pass, add the reviewed GitHub and Pages hostnames to the publication scanner's allowlist. Never transfer the private evidence archive or the full ChatGPT review bundle to the public repository.
