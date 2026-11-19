"""Self-contained HTML, JSON and Markdown exports with no prompt or reply content."""

import html
from pathlib import Path
from typing import Any

from .analysis import analyze
from .evidence import atomic, atomic_text, safe_path
from .legacy import verify_import

CSS = """
:root { color-scheme: light; --ink:#173047; --muted:#496074; --line:#dce4eb; --accent:#006986; }
* { box-sizing:border-box; }
body { margin:0; background:#eef3f6; color:var(--ink); font:16px/1.55 system-ui,sans-serif; }
main { max-width:1050px; margin:0 auto; padding:38px clamp(16px,4vw,48px) 72px; background:#fff; min-height:100vh; }
h1 { font-size:clamp(1.75rem,4vw,2.8rem); line-height:1.1; margin:.8rem 0; letter-spacing:-.035em; }
h2 { margin-top:2.15rem; border-top:1px solid var(--line); padding-top:1rem; font-size:1.4rem; }
h3 { margin:1.25rem 0 .4rem; }
p,dt,dd { max-width:77ch; } dt { font-weight:700; } dd { margin-left:0; margin-bottom:.6rem; }
.brand { color:var(--accent); font-weight:750; letter-spacing:.05em; }
.meta { color:var(--muted); } .warning { padding:.65rem 1rem; background:#fff1da; border-left:4px solid #926021; }
.tablewrap { overflow:auto; } table { width:100%; border-collapse:collapse; white-space:nowrap; font-variant-numeric:tabular-nums; }
th,td { padding:9px 12px; text-align:right; border-bottom:1px solid var(--line); } th { background:#eaf2f6; }
th:first-child,td:first-child { text-align:left; } svg { max-width:100%; height:auto; display:block; }
@media print { body { background:#fff; } main { padding:0; } }
"""


def fmt(value: Any) -> str:
    if value is None:
        return "Unavailable"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def plain_markdown(value: Any) -> str:
    return "".join(
        f"&#{ord(char)};" if char in "\\`*_{}[]()#+!|<>.&~" else " " if char in "\r\n" else char
        for char in fmt(value)
    )


def table(headers: list[str], rows: list[list[Any]]) -> tuple[str, str]:
    def clean(value: Any) -> str:
        return html.escape(fmt(value))

    def mark(value: Any) -> str:
        return plain_markdown(value)

    head = "".join(f"<th scope='col'>{clean(h)}</th>" for h in headers)
    lines = ["<tr>" + "".join(f"<td>{clean(v)}</td>" for v in row) + "</tr>" for row in rows]
    md = "\n".join(
        [
            "| " + " | ".join(mark(v) for v in headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(mark(v) for v in row) + " |" for row in rows],
        ]
    )
    return "<div class='tablewrap'><table><thead><tr>" + head + "</tr></thead><tbody>" + "".join(
        lines
    ) + "</tbody></table></div>", md


def chart(measured: list[tuple[str, float]], label: str, units: str) -> str:
    if not measured or not max(v for _, v in measured):
        return ""
    top = max(v for _, v in measured)
    height = 50 + 28 * len(measured)
    result = [
        f"<h3>{html.escape(label)}</h3><svg viewBox='0 0 700 {height}' role='img' aria-label='{html.escape(label)}'>"
    ]
    for i, (name, value) in enumerate(measured):
        y = 12 + 28 * i
        result.append(
            f"<text x='0' y='{y + 15}' font-size='12'>{html.escape(name[:18])}</text>"
            f"<rect x='145' y='{y}' width='{490 * value / top:.2f}' height='18' rx='2' fill='#006986'/>"
            f"<text x='{153 + 490 * value / top:.2f}' y='{y + 15}' font-size='12'>{value:.2f}</text>"
        )
    result.append(
        f"<path d='M145 {height - 28}h490' stroke='#607789'/><text x='145' y='{height - 9}' font-size='12'>0</text>"
        f"<text x='635' y='{height - 9}' text-anchor='end' font-size='12'>{top:.2f} {html.escape(units)}</text></svg>"
    )
    return "".join(result)


def trend(samples: list[dict[str, Any]], key: str, label: str, units: str) -> str:
    points = [(s["seconds"], s[key]) for s in samples if s.get(key) is not None]
    if len(points) < 2 or points[-1][0] <= 0:
        return ""
    maximum = max(value for _, value in points)
    if maximum <= 0:
        return ""
    span = points[-1][0]
    series = " ".join(f"{60 + 585 * t / span:.2f},{142 - 110 * v / maximum:.2f}" for t, v in points)
    return (
        f"<h3>{html.escape(label)}</h3><svg viewBox='0 0 700 177' role='img' aria-label='{html.escape(label)}'>"
        f"<path d='M60 32v110h585' fill='none' stroke='#607789'/>"
        f"<polyline points='{series}' fill='none' stroke='#006986' stroke-width='1.6'/>"
        f"<text x='55' y='35' text-anchor='end' font-size='11'>{maximum:.0f} {html.escape(units)}</text>"
        f"<text x='55' y='145' text-anchor='end' font-size='11'>0</text>"
        f"<text x='60' y='164' font-size='11'>0 s</text>"
        f"<text x='645' y='164' text-anchor='end' font-size='11'>{span:.1f} s since first sample</text></svg>"
    )


def render(report: dict[str, Any], output: Path) -> None:
    if report.get("source") == "legacy_summary":
        title = f"Phase {report['phase']} historical evidence"
        headers = report["columns"]
        values = [[r[k] for k in headers] for r in report["rows"]]
        sheet, md = table(headers, values)
        sections = [("Imported measurements", sheet, md)]
        note = report["caveat"]
    else:
        title = report["label"]
        stages = report["stages"]
        note = "Measured synthetic service on the stated contract. Latency uses completed streams. Token rates require complete usage coverage."
        headers = [
            "Stage",
            "Pattern",
            "Offered",
            "Admitted",
            "Dispatched",
            "Completed",
            "Correct",
            "On time",
            "Goodput txn/s",
            "Output tok/s",
            "Cache share",
        ]
        values = []
        for stage in stages:
            m = stage["metrics"]
            values.append(
                [
                    stage["name"],
                    stage["pattern"],
                    m["offered"],
                    m["admitted"],
                    m["dispatched"],
                    m["completed"],
                    m["valid"],
                    m["on_time"],
                    m["goodput_rps"],
                    m["output_tps"],
                    m["cache_share"],
                ]
            )
        sheet, md = table(headers, values)
        goodput = [
            (s["name"], s["metrics"]["goodput_rps"])
            for s in stages
            if s["metrics"]["goodput_rps"] is not None
        ]
        latency = [
            (s["name"], s["metrics"]["ttft_s"]["p50"])
            for s in stages
            if s["metrics"]["ttft_s"]["p50"] is not None
        ]
        sections = [
            (
                "Measured service",
                chart(goodput, "On-time goodput by stage", "transactions/s") + sheet,
                md,
            )
        ]
        sheet_scope, md_scope = table(
            ["Scope item", "Value"],
            [
                ["Verdict", report.get("verdict")],
                ["Run", report.get("run")],
                ["Capture version", report.get("tool_version")],
                ["Started UTC", report.get("started_utc")],
                ["Ended UTC", report.get("ended_utc")],
                ["Stop reason", report.get("stop_reason")],
                ["Engine adapter", report.get("engine_hint")],
                ["Verified slot context, tokens", report.get("worker_context_verified")],
                [
                    "Highest passing tested goodput, transactions/s",
                    report.get("highest_passing_tested_goodput_rps"),
                ],
                *[[key, value] for key, value in report.get("target_capabilities", {}).items()],
                *[[key, value] for key, value in report.get("approved_limits", {}).items()],
            ],
        )
        sections.insert(0, ("Audit scope and verdict", sheet_scope, md_scope))
        sheet_load, md_load = table(
            [
                "Stage",
                "Mode",
                "Planned txn/s",
                "Arrival window txn/s",
                "Workers",
                "Peak HTTP overlap",
                "Elapsed including drain, s",
                "Accounted streams",
                "Completed streams",
                "Passing family gate",
            ],
            [
                [
                    s["name"],
                    s["mode"],
                    s["planned_rate"],
                    s.get("arrival_window_offered_rps"),
                    s["workers"],
                    s.get("peak_client_http_overlap"),
                    s["seconds"],
                    s["metrics"]["accounted_streams"],
                    s["metrics"]["completed_streams"],
                    s["strict_qualifies"],
                ]
                for s in stages
            ],
        )
        sections.append(("Workloads and token coverage", sheet_load, md_load))
        sheet, md = table(
            [
                "Stage",
                "P50 first output s",
                "P95 first output s",
                "P99 first output s",
                "P50 visible content s",
                "P50 response headers s",
                "P50 completion s",
                "P95 completion s",
                "P99 completion s",
                "P95 client dispatch delay s",
                "P50 server decode ms/token",
                "P50 server prefill tok/s",
            ],
            [
                [
                    s["name"],
                    s["metrics"]["ttft_s"]["p50"],
                    s["metrics"]["ttft_s"]["p95"],
                    s["metrics"]["ttft_s"]["p99"],
                    s["metrics"]["first_visible_s"]["p50"],
                    s["metrics"]["request_headers_s"]["p50"],
                    s["metrics"]["latency_s"]["p50"],
                    s["metrics"]["latency_s"]["p95"],
                    s["metrics"]["latency_s"]["p99"],
                    s["metrics"]["queue_s"]["p95"],
                    s["metrics"]["server_decode_token_ms_p50"],
                    s["metrics"]["server_prefill_tps_p50"],
                ]
                for s in stages
            ],
        )
        sections.append(
            ("Response latency", chart(latency, "Median transaction time to first output", "s") + sheet, md)
        )
        probes = [s["cache_probe"] for s in stages if s.get("cache_probe")]
        if probes:
            sheet, md = table(
                [
                    "Cache probe",
                    "Verified samples",
                    "Completed probe streams",
                    "Median request TTFT s",
                    "Median server prefill ms",
                ],
                [
                    [
                        p["kind"],
                        p["n"],
                        p["completed_probe_streams"],
                        p["ttft_p50_s"],
                        p["server_prefill_p50_ms"],
                    ]
                    for p in probes
                ],
            )
            sections.append(("Cold and warm cache probes", sheet, md))
        sheet, md = table(
            [
                "Stage",
                "Family",
                "Correct, on time",
                "Offered",
                "SLO pass share",
                "Family gate",
                "P95 first output s",
                "P95 completion s",
            ],
            [
                [
                    s["name"],
                    family,
                    m["on_time"],
                    m["offered"],
                    m["on_time_share"],
                    m.get("family_gate_passes"),
                    m["ttft_s"]["p95"],
                    m["latency_s"]["p95"],
                ]
                for s in stages
                for family, m in s["families"].items()
            ],
        )
        sections.append(("Workload objectives", sheet, md))
        if not any(s.get("strict_qualifies") for s in stages):
            sections.append(
                (
                    "Capacity qualification",
                    "<p>No stage established the strict per-family capacity gate.</p>",
                    "No stage established the strict per-family capacity gate.",
                )
            )
        failures = [
            [s["name"], reason, n]
            for s in stages
            for reason, n in s["metrics"]["status_counts"].items()
            if reason != "ok"
        ]
        failures += [
            [s["name"], kind, s["metrics"][kind]]
            for s in stages
            for kind in ("quality_failures", "unrecorded")
            if s["metrics"][kind]
        ]
        failures += [
            [s["name"], reason, n] for s in stages for reason, n in s["metrics"]["token_issues"].items()
        ]
        if failures:
            sheet, md = table(["Stage", "Outcome", "Transactions"], failures)
            sections.append(("Failures and exclusions", sheet, md))
        gpu = report["gpu"]
        sheet, md = table(
            ["GPU metric", "Value"], [[k, v.get("max") if isinstance(v, dict) else v] for k, v in gpu.items()]
        )
        samples = report.get("gpu_timeline", [])
        graphs = trend(samples, "used_mib", "Device memory", "MiB") + trend(
            samples, "temp_c", "Board temperature", "°C"
        )
        sections.append(("GPU telemetry · sampled maxima where applicable", graphs + sheet, md))
        findings = report["findings"]
        rendered = "".join(
            "<h3>"
            + plain_markdown(f["diagnosis"])
            + "</h3><dl>"
            + "".join(
                f"<dt>{html.escape(k.replace('_', ' ').title())}</dt><dd>{html.escape(fmt(v))}</dd>"
                for k, v in f.items()
                if k != "diagnosis"
            )
            + "</dl>"
            for f in findings
        )
        marked = "\n\n".join(
            "### "
            + html.escape(f["diagnosis"])
            + "\n\n"
            + "\n".join(
                f"- {plain_markdown(k)} — {plain_markdown(v)}" for k, v in f.items() if k != "diagnosis"
            )
            for f in findings
        )
        sections.append(
            (
                "Evidence-backed diagnoses",
                rendered or "<p>No diagnostic rule triggered.</p>",
                marked or "No diagnostic rule triggered.",
            )
        )
        if report.get("economics"):
            sheet, md = table(
                ["Conditional estimate", "Value"],
                [[k.replace("_", " "), v] for k, v in report["economics"].items()],
            )
            sections.append(("Capacity and cost scenario", sheet, md))
            sheet, md = table(
                ["Scenario input", "Value"],
                [[k.replace("_", " "), v] for k, v in report.get("economics_inputs", {}).items()],
            )
            sections.append(("Cost assumptions", sheet, md))
        explanation = (
            "P95 is withheld below 40 completed samples and P99 below 200. Strict gates apply to each represented "
            "family with at least 20 planned transactions. Rates use stage elapsed time including drain. "
            "Agent first output includes the first tool delta. Visible content is recorded separately. "
            "Requests within one launch can be correlated. Board utilization measures active time. "
            "Task checks cover synthetic receipts, simple code structure, tool calls, JSON or arithmetic."
        )
        sections.append(
            (
                "Method and evidence",
                f"<p>{html.escape(explanation)}</p>"
                f"<p>Seed {report['seed']}. See plan.json, events.jsonl, gpu.jsonl and integrity.json for reproducibility.</p>",
                explanation
                + f"\n\nSeed {report['seed']}. See the saved plan, events, GPU samples and checksum index.",
            )
        )
    state = html.escape(report["state"].upper())
    body = "".join(
        f"<section><h2>{html.escape(name)}</h2>{content}</section>" for name, content, _ in sections
    )
    safe_path(output)
    names = ("audit.html", "audit.md", "audit.json")
    for name in names:
        target = output / name
        safe_path(target)
        if target.exists():
            raise ValueError("Choose a new report output directory. Existing files are preserved.")
    output.mkdir(parents=True, exist_ok=True)
    atomic_text(
        output / "audit.html",
        f"<!doctype html><html lang='en'><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        f"<title>{html.escape(title)} | Inference Audit</title><style>{CSS}</style><main>"
        f"<div class='brand'>Inference Audit</div><h1>{html.escape(title)}</h1>"
        f"<p class='{'meta' if report['state'] == 'complete' else 'warning'}'><strong>{state}</strong> · {html.escape(note)}</p>"
        f"{body}</main></html>",
    )
    atomic_text(
        output / "audit.md",
        f"# {plain_markdown(title)}\n\n**{plain_markdown(report['state'].upper())}** · {plain_markdown(note)}\n\n"
        + "\n\n".join(f"## {name}\n\n{md}" for name, _, md in sections)
        + "\n",
    )
    atomic(output / "audit.json", report)


def load_report(run: Path) -> dict[str, Any]:
    return verify_import(run) if (run / "legacy.json").exists() else analyze(run)
