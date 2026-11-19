import asyncio
from collections import Counter
from dataclasses import replace
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys

import httpx
import pytest

from inference_audit.analysis import analyze, summary
from inference_audit.cli import invoke, parser
from inference_audit.config import load, parse
from inference_audit.evidence import atomic, read, rows, run_path, seal, verify
from inference_audit.reporting import plain_markdown, render, table
from inference_audit.runner import run_benchmark
from inference_audit.targets import PinnedHTTPS, public_address
from test_audit import Simulated, configuration, server


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "10.0.0.4",
        "100.64.0.2",
        "224.0.0.1",
        "64:ff9b::a9fe:a9fe",
        "::ffff:8.8.8.8",
    ],
)
def test_remote_rejects_non_global_and_encapsulated_addresses(address):
    assert not public_address(address)


def test_dns_is_validated_once_and_tls_hostname_preserved(monkeypatch):
    async def go():
        calls = []
        requests = []

        async def resolve(*args, **kwargs):
            calls.append(args)
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.215.14", 443))]

        async def send(request):
            requests.append(request)
            return httpx.Response(200)

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        transport = PinnedHTTPS(httpx.URL("https://staging.example"))
        async with httpx.AsyncClient(transport=transport, base_url="https://staging.example") as client:
            monkeypatch.setattr(transport.inner, "handle_async_request", send)
            await client.get("/health")
            await client.get("/v1/models")
            with pytest.raises(httpx.ConnectError):
                await client.get("https://metadata.invalid")
        assert len(calls) == 1
        assert all(r.url.host == "93.184.215.14" for r in requests)
        assert all(r.headers["host"] == "staging.example" for r in requests)
        assert all(r.extensions["sni_hostname"] == "staging.example" for r in requests)

    asyncio.run(go())


def test_dns_mixed_answers_never_connect(monkeypatch):
    async def go():
        async def resolve(*args, **kwargs):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443))
                for ip in ("93.184.215.14", "169.254.169.254")
            ]

        async def send(request):
            pytest.fail("Mixed DNS must fail before opening a connection.")

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
        transport = PinnedHTTPS(httpx.URL("https://staging.example"))
        monkeypatch.setattr(transport.inner, "handle_async_request", send)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get("https://staging.example")

    asyncio.run(go())


def test_pinned_address_real_tls_checks_original_certificate_name(tmp_path, monkeypatch):
    openssl = shutil.which("openssl")
    if not openssl and sys.platform == "win32":
        bundled = Path(os.environ.get("ProgramFiles", "")) / "Git/usr/bin/openssl.exe"
        openssl = str(bundled) if bundled.is_file() else None
    if not openssl:
        pytest.skip("OpenSSL test certificate generator unavailable.")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    name = "audit-test.invalid"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            f"/CN={name}",
            "-addext",
            f"subjectAltName=DNS:{name}",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=15,
        check=True,
    )
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert, key)
    trust = ssl.create_default_context(cafile=str(cert))
    monkeypatch.setattr("inference_audit.targets.public_address", lambda address: address == "127.0.0.1")

    async def go(port):
        loop = asyncio.get_running_loop()
        original = loop.getaddrinfo

        async def resolve(host, *args, **kwargs):
            return await original("127.0.0.1" if host.endswith(".invalid") else host, *args, **kwargs)

        monkeypatch.setattr(loop, "getaddrinfo", resolve)
        for hostname in (name, "wrong-name.invalid"):
            origin = f"https://{hostname}:{port}"
            pinned = PinnedHTTPS(httpx.URL(origin))
            await pinned.inner.aclose()
            pinned.inner = httpx.AsyncHTTPTransport(verify=trust, trust_env=False)
            async with httpx.AsyncClient(transport=pinned, base_url=origin) as client:
                if hostname == name:
                    assert (await client.get("/v1/models")).status_code == 200
                else:
                    with pytest.raises(httpx.ConnectError, match="certificate verify failed"):
                        await client.get("/v1/models")

    with server(ssl_context=tls) as (url, _):
        asyncio.run(go(httpx.URL(url).port))


def test_yaml_and_owned_scope_reject_untrusted_extensions(tmp_path):
    config = tmp_path / "unsafe.yml"
    config.write_text("item: &x [1]\nother: *x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="aliases"):
        load(config)
    config.write_text("!!python/object/apply:os.getcwd []", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML"):
        load(config)
    raw = configuration()
    raw["command"] = ["unapproved"]
    with pytest.raises(ValueError, match="unknown"):
        parse(raw)
    with pytest.raises(ValueError):
        parse(configuration(max_concurrency=999))


def test_symlink_or_existing_export_preserves_destination(tmp_path):
    destination = tmp_path / "real"
    destination.mkdir()
    link = tmp_path / "alias"
    try:
        link.symlink_to(destination, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            pytest.skip("OS does not permit creating directory symlinks.")
        import _winapi

        _winapi.CreateJunction(str(destination), str(link))
    with pytest.raises(ValueError, match="links"):
        run_path(link, "test")


def test_report_escapes_fields_and_refuses_overwrite(tmp_path):
    marker = "<img src=x onerror=alert(1)> [remote](https://example.invalid)"
    text, md = table(["name"], [[marker]])
    assert "<img" not in text and "[remote](" not in md and "<img" not in md
    assert "\n" not in plain_markdown("Line\n**Header**")
    run = tmp_path / "run"
    asyncio.run(run_benchmark(parse(configuration()), Simulated(), run))
    result = analyze(run)
    result["label"] = marker
    render(result, tmp_path / "out")
    html = (tmp_path / "out/audit.html").read_text(encoding="utf-8")
    assert "<img" not in html and "default-src 'none'" in html
    with pytest.raises(ValueError, match="Existing files"):
        render(result, tmp_path / "out")


def test_sealed_semantic_integrity_and_evidence_budget(tmp_path):
    cfg = parse(configuration(count=10))
    run = tmp_path / "normal"
    asyncio.run(run_benchmark(cfg, Simulated(), run))
    checkpoint = read(run / "checkpoint.json")
    checkpoint["completed_stages"] = []
    atomic(run / "checkpoint.json", checkpoint)
    seal(run)
    with pytest.raises(ValueError, match="uncompleted stages"):
        verify(run)
    budget = replace(cfg, runtime_s=7200, evidence_mib=1)
    with pytest.raises(ValueError, match="storage budget"):
        asyncio.run(run_benchmark(budget, Simulated(), tmp_path / "not-created"))
    assert not (tmp_path / "not-created").exists()


def test_partial_usage_withholds_throughput_and_preserves_goodput(tmp_path):
    class MissingUsage(Simulated):
        async def send(self, task, messages, tool, timeout):
            result = await super().send(task, messages, tool, timeout)
            if task.id.endswith("00001"):
                result.output = result.prompt = None
                result.token_status = "missing_token_usage"
            return result

    run = tmp_path / "mixed"
    asyncio.run(run_benchmark(parse(configuration()), MissingUsage(), run))
    info = analyze(run)["stages"][0]["metrics"]
    assert info["output_tps"] is None
    assert info["completed"] == info["on_time"] == 3
    assert info["completed_streams"] == 3 and info["accounted_streams"] == 2
    assert info["token_issues"] == {"missing_token_usage": 1}


def test_unverified_cache_is_not_a_prefill_measurement(tmp_path):
    raw = configuration(stages=[{"name": "warm", "pattern": "warm", "mode": "closed", "count": 2}])
    raw["engine"] = "llama.cpp"
    run = tmp_path / "cache"
    asyncio.run(run_benchmark(parse(raw), Simulated(), run))
    probe = analyze(run)["stages"][0]["cache_probe"]
    assert probe["n"] == 0 and probe["completed_probe_streams"] == 2


def test_failed_quality_excluded_from_goodput():
    batch = [
        {"status": "ok", "on_time": False, "correct": False, "steps": []},
        {"status": "timeout", "on_time": False, "correct": False, "steps": []},
    ]
    for count in range(2, 20):
        info = summary(batch, count, 2)
        assert info["on_time"] <= info["valid"] <= info["completed"] <= info["recorded"] <= info["offered"]
        assert info["goodput_rps"] == 0
        assert info["error_share"] == (count - 1) / count


def test_cli_pilot_exports_verifiable_offline_bundle(tmp_path):
    with server() as (url, stats):
        config = tmp_path / "pilot.json"
        atomic(config, configuration(url))
        runs = tmp_path / "runs"
        export = tmp_path / "bundle"

        def command(*args, root=runs):
            return asyncio.run(invoke(parser().parse_args(["--runs-dir", str(root), *args])))

        assert command("inspect", "--url", url)["models_http"] == 200
        name = ("--run", "pilot")
        assert command("benchmark", "--config", str(config), *name, "--approve-load")["state"] == "complete"
        assert (
            command("export", *name, "--output", str(export), "--include-synthetic-manifest")["state"]
            == "exported"
        )
        assert stats["requests"] == 3
    assert command("verify", *name, root=export)["recorded"] == 3
    command("report", *name, root=export)
    saved = read(export / "pilot/report/audit.json")
    assert saved == analyze(runs / "pilot")
    assert "internal-customer-model" not in (export / "pilot/report/audit.json").read_text()


def test_queue_full_retains_rejection_and_dispatch_deadline(tmp_path):
    raw = configuration(
        max_rps=20,
        dispatch_slack_s=0.08,
        queue_limit=1,
        stages=[{"name": "burst", "pattern": "burst", "count": 10, "workers": 2, "rate": 20}],
    )
    with server("slow") as (url, stats):
        raw["target"]["url"] = url
        # Keep the fake wire server alive through the client run.
        cfg = parse(raw)
        from inference_audit.targets import OpenAI, client_for

        async def go():
            async with client_for(cfg.url) as wire:
                await run_benchmark(cfg, OpenAI(wire, cfg), tmp_path / "queue")

        asyncio.run(go())
        got = Counter(event["status"] for event in rows(tmp_path / "queue/events.jsonl"))
        assert got["admission_limit"] and got["dispatch_deadline"]
        assert sum(got.values()) == 10 and stats["peak"] <= 2
