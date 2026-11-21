"""Build the Labs metrics projection, original silicon plate and sharing posters."""

from argparse import ArgumentParser
from html import escape
import json
from pathlib import Path
from tempfile import TemporaryDirectory

PUBLIC = Path(__file__).resolve().parents[2] / "public"
ASSETS = PUBLIC / "assets"


def silicon():
    paths = []
    for i in range(13):
        x = i * 19
        y = 260 + (i % 2) * 13
        paths.append(f'<path d="M{76 + x} {y}l-39 25v48l-26 15" stroke="#6e7953"/>')
        paths.append(f'<path d="M{310 + x} {229 - y / 12:.1f}l27 -20h63l38 -28" stroke="#676b53"/>')
    for i in range(34):
        v = 14 + i * 7
        paths.append(f'<path d="M{v} 0v560M0 {v}h730" stroke="#99927e" opacity=".075"/>')
    inside = "".join(paths)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 730 560" width="730" height="560">
<title>Silicon package technical plate</title>
<defs><pattern id="etch" width="5" height="5" patternUnits="userSpaceOnUse"><path d="M0 5L5 0" stroke="#a1a17b" opacity=".27"/></pattern></defs>
<path fill="#252721" d="M0 0h730v560H0z"/>
<g fill="none">{inside}</g>
<g fill="none" stroke="#777d5e"><path d="M49 393l348-221 281 139-354 205z"/><path d="M67 401l331-207 253 121-326 189z"/></g>
<g stroke-width="1.6" stroke-linejoin="round">
<path d="M81 306l318-196 240 110v29L325 444 81 336z" fill="#33392a" stroke="#89926c"/>
<path d="M81 306l244 110 314-196-240-110z" fill="#404534" stroke="#89926c"/>
<path d="M109 303l286-177 214 97-285 177z" fill="url(#etch)" stroke="#8ca172"/>
<path d="M247 260l155-95 112 51v25l-151 95-116-52z" fill="#505c37" stroke="#c9d697"/>
<path d="M247 260l155-95 112 51-151 96z" fill="#a3b471" stroke="#d6e5a2"/>
<path d="M263 259l138-84 96 43-136 84z" fill="#636d43" stroke="#dce9a9"/>
<path d="M263 259l138-84 96 43-136 84z" fill="url(#etch)" stroke="#dce9a9"/>
<path d="M291 259l108-67 67 30-107 66z" fill="#b7ca7d" stroke="#e3eab4"/>
<path d="M310 260l88-54 48 21-88 55z" fill="#879950" stroke="#dde9a6"/>
</g>
<g fill="none" stroke="#c8d69e" opacity=".85">
<path d="M402 165V112l51-33h176M247 260l-47-24H84M505 246l42 20h93M325 444v28h-78"/>
<circle cx="629" cy="79" r="3"/><circle cx="84" cy="236" r="3"/><circle cx="640" cy="266" r="3"/><circle cx="247" cy="472" r="3"/>
</g>
<g fill="#d9ddb9" font-size="13" font-family="monospace"><text x="489" y="67">SILICON DIE</text><text x="64" y="222">SUBSTRATE</text><text x="493" y="483">AD104 / SCHEMATIC</text></g>
</svg>"""


def project():
    data = json.loads((PUBLIC / "evidence/measurements.json").read_text(encoding="utf-8"))
    source = data["phase2"]["comparisons"]
    two = source["Chat burst standard c2"]["tok_s"]
    four = source["Chat burst selected c4"]["tok_s"]
    rows = [r for r in data["phase4"]["rows"] if r["window"] == 3 and r["family"] == "all"]
    assert len(rows) == 4 and all(row["offered"] == 345 for row in rows)
    return {
        "source": "measurements.json",
        "burst": {"two": round(two, 2), "four": round(four, 2), "gain_pct": round(100 * (four / two - 1), 1)},
        "mixed": {
            r["stage"]: {
                "on_time": r["on_time"],
                "ttft_p95": round(r["ttft_p95"], 3),
                "completion_p95": round(r["e2e_p95"], 3),
            }
            for r in rows
        },
    }


def poster(data):
    burst, rows = data["burst"], data["mixed"]

    def span(prefix):
        counts = [r["on_time"] for key, r in rows.items() if key.startswith(prefix)]
        return f"{min(counts)}–{max(counts)}"

    lines = [
        (64, 79, 22, "#d4e68d", "Inference Audit Labs"),
        (64, 162, 48, "#f4f1e8", "The cost of counting tokens alone"),
        (64, 207, 20, "#c2c0ad", "RTX 4070 12 GB  /  Qwen3-8B Q4_K_M  /  llama.cpp CUDA"),
        (64, 293, 70, "#d4e68d", f"+{burst['gain_pct']:.1f}%"),
        (64, 333, 21, "#f4f1e8", f"{burst['two']:.2f} → {burst['four']:.2f} output tok/s"),
        (64, 371, 17, "#c2c0ad", "Chat bursts, 48 offers/launch, 3 controls and 2 candidates"),
        (64, 455, 40, "#f4f1e8", f"{span('A')} → {span('B')}"),
        (64, 489, 18, "#c2c0ad", "Correct on time / 345 offers, 2 launches per profile"),
        (64, 533, 18, "#c2c0ad", "Separate mixed trace at 1.15 offers/s. Slots climbed 2 → 4."),
        (64, 583, 16, "#d4e68d", "github.com/somsom786/inference-audit"),
    ]
    words = "".join(
        f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{escape(value)}</text>'
        for x, y, size, color, value in lines
    )
    art = silicon().split("<title>", 1)[1].split("</title>", 1)[1].removesuffix("</svg>")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
<title>Measured Qwen3-8B serving-slot trade-offs on the RTX 4070</title>
<path fill="#201f1c" d="M0 0h1200v630H0z"/>
<g transform="translate(740 225) scale(.54)">{art}</g>
<path d="M64 228H1136M64 552H1136" stroke="#6a6b57" fill="none"/>
<g font-family="Arial, sans-serif">{words}</g>
</svg>"""


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--highres", type=Path, required=True)
    args = parser.parse_args()
    data = project()
    (PUBLIC / "evidence/labs-results.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    (ASSETS / "labs-silicon.svg").write_text(silicon() + "\n", encoding="utf-8")
    svg = ASSETS / "labs-results-poster.svg"
    svg.write_text(poster(data) + "\n", encoding="utf-8")

    from playwright.sync_api import sync_playwright

    with TemporaryDirectory() as tmp, sync_playwright() as runtime:
        wrapper = Path(tmp) / "poster.html"
        wrapper.write_text(
            "<style>body{margin:0}</style>" + svg.read_text(encoding="utf-8"), encoding="utf-8"
        )
        browser = runtime.chromium.launch(
            executable_path=args.browser, args=["--disable-gpu", "--disable-webgl"]
        )
        for scale, path in ((1, ASSETS / "labs-social.png"), (2, args.highres)):
            page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=scale)
            page.goto(wrapper.as_uri())
            page.locator("svg").screenshot(path=path)
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
