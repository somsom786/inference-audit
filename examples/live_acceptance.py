"""Short opt-in integration test against a server this script owns."""

import argparse
import asyncio
from contextlib import AsyncExitStack
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys

from inference_audit.analysis import analyze
from inference_audit.config import parse
from inference_audit.controlled import Guard, available, local_gpu_lease, owned
from inference_audit.evidence import atomic, digest, rows
from inference_audit.targets import client_for, get_json
from inference_audit.telemetry import Nvidia


async def cli(root, *args):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "inference_audit",
        "--runs-dir",
        str(root),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(850):
            stdout, stderr = await process.communicate()
    except BaseException:
        if process.returncode is None:
            process.terminate()
            await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(stderr.decode(errors="replace"))
    return json.loads(stdout)


def cuda_evidence(path: Path):
    with path.open("rb") as log:
        startup = log.read(65536)
    lines = startup.splitlines()
    evidence = {"startup_log_lines_checked": len(lines)}
    for raw in lines:
        line = raw.decode(errors="replace")
        if match := re.search(r"offloaded\s+(\d+)/(\d+)\s+layers", line):
            evidence["offloaded_layers"], evidence["total_layers"] = map(int, match.groups())
        if "RTX 4070" in line and "CUDA0" in line:
            evidence["cuda_device"] = "RTX 4070"
        if match := re.search(r"CUDA0\s+model buffer size\s*=\s*([\d.]+) MiB", line):
            evidence["gpu_model_buffer_mib"] = float(match[1])
    return evidence


async def run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{args.port}"
    raw = {
        "label": args.label,
        "target": {"url": url, "model": "audit-integration"},
        "authorization": {"approved": True},
        "engine": "llama.cpp",
        "gpu_index": 0,
        "seed": 241105,
        "qualification": {"required_context": 3500},
        "limits": {
            "max_requests": 540 if args.extended else 72,
            "runtime_s": 730 if args.extended else 160,
            "timeout_s": 18,
            "max_concurrency": 4,
            "max_rps": 4,
            "dispatch_slack_s": 1.2,
        },
        "stages": [
            {
                "name": "single",
                "pattern": "decode",
                "count": 6,
                "mode": "closed",
                "workers": 1,
                "max_output": 110,
            },
            {
                "name": "parallel",
                "pattern": "concurrent",
                "count": 12,
                "mode": "closed",
                "workers": 4,
                "max_output": 110,
            },
            {
                "name": "cold",
                "pattern": "cold",
                "count": 4,
                "mode": "closed",
                "workers": 1,
                "fixture_set": "cache-pair",
            },
            {
                "name": "warm",
                "pattern": "warm",
                "count": 4,
                "mode": "closed",
                "workers": 1,
                "fixture_set": "cache-pair",
            },
            {
                "name": "mixed",
                "pattern": "mixed",
                "count": 24,
                "mode": "open",
                "rate": 0.65,
                "workers": 4,
                "max_output": 192,
            },
        ],
    }
    if args.extended:
        raw["limits"]["queue_limit"] = 4
        raw["stages"].pop()
        raw["stages"].extend(
            {
                "name": name,
                "pattern": "mixed",
                "count": 210,
                "mode": "open",
                "rate": rate,
                "workers": 4,
                "max_output": 192,
                "fixture_set": "acceptance-mix",
            }
            for name, rate in (("mixed_low", 0.65), ("mixed_high", 1.1))
        )
    cfg = parse(raw)
    config_path = root / f"{args.id}-config.json"
    if config_path.exists() or (root / args.id).exists():
        raise ValueError("Choose a fresh acceptance ID.")
    available("127.0.0.1", args.port)
    gate = Guard(Nvidia(0), 10_500, 1450, 82)
    safety = await gate.sample()
    if safety.get("unsafe") or safety["busy_pct"] > 20:
        raise ValueError("GPU preflight requires an idle board inside the approval limits.")
    argv = [
        str(args.engine.resolve(strict=True)),
        "-m",
        str(args.model.resolve(strict=True)),
        "--alias",
        "audit-integration",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--parallel",
        "2",
        "--ctx-size",
        "8192",
        "--device",
        "CUDA0",
        "--fit",
        "off",
        "--gpu-layers",
        "99",
        "--reasoning",
        "off",
        "--metrics",
        "--slots",
        "--log-verbosity",
        "4",
    ]
    atomic(config_path, raw)
    log_path = root / f"{args.id}-server.private.log"
    shutdown_path = root / f"{args.id}-shutdown.json"
    async with AsyncExitStack() as stack:
        log = stack.enter_context(log_path.open("xb"))
        server = await stack.enter_async_context(
            owned(argv, url=cfg.url, slots=2, evidence=shutdown_path, log=log)
        )
        client = await stack.enter_async_context(client_for(cfg.url))
        async with asyncio.timeout(85):
            while True:
                if server.poll() is not None or (await gate.sample()).get("unsafe"):
                    raise RuntimeError("Owned acceptance server did not satisfy the startup gate.")
                status, health = await get_json(client, "/health")
                if status == 200 and isinstance(health, dict) and health.get("status") == "ok":
                    break
                await asyncio.sleep(0.35)
        placement = cuda_evidence(log_path)
        if not placement.get("gpu_model_buffer_mib") or (
            placement.get("offloaded_layers") != placement.get("total_layers")
        ):
            atomic(root / f"{args.id}-cuda-preflight.json", placement)
            raise RuntimeError("CUDA placement evidence is incomplete before inference.")
        capabilities = await cli(root, "inspect", "--url", cfg.url)
        assert capabilities["models"] == ["audit-integration"]
        bench = asyncio.create_task(
            cli(root, "benchmark", "--config", str(config_path), "--run", args.id, "--approve-load")
        )
        try:
            while not bench.done():
                if (await gate.sample()).get("unsafe"):
                    if (root / args.id).exists():
                        (root / args.id / "STOP").touch()
                    raise RuntimeError("The approval gate stopped local acceptance.")
                await asyncio.sleep(1.5)
            await bench
        finally:
            if not bench.done():
                bench.cancel()
                await asyncio.gather(bench, return_exceptions=True)
    atomic(root / args.id / "cuda-placement.json", placement)
    await cli(root, "verify", "--run", args.id)
    await cli(root, "report", "--run", args.id)
    observed = analyze(root / args.id)
    checked = json.loads((root / args.id / "report/audit.json").read_text(encoding="utf-8"))
    assert observed == checked and observed["state"] == "complete", [
        key for key in observed if observed[key] != checked.get(key)
    ]
    observations = rows(root / args.id / "events.jsonl")
    for stage in checked["stages"]:
        cohort = [event for event in observations if event["stage"] == stage["name"]]
        tokens = [
            step["output_tokens"] for event in cohort for step in event["steps"] if step["status"] == "ok"
        ]
        assert stage["metrics"]["output_tokens"] == (sum(tokens) if tokens and None not in tokens else None)
        assert stage["metrics"]["on_time"] == sum(event["on_time"] for event in cohort)
    assert observed["gpu"]["samples"] >= 2
    assert all(stage["metrics"]["output_tokens"] for stage in observed["stages"][:2])
    assert any(stage["metrics"]["valid"] for stage in observed["stages"])
    assert (
        placement.get("offloaded_layers", 0) == placement.get("total_layers")
        and placement.get("gpu_model_buffer_mib", 0) > 0
    ), placement
    assert all(stage["cache_probe"]["n"] for stage in observed["stages"][2:4])
    device = await gate.sample()
    info = {
        "state": "complete",
        "server_exited": server.returncode is not None,
        "capabilities": capabilities,
        "engine_sha256": digest(args.engine),
        "model_sha256": digest(args.model),
        "offline_metrics_match": True,
        "config_limits": asdict(cfg)["runtime_s"],
        "samples": observed["gpu"]["samples"],
        "GPU_after_mib": device.get("used_mib"),
        "cuda_placement": placement,
    }
    atomic(root / args.id / "local-acceptance.json", info)
    print(json.dumps(info))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(".runs"))
    parser.add_argument("--id", default="qwen-local")
    parser.add_argument("--label", default="Qwen3 local acceptance")
    parser.add_argument("--port", type=int, default=18086)
    parser.add_argument("--approve-local-processes", action="store_true")
    parser.add_argument("--extended", action="store_true", help="Add two matched open-loop mixed stages.")
    args = parser.parse_args()
    if not args.approve_local_processes or not 1024 <= args.port <= 65535:
        parser.error("Local process approval and an unprivileged local port are required.")
    with local_gpu_lease():
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
