"""Check the freshly installed CLI on a bounded CPU-only loopback fixture."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from test_audit import server  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    args = parser.parse_args()
    cli = args.cli.resolve(strict=True)
    with TemporaryDirectory() as folder:
        workspace = Path(folder)

        def run(*arguments, runs="runs"):
            return subprocess.check_output(
                [str(cli), "--runs-dir", runs, *arguments],
                cwd=workspace,
                encoding="utf-8",
                timeout=30,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            ).strip()

        assert run("--version") == "Inference Audit 0.2.1"
        with server() as (url, stats):
            assert json.loads(run("inspect", "--url", url))["models_http"] == 200
            (workspace / "audit.yaml").write_text(
                f"""label: Publication acceptance
target: {{url: "{url}", model: fixture-model}}
authorization: {{approved: true}}
limits: {{max_requests: 4, runtime_s: 10, timeout_s: 2, max_concurrency: 2, max_rps: 4}}
stages:
  - {{name: probe, pattern: decode, mode: closed, workers: 2, count: 4}}
""",
                encoding="utf-8",
            )
            run("benchmark", "--config", "audit.yaml", "--run", "first-local", "--approve-load")
            run("export", "--run", "first-local", "--output", "export", "--include-synthetic-manifest")
            assert stats["requests"] == 4
        assert json.loads(run("verify", "--run", "first-local"))["recorded"] == 4
        run("report", "--run", "first-local")
        assert json.loads(run("verify", "--run", "first-local", runs="export"))["recorded"] == 4
        run("report", "--run", "first-local", runs="export")
        original = (workspace / "runs/first-local/report/audit.json").read_bytes()
        replay = (workspace / "export/first-local/report/audit.json").read_bytes()
        assert original == replay
    print("Fresh CLI smoke passed: version, inspect, benchmark, export, verify, byte-matched offline report.")


if __name__ == "__main__":
    main()
