"""Exercise the static proof package locally with CPU-only browser rendering."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class StaticHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        prefix = "/inference-audit/"
        if not self.path.startswith(prefix):
            self.send_error(404)
            return
        self.path = "/" + self.path.removeprefix(prefix)
        try:
            super().do_GET()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # A browser can close a static transfer while navigating.
            pass

    def log_message(self, format, *args):
        pass


def check(site, browser, screenshot_dir):
    for viewport in (
        {"width": 1440, "height": 1000},
        {"width": 820, "height": 1180},
        {"width": 390, "height": 844},
        {"width": 320, "height": 720},
    ):
        context = browser.new_context(viewport=viewport, locale="en-US", reduced_motion="reduce")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
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
            "replay.html",
            "labs-case-study.html",
            "economics.html",
            "case-study.html",
            "samples.html",
            "research.html",
            "claims.html#p4-goodput",
            "reports/qwen3-8b-audit.html",
            "reports/gemma4-12b-audit.html",
        ):
            response = page.goto(site + endpoint)
            assert response and response.ok, endpoint
            page.locator("img").evaluate_all("(images) => images.forEach(img => img.loading = 'eager')")
            page.wait_for_function("( ) => [...document.images].every(i => i.complete && i.naturalWidth > 0)")
            assert page.locator("img").evaluate_all(
                "(images) => images.every(i => i.complete && i.naturalWidth > 0)"
            )
            assert page.locator("h1").count() == 1, endpoint
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (viewport, endpoint)
            if viewport["width"] in {390, 1440} and endpoint in {"", "case-study.html", "samples.html"}:
                alias = endpoint.split("/")[-1].split(".")[0] or "landing"
                page.screenshot(path=screenshot_dir / f"{alias}-{viewport['width']}.png")

        page.goto(site)
        page.get_by_role("button", name="First token", exact=True).click()
        assert "0.753 s" in page.locator("#tradeoff").inner_text()
        page.get_by_role("button", name="Completion", exact=True).click()
        assert "4.523–4.678 s" in page.locator("#tradeoff").inner_text()
        assert "$1,153.85" in page.locator("#estimate").inner_text()
        page.locator("[name=share]").fill("0")
        assert "$0.00" in page.locator("#estimate").inner_text()
        page.get_by_text("Optional worker assumptions", exact=True).click()
        page.locator("[name=workers]").fill("10")
        assert "8 under the selected reserve" in page.locator("#estimate").inner_text()
        page.locator("[name=gain]").fill("-1")
        assert "stated limits" in page.locator("#estimate").inner_text()
        page.locator("[name=gain]").fill("30")
        page.locator("[name=share]").fill("50")
        if viewport["width"] in {390, 1440}:
            page.locator("#economics").screenshot(path=screenshot_dir / f"economics-{viewport['width']}.png")

        page.goto(site + "replay.html")
        assert page.locator(".skip").evaluate("(node) => getComputedStyle(node).pointerEvents === 'none'")
        page.keyboard.press("Tab")
        assert page.get_by_role("link", name="Skip to content").evaluate(
            "(node) => node === document.activeElement"
        )
        page.keyboard.press("Enter")
        assert page.evaluate("location.hash === '#main'")
        assert page.locator(".skip").evaluate("(node) => getComputedStyle(node).pointerEvents === 'none'")
        replay = page.get_by_role("button", name="1.10 txn/s", exact=True)
        replay.click()
        assert page.locator(".demo-score strong").inner_text() == "200 / 210"
        assert "Agent tasks passed 12 of 20" in page.locator(".demo-reading").inner_text()
        page.get_by_role("button", name="0.65 txn/s", exact=True).click()
        assert page.locator(".demo-score strong").inner_text() == "198 / 210"
        page.get_by_role("link", name="Discuss a staging pilot", exact=True).click()
        assert page.evaluate("location.hash === '#pilot'")
        assert (
            page.get_by_role("link", name="Contact on LinkedIn", exact=False).get_attribute("href")
            == "https://www.linkedin.com/in/rayn-hasan/"
        )
        comparison = page.locator("[data-comparison]")
        for label, values in (
            ("Completion", ("3.714–3.820 s", "4.523–4.678 s")),
            ("Output rate", ("103.78–103.92", "103.79–104.04")),
            ("Goodput", ("1.050–1.057 txn/s", "0.947–0.977 txn/s")),
            ("Context", ("8,192", "4,096")),
            ("First token", ("1.616–1.741 s", "0.753 s")),
        ):
            control = comparison.get_by_role("button", name=label, exact=True)
            page.wait_for_function("(button) => !button.disabled", arg=control.element_handle())
            control.press("Enter")
            assert comparison.locator(".plot-row strong").all_text_contents() == list(values)
            assert control.get_attribute("aria-pressed") == "true"
        page.get_by_role("button", name="Report", exact=False).click()
        assert page.locator("#workflow-report").is_visible() and page.locator("#workflow-inspect").is_hidden()
        page.get_by_role("link", name="Explore the case study").click()
        page.get_by_role("button", name="Prefill", exact=True).click()
        assert page.locator("#life-prefill").is_visible() and page.locator("#life-queue").is_hidden()
        for rate, cohort in (("0.80", "96 offers"), ("1.00", "120 offers"), ("1.15", "137 offers")):
            page.get_by_role("button", name=rate, exact=True).click()
            assert cohort in page.locator(".family-card").first.inner_text()
        for model, gain in (("Forge 9B", "+4.6%"), ("Gemma 12B", "+9.5%"), ("Qwen3-8B", "+19.2%")):
            page.get_by_role("button", name=model, exact=True).click()
            assert page.locator(".model-delta").inner_text() == gain
        page.get_by_text("What interrupted the endurance study?", exact=True).click()
        assert page.get_by_text("Windows suspended during Qwen", exact=False).is_visible()
        if viewport["width"] in {390, 1440}:
            page.locator("#experiment").scroll_into_view_if_needed()
            page.locator("#experiment").screenshot(
                path=screenshot_dir / f"experiment-{viewport['width']}.png"
            )
        page.get_by_role("link", name="Sample audits", exact=True).click()
        page.get_by_role("button", name="1.10 txn/s", exact=True).click()
        assert page.locator(".demo-score strong").inner_text() == "200 / 210"
        assert page.get_by_role("heading", name="Start with the decision.").is_visible()
        assert page.get_by_text("Captured with Inference Audit 0.2.0", exact=False).is_visible()
        page.get_by_role("link", name="Open Qwen audit", exact=False).click()
        assert "Local demonstration audit" in page.locator("h1").inner_text()
        page.goto(site + "case-study.html#measurement-design")
        page.wait_for_url("**/research.html#measurement-design")
        assert page.locator("#measurement-design").is_visible()
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
            origin = f"http://127.0.0.1:{server.server_port}/inference-audit/"
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
                check(origin, browser, args.screenshots)
                page = browser.new_page(java_script_enabled=False)
                page.goto(origin)
                assert "315–317 of 345" in page.locator("#tradeoff").inner_text()
                assert "$1,154/month" in page.locator("#estimate").inner_text()
                page.goto(origin + "replay.html")
                assert "1.616–1.741" in page.locator("[data-plot]").inner_text()
                assert "198 / 210" in page.locator("[data-replay-result]").inner_text()
                assert page.get_by_role("link", name="full research", exact=True).first.is_visible()
                page.close()
            finally:
                browser.close()
        finally:
            server.shutdown()
            thread.join()
    print(
        "Pages subpath and interaction checks passed at 1440, 820, 390 and 320 px. No-script fallback passed."
    )


if __name__ == "__main__":
    main()
