"""Build static GitHub Pages-compatible articles from the repository's Markdown."""

from html import escape
from pathlib import Path
import posixpath
import re
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "public"
SITE_URL = "https://somsom786.github.io/inference-audit/"
PAGES = {
    "docs/case-study/INFERENCE_OPTIMIZATION_CASE_STUDY.md": (
        "research.html",
        "RTX 4070 inference case study",
    ),
    "docs/publication/CLAIMS_LEDGER.md": ("claims.html", "Public measurement claims"),
    "docs/publication/EVIDENCE_INVENTORY.md": ("evidence.html", "Research evidence inventory"),
    "docs/publication/REPRODUCE.md": ("reproduce.html", "Reproduce the proof package"),
    "docs/publication/PUBLICATION_CHECKLIST.md": ("publication-checklist.html", "Publication checks"),
    "docs/publication/PUBLISH.md": ("publish.html", "Publication instructions"),
    "docs/publication/SITE_INSTALL.md": ("install.html", "Install Inference Audit"),
    "validation/INDEPENDENT_REPLICATION.md": ("replication.html", "Independent workload replication"),
    "docs/VALIDATION.md": ("validation.html", "Product acceptance checks"),
}
ASSET_ALIASES = {
    "public/reports/README.md": "samples.html",
    "validation/phase3-recount.json": "evidence/measurements.json",
    "validation/replication-recount.json": "evidence/measurements.json",
    "README.md": "install.html",
    "LICENSE": "license.txt",
    "reports/local-qwen-020/audit.html": "reports/qwen3-8b-audit.html",
    "reports/local-gemma-020/audit.html": "reports/gemma4-12b-audit.html",
}


def link_target(source, href):
    parts = urlsplit(href)
    if parts.scheme or parts.netloc or not parts.path:
        return href
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source), parts.path))
    if target in PAGES:
        url = PAGES[target][0]
    elif target in ASSET_ALIASES:
        url = ASSET_ALIASES[target]
    elif target.startswith("public/"):
        url = target.removeprefix("public/")
    elif target.startswith("docs/case-study/assets/"):
        url = "assets/" + Path(target).name
    else:
        raise ValueError(f"Unmapped static link {href} in {source}")
    fragment = "contact" if target == "README.md" and parts.fragment == "contact" else parts.fragment
    if target == "README.md" and parts.fragment == "quick-start":
        fragment = "install-and-run-a-scoped-audit"
    return url + ("#" + fragment if fragment else "")


def article(source, document):
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = parser.parse(document)
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            slug = re.sub(r"[^a-z0-9 -]", "", tokens[index + 1].content.lower())
            token.attrSet("id", re.sub(r" +", "-", slug.strip()))
        for child in token.children or ():
            key = {"link_open": "href", "image": "src"}.get(child.type)
            if key:
                child.attrSet(key, link_target(source, child.attrGet(key)))
    body = parser.renderer.render(tokens, parser.options, {})
    return body.replace("<table>", '<div class="table-scroll"><table>').replace("</table>", "</table></div>")


def main():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8").rstrip() + "\n"
    (WEB / "license.txt").write_text(license_text, encoding="utf-8", newline="\n")
    for source, (page, title) in PAGES.items():
        markdown = (ROOT / source).read_text(encoding="utf-8-sig")
        if source == "docs/VALIDATION.md":
            markdown = markdown.split("## Reproduce offline")[0]
            markdown = (
                "\n".join(
                    line
                    for line in markdown.splitlines()
                    if not line.startswith(("[Qwen sweep report]", "[Qwen restart report]"))
                )
                + "\n\n[Public sample audits](../public/reports/README.md)\n"
            )
        if source == "validation/INDEPENDENT_REPLICATION.md":
            markdown = markdown.split("## Evidence and reproduction")[0] + (
                "\n\n[How to reproduce the public comparisons](../docs/publication/REPRODUCE.md)\n"
            )
        body = article(source, markdown)
        name = escape(title, quote=True)
        (WEB / page).write_text(
            f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{name} from the Inference Audit public proof package.">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{SITE_URL}{page}">
  <meta property="og:title" content="{name} | Inference Audit">
  <title>{name} | Inference Audit</title>
  <link rel="canonical" href="{SITE_URL}{page}">
  <link rel="stylesheet" href="assets/story.css">
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="v-header"><div class="v-wrap v-header-row">
    <a class="v-brand" href="index.html"><span class="v-mark" aria-hidden="true"></span>Inference Audit</a>
    <nav aria-label="Main"><a href="case-study.html">Case study</a><a href="samples.html">Sample audits</a><a href="install.html">Install</a></nav>
    <a class="v-source" href="https://github.com/somsom786/inference-audit">GitHub <span aria-hidden="true">↗</span></a>
  </div></header>
  <main class="v-wrap v-article" id="main" tabindex="-1">
{body}
  </main>
  <footer class="v-footer"><div class="v-wrap v-footer-row"><a class="v-brand" href="index.html"><span class="v-mark" aria-hidden="true"></span>Inference Audit</a><nav aria-label="Research sources"><a href="research.html">Full research</a><a href="claims.html">Claims ledger</a><a href="reproduce.html">Reproduce</a><a href="license.txt">MIT license</a></nav><span>Public preview <a href="https://github.com/somsom786/inference-audit/releases/tag/v0.2.1">0.2.1</a></span></div></footer>
</body>
</html>
""",
            encoding="utf-8",
            newline="\n",
        )
    print(f"Rendered {len(PAGES)} static articles.")


if __name__ == "__main__":
    main()
