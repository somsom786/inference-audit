# Publish the approved snapshot

The public repository is [somsom786/inference-audit](https://github.com/somsom786/inference-audit). The [project site](https://somsom786.github.io/inference-audit/) serves static files from the root of the `gh-pages` branch.

1. Review the presentation changes and the claims ledger. Apply approved source changes on a checkout based on public `main`. Apply the reviewed static changes at the root of a separate checkout based on `gh-pages`.
2. Keep the report exports and public measurement projection byte-for-byte intact for a presentation refresh. Keep the `.nojekyll` marker at the deployment root.
3. After push approval, verify the deployed subpath, metadata, navigation, interactive charts and sample audits. A presentation refresh leaves the current product release and tag in place.

[GitHub Pages publishing sources](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) · [GitHub release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

Regenerate the Markdown-backed reference pages and check the static package from the repository root:

```powershell
python scripts/publication/build_site_pages.py
python scripts/publication/validate_publication.py
```

The interactive homepage, case study and audit library are authored directly in `public/`. Keep private evidence, experimental source changes and review archives in the local workspace.
