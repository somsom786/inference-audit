"""Independent release recount. Uses only standard-library parsing and arithmetic."""

import argparse
import collections
import json
import math
from pathlib import Path


def json_file(path):
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def tail(values, fraction, minimum):
    if len(values) >= minimum:
        return sorted(values)[math.ceil(len(values) * fraction) - 1]
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    run = args.run
    report = json_file(args.report or run / "report/audit.json")
    plan = json_file(run / "plan.json")
    status = json_file(run / "checkpoint.json")
    events = jsonl(run / "events.jsonl")
    gpu = [r for r in jsonl(run / "gpu.jsonl") if r["state"] == "ok"]
    assert report["state"] == status["state"] == "complete"
    assert len({r["id"] for r in events}) == len(events)
    actual = {}
    for cell in report["stages"]:
        name = cell["name"]
        obs = [r for r in events if r["stage"] == name]
        planned = next(s for s in plan["stages"] if s["name"] == name)
        assert {r["id"] for r in obs} == {task["id"] for task in planned["tasks"]}
        finished = [r for r in obs if r["status"] == "ok"]
        valid = [r for r in finished if r["correct"]]
        on_time = [
            r
            for r in valid
            if r.get("ttft_s") is not None
            and r["ttft_s"] <= plan["slo"][r["family"]][0]
            and r["latency_s"] <= plan["slo"][r["family"]][1]
        ]
        usage = [s for r in obs for s in r["steps"] if s["status"] == "ok"]
        reconciled = [
            s
            for s in usage
            if s["output_tokens"] is not None and s["output_tokens"] == s["server_timing"].get("predicted_n")
        ]
        token_total = (
            sum(s["output_tokens"] for s in usage)
            if usage and all(s["output_tokens"] is not None for s in usage)
            else None
        )
        duration = status["spans_s"][name]
        first = [r["ttft_s"] for r in finished if r.get("ttft_s") is not None]
        elapsed = [r["latency_s"] for r in finished]
        metrics = cell["metrics"]
        assert (len(valid), len(on_time), len(finished), token_total) == (
            metrics["valid"],
            metrics["on_time"],
            metrics["completed"],
            metrics["output_tokens"],
        )
        output_tps = token_total / duration if token_total is not None else None
        assert metrics["output_tps"] == output_tps
        assert metrics["goodput_rps"] == len(on_time) / duration
        for q, minimum in ((50, 1), (95, 40), (99, 200)):
            assert tail(first, q / 100, minimum) == metrics["ttft_s"][f"p{q}"]
            assert tail(elapsed, q / 100, minimum) == metrics["latency_s"][f"p{q}"]
        for family, values in cell["families"].items():
            cohort = [r for r in obs if r["family"] == family]
            assert values["offered"] == len(cohort)
            assert values["on_time"] == sum(r["family"] == family for r in on_time)
        actual[name] = {
            "planned": len(obs),
            "completed": len(finished),
            "correct": len(valid),
            "on_time": len(on_time),
            "duration_s": duration,
            "outputs_s": output_tps,
            "p50_ttft_s": tail(first, 0.5, 1),
            "p95_ttft_s": tail(first, 0.95, 40),
            "p95_completion_s": tail(elapsed, 0.95, 40),
            "streams_with_matched_prediction_count": len(reconciled),
            "completed_streams": len(usage),
            "outcomes": dict(collections.Counter(r["status"] for r in obs)),
        }
    if gpu:
        peak = max(r["used_mib"] for r in gpu if r["used_mib"] is not None)
        assert report["gpu"]["used_mib"]["max"] == peak
        assert len(gpu) == report["gpu"]["samples"]
    result = {
        "stages": actual,
        "matched": True,
        "gpu_samples": len(gpu),
        "peak_device_mib": peak if gpu else None,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
