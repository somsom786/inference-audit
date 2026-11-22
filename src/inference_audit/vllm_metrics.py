"""Allowlisted vLLM Prometheus observations and phase-aligned summaries."""

import asyncio
from hashlib import sha256
import json
from math import isfinite
import re
from typing import Any, TypeGuard

import httpx
from prometheus_client.parser import text_string_to_metric_families

# Select by exposed capabilities. Only direct semantic aliases are interchangeable.
GAUGES = {
    "num_requests_running": "running",
    "num_requests_waiting": "waiting",
    "kv_cache_usage_perc": "kv_usage_fraction",
    "gpu_cache_usage_perc": "kv_usage_fraction",
}
COUNTERS = {
    "num_preemptions": "preemptions",
    "prompt_tokens": "prompt_tokens",
    "generation_tokens": "generation_tokens",
    "prefix_cache_queries": "prefix_queries",
    "prefix_cache_hits": "prefix_hits",
}
HISTOGRAMS = {
    "request_queue_time_seconds": "queue_seconds",
    "request_prefill_time_seconds": "prefill_seconds",
    "request_decode_time_seconds": "decode_seconds",
    "e2e_request_latency_seconds": "e2e_seconds",
    "time_to_first_token_seconds": "ttft_seconds",
    "inter_token_latency_seconds": "itl_seconds",
    "request_time_per_output_token_seconds": "tpot_seconds",
}
MAX_BODY = 512_000
MAX_RECORD = 16_000
MAX_STORED_SERIES = 144
MAX_SUMMARY_SERIES = 512
STATES = {
    "observed",
    "unsupported_or_missing",
    "unsupported_encoding",
    "body_limit",
    "series_limit",
    "transport_failure",
    "malformed",
}


def parse_prometheus(body: str) -> list[dict[str, Any]]:
    """Project selected wire series. Keep label boundaries without storing label values."""
    scalars: dict[tuple[str, str], dict[str, Any]] = {}
    histograms: dict[tuple[str, str], dict[float, float]] = {}
    duplicates = set()
    sample_count = 0
    for family in text_string_to_metric_families(body):
        for sample in family.samples:
            name = sample.name.removeprefix("vllm:")
            if sample.name == name:
                continue
            kind = ""
            if name in GAUGES:
                kind, metric = "gauge", GAUGES[name]
            elif name.removesuffix("_total") in COUNTERS:
                kind, metric = "counter", COUNTERS[name.removesuffix("_total")]
            elif name.endswith("_bucket") and name.removesuffix("_bucket") in HISTOGRAMS:
                kind, metric = "histogram", HISTOGRAMS[name.removesuffix("_bucket")]
            if not kind or not isfinite(sample.value) or sample.value < 0:
                continue
            if metric == "kv_usage_fraction" and sample.value > 1:
                continue
            sample_count += 1
            if sample_count > 4096:
                raise ValueError("Too many selected metric samples.")
            labels = {k: v for k, v in sample.labels.items() if k != "le" or kind != "histogram"}
            series = sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()[:24]
            key = (name, series)
            if kind == "histogram":
                bound = float(sample.labels["le"])
                if bound < 0 or not (isfinite(bound) or bound == float("inf")):
                    continue
                counts = histograms.setdefault(key, {})
                if bound in counts:
                    duplicates.add(key)
                counts[bound] = sample.value
            else:
                if key in scalars:
                    duplicates.add(key)
                scalars[key] = {
                    "source": name,
                    "series": series,
                    "metric": metric,
                    "kind": kind,
                    "value": sample.value,
                }

    result = [record for key, record in scalars.items() if key not in duplicates]
    for (name, series), counts in histograms.items():
        bounds = sorted(counts)
        values = [counts[b] for b in bounds]
        if (
            (name, series) in duplicates
            or not 2 <= len(bounds) <= 128
            or bounds[-1] != float("inf")
            or any(a > b for a, b in zip(values, values[1:]))
        ):
            continue
        result.append(
            {
                "source": name,
                "series": series,
                "metric": HISTOGRAMS[name.removesuffix("_bucket")],
                "kind": "histogram",
                "bounds": bounds[:-1] + [None],
                "counts": values,
            }
        )
    return sorted(result, key=lambda r: (r["source"], r["series"]))


async def collect(client: httpx.AsyncClient) -> dict[str, Any]:
    try:
        async with asyncio.timeout(2), client.stream("GET", "/metrics") as response:
            if response.status_code != 200:
                return {"state": f"http_{response.status_code}"}
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                return {"state": "unsupported_encoding"}
            payload = bytearray()
            async for chunk in response.aiter_raw(chunk_size=16_384):
                payload.extend(chunk)
                if len(payload) > MAX_BODY:
                    return {"state": "body_limit"}
        samples = parse_prometheus(payload.decode("utf-8"))
        if len(samples) > MAX_STORED_SERIES or len(json.dumps(samples).encode()) > MAX_RECORD:
            return {"state": "series_limit"}
        return {"state": "observed" if samples else "unsupported_or_missing", "series": samples}
    except (TimeoutError, httpx.HTTPError):
        return {"state": "transport_failure"}
    except (ValueError, KeyError, RecursionError):
        return {"state": "malformed"}


def histogram_interval_bounds(
    bounds: list[float | None], counts: list[float], p: float
) -> dict[str, float | None] | None:
    if not counts or counts[-1] <= 0:
        return None
    threshold = counts[-1] * p
    index = next(i for i, count in enumerate(counts) if count >= threshold)
    return {"low_s": bounds[index - 1] if index else 0.0, "high_s": bounds[index]}


def validate_snapshots(snapshots: list[dict[str, Any]]) -> None:
    def number(value: Any) -> TypeGuard[int | float]:
        return type(value) in (int, float) and 0 <= value < float("inf")

    last = 0.0
    for snap in snapshots:
        if not isinstance(snap, dict):
            raise ValueError("Invalid vLLM snapshot.")
        state, start, end = (snap.get(key) for key in ("state", "start_s", "t"))
        records = snap.get("series", [])
        if (
            snap.keys() - {"state", "start_s", "t", "counters", "vllm_schema", "series"}
            or snap.get("vllm_schema") != 1
            or snap.get("counters") != {}
            or not isinstance(state, str)
            or (state not in STATES and not re.fullmatch(r"http_[1-5][0-9]{2}", state))
            or not number(start)
            or not number(end)
            or not last <= start <= end
            or not isinstance(records, list)
            or len(records) > MAX_STORED_SERIES
            or (state == "observed") != bool(records)
        ):
            raise ValueError("Invalid vLLM snapshot.")
        last = end
        seen = set()
        for item in records:
            if not isinstance(item, dict):
                raise ValueError("Invalid vLLM series.")
            kind, name, metric, series = (item.get(k) for k in ("kind", "source", "metric", "series"))
            if not (
                isinstance(kind, str)
                and isinstance(name, str)
                and isinstance(metric, str)
                and isinstance(series, str)
            ):
                raise ValueError("Invalid vLLM series identity.")
            if not re.fullmatch(r"[0-9a-f]{24}", series) or (name, series) in seen:
                raise ValueError("Invalid or duplicate vLLM label ID.")
            seen.add((name, series))
            common = {"kind", "source", "metric", "series"}
            if kind == "histogram":
                bounds, counts = item.get("bounds"), item.get("counts")
                valid = (
                    item.keys() == common | {"bounds", "counts"}
                    and HISTOGRAMS.get(name.removesuffix("_bucket")) == metric
                    and name.endswith("_bucket")
                    and isinstance(bounds, list)
                    and isinstance(counts, list)
                    and 2 <= len(bounds) == len(counts) <= 128
                    and bounds[-1] is None
                    and all(number(v) for v in bounds[:-1] + counts)
                    and all(a < b for a, b in zip(bounds[:-2], bounds[1:-1]))
                    and all(a <= b for a, b in zip(counts, counts[1:]))
                )
            else:
                value = item.get("value")
                valid = (
                    item.keys() == common | {"value"}
                    and number(value)
                    and (
                        (
                            kind == "gauge"
                            and GAUGES.get(name) == metric
                            and (metric != "kv_usage_fraction" or value <= 1)
                        )
                        or (kind == "counter" and COUNTERS.get(name.removesuffix("_total")) == metric)
                    )
                )
            if not valid:
                raise ValueError("Invalid vLLM sample.")


def _summarize_series(records: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    first = records[0][1]
    result = {key: first[key] for key in ("metric", "kind", "source", "series")}
    if first["kind"] == "gauge":
        values = [r["value"] for _, r in records]
        return {
            **result,
            "samples": len(values),
            "min": min(values),
            "max": max(values),
            "first": values[0],
            "last": values[-1],
        }
    total: list[float] | None = None
    reset = gap = 0
    pairs = 0
    for (a_id, a), (b_id, b) in zip(records, records[1:]):
        if b_id != a_id + 1 or a.get("bounds") != b.get("bounds"):
            gap += 1
            continue
        left = a["counts"] if first["kind"] == "histogram" else [a["value"]]
        right = b["counts"] if first["kind"] == "histogram" else [b["value"]]
        delta = [y - x for x, y in zip(left, right, strict=True)]
        if any(v < 0 for v in delta):
            reset += 1
            continue
        if first["kind"] == "histogram" and any(x > y for x, y in zip(delta, delta[1:])):
            gap += 1
            continue
        # Use the most recent connected histogram schema segment.
        if first["kind"] == "histogram" and b["bounds"] != records[-1][1]["bounds"]:
            gap += 1
            continue
        total = delta if total is None else [x + y for x, y in zip(total, delta, strict=True)]
        pairs += 1
    result.update(intervals=pairs, detected_resets=reset, gaps=gap)
    if first["kind"] == "counter":
        result["observed_delta"] = total[0] if total is not None else None
    elif total is not None:
        bounds = records[-1][1]["bounds"]
        result.update(
            observations=total[-1],
            bucket_bounds_s=bounds,
            cumulative_bucket_deltas=total,
            p95_bucket=histogram_interval_bounds(bounds, total, 0.95) if total[-1] >= 40 else None,
        )
    return result


def prefix_reuse(series: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]]) -> list[dict[str, Any]]:
    counters: dict[tuple[str, str], list[list[tuple[int, dict[str, Any]]]]] = {}
    for (_, label), records in series.items():
        metric = records[0][1]["metric"]
        if metric in {"prefix_queries", "prefix_hits"}:
            counters.setdefault((label, metric), []).append(records)
    output = []
    for label, metric in counters:
        queries = counters.get((label, "prefix_queries"), [])
        hits = counters.get((label, "prefix_hits"), [])
        if metric != "prefix_queries" or len(queries) != 1 or len(hits) != 1:
            continue
        q = {i: r["value"] for i, r in queries[0]}
        h = {i: r["value"] for i, r in hits[0]}
        total_hits = total_queries = 0.0
        for i in sorted(q.keys() & h.keys()):
            if i - 1 in q and i - 1 in h:
                dq, dh = q[i] - q[i - 1], h[i] - h[i - 1]
                if 0 <= dh <= dq:
                    total_queries += dq
                    total_hits += dh
        if total_queries:
            output.append(
                {
                    "series": label,
                    "queries_delta": total_queries,
                    "hits_delta": total_hits,
                    "observed_hit_fraction": total_hits / total_queries,
                }
            )
    return output


def summarize(snapshots: list[dict[str, Any]], checkpoint: dict[str, Any]) -> dict[str, Any]:
    states: dict[str, int] = {}
    for snap in snapshots:
        key = snap["state"]
        states[key] = states.get(key, 0) + 1
    phases = {}
    for stage, duration in checkpoint.get("spans_s", {}).items():
        start = checkpoint.get("origins_s", {}).get(stage)
        if start is None:
            continue
        phase_samples = [
            snap for snap in snapshots if start <= snap["start_s"] <= snap["t"] <= start + duration
        ]
        series: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
        limit_reached = False
        for i, sample in enumerate(phase_samples):
            for row in sample.get("series", []):
                key = (row["source"], row["series"])
                if key not in series and len(series) >= MAX_SUMMARY_SERIES:
                    limit_reached = True
                    continue
                series.setdefault(key, []).append((i, row))
        phases[stage] = {
            "scrapes": len(phase_samples),
            "series_limit_reached": limit_reached,
            "series": [_summarize_series(value) for value in series.values()],
            "prefix_reuse": prefix_reuse(series),
        }
        # A chart never merges replicas. Cap the displayed series instead.
        timeline = []
        for records in series.values():
            row = records[0][1]
            if row["kind"] != "gauge" or len(records) < 2:
                continue
            points = records[:: max(1, (len(records) + 199) // 200)]
            timeline.append(
                {
                    "metric": row["metric"],
                    "series": row["series"],
                    "points": [
                        {"seconds": phase_samples[i]["t"] - start, "gauge": r["value"]} for i, r in points
                    ],
                }
            )
            if len(timeline) == 12:
                break
        phases[stage]["gauge_timeline"] = timeline
    return {"schema": 1, "states": states, "phases": phases}


def findings(summary: dict[str, Any]) -> list[dict[str, str]]:
    results = []
    for stage, data in summary["phases"].items():
        series = data["series"]
        waiting = [s for s in series if s["metric"] == "waiting" and s["max"] > 0]
        if waiting:
            peak = max(s["max"] for s in waiting)
            results.append(
                {
                    "stage": stage,
                    "diagnosis": "vLLM showed waiting requests",
                    "confidence": "high for sampled queue; low for its cause",
                    "evidence": f"Observed up to {peak:g} waiting requests on a single metric series.",
                    "caveat": "Shared traffic or waiting on cache connectors can contribute. Compare offered load and client tails.",
                    "experiment": "Repeat with a dedicated replica and fixed arrival rates around the observed queue onset.",
                    "tradeoff": "A larger batch budget may raise throughput while worsening decode cadence.",
                    "falsifier": "No waiting or server queue latency on a dedicated replay with the same client tails.",
                }
            )
        # Attribute the signals only when their complete label sets identify the same series.
        pressed = {
            s["series"]: s["max"] for s in series if s["metric"] == "kv_usage_fraction" and s["max"] >= 0.9
        }
        preemptions = [
            s
            for s in series
            if s["metric"] == "preemptions" and s["series"] in pressed and (s["observed_delta"] or 0) > 0
        ]
        if preemptions:
            peak = max(pressed[s["series"]] for s in preemptions)
            results.append(
                {
                    "stage": stage,
                    "diagnosis": "High KV occupancy coincided with preemptions",
                    "confidence": "moderate in the tested stage",
                    "evidence": f"Matching label series reached {peak:.1%} occupancy and recorded preemption deltas.",
                    "caveat": "These are phase summaries. Event-level simultaneity and recompute cost were not established.",
                    "experiment": "Replay matched arrivals with lower context admission while checking workload fit.",
                    "tradeoff": "More KV headroom can reduce admitted concurrency or context.",
                    "falsifier": "Preemptions persist at low cache occupancy on a dedicated, matched replay.",
                }
            )
    return results
