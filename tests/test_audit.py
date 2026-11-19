import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time

import pytest

from inference_audit.analysis import analyze, percentile, wilson
from inference_audit.cli import invoke, parser
from inference_audit.config import authorize, parse
from inference_audit.controlled import compare
from inference_audit.economics import Assumptions, estimate
from inference_audit.evidence import exclusive_lease, read, rows, run_path, verify
from inference_audit.legacy import import_summary, verify_import
from inference_audit.reporting import render
from inference_audit.runner import run_benchmark
from inference_audit.targets import OpenAI, Reply, client_for, inspect, verified_tool
from inference_audit.workload import Task, check_answer, planned


def configuration(url="http://127.0.0.1:8080", count=3, stages=None, **limits):
    return {
        "label": "Demo local audit",
        "target": {"url": url, "model": "internal-customer-model"},
        "authorization": {"approved": True},
        "limits": {
            "max_requests": 15,
            "runtime_s": 5,
            "timeout_s": 1,
            "max_concurrency": 2,
            "max_rps": 20,
            "dispatch_slack_s": 0.3,
            **limits,
        },
        "stages": stages
        or [{"name": "one", "pattern": "decode", "mode": "closed", "workers": 2, "count": count}],
    }


@contextmanager
def server(scenario="normal", ssl_context=None):
    lock = threading.Lock()
    stats = {"starts": [], "active": 0, "peak": 0, "requests": 0}

    class Wire(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            code, body = (
                (200, {"data": [{"id": "fixture-model"}]}) if self.path == "/v1/models" else (404, {})
            )
            self.send_response(code)
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def send_event(self, payload):
            raw = payload if isinstance(payload, str) else json.dumps(payload)
            self.wfile.write(f"data: {raw}\r\n\r\n".encode())
            self.wfile.flush()

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            text = body["messages"][0]["content"]
            rx = re.search(r"R[0-9A-F]{12}", text)
            receipt = rx[0] if rx else "response"
            with lock:
                stats["starts"].append(time.monotonic())
                stats["requests"] += 1
                stats["active"] += 1
                stats["peak"] = max(stats["peak"], stats["active"])
            try:
                if scenario == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1:9/forbidden")
                    self.end_headers()
                    return
                if scenario in {"overload", "context"}:
                    self.send_response(429 if scenario == "overload" else 400)
                    self.end_headers()
                    self.wfile.write(b'{"error":{"code":"context_length_exceeded"}}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                if scenario == "malformed":
                    self.send_event('{"choices":[{"delta":{"content":123}}]}')
                    return
                if scenario == "oversized":
                    self.send_event("x" * 8192)
                    return
                time.sleep(0.22 if scenario in {"slow", "timeout"} else 0.035)
                self.send_event(
                    {"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
                )
                if scenario == "early_usage":
                    self.send_event({"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 12}})
                use_tool = scenario == "tools" and isinstance(body.get("tool_choice"), dict)
                delta = {"content": receipt}
                if use_tool:
                    delta = {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_fixture",
                                "type": "function",
                                "function": {
                                    "name": "lookup_receipt",
                                    "arguments": json.dumps({"case": receipt}),
                                },
                            }
                        ]
                    }
                elif scenario == "tools":
                    assert body["messages"][-1]["content"] == receipt
                    assert body["messages"][-1]["tool_call_id"] == "call_fixture"
                self.send_event({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]})
                self.send_event(
                    {
                        "choices": [
                            {"index": 0, "delta": {}, "finish_reason": "tool_calls" if use_tool else "stop"}
                        ]
                    }
                )
                if scenario not in {"missing", "early_usage"}:
                    self.send_event(
                        {
                            "choices": [],
                            "usage": {
                                "prompt_tokens": 9,
                                "completion_tokens": 12,
                                "total_tokens": 999 if scenario == "bad_usage" else 21,
                                "prompt_tokens_details": {"cached_tokens": 0},
                            },
                        }
                    )
                if scenario != "broken":
                    self.send_event("[DONE]")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            finally:
                with lock:
                    stats["active"] -= 1

    app = ThreadingHTTPServer(("127.0.0.1", 0), Wire)
    if ssl_context is not None:
        app.socket = ssl_context.wrap_socket(app.socket, server_side=True)
    thread = threading.Thread(target=app.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{app.server_port}", stats
    finally:
        app.shutdown()
        app.server_close()
        thread.join()


def test_authorized_target_validation():
    assert authorize("http://localhost:8080", [])[0] == "http://127.0.0.1:8080"
    assert authorize("https://approved.example", ["https://approved.example"])[0].endswith(":443")
    for address in (
        "https://other.example",
        "http://approved.example",
        "https://user:secret@approved.example",
        "http://127.0.0.1:8080/#fragment",
        "http://127.0.0.1:8080\\@host",
    ):
        with pytest.raises(ValueError):
            authorize(address, ["https://approved.example"])
    with pytest.raises(ValueError):
        run_path(Path("runs"), "../secrets")


def test_config_requires_authorization_and_caps():
    raw = configuration(count=3, max_requests=2)
    with pytest.raises(ValueError):
        parse(raw)
    raw["authorization"]["approved"] = False
    with pytest.raises(ValueError, match="authorization"):
        parse(raw)
    with pytest.raises(ValueError):
        parse(configuration(max_rps=float("inf")))


def test_load_flag_checked_before_network(tmp_path):
    args = parser().parse_args(
        ["--runs-dir", str(tmp_path), "benchmark", "--run", "test", "--config", "missing.yaml"]
    )
    with pytest.raises(ValueError, match="approve-load"):
        asyncio.run(invoke(args))


def test_run_lease_excludes_active_peer(tmp_path):
    lease = tmp_path / ".active"
    with exclusive_lease(lease):
        with pytest.raises(ValueError, match="owns the requested lease"), exclusive_lease(lease):
            pytest.fail("Lease was acquired by a second handle")
    with exclusive_lease(lease):
        assert lease.exists()


def test_discovery_only_get():
    with server() as (url, stats):

        async def go():
            async with client_for(url) as client:
                result = await inspect(client)
                assert result["models"] == ["fixture-model"]
                assert result["streaming"].startswith("unverified")

        asyncio.run(go())
        assert stats["requests"] == 0


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("normal", "ok"),
        ("missing", "ok"),
        ("early_usage", "ok"),
        ("broken", "incomplete_stream"),
        ("timeout", "timeout"),
        ("redirect", "http_302"),
        ("overload", "overload_429"),
        ("context", "context_limit"),
        ("malformed", "invalid_delta"),
        ("bad_usage", "ok"),
        ("oversized", "oversize"),
    ],
)
def test_wire_streams(scenario, expected):
    with server(scenario) as (url, _):
        config = parse(configuration(url, max_response_bytes=4096))
        task = planned(config)["one"][0]

        async def go():
            async with client_for(config.url) as client:
                return await OpenAI(client, config).send(
                    task, task.messages, False, 0.12 if scenario == "timeout" else 1
                )

        reply = asyncio.run(go())
        assert reply.status == expected
        if scenario in {"missing", "early_usage"}:
            assert reply.output is None and reply.token_status == "missing_token_usage"
        elif scenario == "bad_usage":
            assert reply.output is None and reply.token_status == "token_accounting_mismatch"
        elif expected == "ok":
            assert reply.output == 12
            assert reply.ttft is not None and 0.02 < reply.ttft <= reply.elapsed
            timing = reply.observed
            assert timing["request_start"] <= timing["response_headers"] <= timing["first_content"]
            assert timing["first_content"] <= timing["last_content"] <= timing["usage_event"]
            assert timing["usage_event"] <= timing["stream_complete"] <= timing["termination"]


def test_bounded_concurrency_and_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_TOKEN", "private-fake-token")
    with server("slow") as (url, stats):
        raw = configuration(url, count=6)
        raw["target"]["credential_env"] = "AUDIT_TOKEN"
        cfg = parse(raw)
        run = tmp_path / "example"

        async def go():
            async with client_for(cfg.url, cfg.credential_env) as client:
                return await run_benchmark(cfg, OpenAI(client, cfg), run)

        checkpoint = asyncio.run(go())
        assert checkpoint["state"] == "complete"
        assert stats["requests"] == 6 and stats["peak"] == 2
        assert all(b - a >= 0.04 for a, b in zip(stats["starts"], stats["starts"][1:]))
        analysis = analyze(run)
        assert analysis["stages"][0]["metrics"]["output_tokens"] == 72
        assert analysis["gpu"]["state"] == "unavailable"
        render(analysis, run / "report")
        for file in ("audit.html", "audit.json", "audit.md"):
            content = (run / "report" / file).read_text(encoding="utf-8")
            assert "private-fake-token" not in content and "internal-customer-model" not in content
    assert verify(run)["recorded"] == 6
    with (run / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write("{}\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify(run)


def test_open_loop_records_rejections(tmp_path):
    with server("slow") as (url, _):
        cfg = parse(
            configuration(
                url,
                stages=[
                    {
                        "name": "burst",
                        "pattern": "burst",
                        "mode": "open",
                        "rate": 20,
                        "count": 10,
                        "workers": 2,
                    }
                ],
            )
        )

        async def go():
            async with client_for(cfg.url) as client:
                return await run_benchmark(cfg, OpenAI(client, cfg), tmp_path / "run")

        asyncio.run(go())
        events = rows(tmp_path / "run/events.jsonl")
        assert len(events) == 10
        assert any(r["status"] == "admission_limit" for r in events)


class Simulated:
    async def send(self, task, messages, tool, timeout):
        await asyncio.sleep(0.02)
        return Reply("ok", 0.02, 0.01, "stop", 10, 2, None, str(task.expected), [])


def test_stop_checkpoint_resume(tmp_path):
    cfg = parse(
        configuration(
            stages=[
                {"name": "first", "pattern": "decode", "mode": "closed", "count": 2},
                {"name": "second", "pattern": "decode", "mode": "open", "count": 3, "rate": 2},
            ]
        )
    )
    first, second = tmp_path / "first", tmp_path / "second"

    async def go():
        async def stop():
            while not (first / "checkpoint.json").exists():
                await asyncio.sleep(0.01)
            while read(first / "checkpoint.json")["active_stage"] != "second":
                await asyncio.sleep(0.01)
            (first / "STOP").touch()

        await asyncio.gather(run_benchmark(cfg, Simulated(), first), stop())
        await run_benchmark(cfg, Simulated(), second, previous=first)

    asyncio.run(go())
    assert verify(first)["state"] == "incomplete"
    assert read(first / "checkpoint.json")["completed_stages"] == ["first"]
    assert verify(second)["planned"] == 3
    assert read(second / "plan.json")["parent_run"] == "first"


def test_required_gpu_guard_stops_before_long_run(tmp_path):
    class Unsafe:
        required = True

        async def sample(self):
            return {"state": "ok", "unsafe": "temperature"}

    cfg = parse(
        configuration(stages=[{"name": "load", "pattern": "decode", "mode": "open", "count": 10, "rate": 1}])
    )
    asyncio.run(run_benchmark(cfg, Simulated(), tmp_path / "guarded", Unsafe()))
    assert verify(tmp_path / "guarded")["state"] == "incomplete"
    assert not rows(tmp_path / "guarded/events.jsonl")


def test_total_runtime_budget_retains_planned_denominator(tmp_path):
    cfg = parse(
        configuration(
            runtime_s=1,
            stages=[{"name": "paced", "pattern": "decode", "mode": "open", "count": 5, "rate": 0.05}],
        )
    )
    run = tmp_path / "bounded"
    start = time.monotonic()
    asyncio.run(run_benchmark(cfg, Simulated(), run))
    assert time.monotonic() - start < 2.5
    assert verify(run)["state"] == "incomplete"
    m = analyze(run)["stages"][0]["metrics"]
    assert m["offered"] == m["unrecorded"] == 5


def test_quality_checks_and_tool_schema():
    m = [{"role": "user", "content": "synthetic"}]
    py = Task("test", "coding", m, "code", 37, 32)
    assert check_answer(py, "def answer():\n    return 37")
    assert not check_answer(py, "def answer(f=print('x')):\n    return 37")
    assert not check_answer(py, "def answer():\n    return int('37')")
    j = Task("json", "chat", m, "json", "blue", 32)
    assert check_answer(j, '{"receipt":"blue"}')
    assert not check_answer(j, '{"receipt":"blue","extra":1}')
    t = Task("tool", "agent", m, "tool", "blue", 32)
    call = {
        "id": "test_1",
        "type": "function",
        "function": {"name": "lookup_receipt", "arguments": '{"case":"blue"}'},
    }
    reply = Reply("ok", 1, 0.1, "tool_calls", 10, 4, 0, "", [call])
    assert verified_tool(reply, t) == call
    call["function"]["arguments"] = '{"case":"blue","extra":1}'
    assert verified_tool(reply, t) is None


def test_dependent_tool_transaction(tmp_path):
    with server("tools") as (url, stats):
        cfg = parse(
            configuration(url, stages=[{"name": "tools", "pattern": "agent", "mode": "closed", "count": 2}])
        )

        async def go():
            async with client_for(cfg.url) as client:
                return await run_benchmark(cfg, OpenAI(client, cfg), tmp_path / "agent")

        assert asyncio.run(go())["state"] == "complete"
        assert stats["requests"] == 4
        m = analyze(tmp_path / "agent")["stages"][0]["metrics"]
        assert m["valid"] == m["on_time"] == 2
        assert m["output_tokens"] == 48


def test_stats_and_cost_gates():
    assert percentile([1.0, 2.0, 3.0], 0.95, 40) is None
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 2
    assert wilson(95, 100)[0] < 0.95
    result = estimate(Assumptions(0.5, 0.5, 2, 0.25, 0, 4), 100, 1, 0.8, 1.1)
    assert result["conditional_workers"] == 3
    assert result["usd_per_on_time"] > result["usd_per_successful"]
    assert estimate(Assumptions(0.5, 0.5, 2, 0.25, 0), 100, 1, 0.8, None)["conditional_workers"] is None


def test_acceptance_requires_two_controls_and_family_gate():
    def run(good, qualified):
        return {
            "stages": [
                {
                    "name": "x",
                    "contract_sha256": "same fixture contract",
                    "strict_qualifies": qualified,
                    "metrics": {"goodput_rps": good, "latency_s": {"p95": 2.0}, "ttft_s": {"p95": 1.0}},
                }
            ]
        }

    panel = {k: run(v, True) for k, v in zip(("A1", "B1", "B2", "A2"), (1, 1.4, 1.4, 1.1), strict=True)}
    assert compare(panel, 0.1, 0.1)[0]["accepted"]
    panel["B2"] = run(2, False)
    assert not compare(panel, 0.1, 0.1)[0]["accepted"]


def test_legacy_summary_import_preserves_source(tmp_path):
    source = tmp_path / "origin"
    (source / "results").mkdir(parents=True)
    csv = source / "results/summary.csv"
    raw = "run,valid_for_comparison,decode_tps,c2_tps,prefill_4096_tps,prefill_7168_tps,peak_device_mib\nA,True,82,145,100,100,2048\n"
    csv.write_text(raw, encoding="utf-8")
    target = tmp_path / "legacy"
    import_summary(source, 1, target)
    assert csv.read_text(encoding="utf-8") == raw
    report = verify_import(target)
    assert report["rows"][0]["decode_tps"] == 82
    render(report, target / "report")
    assert "original evidence not revalidated" in (target / "report/audit.json").read_text()
