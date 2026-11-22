"""Check local links, static HTML safety, export structure and public data projections."""

import argparse
from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from statistics import median
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

from markdown_it import MarkdownIt
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
ASSET_TAGS = {"img", "link", "audio", "video", "source", "input", "track"}
BLOCKED_TAGS = {"script", "iframe", "object", "embed", "base", "form", "foreignobject"}
INTERACTIVE_PAGES = {"replay.html", "case-study.html", "samples.html"}
CANONICAL_ROOT = "https://somsom786.github.io/inference-audit/"


class Page(HTMLParser):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        self.in_script = False
        self.tags = Counter()
        self.anchors = set()
        self.links = []
        self.errors = []
        self.language = False
        self.viewport = False

    def handle_starttag(self, tag, attributes):
        self.tags[tag] += 1
        attrs = dict(attributes)
        if attrs.get("id"):
            self.anchors.add(attrs["id"])
        if tag == "html":
            self.language = attrs.get("lang") == "en"
        if tag == "meta":
            self.viewport |= attrs.get("name") == "viewport"
        permitted_script = (
            tag == "script"
            and self.tags[tag] == 1
            and (
                (self.filename in INTERACTIVE_PAGES and attrs == {"src": "assets/story.js", "defer": None})
                or (self.filename == "index.html" and attrs == {"src": "assets/labs.js", "defer": None})
            )
        )
        permitted_form = (
            self.filename == "index.html" and tag == "form" and attrs == {"id": "economics-model"}
        )
        if tag == "script":
            self.in_script = True
        if (tag in BLOCKED_TAGS and not (permitted_script or permitted_form)) or any(
            key.startswith("on") for key in attrs
        ):
            self.errors.append(f"Active content in {tag}")
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh":
            self.errors.append("Automatic navigation")
        if tag == "img" and not attrs.get("alt"):
            self.errors.append("Missing image alternative")
        for name in ("href", "src", "xlink:href"):
            if (
                tag == "link"
                and name == "href"
                and attrs.get("rel") == "canonical"
                and "/" not in self.filename
                and attrs.get(name)
                == CANONICAL_ROOT + ("" if self.filename == "index.html" else self.filename)
            ):
                continue
            if attrs.get(name):
                self.links.append((tag in ASSET_TAGS or name != "href", attrs[name]))

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script and data.strip():
            self.errors.append("Inline script")

    handle_startendtag = handle_starttag


def local_link(origin, href, root, pages, asset=False):
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        if asset or parts.scheme != "https":
            raise ValueError(f"Unsafe external link in {origin.name}: {href}")
        return
    target = (origin.parent / unquote(parts.path)).resolve() if parts.path else origin.resolve()
    if target.is_dir():
        target /= "index.html"
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError(f"Broken link in {origin.relative_to(root)}: {href}")
    if parts.fragment and target in pages:
        fragment = unquote(parts.fragment)
        if fragment.startswith(":~:text=") and target.parent == root / "public/reports":
            heading = re.escape(fragment.removeprefix(":~:text="))
            if re.search(rf"<h[23]>{heading}</h[23]>", target.read_text(encoding="utf-8")):
                return
        if fragment not in pages[target].anchors:
            raise ValueError(f"Missing HTML anchor in {origin.relative_to(root)}: {href}")


def check_html(web, root):
    pages = {}
    for file in sorted(web.rglob("*.html")):
        page = Page(file.relative_to(web).as_posix())
        page.feed(file.read_text(encoding="utf-8"))
        if page.errors or not page.language or not page.viewport or page.tags["h1"] != 1:
            raise ValueError(f"Invalid or unsafe {file.name}: {page.errors}")
        pages[file.resolve()] = page
    for file, page in pages.items():
        for asset, href in page.links:
            local_link(file, href, root, pages, asset)
    for file in web.rglob("*.svg"):
        for node in ElementTree.parse(file).iter():
            if node.tag.split("}")[-1].lower() in BLOCKED_TAGS:
                raise ValueError(f"Active content in SVG {file.name}")
            for key, value in node.attrib.items():
                name = key.split("}")[-1]
                if (name == "href" and not value.startswith("#")) or name.lower().startswith("on"):
                    raise ValueError(f"External/active SVG resource in {file.name}")
    for file in web.rglob("*.css"):
        source = file.read_text(encoding="utf-8")
        if re.search(r"@import|url\s*\(", source, re.IGNORECASE):
            raise ValueError(f"Unexpected CSS resource in {file.name}")
    return pages


def check_markdown(root, pages):
    # Existing release and research documents include private CLI examples as code.
    # The linked public artifacts, README and static source must all resolve.
    md_files = [
        root / "README.md",
        *sorted((root / "docs/case-study").glob("*.md")),
        *sorted((root / "docs/publication").glob("*.md")),
        root / "public/reports/README.md",
    ]
    parser = MarkdownIt("commonmark", {"html": False}).enable("table")
    for file in md_files:
        for token in parser.parse(file.read_text(encoding="utf-8")):
            for child in token.children or ():
                key = {"link_open": "href", "image": "src"}.get(child.type)
                if key:
                    local_link(file, child.attrGet(key), root, pages, child.type == "image")
    return len(md_files)


def load_json(path):
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_reports(root):
    schema = load_json(root / "docs/audit-report.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for name, count in (("qwen3-8b-audit", 446), ("gemma4-12b-audit", 50)):
        base = root / "public/reports" / name
        audit = load_json(base.with_suffix(".json"))
        validator.validate(audit)
        require(
            audit["integrity"]["recorded"] == audit["integrity"]["planned"] == count, "Report count mismatch"
        )
        require(audit["state"] == "complete" and audit["tool_version"] == "0.2.0", "Wrong capture state")
        require(
            audit["run"] == name and audit["started_utc"] is None and audit["ended_utc"] is None,
            "Unredacted provenance",
        )
        for stage in audit["stages"]:
            metrics = stage["metrics"]
            require(
                0 <= metrics["on_time"] <= metrics["valid"] <= metrics["completed"] <= metrics["offered"],
                "Invalid counts",
            )
        markup = base.with_suffix(".html").read_text(encoding="utf-8")
        require(
            "default-src 'none'" in markup and "Local demonstration audit" in markup,
            "Weak or unlabeled HTML export",
        )


def check_data(root):
    data = load_json(root / "public/evidence/measurements.json")
    forge = load_json(root / "public/evidence/forge-mtp.json")
    require(len(forge["brackets"]) == 3, "Incomplete MTP control brackets")
    for bracket, manifest in zip(forge["brackets"], ("screen", "screen", "qual"), strict=True):
        source = root / f"public/evidence/forge-{manifest}-fixtures.json"
        payload = source.read_bytes().replace(b"\r\n", b"\n")
        # The raw Windows captures used CRLF. Git's metadata may normalize the tracked copy.
        hashes = {sha256(payload).hexdigest(), sha256(payload.replace(b"\n", b"\r\n")).hexdigest()}
        require(bracket["fixture_sha256"] in hashes, "MTP workload digest disagrees")
    for bracket, expected, draft_length in zip(forge["brackets"][1:], (6.9, 7.0), (1, 1), strict=True):
        left, candidate, right = (bracket["arms"][name] for name in bracket["order"])
        require(
            [a["draft"] for a in (left, candidate, right)] == [0, draft_length, 0], "Incorrect MTP controls"
        )
        code = [a["metrics"]["code"] for a in (left, candidate, right)]
        require(all(m["n"] == 8 for m in code), "Incomplete MTP samples")
        gain = 100 * (
            code[1]["server_decode_tps"] / max(code[0]["server_decode_tps"], code[2]["server_decode_tps"]) - 1
        )
        require(round(gain, 1) == expected, "MTP code comparison disagrees")
    require(all(r["correct"] for r in candidate["retrieval"]), "MTP retrieval failed")
    require(
        sum(r["prompt_tokens"] >= 7500 for r in candidate["retrieval"]) == 2, "MTP context probes missing"
    )
    require(
        len(data["phase4"]["rows"]) == data["phase3"]["matched_strata"] == 60, "Unexpected historical strata"
    )
    require(
        len(data["transfer"]) == 3 and data["phase3"]["scheduled_minutes"] == 180,
        "Unexpected transfer design",
    )
    require(
        data["phase3"]["excluded_a2_wall_seconds"] > data["phase3"]["planned_a2_seconds"] + 3,
        "Suspended A2 was not excluded",
    )
    page = (root / "public/replay.html").read_text(encoding="utf-8")
    for r in data["phase4"]["rows"]:
        require(math.isclose(r["goodput_rps"], r["on_time"] / 300), "Replication goodput disagrees")
        require(math.isclose(r["share"], r["on_time"] / r["offered"]), "Replication SLA share disagrees")
    for item in data["transfer"]:
        controls, candidates = (
            median(r["output_tps"] for r in item["launches"] if r["stage"].startswith(arm))
            for arm in ("A", "B")
        )
        require(
            math.isclose(item["delta_pct"], 100 * (candidates / controls - 1)), "Transfer ratio disagrees"
        )
    rows = [r for r in data["phase4"]["rows"] if r["window"] == 3 and r["family"] == "all"]
    for arm in ("A", "B"):
        low, high = (fn(r["ttft_p95"] for r in rows if r["stage"].startswith(arm)) for fn in (min, max))
        span = f"{low:.3f}" if round(low, 3) == round(high, 3) else f"{low:.3f}–{high:.3f}"
        require(span in page, f"Landing TTFT fallback is out of sync ({arm})")
    for pool in ("Chat burst standard c2", "Chat burst selected c4"):
        result = data["phase2"]["comparisons"][pool]
        raw_rate = sum(r["tokens"] for r in result["launches"]) / sum(r["wall_s"] for r in result["launches"])
        require(math.isclose(raw_rate, result["tok_s"]), "Phase 2 pooled rate disagrees")
        require(
            f"{raw_rate:.2f}" in (root / "public/case-study.html").read_text(encoding="utf-8"),
            "Case study burst rate is out of sync",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    pages = check_html(root / "public", root)
    documents = check_markdown(root, pages)
    check_reports(root)
    check_data(root)
    print(
        f"{len(pages)} static HTML pages, {documents} linked Markdown documents, report schemas and landing metrics passed."
    )


if __name__ == "__main__":
    main()
