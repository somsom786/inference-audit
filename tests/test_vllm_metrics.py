"""Synthetic software checks. These fixtures contain no accelerator measurements."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from inference_audit.analysis import analyze
from inference_audit.config import parse
from inference_audit.evidence import read, seal, verify
from inference_audit.reporting import render
from inference_audit.runner import run_benchmark
from inference_audit.targets import OpenAI, inspect
from inference_audit.vllm_metrics import collect, findings, parse_prometheus, summarize, validate_snapshots
from test_audit import configuration

LABEL = '{engine="0",model_name="private-stage-model"}'


def image(wait=2, cache=0.95, preempt=3, le=10, inf=50, upper=0.2):
    return (
        f"vllm:num_requests_waiting{LABEL} {wait}\n"
        f"vllm:kv_cache_usage_perc{LABEL} {cache}\n"
        f"vllm:num_preemptions_total{LABEL} {preempt}\n"
        f'vllm:num_requests_waiting{{engine="1",model_name="private-stage-model"}} 4\n'
        f'vllm:time_to_first_token_seconds_bucket{LABEL[:-1]},le="{upper}"}} {le}\n'
        f'vllm:time_to_first_token_seconds_bucket{LABEL[:-1]},le="+Inf"}} {inf}\n'
    )


def with_time(t, projected):
    return {"start_s": t - 0.1, "t": t, "counters": {}, "vllm_schema": 1, **projected}


def sample(t, **kwargs):
    return with_time(t, {"state": "observed", "series": parse_prometheus(image(**kwargs))})


def test_label_separation_deltas_and_histogram():
    records = [
        sample(1),
        sample(2, wait=3, preempt=6, le=59, inf=100),
        sample(3, wait=12, preempt=2, le=0, inf=2),
    ]
    validate_snapshots(records)
    report = summarize(records, {"origins_s": {"load": 0.0}, "spans_s": {"load": 3.0}})
    series = report["phases"]["load"]["series"]
    assert sorted(r["max"] for r in series if r["metric"] == "waiting") == [4, 12]
    assert "private-stage-model" not in json.dumps(report)
    preemptions = next(r for r in series if r["metric"] == "preemptions")
    assert preemptions["observed_delta"] == 3 and preemptions["detected_resets"] == 1
    ttft = next(r for r in series if r["metric"] == "ttft_seconds")
    assert ttft["p95_bucket"] == {"low_s": 0, "high_s": 0.2}
    assert ttft["observations"] == 50 and ttft["detected_resets"] == 1
    assert len(findings(report)) == 2


def test_incompatible_histogram_and_missing_scrapes_are_not_combined():
    records = [
        sample(1),
        with_time(2, {"state": "transport_failure"}),
        sample(3, upper=0.1),
        sample(4, upper=0.4),
        sample(5, upper=0.4, preempt=4, le=98, inf=140),
    ]
    result = summarize(records, {"origins_s": {"a": 0, "b": 4.95}, "spans_s": {"a": 5, "b": 1}})
    assert result["phases"]["b"]["scrapes"] == 0
    series = result["phases"]["a"]["series"]
    hist = next(r for r in series if r["kind"] == "histogram")
    assert hist["observations"] == 90 and hist["gaps"] == 2
    assert hist["p95_bucket"] == {"low_s": 0, "high_s": 0.4}


def test_kv_legacy_alias_invalid_and_duplicate_samples():
    parsed = parse_prometheus(
        "vllm:gpu_cache_usage_perc 0.5\nvllm:num_requests_waiting -1\n"
        "vllm:kv_cache_usage_perc 50\nvllm:num_requests_running 1\nvllm:num_requests_running 2\n"
    )
    assert [(r["metric"], r["value"]) for r in parsed] == [("kv_usage_fraction", 0.5)]


def test_prefix_rate_uses_only_common_monotone_label_intervals():
    def prefix(t, hits, queries):
        body = f"vllm:prefix_cache_hits_total{LABEL} {hits}\nvllm:prefix_cache_queries_total{LABEL} {queries}"
        return with_time(t, {"state": "observed", "series": parse_prometheus(body)})

    samples = [prefix(1, 9, 11), prefix(2, 10, 15), prefix(3, 1, 2), prefix(4, 4, 7)]
    report = summarize(samples, {"origins_s": {"a": 0}, "spans_s": {"a": 4}})
    (reuse,) = report["phases"]["a"]["prefix_reuse"]
    assert reuse["hits_delta"] == 4
    assert reuse["queries_delta"] == 9
    assert reuse["observed_hit_fraction"] == 4 / 9


def test_requires_explicit_metrics_approval_and_vllm_adapter():
    config = configuration()
    assert not parse(config).vllm_metrics
    config["server_observability"] = {"vllm_metrics_approved": True}
    with pytest.raises(ValueError, match="explicit vllm"):
        parse(config)
    config["engine"] = "vllm"
    assert parse(config).vllm_metrics
    config["server_observability"]["vllm_metrics_approved"] = "/other"
    with pytest.raises(ValueError):
        parse(config)


def test_authorized_origin_only_and_no_discovery_or_redirect():
    async def check():
        history = []

        def mock(request):
            history.append(str(request.url))
            return httpx.Response(302, headers={"Location": "http://forbidden.invalid/metrics"})

        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:8080", transport=httpx.MockTransport(mock)
        ) as client:
            await inspect(client)
            assert not any(path.endswith("/metrics") for path in history)
            result = await collect(client)
            assert result == {"state": "http_302"}
            assert history[-1] == "http://127.0.0.1:8080/metrics"
            assert all("forbidden" not in path for path in history)

    asyncio.run(check())


@pytest.mark.parametrize(
    "exposition,status",
    [
        (b"", "unsupported_or_missing"),
        (b'vllm:num_requests_running{broken="value" 2', "malformed"),
        (b"x" * 512_001, "body_limit"),
    ],
    ids=["missing", "malformed", "oversized"],
)
def test_bounded_optional_collection(exposition, status):
    async def check():
        async with httpx.AsyncClient(
            base_url="http://127.0.0.1:8080",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=httpx.ByteStream(exposition))
            ),
        ) as client:
            assert (await collect(client))["state"] == status

    asyncio.run(check())


def test_sealed_run_and_customer_html(tmp_path: Path):
    from test_audit import server

    run = tmp_path / "synthetic-vllm"

    async def check(url):
        cfg = configuration(url)
        cfg.update(engine="vllm", label="Synthetic vLLM verification")
        cfg["server_observability"] = {"vllm_metrics_approved": True}
        config = parse(cfg)
        async with httpx.AsyncClient(base_url=url) as client:
            engine = OpenAI(client, config)

            async def synthetic():
                await asyncio.sleep(0.01)
                return {"state": "observed", "series": parse_prometheus(image())}

            engine.engine_snapshot = synthetic
            await run_benchmark(config, engine, run)

    with server() as (url, _):
        asyncio.run(check(url))
    assert verify(run)["recorded"] == 3
    result = analyze(run)
    assert result["vllm_observability"]["schema"] == 1
    assert result["vllm_observability"]["states"] == {"observed": 1}
    render(result, run / "report")
    html = (run / "report/audit.html").read_text(encoding="utf-8")
    assert "vLLM server observability" in html and "Synthetic vLLM verification" in html
    assert "private-stage-model" not in html
    records_path = run / "server.jsonl"
    record = json.loads(records_path.read_text(encoding="utf-8"))
    record["series"][0]["series"] = "<script>"
    records_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    seal(run)
    with pytest.raises(ValueError, match="label ID"):
        verify(run)
    assert read(run / "plan.json")["server_observability"]["schema"] == 1
