import asyncio
from contextlib import asynccontextmanager
import json
import sys

import httpx
import pytest

from inference_audit import controlled
from inference_audit.config import parse
from inference_audit.evidence import append, read, rows, seal, verify
from inference_audit.runner import run_benchmark
from inference_audit.targets import OpenAI, client_for
from test_audit import Simulated, configuration, server


@pytest.fixture(params=["agent", "warm"])
def dependent_run(request, tmp_path):
    kind = request.param
    run = tmp_path / kind
    stages = [{"name": "probe", "pattern": kind, "count": 1, "mode": "closed"}]

    async def capture(engine, config):
        await run_benchmark(config, engine, run)

    if kind == "agent":
        with server("tools") as (url, _):
            config = parse(configuration(url, stages=stages))

            async def capture_agent():
                async with client_for(config.url) as client:
                    await capture(OpenAI(client, config), config)

            asyncio.run(capture_agent())
    else:
        config = parse({**configuration(stages=stages), "engine": "llama.cpp"})
        asyncio.run(capture(Simulated(), config))
    assert verify(run)["recorded"] == 1
    return run, rows(run / "events.jsonl")[0]


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("remove", "missing required successful steps"),
        ("extra", "step count"),
        ("finish_prime", "finish"),
        ("finish_followup", "finish"),
        ("invalid_finish", "invalid finish reason"),
        ("fail_prime", "failed request cannot precede"),
        ("fail_followup", "missing required successful steps"),
        ("admission", "Undispatched transaction"),
        ("fail_status_mismatch", "failure contradicts"),
        ("cache_proof", "Cached-token state contradicts"),
    ],
)
def test_resealed_dependent_evidence_rejects_inconsistent_steps(dependent_run, change, reason):
    run, row = dependent_run
    assert row["correct"] and len(row["steps"]) == 2
    steps = row["steps"]
    if change == "remove":
        steps.pop()
    elif change == "extra":
        steps.append(steps[-1].copy())
    elif change == "finish_prime":
        steps[0]["finish"] = "length"
    elif change == "finish_followup":
        steps[-1]["finish"] = "length"
    elif change == "invalid_finish":
        steps[-1]["finish"] = None
    elif change == "fail_prime":
        steps[0]["status"] = "timeout"
    elif change == "fail_followup":
        steps[-1]["status"] = "timeout"
    elif change == "cache_proof":
        steps[-1]["cache_status"] = "hit"
    else:
        row.update(
            status="admission_limit" if change == "admission" else "timeout", correct=False, on_time=False
        )
    with (run / "events.jsonl").open("w", encoding="utf-8") as handle:
        append(handle, row)
    seal(run)
    with pytest.raises(ValueError, match=reason):
        verify(run)


def test_genuine_failed_quality_can_keep_completed_streams(dependent_run):
    run, row = dependent_run
    row.update(correct=False, on_time=False)
    row["steps"][-1]["finish"] = "length"
    with (run / "events.jsonl").open("w", encoding="utf-8") as handle:
        append(handle, row)
    seal(run)
    assert verify(run)["recorded"] == 1


class FakeProcess:
    pid = 712

    def __init__(self, behavior):
        self.returncode = None
        self.behavior = behavior
        self.signals = []

    def poll(self):
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        if self.behavior == "signal_error":
            raise OSError("signal unavailable")
        if self.behavior == "exit":
            self.returncode = 0


@pytest.mark.parametrize(
    ("scenario", "behavior", "state", "reason", "signals"),
    [
        ("drains", "exit", "drained_and_exited", None, 1),
        ("busy_slot", "exit", "operator_intervention_required", "drain_not_confirmed", 0),
        ("queued_request", "exit", "operator_intervention_required", "drain_not_confirmed", 0),
        ("unavailable", "exit", "operator_intervention_required", "activity_unverified", 0),
        ("duplicate_gauge", "exit", "operator_intervention_required", "activity_unverified", 0),
        ("idle", "signal_error", "operator_intervention_required", "graceful_signal_failed", 1),
        ("idle", "ignore_signal", "operator_intervention_required", "exit_not_observed", 1),
    ],
)
def test_owned_shutdown_checks_slots_and_queue_before_only_graceful_signal(
    tmp_path, monkeypatch, scenario, behavior, state, reason, signals
):
    child = FakeProcess(behavior)
    calls = {"slots": 0, "metrics": 0}
    admitting = True

    def endpoint(request):
        assert not admitting
        if request.url.path == "/slots":
            calls["slots"] += 1
            active = scenario == "busy_slot" or scenario == "drains" and calls["slots"] == 1
            return httpx.Response(
                200, stream=httpx.ByteStream(json.dumps([{"id": 0, "is_processing": active}]).encode())
            )
        assert request.url.path == "/metrics"
        calls["metrics"] += 1
        deferred = int(scenario == "queued_request")
        body = "llamacpp:requests_processing 0\n"
        if scenario != "unavailable":
            body += f"llamacpp:requests_deferred {deferred}\n"
        if scenario == "duplicate_gauge":
            body += "llamacpp:requests_deferred 1\n"
        return httpx.Response(200, stream=httpx.ByteStream(body.encode()))

    @asynccontextmanager
    async def admission():
        nonlocal admitting
        try:
            yield
        finally:
            admitting = False

    monkeypatch.setattr(controlled.subprocess, "Popen", lambda *_, **__: child)
    monkeypatch.setattr(
        controlled,
        "client_for",
        lambda url: httpx.AsyncClient(base_url=url, transport=httpx.MockTransport(endpoint)),
    )
    monkeypatch.setattr(controlled, "SHUTDOWN_POLL_S", 0.002)
    monkeypatch.setattr(controlled, "DRAIN_TIMEOUT_S", 0.25)
    monkeypatch.setattr(controlled, "EXIT_TIMEOUT_S", 0.04)
    path = tmp_path / "A1-shutdown.json"

    async def run():
        async with (
            controlled.owned(["fake"], url="http://127.0.0.1:8080", slots=1, evidence=path),
            admission(),
        ):
            assert read(path)["state"] == "running"

    if reason is None:
        asyncio.run(run())
        assert calls == {"slots": 3, "metrics": 3}
    else:
        with pytest.raises(controlled.ShutdownError, match="Operator intervention"):
            asyncio.run(run())
    record = read(path)
    assert (record["state"], record["reason"], record["pid"]) == (state, reason, child.pid)
    assert record["drain_confirmed"] is bool(signals)
    assert len(child.signals) == signals
    assert (record["returncode"] is None) is (reason is not None)


def test_unverified_shutdown_leaves_the_real_cpu_child_running_after_loop_closes(tmp_path, monkeypatch):
    async def unavailable(child, url, slots, record):
        record.update(state="operator_intervention_required", reason="activity_unverified")

    monkeypatch.setattr(controlled, "shutdown", unavailable)
    path = tmp_path / "shutdown.json"
    child = None

    async def run():
        nonlocal child
        async with controlled.owned(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            url="http://127.0.0.1:8080",
            slots=1,
            evidence=path,
        ) as child:
            pass

    try:
        with pytest.raises(controlled.ShutdownError, match="Operator intervention"):
            asyncio.run(run())
        assert child is not None and child.poll() is None
        assert read(path)["returncode"] is None
    finally:
        if child is not None and child.poll() is None:
            # This fixture owns a sleeping Python process with no inference or GPU work.
            child.terminate()
            child.wait(timeout=4)


def test_unsignaled_exit_is_not_reported_as_a_drained_shutdown(tmp_path, monkeypatch):
    child = FakeProcess("exit")
    child.returncode = 0
    monkeypatch.setattr(controlled.subprocess, "Popen", lambda *_, **__: child)
    path = tmp_path / "shutdown.json"

    async def run():
        async with controlled.owned(["fake"], url="http://127.0.0.1:8080", slots=1, evidence=path):
            pass

    with pytest.raises(controlled.ShutdownError, match="exit.*without_drain"):
        asyncio.run(run())
    record = read(path)
    assert record["state"] == "unverified_exit"
    assert record["returncode"] == 0
    assert not record["drain_confirmed"] and not child.signals
