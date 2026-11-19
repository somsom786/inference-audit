"""Derive observed metrics, sample-aware uncertainty and testable diagnoses."""

from collections import Counter
import hashlib
import math
from pathlib import Path
import re
import statistics
from typing import Any

from .evidence import read, rows, stable, verify


def percentile(values: list[float], q: float, minimum: int = 1) -> float | None:
    if len(values) < minimum:
        return None
    return sorted(values)[math.ceil(q * len(values)) - 1]


def wilson(good: int, total: int) -> list[float] | None:
    if total == 0:
        return None
    z = 1.96
    p = good / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / (1 + z * z / total)
    return [max(0.0, center - half), min(1.0, center + half)]


def finite(value: Any) -> bool:
    return type(value) in (float, int) and -math.inf < value < math.inf


def summary(batch: list[dict[str, Any]], expected: int, seconds: float | None) -> dict[str, Any]:
    good = sum(x["on_time"] is True for x in batch)
    valid = sum(x["correct"] is True and x["status"] == "ok" for x in batch)
    completed = sum(x["status"] == "ok" for x in batch)
    steps = [s for x in batch for s in x["steps"] if s["status"] == "ok"]
    all_counted = bool(steps) and all(finite(s["output_tokens"]) for s in steps)
    tok = sum(s["output_tokens"] for s in steps if finite(s["output_tokens"]))
    known = [s for s in steps if finite(s["cached_tokens"]) and finite(s["prompt_tokens"])]
    prompt = sum(s["prompt_tokens"] for s in known)
    cached = sum(s["cached_tokens"] for s in known)
    decode_times = [
        s["server_timing"]["predicted_ms"] / s["output_tokens"]
        for s in steps
        if s["output_tokens"]
        and finite(s["server_timing"].get("predicted_ms"))
        and s["server_timing"].get("predicted_n") == s["output_tokens"]
    ]
    prefill = [
        s["server_timing"]["prompt_n"] * 1000 / s["server_timing"]["prompt_ms"]
        for s in steps
        if finite(s["server_timing"].get("prompt_n"))
        and finite(s["server_timing"].get("prompt_ms"))
        and s["server_timing"]["prompt_ms"] > 0
    ]

    def rate(count: int) -> float | None:
        return count / seconds if seconds and seconds > 0 else None

    info: dict[str, Any] = {
        "offered": expected,
        "admitted": sum(x.get("client_admitted", x.get("dispatch_s") is not None) for x in batch),
        "dispatched": sum(x.get("dispatch_s") is not None for x in batch),
        "recorded": len(batch),
        "completed": completed,
        "valid": valid,
        "on_time": good,
        "status_counts": dict(Counter(x["status"] for x in batch)),
        "quality_failures": completed - valid,
        "unrecorded": expected - len(batch),
        "on_time_share": good / expected if expected else None,
        "correct_share": valid / expected if expected else None,
        "error_share": (expected - completed) / expected if expected else None,
        "wilson95_descriptive": wilson(good, expected),
        "output_tokens": tok if all_counted else None,
        "output_tps": rate(tok) if all_counted else None,
        "completed_streams": len(steps),
        "accounted_streams": sum(finite(s["output_tokens"]) for s in steps),
        "decode_counter_matched_streams": len(decode_times),
        "token_issues": dict(
            Counter(s.get("token_status", "unknown") for s in steps if not finite(s["output_tokens"]))
        ),
        "completed_rps": rate(completed),
        "valid_rps": rate(valid),
        "goodput_rps": rate(good),
        "observed_offered_per_elapsed_s": rate(len(batch)),
        "cache_share": cached / prompt if prompt else None,
        "cache_samples": len(known),
        "server_decode_token_ms_p50": percentile(decode_times, 0.5),
        "server_prefill_tps_p50": percentile(prefill, 0.5),
    }
    for key in ("ttft_s", "first_visible_s", "latency_s", "queue_s"):
        sample = [x[key] for x in batch if finite(x.get(key)) and (x["status"] == "ok" or key == "queue_s")]
        info[key] = {
            "n": len(sample),
            "p50": percentile(sample, 0.5),
            "p95": percentile(sample, 0.95, 40),
            "p99": percentile(sample, 0.99, 200),
        }
    headers = [
        s["observed"]["response_headers"] for s in steps if "response_headers" in s.get("observed", {})
    ]
    info["request_headers_s"] = {
        "n": len(headers),
        "p50": percentile(headers, 0.5),
        "p95": percentile(headers, 0.95, 40),
    }
    return info


def gpu_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    good = [s for s in samples if s["state"] == "ok"]
    if not good:
        return {"state": "unavailable", "samples": 0, "unavailable_samples": len(samples)}
    name = good[0].get("gpu")
    driver = good[0].get("driver")
    capability = good[0].get("compute_capability")
    result = {
        "state": "measured",
        "samples": len(good),
        "unavailable_samples": len(samples) - len(good),
        "scope": "total device; includes other resident processes",
        "model": name
        if isinstance(name, str) and re.fullmatch(r"NVIDIA [A-Za-z0-9 ().+-]{1,64}", name)
        else None,
        "driver": driver if isinstance(driver, str) and re.fullmatch(r"[0-9.]{1,24}", driver) else None,
        "compute_capability": capability
        if isinstance(capability, str) and re.fullmatch(r"[0-9.]{1,12}", capability)
        else None,
        "thermal_slowdown_samples": sum("Active" in (r.get("hw_thermal"), r.get("sw_thermal")) for r in good),
        "power_limited_samples": sum(r.get("power_cap_active") == "Active" for r in good),
    }
    for key in ("total_mib", "used_mib", "free_mib", "temp_c", "busy_pct", "sm_mhz", "mem_mhz", "power_w"):
        values = [r[key] for r in good if finite(r.get(key))]
        result[key] = (
            {"min": min(values), "max": max(values), "mean": statistics.mean(values), "n": len(values)}
            if values
            else None
        )
    windows = [
        (y["t"] - x["t"], x["power_w"], y["power_w"])
        for x, y in zip(good, good[1:])
        if finite(x["power_w"]) and finite(y["power_w"]) and 0 < y["t"] - x["t"] <= 4.0
    ]
    result["board_sample_joules"] = sum(dt * (x + y) / 2 for dt, x, y in windows) if windows else None
    result["energy_covered_s"] = sum(dt for dt, _, _ in windows)
    intervals = [
        b["t"] - a["t"]
        for a, b in zip(samples, samples[1:])
        if finite(a.get("t")) and finite(b.get("t")) and b["t"] > a["t"]
    ]
    result["observed_median_sample_interval_s"] = percentile(intervals, 0.5)
    return result


def diagnoses(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings = []
    for s in stages:
        total = s["metrics"]
        counts = total["status_counts"]
        dropped = counts.get("admission_limit", 0) + counts.get("dispatch_deadline", 0)
        if dropped:
            findings.append(
                {
                    "diagnosis": "Client admission pressure",
                    "stage": s["name"],
                    "confidence": "high for client",
                    "evidence": f"{dropped} transactions reached the configured client concurrency or dispatch limit.",
                    "caveat": "The observation alone cannot locate a server-side queue.",
                    "experiment": "Replay at a lower offered rate while holding prompts and output caps fixed.",
                    "tradeoff": "A lower rate can improve deadlines and reduce useful capacity.",
                    "falsifier": "At equal workload, lowering the rate does not reduce missed admissions.",
                }
            )
        bad = (
            sum(total["token_issues"].values())
            + counts.get("missing_token_usage", 0)
            + counts.get("token_accounting_mismatch", 0)
        )
        if bad:
            findings.append(
                {
                    "diagnosis": "Unusable token accounting",
                    "stage": s["name"],
                    "confidence": "high",
                    "evidence": f"{bad} accounting issues were observed across streams and legacy transactions.",
                    "caveat": "Output throughput is withheld for partial usage coverage on current evidence. Aborted work can still use the GPU.",
                    "experiment": "Check usage on complete streamed responses with a known adapter.",
                    "tradeoff": "Enabling usage may change server response metadata.",
                    "falsifier": "A repeated capture supplies consistent final streamed usage.",
                }
            )
    for low, high in zip(stages, stages[1:]):
        if not (
            low["match_key"] == high["match_key"]
            and low["mode"] == high["mode"] == "open"
            and high["planned_rate"] >= 1.1 * low["planned_rate"]
            and low["complete"]
            and high["complete"]
        ):
            continue
        a, b = low["metrics"], high["metrics"]
        t0, t1 = a["ttft_s"]["p95"], b["ttft_s"]["p95"]
        p0, p1 = a["output_tps"], b["output_tps"]
        if None not in (t0, t1, p0, p1) and p0 > 0 and p1 <= 1.08 * p0 and t1 >= 1.30 * t0:
            findings.append(
                {
                    "diagnosis": "Throughput plateau with rising first-token tail",
                    "stage": high["name"],
                    "confidence": "moderate, single replay",
                    "evidence": f"Output {p0:.1f} to {p1:.1f} tok/s; p95 TTFT {t0:.2f} to {t1:.2f} s.",
                    "caveat": "A fixed sequential stage order can change cache and thermal state. GPU busy cannot locate a kernel bottleneck.",
                    "experiment": "Repeat the matched rate bracket with a fresh start and compare useful service across concurrency levels.",
                    "tradeoff": "Extra slots can reduce the usable context per request and increase decode contention.",
                    "falsifier": "A repeated bracket sustains proportional useful throughput with stable tail latency.",
                }
            )
    for s in stages:
        probe = s.get("cache_probe")
        if probe and probe["completed_probe_streams"] > probe["n"]:
            findings.append(
                {
                    "diagnosis": "Requested cache state was not verified on every probe",
                    "stage": s["name"],
                    "confidence": "high for observed cache coverage",
                    "evidence": f"{probe['n']} of {probe['completed_probe_streams']} completed probe streams verified.",
                    "caveat": "An unavailable cache counter and a verified zero hit are different observations.",
                    "experiment": "Repeat the controlled same-slot replay with backend cache counters and compare verified prompt processing times.",
                    "tradeoff": "Keeping a prefix resident can consume KV capacity needed for other sessions.",
                    "falsifier": "Every probe reports the intended cache state in a repeated capture.",
                }
            )
    return findings


def analyze(run: Path) -> dict[str, Any]:
    integrity = verify(run)
    plan, checkpoint = read(run / "plan.json"), read(run / "checkpoint.json")
    recorded = rows(run / "events.jsonl")
    board = rows(run / "gpu.jsonl")
    trace = [x for x in board if x["state"] == "ok"]
    origin = trace[0]["t"] if trace else 0.0
    reduced = trace[:: max(1, math.ceil(len(trace) / 200))]
    timeline = [
        {"seconds": x["t"] - origin, "used_mib": x.get("used_mib"), "temp_c": x.get("temp_c")}
        for x in reduced
    ]
    server_samples = rows(run / "server.jsonl")
    gates = plan.get(
        "qualification",
        {
            "min_correct_share": 0.95,
            "min_on_time_share": 0.95,
            "max_error_share": 0.05,
            "required_context": None,
        },
    )
    context = plan.get("worker_context_verified")
    context_ok = gates["required_context"] is None or (
        finite(context) and context >= gates["required_context"]
    )
    stages = []
    for stage in plan["stages"]:
        data = [r for r in recorded if r["stage"] == stage["name"]]
        span = checkpoint["spans_s"].get(stage["name"])
        m = summary(data, len(stage["tasks"]), span)
        cache_probe = None
        if stage["pattern"] in {"cold", "warm"}:
            position = 1 if stage["pattern"] == "warm" else 0
            observed = [
                x["steps"][position]
                for x in data
                if len(x["steps"]) > position and x["steps"][position]["status"] == "ok"
            ]
            observations = [
                s for s in observed if s.get("cache_status", "unavailable") == ("hit" if position else "cold")
            ]
            ttft = [x["ttft_s"] for x in observations if finite(x["ttft_s"])]
            prefill_ms = [x["server_timing"].get("prompt_ms") for x in observations]
            cache_probe = {
                "n": len(observations),
                "completed_probe_streams": len(observed),
                "kind": stage["pattern"],
                "ttft_p50_s": percentile(ttft, 0.5),
                "server_prefill_p50_ms": percentile([x for x in prefill_ms if finite(x)], 0.5),
            }
        families = {
            f: summary(
                [r for r in data if r["family"] == f], sum(t["family"] == f for t in stage["tasks"]), span
            )
            for f in sorted({t["family"] for t in stage["tasks"]})
        }
        for family, f in families.items():
            settings = {**gates, **gates.get("families", {}).get(family, {})}
            f["family_gate_passes"] = (
                f["offered"] >= 20
                and f["on_time_share"] >= settings["min_on_time_share"]
                and f["correct_share"] >= settings["min_correct_share"]
                and f["error_share"] <= settings["max_error_share"]
            )
        complete = stage["name"] in checkpoint["completed_stages"]
        origins = checkpoint.get("origins_s", {})
        start = origins.get(stage["name"])
        stage_gpu = [
            row
            for row in board
            if finite(start) and finite(span) and finite(row.get("t")) and start <= row["t"] <= start + span
        ]
        actual_coverage = None
        if stage["mode"] == "open" and complete and data:
            # Arrival-window coverage excludes drain time and uses the manifested final offset.
            actual_coverage = len(data) / max(
                len(stage["tasks"]) / stage["rate"], stage["offsets_s"][-1] + 1 / stage["rate"]
            )
        boundaries = sorted(
            (tick, delta)
            for row in data
            for step in row["steps"]
            if finite(step.get("dispatch_s")) and step["latency_s"] > 0
            for tick, delta in ((step["dispatch_s"], 1), (step["dispatch_s"] + step["latency_s"], -1))
        )
        simultaneous, peak_overlap = 0, 0
        for _, delta in boundaries:
            simultaneous += delta
            peak_overlap = max(simultaneous, peak_overlap)
        stages.append(
            {
                "name": stage["name"],
                "mode": stage["mode"],
                "pattern": stage["pattern"],
                "workers": stage["workers"],
                "match_key": [
                    stage.get("fixture_set", stage["name"]),
                    stage["pattern"],
                    stage["workers"],
                    stage["max_output"],
                    len(stage["tasks"]),
                ],
                "contract_sha256": hashlib.sha256(
                    stable([plan["configuration_sha256"], stage, plan.get("sampling")]).encode()
                ).hexdigest(),
                "complete": complete,
                "planned_rate": stage["rate"],
                "arrival_window_offered_rps": actual_coverage,
                "peak_client_http_overlap": peak_overlap or None,
                "gpu": gpu_summary(stage_gpu),
                "seconds": span,
                "cache_probe": cache_probe,
                "metrics": m,
                "families": families,
                "strict_qualifies": bool(families)
                and complete
                and context_ok
                and plan["schema"] == 2
                and all(v["family_gate_passes"] for v in families.values()),
            }
        )
    findings = diagnoses(stages)
    deferred = [
        s["counters"]["requests_deferred"] for s in server_samples if "requests_deferred" in s["counters"]
    ]
    if deferred and max(deferred) > 0:
        findings.append(
            {
                "diagnosis": "Server observed requests waiting for admission",
                "stage": "run observation",
                "confidence": "high for sampled queue existence",
                "evidence": f"Known engine reported up to {max(deferred):g} deferred requests.",
                "caveat": "The gauge covers the server and may include other customers. Peaks can occur between samples.",
                "experiment": "Repeat at matched load with a supported, context-qualified slot change.",
                "tradeoff": "Extra slots compete for the context budget and can increase decode contention.",
                "falsifier": "Dedicated replay reports no deferred work while the first-token tail remains elevated.",
            }
        )
    qualified = [
        min(s["arrival_window_offered_rps"], s["metrics"]["goodput_rps"])
        for s in stages
        if s["strict_qualifies"] and s["arrival_window_offered_rps"] is not None
    ]
    if checkpoint["state"] != "complete":
        verdict = "Inconclusive: run interrupted"
    elif any(s["metrics"]["error_share"] > gates["max_error_share"] for s in stages):
        verdict = "Reliability problem identified within tested bounds"
    elif any(f["diagnosis"] == "Throughput plateau with rising first-token tail" for f in findings):
        verdict = "Capacity-limited within tested bounds"
    elif findings:
        verdict = "Performance or measurement issue identified"
    elif qualified:
        verdict = "Healthy within tested bounds"
    else:
        verdict = "Inconclusive for capacity"
    success_steps = [s for row in recorded for s in row["steps"] if s["status"] == "ok"]
    capabilities = plan.get("target_capabilities", {})
    engine_usage = {
        key: capabilities[key]
        for key in ("models_http", "listed_models", "health_http", "metrics_http", "context_tokens")
        if key in capabilities and type(capabilities[key]) in (int, type(None))
    }
    engine_usage.update(
        {
            "completed_streams": len(success_steps),
            "usage_accounted_streams": sum(s["output_tokens"] is not None for s in success_steps),
            "cache_counter_streams": sum(s["cached_tokens"] is not None for s in success_steps),
            "successful_tool_delta_streams": sum(s["finish"] == "tool_calls" for s in success_steps),
        }
    )
    return {
        "schema": 2,
        "evidence_schema": plan["schema"],
        "tool_version": plan.get("tool_version", "0.1.0"),
        "verdict": verdict,
        "stop_reason": checkpoint.get("reason"),
        "started_utc": checkpoint.get("started_utc"),
        "ended_utc": checkpoint.get("ended_utc"),
        "target_capabilities": engine_usage,
        "sampling": plan.get("sampling", {}),
        "qualification": gates,
        "worker_context_verified": context,
        "highest_passing_tested_goodput_rps": max(qualified, default=None)
        if checkpoint["state"] == "complete"
        else None,
        "run": run.name,
        "state": checkpoint["state"],
        "label": plan["label"],
        "seed": plan["seed"],
        "engine_hint": plan["engine_hint"],
        "approved_limits": {
            key: plan["limits"][key]
            for key in (
                "requests",
                "runtime_s",
                "concurrency",
                "rps",
                "response_bytes",
                "evidence_mib",
                "client_queue",
                "timeout_s",
                "dispatch_slack_s",
            )
            if finite(plan["limits"].get(key))
        },
        "slo": plan["slo"],
        "parent_run": plan["parent_run"],
        "integrity": integrity,
        "stages": stages,
        "gpu": gpu_summary(board),
        "gpu_timeline": timeline,
        "server_counters": {"samples": len(server_samples), "peak_deferred": max(deferred, default=None)},
        "findings": findings,
    }
