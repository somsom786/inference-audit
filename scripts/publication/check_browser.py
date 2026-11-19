"""Exercise the static proof package locally with CPU-only browser rendering."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.parse import urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class StaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def check(site, browser, screenshot_dir):
    for viewport in (
        {"width": 1440, "height": 1000},
        {"width": 390, "height": 844},
        {"width": 320, "height": 720},
    ):
        context = browser.new_context(viewport=viewport, locale="en-US")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "response",
            lambda response: errors.append(str(response.status)) if response.status >= 400 else None,
        )

        def route(request):
            if urlsplit(request.request.url).netloc == urlsplit(site).netloc:
                request.continue_()
            else:
                errors.append("Unexpected external request")
                request.abort()

        context.route("**/*", route)
        for endpoint in (
            "",
            "case-study.html",
            "claims.html#p4-goodput",
            "reports/qwen3-8b-audit.html",
            "reports/gemma4-12b-audit.html",
        ):
            page.goto(site + endpoint)
            page.wait_for_load_state("networkidle")
            assert page.locator("img").evaluate_all(
                "(images) => images.every(i => i.complete && i.naturalWidth > 0)"
            )
            assert page.locator("h1").count() == 1, endpoint
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (viewport, endpoint)
            if viewport["width"] >= 390:
                alias = endpoint.split("/")[-1].split(".")[0] or "landing"
                page.screenshot(path=screenshot_dir / f"{alias}-{viewport['width']}.png", full_page=True)

        page.goto(site)
        page.keyboard.press("Tab")
        assert page.get_by_role("link", name="Skip to content").evaluate(
            "(node) => node === document.activeElement"
        )
        page.keyboard.press("Enter")
        assert page.evaluate("location.hash === '#main'")
        page.get_by_role("link", name="Read the case study").click()
        assert page.get_by_role("heading", name="More tokens, less useful work", exact=True).count() == 1
        page.get_by_role("link", name="P4-GOODPUT", exact=True).first.click()
        assert page.locator("#p4-goodput").count() == 1
        assert not errors, errors
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, default=ROOT / "dist/publication/browser")
    args = parser.parse_args()
    args.screenshots.mkdir(parents=True, exist_ok=True)
    handler = partial(StaticHandler, directory=ROOT / "public")
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as playwright:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}/"
            browser = playwright.chromium.launch(
                headless=True,
                executable_path=args.browser,
                args=[
                    "--disable-gpu",
                    "--disable-gpu-compositing",
                    "--disable-gpu-rasterization",
                    "--disable-webgl",
                    "--disable-background-networking",
                ],
            )
            try:
                with TemporaryDirectory() as tmp:
                    preview = Path(tmp) / "report.png"
                    page = browser.new_page(viewport={"width": 1050, "height": 620}, locale="en-US")
                    page.goto(origin + "reports/qwen3-8b-audit.html")
                    page.screenshot(path=preview)
                    page.close()
                    with Image.open(preview) as raw:
                        raw.convert("RGB").save(ROOT / "public/assets/qwen-report-preview.png", optimize=True)
                check(origin, browser, args.screenshots)
                page = browser.new_page()
                page.goto((ROOT / "public/index.html").as_uri())
                page.get_by_role("link", name="View a measured audit", exact=True).click()
                assert "Local demonstration audit" in page.locator("h1").inner_text()
                page.close()
            finally:
                browser.close()
        finally:
            server.shutdown()
            thread.join()
    print(
        "Static landing, case study, ledger and both reports passed at 1440, 390 and 320 px. File preview passed."
    )


if __name__ == "__main__":
    main()
