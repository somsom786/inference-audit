"""Render the final-campaign posters (Inkling hybrid, economics, research comparison).

All numbers come from the public evidence projections (inkling-hybrid.json and
forge-mtp-extended.json) or from the arithmetic of the stated economics scenario.
External research figures are transcribed from the verified literature notes and are
labelled as published by a third party. SVGs contain no scripts and no external links.
"""

from argparse import ArgumentParser
from decimal import ROUND_HALF_UP, Decimal
from html import escape
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_labs import ASSETS, PUBLIC

BG, CREAM, LIME, MUTED, RULE, PANEL = "#201f1c", "#f4f1e8", "#d4e68d", "#c2c0ad", "#6a6b57", "#2b2a26"
SERIF = "Georgia, 'Times New Roman', serif"
SANS = "Arial, Helvetica, sans-serif"
MONO = "Consolas, 'Courier New', monospace"


def fmt(value, places=2):
    quantum = Decimal(1).scaleb(-places)
    return str(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def pct(value):
    return fmt(value, 1)


def t(x, y, size, fill, text, family=SANS, weight="normal", anchor="start"):
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}">{escape(text)}</text>'
    )


def frame(title, kicker, headline, sub, body, footer):
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">',
        f"<title>{escape(title)}</title>",
        f'<rect width="1200" height="630" fill="{BG}"/>',
        f'<rect x="0" y="0" width="12" height="630" fill="{LIME}"/>',
        t(62, 54, 16, LIME, kicker, MONO, "bold"),
        t(62, 106, 42, CREAM, headline, SERIF, "bold"),
        t(62, 140, 17, MUTED, sub, MONO),
        f'<path d="M62 160H1138" stroke="{RULE}" stroke-width="1" fill="none"/>',
        body,
        f'<path d="M62 540H1138" stroke="{RULE}" stroke-width="1" fill="none"/>',
        "".join(t(62, y, size, color, text, SANS) for y, size, color, text in footer),
        "</svg>",
    ]
    return "\n".join(parts)


def inkling_svg(data, ext=None):
    q = data["qualified_comparison"]
    gains = data["headline_qualified_gains"]
    cpu = [q["cpumoe_controls"][k] for k in ("C1-cpumoe", "C2-cpumoe")]
    fit = [q["autofit_controls"][k] for k in ("A1-fit", "A2-fit")]
    win = [q["winner_qualified"][k] for k in ("B1-loop11", "B3-loop11-rep")]

    def span(arms, key):
        values = sorted(a[key] for a in arms)
        return values[0], values[-1]

    def p8k(arm):
        return next(p["prefill_tps"] for p in arm["prefill"] if p["tokens"] == 8192)

    dec_cpu, dec_fit, dec_win = (span(a, "decode_med_tps") for a in (cpu, fit, win))
    startup = sorted(a["ready_s"] for a in win)
    fit_startup = sorted(a["ready_s"] for a in fit)
    drops = sorted(100 * (1 - w["ready_s"] / f["ready_s"]) for w, f in zip(win, fit))
    startup_drop = (drops[0], drops[1])
    d_lo, d_hi = gains["vs_autofit_decode_pct"]
    p_hi, p_lo = gains["vs_autofit_prefill_8k_pct"]
    cpu_d_lo, cpu_d_hi = gains["vs_cpumoe_decode_pct"]
    cpu_p = gains["vs_cpumoe_prefill_8k_pct"]
    prefill_lo, prefill_hi = 1 + min(cpu_p) / 100, 1 + max(cpu_p) / 100
    cols = [
        (62, f"+{pct(d_hi)}%", "decode vs auto-fit", f"({pct(d_lo)}% to {pct(d_hi)}% across the bracket)"),
        (442, f"+{pct(p_hi)}%", "8K prefill vs auto-fit", f"({pct(p_lo)}% to {pct(p_hi)}%)"),
        (
            822,
            f"\u2212{round(startup_drop[0])}\u2013{round(startup_drop[1])}%",
            "startup vs auto-fit",
            f"({fmt(startup[0])}\u2013{fmt(startup[1])} s vs {fmt(fit_startup[0])}\u2013{fmt(fit_startup[1])} s)",
        ),
    ]
    body = []
    for x, big, label, note in cols:
        body += [
            t(x, 232, 62, LIME, big, SERIF, "bold"),
            t(x, 262, 18, CREAM, label, SANS, "bold"),
            t(x, 284, 14, MUTED, note, SANS),
        ]
    body.append(t(62, 322, 13, MUTED, "DECODE tok/s, single stream, qualified interleaved bracket", MONO, "bold"))
    top = max(dec_win[1], dec_fit[1], dec_cpu[1])
    rows = [
        ("--cpu-moe", dec_cpu, MUTED),
        ("auto-fit (safe)", dec_fit, MUTED),
        ("loop-core-11 (ours)", dec_win, LIME),
    ]
    for i, (name, (lo, hi), color) in enumerate(rows):
        y = 340 + i * 50
        width = 560 * hi / top
        body += [
            t(62, y + 23, 16, CREAM, name, SANS, "bold" if color == LIME else "normal"),
            f'<rect x="250" y="{y}" width="{width:.1f}" height="32" fill="{color}"/>',
            t(250 + width + 14, y + 23, 17, CREAM, f"{fmt(lo)}\u2013{fmt(hi)}", MONO, "bold"),
        ]
    footer = [
        (566, 15, CREAM, f"6/6 local-ai-registry gates \u00b7 loop core blk.6..17 = {data['architecture']['loop_core_share_of_expert_traffic_pct']}% of active expert bytes \u00b7 vs --cpu-moe: +{round(cpu_d_hi)}% decode, {fmt(prefill_lo, 1)}\u2013{fmt(prefill_hi, 1)}x 8K prefill"),
        (592, 13, MUTED, "RTX 4070 12 GB + 64 GB DDR5-6000, llama.cpp b12588, 16K context, f16 KV. Single stream, one machine; not a general guarantee."),
    ]
    sub = f"Inkling-2-Mini UD-Q4_K_M ({fmt(data['weight_bytes'] / 1e9)} GB) \u00b7 RTX 4070 12 GB \u00b7 llama.cpp {data['engine']['build']}"
    return frame(
        "Inkling-2-Mini on a 12 GB RTX 4070 with loop-aware tensor placement",
        "INFERENCE AUDIT LABS \u00b7 MEASURED RESULT",
        "More Inkling from the same 12 GB GPU",
        sub,
        "\n".join(body),
        footer,
    )


def economics_svg():
    monthly = 50_000
    yearly = monthly * 12
    scenarios = [(30, True), (50, False), (100, False)]
    body = [t(62, 196, 13, MUTED, f"ILLUSTRATIVE CONDITIONAL SCENARIO \u00b7 ${monthly:,}/month GPU spend (${yearly:,}/year) held at constant demand", MONO, "bold")]
    for i, (gain, hero) in enumerate(scenarios):
        x = 62 + i * 368
        fewer = 100 * (1 - 1 / (1 + gain / 100))
        saved = yearly * fewer / 100
        body += [
            f'<rect x="{x}" y="212" width="340" height="300" fill="{PANEL}" stroke="{LIME if hero else RULE}" stroke-width="{2 if hero else 1}"/>',
            t(x + 24, 250, 16, MUTED, f"+{gain}% qualified throughput", MONO, "bold"),
            t(x + 24, 330, 78, LIME if hero else CREAM, f"{fmt(fewer, 1)}%", SERIF, "bold"),
            t(x + 24, 368, 19, CREAM, "fewer GPU-hours", SANS, "bold"),
            f'<path d="M{x + 24} 390H{x + 316}" stroke="{RULE}" fill="none"/>',
            t(x + 24, 428, 15, MUTED, "up to", SANS),
            t(x + 24, 466, 36, LIME if hero else CREAM, f"${round(saved):,}/yr", SERIF, "bold"),
            t(x + 24, 494, 14, MUTED, "conditional, at constant demand", SANS),
        ]
    footer = [
        (566, 15, CREAM, "GPU-hours saved = 1 \u2212 1/(1 + g). Applies only if the added throughput is qualified on your workload."),
        (592, 13, MUTED, "Not a measured customer saving. Depends on billing granularity, scheduling, deadlines and quality gates. Scenario arithmetic only."),
    ]
    return frame(
        "Illustrative economics of qualified inference throughput gains",
        "INFERENCE AUDIT LABS \u00b7 ECONOMICS",
        "More inference. Same GPU budget.",
        "What qualified throughput gains could be worth at $50K/month",
        "\n".join(body),
        footer,
    )


def research_svg(data, ext):
    q = data["qualified_comparison"]
    gains = data["headline_qualified_gains"]
    fit_hi = max(gains["vs_autofit_decode_pct"])
    p_hi = max(gains["vs_autofit_prefill_8k_pct"])
    arms = ext["draft_sweep_single_stream"]["arms"]
    controls = [arms["A1"]["func_code"]["server_decode_tps"], arms["A2"]["func_code"]["server_decode_tps"]]
    k1 = arms["B1"]["func_code"]["server_decode_tps"]
    structured = 100 * (k1 / max(controls) - 1)
    win = [q["winner_qualified"][k]["ready_s"] for k in ("B1-loop11", "B3-loop11-rep")]
    fit = [q["autofit_controls"][k]["ready_s"] for k in ("A1-fit", "A2-fit")]
    startup = (100 * (1 - win[0] / fit[0]), 100 * (1 - win[1] / fit[1]))
    mine = [
        (f"+{pct(fit_hi)}% decode", "Inkling-2-Mini vs auto-fit, RTX 4070"),
        (f"+{pct(p_hi)}% prefill", f"Inkling-2-Mini 8K; startup \u2212{round(startup[0])}\u2013{round(startup[1])}%"),
        (f"+{pct(structured)}% code", "Forge Qwen3.5-9B MTP k=1, structured Python"),
        ("+57.7% burst", "Qwen3-8B 2\u21924 slots; mixed trace regressed"),
    ]
    theirs = [
        ("2.1\u00d7 prefill", "Arc B390 iGPU \u00b7 256K prefill 297 \u2192 628 tok/s"),
        ("+44.2% decode", "RTX 3090 \u00b7 MTP 45.5 \u2192 65.6 tok/s"),
        ("\u221262% startup", "Arc B390 iGPU \u00b7 113 \u2192 43 s"),
        ("229.1 tok/s", "4\u00d7 H200 NVL \u00b7 DeepSeek-V4.1-Flash \u00b7 was crashing"),
    ]
    body = [
        f'<rect x="62" y="176" width="510" height="344" fill="{PANEL}" stroke="{LIME}" stroke-width="2"/>',
        f'<rect x="628" y="176" width="510" height="344" fill="{PANEL}" stroke="{RULE}" stroke-width="1"/>',
        t(84, 206, 14, LIME, "MEASURED BY INFERENCE AUDIT LABS", MONO, "bold"),
        t(84, 226, 13, MUTED, "RTX 4070 12 GB, our harness, repeated brackets", SANS),
        t(650, 206, 14, CREAM, "PUBLISHED EXTERNAL RESEARCH", MONO, "bold"),
        t(650, 226, 13, MUTED, "Sybil Solutions \u00b7 third-party, not reproduced by us", SANS),
    ]
    for col_x, rows, color in ((84, mine, LIME), (650, theirs, CREAM)):
        for i, (big, cap) in enumerate(rows):
            y = 280 + i * 64
            body += [t(col_x, y, 32, color, big, SERIF, "bold"), t(col_x, y + 22, 14, MUTED, cap, SANS)]
    footer = [
        (566, 14, CREAM, "Sybil Solutions / 0xSero published the right-hand results independently. They are not a customer or affiliate of Inference Audit Labs,"),
        (586, 14, CREAM, "and this poster is not an endorsement. Hardware, models and engines differ, so the two columns are not a head-to-head comparison."),
        (610, 12, MUTED, "Source: github.com/sybil-solutions (local-ai-registry PR 453, trellis-serve, inference-optimisation-skill). Not independently reproduced."),
    ]
    return frame(
        "Measured results by Inference Audit Labs beside published external research",
        "INFERENCE AUDIT LABS \u00b7 CONTEXT",
        "Measured here vs published elsewhere",
        "Two separate bodies of work, labelled by who measured them",
        "\n".join(body),
        footer,
    )


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument(
        "--highres-dir",
        type=Path,
        default=Path(__file__).resolve().parents[4] / "final-campaign" / "posters",
    )
    args = parser.parse_args()
    data = json.loads((PUBLIC / "evidence/inkling-hybrid.json").read_text(encoding="utf-8"))
    ext = json.loads((PUBLIC / "evidence/forge-mtp-extended.json").read_text(encoding="utf-8"))
    jobs = {
        "inkling-hybrid": inkling_svg(data),
        "economics-opportunity": economics_svg(),
        "research-comparison": research_svg(data, ext),
    }
    args.highres_dir.mkdir(parents=True, exist_ok=True)
    for name, svg in jobs.items():
        lowered = svg.lower()
        assert "<script" not in lowered and "href" not in lowered and "onload" not in lowered
        assert svg.count("http") == 1  # only the XML namespace
        (ASSETS / f"{name}-poster.svg").write_text(svg + "\n", encoding="utf-8")
    from playwright.sync_api import sync_playwright

    with TemporaryDirectory() as temp, sync_playwright() as runtime:
        browser = runtime.chromium.launch(
            executable_path=args.browser, args=["--disable-gpu", "--disable-webgl"]
        )
        for name, svg in jobs.items():
            wrapper = Path(temp) / f"{name}.html"
            wrapper.write_text("<style>body{margin:0}</style>" + svg, encoding="utf-8")
            for scale, path in (
                (1, ASSETS / f"{name}-social.png"),
                (2, args.highres_dir / f"{name}-2400.png"),
            ):
                page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=scale)
                page.goto(wrapper.as_uri())
                page.locator("svg").screenshot(path=path)
                page.close()
        browser.close()


if __name__ == "__main__":
    main()
