"""Generate clearly labeled demonstration reports without an API or GPU."""

from pathlib import Path
import argparse

from inference_audit.analysis import diagnoses, summary
from inference_audit.reporting import render


def demo(output: Path):
    stages = []
    for name, rate in (("light", 0.7), ("stress", 1.2)):
        records = []
        for i in range(100):
            first = (0.24 + i * 0.004) if rate < 1 else (0.67 + i * 0.04)
            row = {
                "status": "ok",
                "correct": True,
                "on_time": first < 1.5,
                "ttft_s": first,
                "latency_s": first + 1.2,
                "queue_s": 0.03 if rate < 1 else 0.95,
                "steps": [
                    {
                        "status": "ok",
                        "prompt_tokens": 53,
                        "output_tokens": 96,
                        "cached_tokens": 0,
                        "server_timing": {},
                    }
                ],
            }
            records.append(row)
        m = summary(records, 100, 140 if rate < 1 else 134)
        stages.append(
            {
                "name": name,
                "pattern": "chat",
                "mode": "open",
                "metrics": m,
                "families": {"chat": m},
                "planned_rate": rate,
                "workers": 4,
                "seconds": 140 if rate < 1 else 134,
                "strict_qualifies": False,
                "match_key": ["demo"],
                "complete": True,
            }
        )
    render(
        {
            "label": "Inference Audit demonstration",
            "verdict": "Illustrative example only",
            "state": "synthetic demonstration data",
            "seed": 407,
            "stages": stages,
            "gpu": {"state": "unavailable"},
            "findings": diagnoses(stages),
        },
        output,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("reports/demo"))
    demo(parser.parse_args().output)
