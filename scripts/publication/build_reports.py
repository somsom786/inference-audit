"""Regenerate redacted demonstration reports through the installed audit renderer."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from inference_audit import __version__
from inference_audit.reporting import load_report, render

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = (
    ("qwen-020", "local-qwen-020", "qwen3-8b-audit", "Qwen3-8B Q4_K_M"),
    ("gemma-020", "local-gemma-020", "gemma4-12b-audit", "Gemma 4 12B IT QAT (text Q4_0)"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=ROOT / ".runs")
    args = parser.parse_args()
    if __version__ != "0.2.1":
        raise ValueError("Install the preserved 0.2.1 wheel before regenerating the sample reports.")
    out = ROOT / "public/reports"
    for run, original, alias, model in SAMPLES:
        report = load_report(args.runs / run)
        expected = json.loads((ROOT / "reports" / original / "audit.json").read_text(encoding="utf-8"))
        if not all(expected.get(key) == value for key, value in report.items()):
            raise ValueError(f"Replayed report disagrees with the archived report: {alias}")
        report.update(
            label=f"Local demonstration audit — NVIDIA RTX 4070 — synthetic workloads ({model})",
            run=alias,
            started_utc=None,
            ended_utc=None,
            parent_run=None,
        )
        with TemporaryDirectory() as tmp:
            render(report, Path(tmp))
            for ext in ("html", "json", "md"):
                (out / f"{alias}.{ext}").write_bytes((Path(tmp) / f"audit.{ext}").read_bytes())
        print(f"{alias}: exact replay before redaction ({report['integrity']['recorded']} transactions).")


if __name__ == "__main__":
    main()
