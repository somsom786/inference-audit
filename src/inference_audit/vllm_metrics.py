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
                le_raw = sample.labels.get("le")
                if le_raw is None:
                    duplicates.add(key)
                    continue
                try:
                    bound = float(le_raw)
                except ValueError:
                    duplicates.add(key)
                    continue
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
            if response.headers.get("Content-Encoding", "identity").strip().lower() not in {"", "identity"}:
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
    if not counts or counts[-1] <= 0 or not (0.0 < p <= 1.0):
        return None
    threshold = counts[-1] * p
    index = next((i for i, count in enumerate(counts) if count >= threshold), len(counts) - 1)
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
            or len(json.dumps(records).encode()) > MAX_RECORD
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
    if first["kind"] == "histogram":
        # Group valid consecutive intervals by bucket schema and keep the most recent schema
        # that produced at least one valid interval (avoids losing an entire stage to a lone
        # trailing schema change).
        by_schema: dict[tuple[float | None, ...], tuple[list[float], int]] = {}
        schema_order: list[tuple[float | None, ...]] = []
        for (a_id, a), (b_id, b) in zip(records, records[1:]):
            if b_id != a_id + 1 or a.get("bounds") != b.get("bounds"):
                gap += 1
                continue
            delta = [y - x for x, y in zip(a["counts"], b["counts"], strict=True)]
            if any(v < 0 for v in delta):
                reset += 1
                continue
            if any(x > y for x, y in zip(delta, delta[1:])):
                gap += 1
                continue
            schema_key = tuple(b["bounds"])
            if schema_key not in by_schema:
                by_schema[schema_key] = (delta, 1)
                schema_order.append(schema_key)
            else:
                prev_tot, prev_pairs = by_schema[schema_key]
                by_schema[schema_key] = (
                    [x + y for x, y in zip(prev_tot, delta, strict=True)],
                    prev_pairs + 1,
                )
        if schema_order:
            chosen_key = schema_order[-1]
            total, pairs = by_schema[chosen_key]
            # Any valid intervals under earlier superseded schemas count as schema-mismatch gaps.
            for other_key in schema_order[:-1]:
                gap += by_schema[other_key][1]
            chosen_bounds: list[float | None] = list(chosen_key)
        else:
            chosen_bounds = records[-1][1]["bounds"]
        result.update(intervals=pairs, detected_resets=reset, gaps=gap)
        if total is not None:
            result.update(
                observations=total[-1],
                bucket_bounds_s=chosen_bounds,
                cumulative_bucket_deltas=total,
                p50_bucket=histogram_interval_bounds(chosen_bounds, total, 0.50) if total[-1] >= 10 else None,
                p95_bucket=histogram_interval_bounds(chosen_bounds, total, 0.95) if total[-1] >= 40 else None,
            )
        return result

    for (a_id, a), (b_id, b) in zip(records, records[1:]):
        if b_id != a_id + 1:
            gap += 1
            continue
        delta_val = b["value"] - a["value"]
        if delta_val < 0:
            reset += 1
            continue
        total = [delta_val] if total is None else [total[0] + delta_val]
        pairs += 1
    result.update(intervals=pairs, detected_resets=reset, gaps=gap)
    result["observed_delta"] = total[0] if total is not None else None
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
        matched = skipped = 0
        all_indices = sorted(q.keys() | h.keys())
        for prev_idx, idx in zip(all_indices, all_indices[1:]):
            if idx != prev_idx + 1 or prev_idx not in q or prev_idx not in h or idx not in q or idx not in h:
                skipped += 1
                continue
            dq, dh = q[idx] - q[prev_idx], h[idx] - h[prev_idx]
            if 0 <= dh <= dq:
                total_queries += dq
                total_hits += dh
                matched += 1
            else:
                skipped += 1
        if total_queries:
            output.append(
                {
                    "series": label,
                    "queries_delta": total_queries,
                    "hits_delta": total_hits,
                    "observed_hit_fraction": total_hits / total_queries,
                    "matched_intervals": matched,
                    "skipped_intervals": skipped,
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


def findings(
    summary: dict[str, Any],
    stages: list[dict[str, Any]] | None = None,
    gpu: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    stage_by_name = {s["name"]: s for s in (stages or [])}

    # Global observability-degradation alert if scrapes failed or hit caps.
    degraded_states = {k: v for k, v in summary.get("states", {}).items() if k != "observed"}
    truncated_stages = [
        stage for stage, data in summary["phases"].items() if data.get("series_limit_reached")
    ]
    if degraded_states or truncated_stages:
        details = []
        if degraded_states:
            details.append(
                "non-observed scrape states: "
                + ", ".join(f"{k}={v}" for k, v in sorted(degraded_states.items()))
            )
        if truncated_stages:
            details.append("series limit reached in stages: " + ", ".join(truncated_stages))
        results.append(
            {
                "stage": "run observation",
                "diagnosis": "Incomplete vLLM server observability",
                "confidence": "high for missing coverage; cannot infer unobserved events",
                "evidence": "; ".join(details) + ".",
                "rationale": "Missing scrapes, HTTP failures, or series truncation create blind intervals where peaks, preemptions, or resets cannot be verified.",
                "alternative_explanations": "Transient network timeouts, auth/proxy rate limiting on /metrics, or high label cardinality on a shared multi-model endpoint.",
                "missing_information": "Uninterrupted scrape continuity across all replicas and label cardinality breakdown.",
                "experiment": "Re-run a short bounded probe on a dedicated staging replica while confirming 200 OK identity-encoded /metrics responses under load.",
                "possible_changes": "Verify /metrics auth/proxy limits, isolate a single replica for staging, or reduce unrelated model cardinality.",
                "tradeoff": "Shorter scrape intervals raise metric overhead slightly but reduce blind windows.",
                "caveat": "Unavailable intervals have no implied zero; server findings below apply only to captured windows.",
                "falsifier": "100% observed scrapes with zero truncation on a dedicated staging replica.",
            }
        )

    for stage, data in summary["phases"].items():
        series = data["series"]
        stage_info = stage_by_name.get(stage)

        # 1. Request queue saturation
        waiting = [s for s in series if s["metric"] == "waiting" and s["max"] > 0]
        if waiting:
            peak = max(s["max"] for s in waiting)
            results.append(
                {
                    "stage": stage,
                    "diagnosis": "vLLM showed waiting requests",
                    "confidence": "high for sampled queue; low for its root cause",
                    "evidence": f"Observed up to {peak:g} waiting requests on a single metric series.",
                    "rationale": "Non-zero waiting gauge indicates admitted concurrency exceeded immediate scheduler slots or KV block availability.",
                    "alternative_explanations": "Unrelated concurrent traffic on a shared endpoint, KV-cache connector delays, or bursty client arrival clustering.",
                    "missing_information": "Per-request server queue timestamps, dedicated replica isolation, and KV block allocation trace.",
                    "experiment": "Repeat with a dedicated replica and fixed arrival rates around the observed queue onset.",
                    "possible_changes": "Adjust --max-num-seqs, --max-num-batched-tokens, or add replica capacity after checking KV headroom.",
                    "tradeoff": "A larger batch budget or concurrency cap may raise throughput while worsening decode cadence or tail latency.",
                    "caveat": "Shared traffic or waiting on cache connectors can contribute. Compare offered load and client tails.",
                    "falsifier": "No waiting or server queue latency on a dedicated replay with the same client tails.",
                }
            )

        # 2. KV-cache pressure WITH preemptions (same label series)
        pressed = {
            s["series"]: s["max"] for s in series if s["metric"] == "kv_usage_fraction" and s["max"] >= 0.9
        }
        preemptions = [
            s
            for s in series
            if s["metric"] == "preemptions" and s["series"] in pressed and (s["observed_delta"] or 0) > 0
        ]
        preempted_series = {s["series"] for s in preemptions}
        if preemptions:
            peak = max(pressed[s["series"]] for s in preemptions)
            total_preempt = sum(int(s["observed_delta"] or 0) for s in preemptions)
            results.append(
                {
                    "stage": stage,
                    "diagnosis": "High KV occupancy coincided with preemptions",
                    "confidence": "moderate in the tested stage",
                    "evidence": f"Matching label series reached {peak:.1%} KV occupancy and recorded {total_preempt} preemption delta(s).",
                    "rationale": "When paged KV blocks saturate, vLLM preempts running sequences and later recomputes or swaps their KV state, amplifying tail latency.",
                    "alternative_explanations": "Unrelated long-context traffic sharing the replica or an oversized max_model_len reservation starving active sequences.",
                    "missing_information": "Event-level simultaneity between preemption timestamps and client tail requests, plus recompute token cost.",
                    "experiment": "Replay matched arrivals with lower max-model-len or admission cap while checking workload context fit.",
                    "possible_changes": "Raise --gpu-memory-utilization (within safe VRAM margin), lower --max-model-len to actual workload need, or evaluate FP8 KV cache where quality-verified.",
                    "tradeoff": "More KV headroom can reduce admitted concurrency or maximum context; FP8 KV requires quality re-verification.",
                    "caveat": "These are phase summaries. Event-level simultaneity and recompute cost were not established.",
                    "falsifier": "Preemptions persist at low cache occupancy on a dedicated, matched replay.",
                }
            )

        # 3. KV-cache pressure WITHOUT observed preemptions (high occupancy >= 85% on non-preempted series)
        near_full_no_preempt = {
            s["series"]: s["max"]
            for s in series
            if s["metric"] == "kv_usage_fraction" and s["max"] >= 0.85 and s["series"] not in preempted_series
        }
        if near_full_no_preempt:
            peak = max(near_full_no_preempt.values())
            results.append(
                {
                    "stage": stage,
                    "diagnosis": "KV-cache occupancy approached saturation without observed preemptions",
                    "confidence": "moderate for memory pressure; low for preemption absence",
                    "evidence": f"KV cache usage reached {peak:.1%} on a label series with no positive preemption delta captured.",
                    "rationale": "Near-full KV occupancy leaves minimal headroom for burst arrivals or longer outputs and can cause scheduler admission queuing even before preemptions trigger.",
                    "alternative_explanations": "Short transient spike between 5s scrapes, or preemptions hidden inside a counter reset/scrape gap.",
                    "missing_information": "Sub-second KV occupancy trace and exact block count allocated at startup.",
                    "experiment": "Step offered concurrency +25% on a dedicated replica while logging waiting queue and preemption deltas.",
                    "possible_changes": "Verify --gpu-memory-utilization headroom, cap --max-model-len to required context, or enable/verify prefix caching for shared prompts.",
                    "tradeoff": "Tighter admission protects tail latency at the cost of queuing under burst load.",
                    "caveat": "High KV utilization alone is healthy if waiting queue and tail deadlines remain within SLO.",
                    "falsifier": "Stepping concurrency +25% keeps waiting at zero and all SLO gates green.",
                }
            )

        # 4. Prefix-cache inefficiency (high queries, low observed hit fraction)
        low_reuse = [
            r
            for r in data.get("prefix_reuse", [])
            if r["queries_delta"] >= 1000 and r["observed_hit_fraction"] < 0.15
        ]
        if low_reuse:
            worst = min(low_reuse, key=lambda r: r["observed_hit_fraction"])
            results.append(
                {
                    "stage": stage,
                    "diagnosis": "Low prefix-cache reuse under substantial query volume",
                    "confidence": "moderate for low observed reuse; low for exploitability",
                    "evidence": f"Observed {worst['hits_delta']:g} hits / {worst['queries_delta']:g} queries ({worst['observed_hit_fraction']:.1%}) over {worst.get('matched_intervals', 0)} matched interval(s).",
                    "rationale": "Low hit rates on high prompt volume mean repeated prefill work may be recomputed each request if prompts share static system/tool/document prefixes.",
                    "alternative_explanations": "Workload prompts are genuinely unique, variable tokens appear early in the prompt template, or multi-replica load balancing lacks cache-aware routing.",
                    "missing_information": "Prompt-prefix structure, cache-eviction rate under KV pressure, and load-balancer routing policy.",
                    "experiment": "Run a paired cold/warm/early-change prefix replay against a single replica to verify block hashing and hit-rate sensitivity.",
                    "possible_changes": "Move static system instructions and tool schemas to the front of prompts, enable --enable-prefix-caching, or add prefix-aware routing across replicas.",
                    "tradeoff": "Prefix-aware routing can create hot-replica skew if one tenant dominates traffic.",
                    "caveat": "Server counters aggregate all traffic on that label series and do not prove prompts are reusable.",
                    "falsifier": "Controlled identical-prefix replay still produces low hit rates or zero TTFT reduction.",
                }
            )

        # 5. Prefill interference / decode-stall correlation (histogram evidence)
        high_prefill = [
            s
            for s in series
            if s["metric"] in {"prefill_seconds", "ttft_seconds"}
            and s.get("p95_bucket")
            and (s["p95_bucket"]["low_s"] or 0.0) >= 0.5
        ]
        high_decode_step = [
            s
            for s in series
            if s["metric"] in {"itl_seconds", "tpot_seconds"}
            and s.get("p95_bucket")
            and (s["p95_bucket"]["low_s"] or 0.0) >= 0.1
        ]
        if high_prefill and high_decode_step:
            p_row = high_prefill[0]
            d_row = high_decode_step[0]
            results.append(
                {
                    "stage": stage,
                    "diagnosis": "Elevated prefill/TTFT coincided with inter-token decode stalls",
                    "confidence": "low-to-moderate (correlation within stage, not causal proof)",
                    "evidence": (
                        f"{p_row['metric']} p95 >= {p_row['p95_bucket']['low_s']:.3f}s alongside "
                        f"{d_row['metric']} p95 >= {d_row['p95_bucket']['low_s']:.3f}s."
                    ),
                    "rationale": "Large unchunked or oversized prefill batches can monopolize compute steps and stall concurrent decode tokens.",
                    "alternative_explanations": "Memory-bandwidth saturation at high batch size, KV recomputation after preemption, or host CPU scheduling jitter.",
                    "missing_information": "Step-level scheduled token mix (prefill vs decode tokens per step) and isolated short-only control.",
                    "experiment": "Compare --max-num-batched-tokens across two values (e.g., 512 vs 2048) against a short-prompt-only control at matched arrivals.",
                    "possible_changes": "Tune --max-num-batched-tokens with chunked prefill enabled, or separate long-context traffic onto dedicated replicas.",
                    "tradeoff": "Smaller token budgets protect decode ITL but can increase long-prompt TTFT and reduce peak aggregate throughput.",
                    "caveat": "Co-occurring stage histograms do not prove prefill caused the decode stalls without a controlled bracket.",
                    "falsifier": "Short-only control at the same decode concurrency exhibits the same ITL p95.",
                }
            )

        # 6. CPU / scheduling overhead suspicion (requires stage GPU telemetry)
        if stage_info is not None:
            raw_gpu = stage_info.get("gpu") or gpu
            stage_gpu: dict[str, Any] = raw_gpu if isinstance(raw_gpu, dict) else {}
            raw_util = stage_gpu.get("util_pct")
            gpu_util: dict[str, Any] = raw_util if isinstance(raw_util, dict) else {}
            gpu_max = gpu_util.get("max")
            if waiting and isinstance(gpu_max, (int, float)) and gpu_max < 40.0:
                results.append(
                    {
                        "stage": stage,
                        "diagnosis": "Queueing occurred while sampled GPU utilization stayed low",
                        "confidence": "low-to-moderate (requires host/device timeline profiling)",
                        "evidence": f"Waiting requests observed while sampled peak GPU utilization was {gpu_max:.1f}%.",
                        "rationale": "Persistent queues with under-utilized GPU often indicate CPU tokenization/scheduling overhead, eager Python launch overhead, or PCIe/KV transfer stalls.",
                        "alternative_explanations": "Coarse 1.5s nvidia-smi sampling missing bursty kernels, KV-cache memory limit capping active batch size, or network/client bottleneck.",
                        "missing_information": "PyTorch profiler / Nsight Systems timeline separating CPU prep, kernel launch, and GPU active time.",
                        "experiment": "Profile a 30-second matched replay with CUDA graphs enabled vs eager mode and inspect host CPU core saturation.",
                        "possible_changes": "Enable CUDA graphs (avoid --enforce-eager if VRAM allows), verify async output processing and tokenizer threads, or check CPU pinning.",
                        "tradeoff": "CUDA graph capture consumes additional VRAM and reduces available KV-cache blocks.",
                        "caveat": "nvidia-smi utilization measures SM busy time percentage, not memory-bandwidth saturation or tensor-core efficiency.",
                        "falsifier": "Nsight/torch profile shows GPU kernels are memory-bandwidth bound with negligible host gaps.",
                    }
                )

            # 7. Deadline-bound goodput / model quality failure separation
            metrics = stage_info.get("metrics", {})
            q_fail = metrics.get("quality_failures", 0)
            err_share = metrics.get("error_share", 0.0)
            if q_fail > 0 or err_share > 0.05:
                results.append(
                    {
                        "stage": stage,
                        "diagnosis": "Quality or error failures reduced qualified goodput",
                        "confidence": "high for observed failure count; separate from raw speed",
                        "evidence": (
                            f"Stage recorded {q_fail} quality failure(s) and {err_share:.1%} error share "
                            f"(goodput {metrics.get('goodput_rps', 0.0):.3f} vs offered {metrics.get('offered', 0)})."
                        ),
                        "rationale": "Raw token throughput can look high while context-limit rejections, HTTP 400s, tool-schema mismatches, or truncated outputs destroy usable capacity.",
                        "alternative_explanations": "Misconfigured --max-model-len, chat-template/tool-parser mismatch, aggressive quantization degradation, or client timeout too tight.",
                        "missing_information": "Per-family error taxonomy (context limit vs tool parse vs timeout) and baseline unquantized quality check.",
                        "experiment": "Replay failing task families at concurrency=1 with verified context budget and tool-call parser flags.",
                        "possible_changes": "Increase --max-model-len to cover required prompts + output, verify --tool-call-parser and chat template, or roll back aggressive quantization.",
                        "tradeoff": "Higher max-model-len or higher-precision weights reduce concurrent KV capacity per GPU.",
                        "caveat": "Never claim a throughput speedup if quality or error gates fail.",
                        "falsifier": "Single-stream replay with verified context and parser passes 100% of quality checks.",
                    }
                )

    return results
