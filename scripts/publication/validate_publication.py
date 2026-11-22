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


def check_extended_evidence(root):
    hex64 = re.compile(r"[0-9a-f]{64}")
    ink = load_json(root / "public/evidence/inkling-hybrid.json")
    require(ink["weight_bytes"] == 16610543328 and hex64.fullmatch(ink["weight_sha256"]), "Inkling weight identity")
    require(all(hex64.fullmatch(v) for v in ink["source_hashes"].values()), "Inkling source hashes")
    arch = ink["architecture"]
    require(arch["physical_blocks"] == 24 and arch["logical_layers"] == 48, "Inkling block counts")
    require(
        math.isclose(
            arch["loop_core_share_of_expert_traffic_pct"],
            100 * arch["active_expert_mb_per_token_loop_core"] / arch["active_expert_mb_per_token_total"],
            abs_tol=0.1,
        ),
        "Inkling loop-core traffic share disagrees",
    )
    winner = ink["winning_configuration"]
    require("--fit off" in winner["flags"] and "ffn_.*_exps" in winner["flags"], "Inkling flags")
    q = ink["qualified_comparison"]
    cpu, auto, win = (
        [a["decode_med_tps"] for a in q[group].values()]
        for group in ("cpumoe_controls", "autofit_controls", "winner_qualified")
    )

    def pre8k(group):
        return [
            next(p["prefill_tps"] for p in a["prefill"] if p["id"] == "prefill-8192") for a in q[group].values()
        ]

    require(len(cpu) == len(auto) == len(win) == 2, "Inkling qualified arms")
    gains = ink["headline_qualified_gains"]
    checks = (
        (gains["vs_autofit_decode_pct"], win, auto),
        (gains["vs_cpumoe_decode_pct"], win, cpu),
        (gains["vs_autofit_prefill_8k_pct"], pre8k("winner_qualified"), pre8k("autofit_controls")),
        (gains["vs_cpumoe_prefill_8k_pct"], pre8k("winner_qualified"), pre8k("cpumoe_controls")),
    )
    for reported, numerator, denominator in checks:
        low = 100 * (min(numerator) / max(denominator) - 1)
        high = 100 * (max(numerator) / min(denominator) - 1)
        require(all(low - 0.06 <= v <= high + 0.06 for v in reported), "Inkling headline gain disagrees")
    require(min(win) > max(auto) > max(cpu), "Inkling winner ordering")
    boundary = q["boundary_12core_arm"]
    require(boundary["status"] == "safety-stop" and boundary["min_free_vram_mib"] < 1000, "Inkling boundary arm")
    gates = ink["acceptance_gates_b1_loop11"]
    require(
        gates["load"] is True
        and all(gates[k]["pass"] for k in ("chat", "reasoning", "tools", "context_85pct"))
        and gates["tools"]["strict_pass"]
        and gates["context_85pct"]["pct_of_ctx"] >= 85
        and gates["speed_30s"]["client_tps"] > 30
        and gates["stability_soak"]["n"] == 6
        and gates["stability_soak"]["min_tps"] > 30,
        "Inkling acceptance gates",
    )
    page = (root / "public/inkling-hybrid.html").read_text(encoding="utf-8")
    require(
        all(text in page for text in ("+37.8%", "+55.2%", "6 of 6", "evidence/inkling-hybrid.json")),
        "Inkling page is out of sync",
    )

    forge = load_json(root / "public/evidence/forge-mtp-extended.json")
    require(all(hex64.fullmatch(v) for v in forge["source_hashes"].values()), "Forge extended hashes")
    sweep = forge["draft_sweep_single_stream"]
    arms = sweep["arms"]
    require(
        [arms[name]["draft"] for name in sweep["order"]] == [0, 1, 2, 3, 0], "Forge sweep order or draft lengths"
    )
    require(
        sweep["exact_greedy_matches_A1_vs_B1"] == sweep["exact_greedy_matches_A1_vs_A2"] == "19/19",
        "Forge byte-for-byte matches",
    )

    def gain(panel):
        return 100 * (
            arms["B1"][panel]["server_decode_tps"]
            / max(arms["A1"][panel]["server_decode_tps"], arms["A2"][panel]["server_decode_tps"])
            - 1
        )

    require(round(gain("func_code"), 1) == 23.5 and round(gain("long_code"), 1) == 16.5, "Forge panel gains")
    for panel in ("code", "prose", "long_code", "func_code"):
        speeds = {name: arms[name][panel]["server_decode_tps"] for name in ("B1", "B2", "B3")}
        require(speeds["B1"] > speeds["B2"] > speeds["B3"], f"Forge k=1 is not the optimum for {panel}")
    c2 = forge["concurrency_2_bracket"]["arms"]
    controls = max(c2[name]["code_c2"]["median_aggregate_tps"] for name in ("C1", "C2"))
    require(c2["D1"]["code_c2"]["median_aggregate_tps"] < controls, "Concurrency-2 result is not negative")
    require(c2["D1"]["peak_mib"] - c2["C2"]["peak_mib"] == 522, "Concurrency-2 VRAM delta disagrees")
    forge_page = (root / "public/forge-mtp.html").read_text(encoding="utf-8")
    require(
        all(text in forge_page for text in ("23.5", "16.5", "19/19", "522 MiB", "evidence/forge-mtp-extended.json")),
        "Forge page is out of sync",
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
    check_extended_evidence(root)
    print(
        f"{len(pages)} static HTML pages, {documents} linked Markdown documents, report schemas and landing metrics passed."
    )


if __name__ == "__main__":
    main()
