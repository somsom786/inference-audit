"""Collect public measurements from archived evidence without editing the captures."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation"))
from recount import recount  # noqa: E402


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if path.suffix == ".csv":
            yield from csv.DictReader(stream)
        else:
            yield from (json.loads(line) for line in stream if line.strip())


def project(source, *keys):
    return {key: source[key] for key in keys}


def check(condition, description):
    if not condition:
        raise ValueError(description)


def same(actual, expected):
    for key, value in actual.items():
        check(
            math.isclose(value, float(expected[key]), abs_tol=1e-8),
            f"Archive disagreement for {key}: {value} vs {expected[key]}",
        )


def quantile(values, p):
    return sorted(values)[math.ceil(p * len(values)) - 1]


def phase1(root):
    csv_rows = {row["run"]: row for row in rows(root / "results/summary.csv")}
    output = {}
    for name in ("baseline", "qualification-baseline", "qualification-best"):
        base = root / "results/raw"
        probes = [load(path) for path in sorted(base.glob(f"{name}-decode-*.json"))]
        cold = [load(path) for path in sorted(base.glob(f"{name}-prefill-7168-*.json"))]
        check(len(probes) == 6 and len(cold) == 3, f"Wrong Phase 1 panel size: {name}")
        for item in probes + cold:
            check(item["usage"]["completion_tokens"] == item["completion_tokens"], "Phase 1 usage mismatch")
        check(
            all(
                item["prompt_tokens"] == item["template_token_count"] == 7168
                and item["usage"]["prompt_tokens_details"]["cached_tokens"] == 0
                for item in cold
            ),
            "Phase 1 prefill was not a matched cold probe",
        )
        decode = [(r["completion_tokens"] - 1) / (r["wall_s"] - r["ttft_s"]) for r in probes]
        prefill = [7168 / r["ttft_s"] for r in cold]
        check(csv_rows[name]["valid_for_comparison"] == "True", f"Ineligible Phase 1 run: {name}")
        stats = {"decode_tps": median(decode), "prefill_7168_tps": median(prefill)}
        same(stats, csv_rows[name])
        output[name] = {
            **stats,
            "decode_samples": decode,
            "cold_7168_samples": prefill,
            **project(csv_rows[name], "flash_attention", "kv", "logical_batch", "microbatch", "threads"),
        }
    return output


POOLS = (
    "Chat burst standard c2",
    "Chat burst selected c4",
    "V3 default c2",
    "V3 standard c2",
    "V3 selected c4",
    "V3 c4 n-gram",
    "Learned draft c2",
)


def phase2(root):
    base = root / "phase2"
    design = load(base / "configs/design.json")
    pooled = load(base / "data/pooled.json")
    summary = load(base / "data/summary.json")["launches"]
    selections = {}
    manifest = defaultdict(set)
    for name in POOLS:
        archive = pooled[name]
        launches = []
        ttft = []
        e2e = []
        for launch in archive["launches"]:
            run = base / "data" / launch
            meta = load(run / "run.json")
            check(meta["status"] == "complete" and meta["process_exited"], f"Unfinished phase 2: {launch}")
            if name != "Learned draft c2":
                manifest["chat" if name.startswith("Chat") else "v3"].add(meta["manifest_sha256"])
            check(meta["total_context"] == 16384, "Phase 2 context differs")
            mixed = [r for r in rows(run / "requests.jsonl") if r["group"] == "mix"]
            accepted = [r for r in mixed if r["ok"] and r["quality_pass"]]
            check(
                all(r["output_tokens"] == r["timings"]["predicted_n"] for r in accepted),
                f"Phase 2 token disagreement: {launch}",
            )
            within = [
                r
                for r in accepted
                if r["ttft_s"] <= design["slo"][r["family"]]["ttft_s"]
                and r["e2e_s"] <= design["slo"][r["family"]]["e2e_s"]
            ]
            launches.append(
                dict(
                    arm=launch,
                    offered=len(mixed),
                    valid=len(accepted),
                    on_time=len(within),
                    wall_s=max(r["end"] for r in mixed) - min(r["arrival"] for r in mixed),
                    tokens=sum(r["output_tokens"] for r in accepted),
                )
            )
            ttft.extend(r["ttft_s"] for r in accepted)
            e2e.extend(r["e2e_s"] for r in accepted)
        span = sum(r["wall_s"] for r in launches)
        totals = {key: sum(r[key] for r in launches) for key in ("offered", "valid", "on_time", "tokens")}
        stats = dict(
            tok_s=totals["tokens"] / span, req_s=totals["valid"] / span, goodput=totals["on_time"] / span
        )
        same(stats, archive)
        tail = {"ttft_p95": quantile(ttft, 0.95), "e2e_p95": quantile(e2e, 0.95)}
        same(tail, {"ttft_p95": archive["overall_ttft_s"]["p95"], "e2e_p95": archive["overall_e2e_s"]["p95"]})
        selections[name] = {**totals, **stats, **tail, "launches": launches}
    check(
        all(len(digests) == 1 for digests in manifest.values()), "Phase 2 comparison has mismatched manifests"
    )
    probes = {}
    for name in ("default-a", "default-b", "prior-a"):
        probe_rows = list(rows(base / "data" / name / "requests.jsonl"))
        startup = (base / "data" / name / "server.log").read_text(encoding="utf-8")
        check(
            "Flash Attention enabled" in startup
            or (name == "prior-a" and "flash_attn            = enabled" in startup),
            f"Expected enabled Flash Attention in {name}",
        )
        probes[name] = {}
        for kind, field in (("decode", "eval_tps"), ("cold", "effective_prefill_tps"), ("warm", "cached")):
            values = summary[name][kind][field]
            panel = [r for r in probe_rows if r["group"] == kind and r["ok"]]
            if kind == "cold":
                check(
                    all(r["prompt_tokens"] == 7168 and r["cached"] == 0 for r in panel),
                    f"Cold probe has incorrect size or cache state: {name}",
                )
                measured = [r["prompt_tokens"] / r["ttft_s"] for r in panel]
            else:
                key = "server_decode_tps" if kind == "decode" else "cached"
                measured = [r[key] for r in panel]
            same({"n": len(measured), "p50": median(measured)}, values)
            probes[name][kind] = project(values, "n", "p50")
    trace = load(base / "data/serving-trace/phase-trace.json")["windows"]
    cache = {
        name: project(pooled[name], "launches", "completed", "tok_s", "cache_share_mean_launch")
        for name in ("Host cache off c2", "Production c2")
    }
    return {
        "comparisons": selections,
        "manifest_sha256": {group: next(iter(values)) for group, values in manifest.items()},
        "probes": probes,
        "legacy_cache_screen": cache,
        "trace_kernel_shares_pct": {
            name: trace[name]["kernel_shares_pct"] for name in ("short_decode", "cold_prefill")
        },
    }


def historical(directory):
    expected = {(r["stage"], int(r["window"]), r["family"]): r for r in rows(directory / "summary.csv")}
    selected = recount(directory)
    for r in selected:
        prior = expected[r["stage"], r["window"], r["family"]]
        same(project(r, "offered", "valid", "on_time", "goodput_rps", "output_tps"), prior)
        for metric in ("ttft_p95", "e2e_p95"):
            check(
                r[metric] is None or abs(r[metric] - float(prior[metric])) <= 0.000051,
                f"Recount mismatch: {metric}",
            )
    return selected


def transfer(directory, key, window):
    verification = load(directory / "verification.json")
    check(verification["integrity_pass"] and verification["wall_clock_agrees"], f"Ineligible transfer: {key}")
    summary = list(rows(directory / "summary.csv"))
    stages = ("A1", "B1", "B2", "A2") if key == "Qwen3-8B" else ("A1", "B1", "B2", "A2", "A3")
    controls = [r for r in summary if r["stage"] in stages and r["family"] == "all"]
    schedule = load(directory / "schedule.json")
    check(all(schedule[a] == schedule[stages[0]] for a in stages), f"Unmatched schedules in {key}")
    request_rows = defaultdict(list)
    for r in rows(directory / "requests.jsonl"):
        if r["stage"] in stages:
            request_rows[r["schedule_id"]].append(r)
    for r in controls:
        arm, index = r["stage"], int(r["window"]) - 1
        plans = [(i, event) for i, event in enumerate(schedule[arm]) if event["window"] == index]
        chains = [request_rows[f"{arm}-{i}"] for i, _ in plans]
        check(all(c and c[-1]["transaction_end"] for c in chains), f"Missing outcomes in {key}")
        passed = [
            c
            for (_, event), c in zip(plans, chains, strict=True)
            if len(c) == len(event["items"]) and all(s["ok"] and s["quality_pass"] for s in c)
        ]
        for chain in chains:
            for step in chain:
                if step["ok"]:
                    check(
                        step["output_tokens"] == step["timings"]["predicted_n"],
                        f"Transfer count mismatch: {key}",
                    )
        same(
            {
                "offered": len(chains),
                "valid": len(passed),
                "on_time": sum(all(s["on_time"] for s in c) for c in passed),
                "output_tps": sum(s.get("output_tokens", 0) for c in chains for s in c) / float(r["seconds"]),
            },
            r,
        )
    selected = [r for r in controls if int(r["window"]) == window]
    fields = (
        "stage",
        "offered",
        "valid",
        "on_time",
        "offered_rps",
        "output_tps",
        "ttft_p95",
        "peak_mib",
        "seconds",
    )
    data = [{k: r[k] if k == "stage" else float(r[k]) for k in fields} for r in selected]
    a = median(r["output_tps"] for r in data if r["stage"].startswith("A"))
    b = median(r["output_tps"] for r in data if r["stage"].startswith("B"))
    environment = load(directory / "environment.json")
    context = environment.get("context", 16384)
    for arm in stages:
        if key == "Qwen3-8B":
            original = "endurance-resume-02" if arm == "A2" else "endurance-02"
            log = directory.parent / original / "runs" / arm / "server.log"
        else:
            log = directory / "runs" / arm / "server.log"
        startup = log.read_text(encoding="utf-8")
        slots = 2 if arm.startswith("A") else 4
        check(
            re.search(rf"n_slots = {slots}, n_ctx_slot = {context // slots}\b", startup)
            and "K (f16)" in startup
            and "V (f16)" in startup,
            f"Serving context or cache precision differs: {key} {arm}",
        )
    return {
        "model": key,
        "two_slots_median": a,
        "four_slots_median": b,
        "delta_pct": 100 * (b / a - 1),
        "launches": data,
        "windows": window,
        "screening": [
            {k: r[k] if k == "stage" else float(r[k]) for k in (*fields, "goodput_rps")}
            for r in summary
            if r["family"] == "all"
            and int(r["window"]) == window
            and r["stage"] in ("default", "batch-512", "cache-off", "ngram")
        ],
        "scheduled_minutes": sum(c["achieved"] for c in verification["checks"]) / 60,
        "engine_version": environment["engine_version"].splitlines()[0],
        "model_sha256": environment["model_sha256"],
        "total_context": context,
    }


def sustained(root):
    results = root / "phase3/results"
    main = results / "endurance-segmented"
    recounted = historical(main)
    check(len(recounted) == 60, "Unexpected Phase 3 ABBA stratum count")
    original = load(results / "endurance-02/runs/A2-window.json")
    replacement = load(main / "runs/A2-window.json")
    check(original["wall_seconds"] - original["duration"] > 3, "Original A2 exclusion is not reproducible")
    check(
        abs(replacement["wall_seconds"] - replacement["duration"]) <= 3, "Replacement A2 clock disagreement"
    )
    gpu = list(rows(main / "gpu-telemetry.csv"))
    checks = load(main / "verification.json")["checks"]
    summary = list(rows(main / "summary.csv"))
    rates = {}
    for arm, stages in (("two_slots", {"A1", "A2"}), ("four_slots", {"B1", "B2"})):
        arm_rows = [r for r in summary if r["stage"] in stages]
        rates[arm] = {}
        for mode in ("family", "aggregate"):
            rates[arm][mode] = [
                round(
                    float(
                        next(
                            r["offered_rps"]
                            for r in arm_rows
                            if r["family"] == "all" and int(r["window"]) == w
                        )
                    ),
                    2,
                )
                for w in (1, 2, 3)
                if all(
                    float(r["on_time_fraction"]) >= 0.95 and float(r["error_fraction"]) <= 0.01
                    for r in arm_rows
                    if int(r["window"]) == w and (r["family"] == "all") == (mode == "aggregate")
                )
            ]
    failures = Counter(r.get("error_type", "unknown") for r in rows(main / "requests.jsonl") if not r["ok"])
    return {
        "scheduled_minutes": sum(c["achieved"] for c in checks) / 60,
        "excluded_a2_wall_seconds": original["wall_seconds"],
        "planned_a2_seconds": original["duration"],
        "matched_strata": len(recounted),
        "sample_count": len(gpu),
        "comparison_rows": recounted,
        "peak_c": max(float(r["temp_c"]) for r in gpu),
        "peak_mib": max(float(r["used_mib"]) for r in gpu),
        "failures": dict(failures),
        "qualification": rates,
        "overload_recovery": [
            {
                k: r[k] if k == "stage" else float(r[k])
                for k in ("stage", "window", "offered", "on_time", "on_time_fraction", "seconds")
            }
            for r in summary
            if r["family"] == "all" and r["stage"] in ("overload", "recovery")
        ],
    }


def collect(research, replication):
    phase4 = historical(replication)
    check(phase4 == load(ROOT / "validation/replication-recount.json"), "Phase 4 archived recount differs")
    phase4_design = load(replication / "plan.json")
    disqualifying = [
        [r["stage"], r["window"], r["family"]]
        for r in phase4
        if r["family"] != "all" and (r["share"] < 0.95 or sum(r["errors"].values()) > 0.01 * r["offered"])
    ]
    stage_checks = load(replication / "verification.json")["checks"]
    results = research / "phase3/results"
    return {
        "schema": 1,
        "phase1": phase1(research),
        "phase2": phase2(research),
        "phase3": sustained(research),
        "transfer": [
            transfer(results / "endurance-segmented", "Qwen3-8B", 3),
            transfer(results / "forge-transfer-01", "Forge Qwen3.5 9B", 2),
            transfer(results / "gemma-transfer-01", "Gemma 4 12B", 2),
        ],
        "phase4": {
            "slo": phase4_design.get(
                "slo", {"chat": [1.5, 4], "coding": [2.5, 8], "rag": [3, 5], "agent": [1.5, 4.5]}
            ),
            "rows": phase4,
            "disqualifying_family_windows": disqualifying,
            "scheduled_minutes": sum(c["achieved"] for c in stage_checks) / 60,
            "totals": sum(r["offered"] for r in phase4 if r["family"] == "all"),
            "archive_request_sha256": hashlib.sha256(
                (replication / "requests.jsonl").read_bytes()
            ).hexdigest(),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research", type=Path, default=ROOT.parent / "inference-bench")
    parser.add_argument("--replication", type=Path, default=ROOT / "validation/runs/replication-01")
    parser.add_argument("--out", type=Path, default=ROOT / "public/evidence/measurements.json")
    args = parser.parse_args()
    evidence = collect(args.research, args.replication)
    args.out.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(
        f"Verified Phase 1 panels, Phase 2 pools, Phase 3 transfer/segmented, {len(evidence['phase4']['rows'])} Phase 4 strata."
    )


if __name__ == "__main__":
    main()
