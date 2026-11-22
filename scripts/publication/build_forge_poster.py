"""Render the Forge result poster from the published benchmark projection."""

from argparse import ArgumentParser
from html import escape
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_labs import ASSETS, PUBLIC, silicon


def make_svg(data):
    latest = data["brackets"][-1]
    a, b, c = (latest["arms"][key] for key in latest["order"])

    def code(arm):
        return arm["metrics"]["code"]["server_decode_tps"]

    controls = sorted([code(a), code(c)])
    delta = 100 * (code(b) / controls[-1] - 1)
    retrieval = sum(item["correct"] for item in b["retrieval"] if item["prompt_tokens"] >= 7500)
    lines = [
        (75, 27, "#d4e68d", "Inference Audit Labs"),
        (160, 54, "#f4f1e8", "One draft token. A faster code stream."),
        (214, 22, "#c2c0ad", "Forge Qwen3.5-9B Q4_K_M / RTX 4070 / Ollama 0.40.16"),
        (323, 80, "#d4e68d", f"+{delta:.1f}%"),
        (374, 28, "#f4f1e8", f"{controls[0]:.2f}–{controls[1]:.2f} → {code(b):.2f} code tok/s"),
        (413, 20, "#c2c0ad", "Median of 8 capped code requests per arm, default → MTP ×1 → default"),
        (471, 20, "#f4f1e8", f"{retrieval}/2 exact near-full-context retrieval checks on the candidate"),
        (512, 20, "#c2c0ad", "Single stream. Novel prose throughput was effectively flat."),
        (580, 17, "#d4e68d", "somsom786.github.io/inference-audit/"),
    ]
    content = "".join(
        f'<text x="62" y="{y}" fill="{color}" font-size="{size}">{escape(text)}</text>'
        for y, size, color, text in lines
    )
    art = silicon().split("</title>", 1)[1].removesuffix("</svg>")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
<title>Measured Forge Qwen3.5-9B code decode with one-token MTP</title>
<path fill="#201f1c" d="M0 0h1200v630H0z"/>
<g transform="translate(820 249) scale(.45)">{art}</g>
<path d="M62 235H1138M62 548H1138" stroke="#6a6b57" fill="none"/>
<g font-family="Arial, sans-serif">{content}</g>
</svg>"""


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--highres", type=Path, required=True)
    args = parser.parse_args()
    svg = make_svg(json.loads((PUBLIC / "evidence/forge-mtp.json").read_text(encoding="utf-8")))
    (ASSETS / "forge-mtp-poster.svg").write_text(svg + "\n", encoding="utf-8")
    from playwright.sync_api import sync_playwright

    with TemporaryDirectory() as temp, sync_playwright() as runtime:
        wrapper = Path(temp) / "poster.html"
        wrapper.write_text("<style>body{margin:0}</style>" + svg, encoding="utf-8")
        browser = runtime.chromium.launch(
            executable_path=args.browser, args=["--disable-gpu", "--disable-webgl"]
        )
        for scale, path in ((1, ASSETS / "forge-mtp-social.png"), (2, args.highres)):
            page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=scale)
            page.goto(wrapper.as_uri())
            page.locator("svg").screenshot(path=path)
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
