"""Async bounded scheduling and loss-aware transaction evidence."""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import random
import shutil
import time
from typing import Any, TextIO

from . import __version__
from .config import Config, Stage
from .evidence import (
    append,
    atomic,
    exclusive_lease,
    new_directory,
    read,
    rows,
    run_path,
    safe_path,
    seal,
    stable,
    verify,
)
from .targets import Engine, Reply, verified_tool
from .telemetry import Telemetry
from .workload import Task, check_answer, planned, task_record


def now() -> float:
    return time.monotonic()


def offsets(config: Config, stage: Stage) -> list[float]:
    rng = random.Random(f"{config.seed}:{stage.name}:arrivals")
    if stage.pattern == "burst":
        return [(i // stage.workers) * stage.workers / stage.rate for i in range(stage.count)]
    return [(i + rng.uniform(0.15, 0.75)) / stage.rate for i in range(stage.count)]


class Pacer:
    def __init__(self, rate: float):
        self.interval = 1 / rate
        self.next_start = 0.0
        self.lock = asyncio.Lock()

    async def admit(self, deadline: float) -> float | None:
        async with self.lock:
            target = max(now(), self.next_start)
            if target >= deadline:
                return None
            await asyncio.sleep(max(0.0, target - now()))
            dispatch = now()
            if dispatch >= deadline:
                return None
            self.next_start = dispatch + self.interval
            return dispatch


def fingerprint(config: Config) -> str:
    return hashlib.sha256(stable(asdict(config)).encode()).hexdigest()


def resume_from(previous: Path, config: Config) -> set[str]:
    configuration_hash = fingerprint(config)
    completed: set[str] = set()
    visited: set[str] = set()
    current = previous
    while current.name not in visited and len(visited) < 64:
        visited.add(current.name)
        with exclusive_lease(current / ".active"):
            plan, checkpoint = read(current / "plan.json"), read(current / "checkpoint.json")
            if (current / "integrity.json").exists():
                verify(current)
            saved = rows(current / "events.jsonl", recover=True)
        if (
            plan.get("schema") != 2
            or plan.get("tool_version") != __version__
            or plan["configuration_sha256"] != configuration_hash
        ):
            raise ValueError("Resume requires the original tool version and exact configuration.")
        if checkpoint["state"] == "complete":
            raise ValueError("The prior run is already complete.")
        known = set(checkpoint["completed_stages"])
        for stage in plan["stages"]:
            if stage["name"] in known:
                ids = [e["id"] for e in saved if e["stage"] == stage["name"]]
                if sorted(ids) != sorted(t["id"] for t in stage["tasks"]):
                    raise ValueError("Completed checkpoint stage does not match saved rows.")
                completed.add(stage["name"])
        parent = plan.get("parent_run")
        if parent is None:
            return completed
        current = run_path(previous.parent, parent)
    raise ValueError("Invalid continuation history.")


def step_record(reply: Reply, dispatch: float) -> dict[str, Any]:
    return {
        "status": reply.status,
        "latency_s": reply.elapsed,
        "ttft_s": reply.ttft,
        "finish": reply.finish,
        "prompt_tokens": reply.prompt,
        "output_tokens": reply.output,
        "cached_tokens": reply.cached,
        "server_timing": reply.timing,
        "dispatch_s": dispatch,
        "first_output_s": reply.first_output,
        "observed": reply.observed,
        "token_status": reply.token_status,
        "cache_status": reply.cache_status,
    }


async def transaction(
    engine: Engine,
    config: Config,
    stage: Stage,
    task: Task,
    due: float,
    hard_end: float,
    pacer: Pacer,
    start: float,
    base: dict[str, Any],
    workers: asyncio.Semaphore,
) -> dict[str, Any]:
    deadline = min(hard_end, due + config.dispatch_slack_s)
    try:
        async with asyncio.timeout(max(0, deadline - now())):
            await workers.acquire()
    except TimeoutError:
        return base
    try:
        return await execute(engine, config, stage, task, due, hard_end, pacer, start, base, deadline)
    finally:
        workers.release()


async def execute(
    engine: Engine,
    config: Config,
    stage: Stage,
    task: Task,
    due: float,
    hard_end: float,
    pacer: Pacer,
    start: float,
    base: dict[str, Any],
    deadline: float,
) -> dict[str, Any]:
    dispatch = await pacer.admit(deadline)
    if dispatch is None:
        return base
    base.update(dispatch_s=dispatch - start, queue_s=max(0.0, dispatch - due))
    reply = await engine.send(
        task, task.messages, task.check == "tool", min(config.timeout_s, hard_end - now())
    )
    records = [step_record(reply, dispatch - start)]
    base["steps"] = records
    status = reply.status
    checked = False
    if status == "ok":
        if task.steps == 2:
            call = verified_tool(reply, task) if task.check == "tool" else None
            if task.check == "tool" and call is None:
                status = "incorrect_tool"
            elif (follow_dispatch := await pacer.admit(hard_end)) is None:
                status = "runtime_budget"
            else:
                messages = task.messages
                if call:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": None, "tool_calls": [call]},
                        {"role": "tool", "tool_call_id": call["id"], "content": str(task.expected)},
                    ]
                follow = await engine.send(task, messages, False, min(config.timeout_s, hard_end - now()))
                records.append(step_record(follow, follow_dispatch - start))
                status = follow.status
                checked = (
                    check_answer(task, follow.text, "receipt")
                    and follow.finish == "stop"
                    and (
                        task.check != "warm_receipt"
                        or check_answer(task, reply.text)
                        and reply.finish == "stop"
                    )
                )
        else:
            checked = check_answer(task, reply.text) and (
                reply.finish == "stop"
                or stage.pattern in {"decode", "concurrent"}
                and reply.finish == "length"
            )
    elapsed = now() - due
    # Tool deltas are usable output for an agent, but never count as visible content.
    first = reply.first_output if task.check == "tool" else reply.ttft
    ttft = None if first is None else dispatch - due + first
    delay, duration = config.slo[task.family]
    base.update(
        status=status,
        steps=records,
        correct=checked,
        latency_s=elapsed,
        ttft_s=ttft,
        end_s=now() - start,
        first_visible_s=next(
            (s["dispatch_s"] + s["ttft_s"] - (due - start) for s in records if s["ttft_s"] is not None),
            None,
        ),
        on_time=status == "ok" and checked and ttft is not None and ttft <= delay and elapsed <= duration,
    )
    return base


async def stage_run(
    engine: Engine,
    config: Config,
    stage: Stage,
    tasks: list[Task],
    offsets_s: list[float],
    hard_end: float,
    handle: TextIO,
    pacer: Pacer,
    stop: asyncio.Event,
    origin: float,
) -> tuple[float, str | None]:
    pending: set[asyncio.Task[dict[str, Any]]] = set()
    inflight: dict[asyncio.Task[dict[str, Any]], dict[str, Any]] = {}
    workers = asyncio.Semaphore(stage.workers)
    wall = time.time()

    def save_finished(futures: set[asyncio.Task[dict[str, Any]]]) -> None:
        for f in futures:
            if not f.cancelled() and f.exception() is None:
                append(handle, f.result())
                inflight.pop(f)
            pending.discard(f)

    reason: str | None = "interrupted"
    try:
        async with asyncio.timeout(max(0.0, hard_end - now())):
            for task, offset in zip(tasks, offsets_s, strict=True):
                if abs((time.time() - wall) - (now() - origin)) > 5:
                    reason = "clock_discontinuity"
                    break
                if stage.mode == "open":
                    due = origin + offset
                    await asyncio.sleep(max(0.0, due - now()))
                else:
                    if len(pending) >= stage.workers:
                        done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                        save_finished(done)
                    due = now()
                if abs((time.time() - wall) - (now() - origin)) > 5:
                    reason = "clock_discontinuity"
                    break
                if stop.is_set():
                    break
                save_finished({f for f in pending if f.done()})
                base = {
                    "id": task.id,
                    "stage": stage.name,
                    "family": task.family,
                    "scheduled_s": due - origin,
                    "status": "dispatch_deadline",
                    "steps": [],
                    "correct": False,
                    "on_time": False,
                }
                if len(pending) >= stage.workers + config.queue_limit:
                    base["status"] = "admission_limit"
                    append(handle, base)
                else:
                    base["client_admitted"] = True
                    f = asyncio.create_task(
                        transaction(engine, config, stage, task, due, hard_end, pacer, origin, base, workers)
                    )
                    pending.add(f)
                    inflight[f] = base
            else:
                reason = None
            while pending:
                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                save_finished(done)
            if abs((time.time() - wall) - (now() - origin)) > 5:
                reason = "clock_discontinuity"
            if inflight and reason is None:
                reason = "request_engine_error"
    except TimeoutError:
        reason = "runtime_budget"
    finally:
        save_finished({f for f in pending if f.done() and not f.cancelled()})
        for f in pending:
            f.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for partial in inflight.values():
            append(handle, {**partial, "status": "interrupted"})
        os.fsync(handle.fileno())
    return now() - origin, reason


async def monitor(
    sensor: Telemetry, handle: TextIO, end: asyncio.Event, stop: asyncio.Event, checkpoint: dict[str, Any]
) -> None:
    while not end.is_set():
        try:
            row = await sensor.sample()
        except (TimeoutError, OSError, ValueError):
            row = {"state": "unavailable", "reason": "GPU sample failed"}
        row.setdefault("t", now())
        append(handle, row)
        if row.get("unsafe") or (getattr(sensor, "required", False) and row["state"] != "ok"):
            checkpoint["reason"] = "gpu_safety"
            stop.set()
            return
        try:
            async with asyncio.timeout(1.5):
                await end.wait()
        except TimeoutError:
            pass


async def stop_file(run: Path, stop: asyncio.Event, checkpoint: dict[str, Any]) -> None:
    while not stop.is_set():
        if (run / "STOP").exists():
            checkpoint["reason"] = "operator_stop"
            stop.set()
            return
        await asyncio.sleep(0.2)


async def watch_runtime(run: Path, stop: asyncio.Event, checkpoint: dict[str, Any]) -> None:
    last = now()
    saved = last
    while not stop.is_set():
        tick = now()
        if tick - last > 6:
            checkpoint["reason"] = "scheduler_discontinuity"
            stop.set()
            return
        if shutil.disk_usage(run).free < 8 * 1024**2:
            checkpoint["reason"] = "disk_space"
            stop.set()
            return
        if tick - saved >= 15:
            checkpoint["heartbeat_utc"] = datetime.now(timezone.utc).isoformat()
            atomic(run / "checkpoint.json", checkpoint)
            saved = tick
        last = tick
        await asyncio.sleep(1)


async def monitor_server(engine: Engine, handle: TextIO, end: asyncio.Event) -> None:
    sample = getattr(engine, "counters", None)
    if sample is None:
        await end.wait()
        return
    while not end.is_set():
        values = await sample()
        if values is not None:
            append(handle, {"t": now(), "counters": values})
        try:
            async with asyncio.timeout(5):
                await end.wait()
        except TimeoutError:
            pass


async def run_benchmark(
    config: Config,
    engine: Engine,
    run: Path,
    sensor: Telemetry | None = None,
    previous: Path | None = None,
    identity: str | None = None,
    verified_context: int | None = None,
    target_capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tasks = planned(config)
    skip = resume_from(previous, config) if previous else set()
    stages = [s for s in config.stages if s.name not in skip]
    if not stages:
        raise ValueError("No unfinished stages to resume.")
    safe_path(run)
    plan: dict[str, Any] = {
        "schema": 2,
        "tool_version": __version__,
        "label": config.label,
        "engine_hint": config.engine,
        "seed": config.seed,
        "gpu_index": config.gpu_index,
        "configuration_sha256": fingerprint(config),
        "parent_run": previous.name if previous else None,
        "launch_id": identity,
        "worker_context_verified": verified_context,
        "target_capabilities": target_capabilities or {},
        "sampling": {
            "temperature": 0,
            "seed_sent": config.engine == "llama.cpp",
            "llama_thinking_requested_off": config.engine == "llama.cpp",
        },
        "system": {"platform": os.name},
        "qualification": {
            "min_correct_share": config.min_correct_share,
            "min_on_time_share": config.min_on_time_share,
            "max_error_share": config.max_error_share,
            "required_context": config.required_context,
            "families": config.family_gates,
        },
        "slo": config.slo,
        "limits": {
            "requests": config.max_requests,
            "runtime_s": config.runtime_s,
            "concurrency": config.max_concurrency,
            "rps": config.max_rps,
            "response_bytes": config.max_response_bytes,
            "evidence_mib": config.evidence_mib,
            "client_queue": config.queue_limit,
            "timeout_s": config.timeout_s,
            "dispatch_slack_s": config.dispatch_slack_s,
        },
        "stages": [
            {**asdict(s), "offsets_s": offsets(config, s), "tasks": [task_record(t) for t in tasks[s.name]]}
            for s in stages
        ],
    }
    # Reserve space before side effects. Response content is never written to evidence.
    bound: float = len(stable(plan)) + 4096 * sum(t.steps for s in stages for t in tasks[s.name])
    bound += 1024 * (config.runtime_s / 1.5 + config.runtime_s / 5) + 131072
    if bound > config.evidence_mib * 1024**2:
        raise ValueError("Planned evidence exceeds the configured storage budget.")
    existing = next(p for p in run.absolute().parents if p.is_dir())
    if shutil.disk_usage(existing).free < bound + 16 * 1024**2:
        raise ValueError("Insufficient free disk space for the evidence budget.")
    new_directory(run)
    atomic(run / "plan.json", plan)
    checkpoint: dict[str, Any] = {
        "state": "running",
        "completed_stages": [],
        "spans_s": {},
        "origins_s": {},
        "reason": None,
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    end, stop = asyncio.Event(), asyncio.Event()
    pacer = Pacer(config.max_rps)
    hard_end = now() + config.runtime_s
    with (
        exclusive_lease(run / ".active"),
        (run / "events.jsonl").open("x", encoding="utf-8") as data,
        (run / "gpu.jsonl").open("x", encoding="utf-8") as gpu,
        (run / "server.jsonl").open("x", encoding="utf-8") as counters,
    ):
        if sensor is None:
            append(gpu, {"state": "unavailable", "reason": "No local telemetry enabled"})
        atomic(run / "checkpoint.json", checkpoint)
        watcher = asyncio.create_task(monitor(sensor, gpu, end, stop, checkpoint)) if sensor else None
        server_watch = asyncio.create_task(monitor_server(engine, counters, end))
        cancel = asyncio.create_task(stop_file(run, stop, checkpoint))
        disk = asyncio.create_task(watch_runtime(run, stop, checkpoint))
        wait_stop = asyncio.create_task(stop.wait())
        try:
            for stage in stages:
                checkpoint["active_stage"] = stage.name
                checkpoint["origins_s"][stage.name] = now()
                atomic(run / "checkpoint.json", checkpoint)
                pacer.interval = (
                    1 / min(config.max_rps, stage.rate) if stage.mode == "closed" else 1 / config.max_rps
                )
                began = checkpoint["origins_s"][stage.name]
                work = asyncio.create_task(
                    stage_run(
                        engine,
                        config,
                        stage,
                        tasks[stage.name],
                        offsets(config, stage),
                        hard_end,
                        data,
                        pacer,
                        stop,
                        began,
                    )
                )
                try:
                    guards = [wait_stop, server_watch, disk, cancel]
                    if watcher is not None:
                        guards.append(watcher)
                    await asyncio.wait((work, *guards), return_when=asyncio.FIRST_COMPLETED)
                    for guard in guards:
                        if guard.done() and not guard.cancelled() and guard.exception() is not None:
                            guard.result()
                    span, reason = work.result() if work.done() else (now() - began, "stopped")
                finally:
                    if not work.done():
                        work.cancel()
                        await asyncio.gather(work, return_exceptions=True)
                checkpoint["spans_s"][stage.name] = span
                if reason or stop.is_set():
                    checkpoint["state"] = "incomplete"
                    checkpoint["reason"] = checkpoint["reason"] or reason
                    break
                checkpoint["completed_stages"].append(stage.name)
                atomic(run / "checkpoint.json", checkpoint)
            else:
                checkpoint["state"] = "complete"
        except BaseException:
            checkpoint["state"] = "interrupted"
            checkpoint["reason"] = checkpoint["reason"] or "runner_interrupted"
            raise
        finally:
            end.set()
            cancel.cancel()
            disk.cancel()
            wait_stop.cancel()
            await asyncio.gather(
                cancel, disk, wait_stop, server_watch, *([watcher] if watcher else []), return_exceptions=True
            )
            checkpoint["recorded"] = len(rows(run / "events.jsonl", recover=True))
            checkpoint["pending_planned"] = (
                sum(len(s["tasks"]) for s in plan["stages"]) - checkpoint["recorded"]
            )
            checkpoint["ended_utc"] = datetime.now(timezone.utc).isoformat()
            atomic(run / "checkpoint.json", checkpoint)
            gpu.flush()
            os.fsync(gpu.fileno())
            counters.flush()
            os.fsync(counters.fileno())
            seal(run)
    return checkpoint
