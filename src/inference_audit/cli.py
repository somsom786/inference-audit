"""Command line entry points."""

import argparse
import asyncio
from pathlib import Path
import shutil
import sys
from typing import Any

from . import __version__
from .config import authorize, load, parse
from .controlled import ShutdownError, experiment, local_gpu_lease
from .economics import Assumptions, estimate
from .evidence import FILES, exclusive_lease, new_directory, read, run_path, stable, verify
from .legacy import import_summary, verify_import
from .reporting import load_report, render
from .runner import run_benchmark
from .targets import OpenAI, client_for, get_json, inspect
from .telemetry import Nvidia


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="inference-audit")
    top.add_argument("--version", action="version", version=f"Inference Audit {__version__}")
    top.add_argument("--runs-dir", default="runs", type=Path)
    sub = top.add_subparsers(dest="command", required=True)
    view = sub.add_parser("inspect")
    view.add_argument("--url", default="http://127.0.0.1:8080")
    view.add_argument("--allow-origin", action="append", default=[])
    view.add_argument("--credential-env")
    bench = sub.add_parser("benchmark")
    bench.add_argument("--config", type=Path, required=True)
    bench.add_argument("--run", required=True)
    bench.add_argument("--resume-from")
    bench.add_argument("--approve-load", action="store_true")
    for name in ("verify", "report"):
        child = sub.add_parser(name)
        child.add_argument("--run", required=True)
        if name == "report":
            child.add_argument("--output", type=Path)
            child.add_argument("--cost", type=Path)
            child.add_argument("--capacity-stage")
    status = sub.add_parser("status")
    status.add_argument("--run", required=True)
    export = sub.add_parser("export")
    export.add_argument("--run", required=True)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--include-synthetic-manifest", action="store_true")
    imported = sub.add_parser("import")
    imported.add_argument("--source", type=Path, required=True)
    imported.add_argument("--phase", type=int, choices=(1, 2, 3), required=True)
    imported.add_argument("--run", required=True)
    control = sub.add_parser("experiment")
    control.add_argument("--config", type=Path, required=True)
    control.add_argument("--run", required=True)
    control.add_argument("--approve-local-processes", action="store_true")
    return top


async def invoke(args: argparse.Namespace) -> Any:
    if args.command == "inspect":
        url, _ = authorize(args.url, args.allow_origin)
        async with client_for(url, args.credential_env) as client:
            return await inspect(client)
    path = run_path(args.runs_dir, args.run)
    if args.command == "benchmark":
        if not args.approve_load:
            raise ValueError(
                "Benchmark traffic affects the target. Confirm the approved load with --approve-load."
            )
        cfg = parse(load(args.config))
        previous = run_path(args.runs_dir, args.resume_from) if args.resume_from else None
        async with client_for(cfg.url, cfg.credential_env) as client:
            capabilities = await inspect(client, probe_metrics=cfg.engine == "llama.cpp")
            verified_context = None
            if cfg.engine == "llama.cpp" and cfg.local:
                status, slots = await get_json(client, "/slots")
                if (
                    status == 200
                    and isinstance(slots, list)
                    and slots
                    and all(
                        isinstance(slot, dict)
                        and type(slot.get("n_ctx")) is int
                        and 0 < slot["n_ctx"] <= 1_000_000
                        for slot in slots
                    )
                ):
                    verified_context = min(slot["n_ctx"] for slot in slots)
            if cfg.required_context and (verified_context is None or verified_context < cfg.required_context):
                raise ValueError("Required context is unavailable or exceeds the smallest measured slot.")
            capabilities["listed_models"] = len(capabilities.pop("models"))
            capabilities["context_tokens"] = verified_context

            async def execute() -> Any:
                return await run_benchmark(
                    cfg,
                    OpenAI(client, cfg),
                    path,
                    Nvidia(cfg.gpu_index) if cfg.gpu_index is not None else None,
                    previous,
                    verified_context=verified_context,
                    target_capabilities=capabilities,
                )

            if previous:
                with exclusive_lease(previous / ".continuation"):
                    return await execute()
            result = await execute()
        return result
    if args.command == "import":
        import_summary(args.source, args.phase, path)
        return {"state": "imported", "run": args.run, "phase": args.phase}
    if args.command == "verify":
        if (path / "legacy.json").exists():
            report = verify_import(path)
            return {"state": report["state"], "source": "legacy_summary", "rows": len(report["rows"])}
        return verify(path)
    if args.command == "status":
        status = read(path / "checkpoint.json", 131072)
        if status["state"] == "running":
            try:
                with exclusive_lease(path / ".active"):
                    status["state"] = "unsealed_interruption"
            except ValueError:
                pass
        return status
    if args.command == "export":
        if not args.include_synthetic_manifest:
            raise ValueError(
                "Export includes the synthetic workload. Confirm with --include-synthetic-manifest."
            )
        verify(path)
        bundle = run_path(args.output, args.run)
        new_directory(bundle)
        for name in (*FILES, "integrity.json"):
            with (path / name).open("rb") as source, (bundle / name).open("xb") as destination:
                shutil.copyfileobj(source, destination)
        verify(bundle)
        return {"state": "exported", "run": args.run}
    if args.command == "experiment":
        if not args.approve_local_processes:
            raise ValueError("Explicit local process approval is required.")
        with local_gpu_lease():
            return await experiment(args.config, path, args.approve_local_processes)
    report = load_report(path)
    if args.cost:
        if not args.capacity_stage or "stages" not in report:
            raise ValueError("Choose a native stage for the cost model.")
        s = next((s for s in report["stages"] if s["name"] == args.capacity_stage), None)
        if s is None:
            raise ValueError("Capacity stage does not exist.")
        model = Assumptions(**load(args.cost))
        m = s["metrics"]
        if report["state"] != "complete" or any(m[k] is None for k in ("valid_rps", "goodput_rps")):
            raise ValueError("Costs require a complete stage with verified measured rates.")
        report["economics"] = estimate(
            model,
            m["output_tps"],
            m["valid_rps"],
            m["goodput_rps"],
            min(s["arrival_window_offered_rps"], m["goodput_rps"])
            if s["strict_qualifies"] and s["arrival_window_offered_rps"] is not None
            else None,
        )
        report["economics_inputs"] = vars(model)
    result_path = args.output or path / "report"
    render(report, result_path)
    return {"state": report["state"], "report_directory": str(result_path)}


def main() -> int:
    args = parser().parse_args()
    try:
        result = asyncio.run(invoke(args))
    except KeyboardInterrupt:
        print(stable({"error": "interrupted"}), file=sys.stderr)
        return 130
    except ShutdownError as error:
        print(stable({"error": error.record["state"], "detail": str(error)}), file=sys.stderr)
        return 1
    except (
        OSError,
        TimeoutError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        RecursionError,
        OverflowError,
    ):
        print(
            stable(
                {
                    "error": "operation_failed",
                    "detail": "Check local paths, configuration, and run checkpoint.",
                }
            ),
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        # Application errors are controlled; parser errors can include the input.
        safe = str(error) if type(error) is ValueError else "Configuration or evidence could not be parsed."
        print(stable({"error": "validation_failed", "detail": safe}), file=sys.stderr)
        return 1
    print(stable(result))
    return 2 if result.get("state") in {"incomplete", "interrupted"} else 0
