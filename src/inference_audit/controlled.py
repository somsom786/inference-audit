"""Owned local llama.cpp comparisons. No access to existing server processes."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
import os
import stat
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from typing import Any, AsyncIterator, BinaryIO, Iterator
from urllib.parse import urlsplit

from .analysis import analyze
from .config import fields, load, number, parse
from .evidence import atomic, digest, exclusive_lease, new_directory, safe_path
from .runner import run_benchmark
from .targets import OpenAI, client_for, get_json, llama_counters
from .telemetry import Nvidia
from .workload import TOOLS, planned


@dataclass(frozen=True)
class Guard:
    required = True
    sensor: Nvidia
    max_mib: int
    min_free_mib: int
    max_temp: float

    async def sample(self) -> dict[str, Any]:
        row = await self.sensor.sample()
        used, free, temp = (row.get(k) for k in ("used_mib", "free_mib", "temp_c"))
        if (
            row["state"] != "ok"
            or not isinstance(used, (int, float))
            or not isinstance(free, (int, float))
            or not isinstance(temp, (int, float))
        ):
            row["unsafe"] = "GPU monitoring unavailable"
        elif used > self.max_mib or free < self.min_free_mib or temp >= self.max_temp:
            row["unsafe"] = "Approved GPU ceiling breached"
        elif "Active" in (row.get("hw_thermal"), row.get("sw_thermal")):
            row["unsafe"] = "Thermal slowdown reported"
        return row


@contextmanager
def local_gpu_lease() -> Iterator[None]:
    path = Path(tempfile.gettempdir()) / "inference-audit-gpu0.lock"
    with exclusive_lease(path):
        yield


DRAIN_TIMEOUT_S = 15
EXIT_TIMEOUT_S = 8
SHUTDOWN_POLL_S = 0.25


class ShutdownError(ValueError):
    def __init__(self, record: dict[str, Any], evidence: Path):
        self.record = record
        self.evidence = evidence
        action = (
            "Operator intervention required."
            if record["state"] == "operator_intervention_required"
            else "Launch aborted."
        )
        super().__init__(f"{action} Owned PID {record['pid']}, {record['reason']}. See {evidence.name}.")


async def shutdown(process: subprocess.Popen[bytes], url: str, slots: int, record: dict[str, Any]) -> None:
    record.update(state="unverified_exit", reason="process_exited_without_drain")
    idle = 0
    if process.poll() is None:
        async with client_for(url) as client:
            try:
                async with asyncio.timeout(DRAIN_TIMEOUT_S):
                    while process.poll() is None:
                        (status, data), counters = await asyncio.gather(
                            get_json(client, "/slots"), llama_counters(client)
                        )
                        active = None
                        if (
                            status == 200
                            and isinstance(data, list)
                            and len(data) == slots
                            and all(
                                isinstance(slot, dict) and type(slot.get("is_processing")) is bool
                                for slot in data
                            )
                        ):
                            active = sum(slot["is_processing"] for slot in data)
                        processing = (counters or {}).get("requests_processing")
                        deferred = (counters or {}).get("requests_deferred")
                        record.update(
                            active_slots=active, requests_processing=processing, requests_deferred=deferred
                        )
                        idle = idle + 1 if active == processing == deferred == 0 else 0
                        if idle == 2:
                            break
                        await asyncio.sleep(SHUTDOWN_POLL_S)
            except TimeoutError:
                if process.poll() is None:
                    unknown = any(
                        record.get(k) is None
                        for k in ("active_slots", "requests_processing", "requests_deferred")
                    )
                    record.update(
                        state="operator_intervention_required",
                        reason="activity_unverified" if unknown else "drain_not_confirmed",
                    )
                return
    if process.poll() is not None:
        return
    record["drain_confirmed"] = True
    sig = signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGTERM
    try:
        process.send_signal(sig)
    except OSError:
        record.update(state="operator_intervention_required", reason="graceful_signal_failed")
        return
    record["signal"] = sig.name
    try:
        async with asyncio.timeout(EXIT_TIMEOUT_S):
            while process.poll() is None:
                await asyncio.sleep(SHUTDOWN_POLL_S)
    except TimeoutError:
        if process.poll() is None:
            record.update(state="operator_intervention_required", reason="exit_not_observed")
            return
    record.update(state="drained_and_exited", reason=None)


@asynccontextmanager
async def owned(
    argv: list[str],
    *,
    url: str,
    slots: int,
    evidence: Path,
    log: BinaryIO | None = None,
) -> AsyncIterator[subprocess.Popen[bytes]]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    atomic(evidence, {"state": "launching", "expected_slots": slots})
    # asyncio's subprocess transport can kill a live child while closing the event loop.
    # Keep an ordinary process handle so an intervention leaves the owned child running.
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=log if log is not None else subprocess.DEVNULL,
        stderr=subprocess.STDOUT if log is not None else subprocess.DEVNULL,
        creationflags=flags,
    )
    record: dict[str, Any] = {
        "pid": process.pid,
        "expected_slots": slots,
        "state": "running",
        "drain_confirmed": False,
        "signal": None,
    }
    try:
        atomic(evidence, record)
        yield process
    except BaseException as error:
        record["work_error"] = type(error).__name__
        raise
    finally:
        record["state"] = "draining"
        try:
            # Callers exit their inference client context before reaching this point.
            atomic(evidence, record)
            await shutdown(process, url, slots, record)
        except BaseException:
            record.update(
                state="operator_intervention_required" if process.poll() is None else "unverified_exit",
                reason="shutdown_interrupted",
            )
            raise ShutdownError(record, evidence)
        finally:
            record["returncode"] = process.poll()
            atomic(evidence, record)
        if record["state"] != "drained_and_exited":
            raise ShutdownError(record, evidence)


def available(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex((host, port)) == 0:
            raise ValueError("The configured owned-server port is already in use.")


def compare(
    results: dict[str, dict[str, Any]], required_gain: float, tail_regression: float
) -> list[dict[str, Any]]:
    def acceptable_tail(values: list[Any]) -> bool:
        return all(isinstance(v, (int, float)) and v >= 0 for v in values) and max(values[2:]) <= min(
            values[:2]
        ) * (1 + tail_regression)

    outcomes = []
    for s in results["A1"]["stages"]:
        arms = {k: next(x for x in v["stages"] if x["name"] == s["name"]) for k, v in results.items()}
        controls = [arms[k] for k in ("A1", "A2")]
        candidates = [arms[k] for k in ("B1", "B2")]
        before = [x["metrics"]["goodput_rps"] for x in controls]
        after = [x["metrics"]["goodput_rps"] for x in candidates]
        paired = (
            min(after) / max(before) - 1
            if all(isinstance(v, (int, float)) and v > 0 for v in before + after)
            else None
        )
        gate = all(x["strict_qualifies"] for x in candidates)
        signatures = {x.get("contract_sha256") for x in arms.values()}
        comparable = None not in signatures and len(signatures) == 1
        family_gates = {}
        for family in s.get("families", {}):
            family_gates[family] = all(
                acceptable_tail([x["families"][family][metric]["p95"] for x in [*controls, *candidates]])
                for metric in ("latency_s", "ttft_s")
            )
        tail_ok = all(
            acceptable_tail([x["metrics"][metric]["p95"] for x in [*controls, *candidates]])
            for metric in ("latency_s", "ttft_s")
        )
        accepted = (
            comparable
            and gate
            and tail_ok
            and all(family_gates.values())
            and paired is not None
            and paired >= required_gain
        )
        outcomes.append(
            {
                "stage": s["name"],
                "accepted": accepted,
                "candidate_family_gate": gate,
                "min_goodput_gain_fraction": paired,
                "p95_gate": tail_ok,
                "per_family_p95_gates": family_gates,
                "comparable": comparable,
                "control_goodput": before,
                "candidate_goodput": after,
            }
        )
    return outcomes


async def experiment(path: Path, destination: Path, approved: bool) -> dict[str, Any]:
    args = fields(load(path), {"audit", "local", "acceptance"})
    local = fields(
        args.get("local"),
        {
            "approved",
            "executable",
            "model",
            "total_context",
            "required_context",
            "baseline_slots",
            "candidate_slots",
            "max_vram_mib",
            "min_free_mib",
            "max_temp_c",
        },
    )
    if not approved or local.get("approved") is not True:
        raise ValueError("This action requires explicit approval to launch and stop owned local servers.")
    cfg = parse(args.get("audit"))
    url = urlsplit(cfg.url)
    if (
        url.hostname != "127.0.0.1"
        or url.scheme != "http"
        or cfg.engine != "llama.cpp"
        or cfg.gpu_index != 0
        or cfg.credential_env is not None
    ):
        raise ValueError("Controlled mode requires explicit local llama.cpp and NVIDIA settings.")
    if cfg.model != "audit-local":
        raise ValueError("Set the controlled model alias to audit-local.")
    port = number(url.port, 1024, 65535, "owned port", True)
    executable = Path(local["executable"]).absolute()
    model = Path(local["model"]).absolute()
    safe_path(executable)
    safe_path(model)
    if (
        executable.name not in {"llama-server", "llama-server.exe"}
        or not stat.S_ISREG(executable.stat().st_mode)
        or model.suffix != ".gguf"
        or not model.is_file()
    ):
        raise ValueError("Specify the approved llama-server executable and a local GGUF.")
    total = number(local["total_context"], 512, 32768, "total context", True)
    required = number(local["required_context"], 128, 8192, "required context", True)
    a = number(local["baseline_slots"], 1, 8, "baseline slots", True)
    b = number(local["candidate_slots"], 1, 8, "candidate slots", True)
    if a == b or min(total // a, total // b) < required:
        raise ValueError("Both slot profiles must satisfy the declared per-request context contract.")
    gate = Guard(
        Nvidia(cfg.gpu_index),
        number(local["max_vram_mib"], 1000, 100000, "VRAM limit", True),
        number(local["min_free_mib"], 512, 10000, "free VRAM floor", True),
        number(local["max_temp_c"], 45, 85, "temperature limit"),
    )
    accepted = fields(args.get("acceptance"), {"min_goodput_gain", "max_p95_regression"})
    gain = number(accepted["min_goodput_gain"], 0, 4, "minimum gain")
    regression = number(accepted["max_p95_regression"], 0, 1, "maximum p95 regression")
    new_directory(destination)
    model_hash = await asyncio.to_thread(digest, model)
    binary_hash = await asyncio.to_thread(digest, executable)
    record: dict[str, Any] = {
        "state": "running",
        "mode": "owned loopback ABBA",
        "required_context": required,
        "total_context": total,
        "model_sha256": model_hash,
        "engine_sha256": binary_hash,
        "slots": {"A": a, "B": b},
        "arms": [],
        "acceptance": {"min_goodput_gain": gain, "max_p95_regression": regression},
    }
    atomic(destination / "experiment.json", record)
    samples: dict[str, dict[str, Any]] = {}
    tasks = planned(cfg)
    largest_budget = 0

    async def arm(name: str, slots: int, measure: bool) -> None:
        nonlocal largest_budget
        available("127.0.0.1", port)
        if (await gate.sample()).get("unsafe"):
            raise ValueError("The GPU approval gate blocked launch.")
        other = shutil.which("nvidia-smi")
        if not other:
            raise ValueError("GPU ownership check requires nvidia-smi.")
        # Collect only whether another known inference process appears in the driver view.
        probe = await asyncio.create_subprocess_exec(
            other,
            "--query-compute-apps=process_name",
            "--format=csv,noheader",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            async with asyncio.timeout(5):
                info, _ = await probe.communicate()
        except TimeoutError:
            if probe.returncode is None:
                probe.kill()
                await probe.wait()
            raise
        if probe.returncode or any(x in info.lower() for x in (b"llama-server", b"ollama", b"vllm")):
            raise ValueError("Existing GPU compute or unavailable process telemetry blocked owned mode.")
        argv = [
            str(executable),
            "-m",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--alias",
            "audit-local",
            "--ctx-size",
            str(total),
            "--parallel",
            str(slots),
            "--fit",
            "off",
            "--device",
            "CUDA0",
            "--gpu-layers",
            "99",
            "--slots",
            "--metrics",
            "--reasoning",
            "off",
        ]
        shutdown_path = destination / f"{name}-shutdown.json"
        record["active_arm"] = name
        atomic(destination / "experiment.json", record)
        async with (
            owned(argv, url=cfg.url, slots=slots, evidence=shutdown_path) as process,
            client_for(cfg.url) as client,
        ):
            until = time.monotonic() + 90
            while time.monotonic() < until and process.poll() is None:
                if (await gate.sample()).get("unsafe"):
                    raise ValueError("The GPU approval gate stopped startup.")
                status, props = await get_json(client, "/props")
                if status == 200 and isinstance(props, dict) and props.get("total_slots") == slots:
                    slot_status, slot_data = await get_json(client, "/slots")
                    if (
                        slot_status == 200
                        and isinstance(slot_data, list)
                        and len(slot_data) == slots
                        and all(isinstance(x, dict) and x.get("n_ctx", 0) >= required for x in slot_data)
                    ):
                        break
                await asyncio.sleep(0.4)
            else:
                raise ValueError("Owned server did not verify readiness, slots and context.")
            if measure:
                if not largest_budget:
                    for task in (t for batch in tasks.values() for t in batch):
                        request = {
                            "messages": task.messages,
                            "chat_template_kwargs": {"enable_thinking": False},
                        }
                        if task.check == "tool":
                            request["tools"] = TOOLS
                        status, rendered = await get_json(client, "/apply-template", request)
                        if (
                            status != 200
                            or not isinstance(rendered, dict)
                            or not isinstance(rendered.get("prompt"), str)
                        ):
                            raise ValueError("The engine did not supply the chat template preflight.")
                        status, tokens = await get_json(
                            client, "/tokenize", {"content": rendered["prompt"], "add_special": True}
                        )
                        if (
                            status != 200
                            or not isinstance(tokens, dict)
                            or not isinstance(tokens.get("tokens"), list)
                        ):
                            raise ValueError("The engine did not supply the tokenization preflight.")
                        budget = len(tokens["tokens"]) + task.max_output + (512 if task.steps > 1 else 0)
                        largest_budget = max(largest_budget, budget)
                        if budget > required or (await gate.sample()).get("unsafe"):
                            raise ValueError(
                                "A planned request or the board exceeded the approved preflight budget."
                            )
                    record["max_preflight_context"] = largest_budget
                outcome = await run_benchmark(
                    cfg,
                    OpenAI(client, cfg),
                    destination / name,
                    gate,
                    identity=name,
                    verified_context=min(item["n_ctx"] for item in slot_data),
                )
                if outcome["state"] != "complete":
                    raise ValueError("The arm stopped before completing the approved plan.")
                samples[name] = analyze(destination / name)
        record["arms"].append(
            {"name": name, "slots": slots, "process_exited": True, "shutdown_evidence": shutdown_path.name}
        )
        record.pop("active_arm")
        atomic(destination / "experiment.json", record)

    try:
        for name, slots in (("A1", a), ("B1", b), ("B2", b), ("A2", a)):
            await arm(name, slots, True)
        record["decisions"] = compare(samples, gain, regression)
        if all(s["accepted"] for s in record["decisions"]):
            record["state"] = "accepted, no persistent changes"
        else:
            await arm("rollback", a, False)
            record["state"] = "rejected, baseline readiness restored and owned server stopped"
    except ShutdownError as error:
        record["state"] = (
            "operator_intervention_required"
            if error.record["state"] == "operator_intervention_required"
            else "aborted, owned server exit unverified"
        )
        record["shutdown_evidence"] = error.evidence.name
        raise
    except BaseException:
        record["state"] = "aborted"
        raise
    finally:
        atomic(destination / "experiment.json", record)
    return record
