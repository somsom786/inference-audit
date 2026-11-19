"""Validate benchmark policy before building an HTTP client."""

from dataclasses import dataclass, field
import ipaddress
import math
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

import yaml

from .evidence import bounded_file

FAMILIES = ("chat", "coding", "rag", "agent")
PATTERNS = ("mixed", "decode", "cold", "warm", "concurrent", "burst", *FAMILIES)
DEFAULT_SLO = dict(zip(FAMILIES, ((1.5, 4.0), (2.5, 8.0), (3.0, 5.0), (1.5, 4.5))))


def origin(url: str) -> tuple[str, bool]:
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        raise ValueError("Invalid target origin or port.") from None
    if (
        p.scheme not in {"http", "https"}
        or not p.hostname
        or p.username is not None
        or p.password is not None
        or p.query
        or p.fragment
        or p.path not in {"", "/"}
        or not re.fullmatch(r"[A-Za-z0-9.\-:]+", p.hostname)
        or "\\" in url
        or any(ord(c) <= 32 for c in url)
        or port == 0
    ):
        raise ValueError("Use an HTTP(S) origin without a path, credentials or query.")
    try:
        loopback = ipaddress.ip_address(p.hostname).is_loopback
    except ValueError:
        loopback = False
    # localhost is deliberately pinned to an IP, even if a resolver is misconfigured.
    host = "127.0.0.1" if p.hostname == "localhost" else p.hostname
    loopback = loopback or p.hostname == "localhost"
    return (
        f"{p.scheme}://{'[' + host + ']' if ':' in host else host}:{port or (443 if p.scheme == 'https' else 80)}",
        loopback,
    )


def authorize(url: str, allowed: list[str]) -> tuple[str, bool]:
    value, local = origin(url)
    if not local and (not value.startswith("https:") or value not in {origin(u)[0] for u in allowed}):
        raise ValueError("Remote targets require HTTPS and an exact authorized origin.")
    return value, local


def number(value: Any, low: float, high: float, name: str, integer: bool = False) -> Any:
    valid_type = type(value) is int if integer else type(value) in (int, float)
    if not valid_type or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"Invalid {name}. Expected a value in [{low}, {high}].")
    return value


def fields(data: Any, names: set[str]) -> dict[str, Any]:
    if not isinstance(data, dict) or not data.keys() <= names:
        raise ValueError("Invalid or unknown configuration fields.")
    return data


@dataclass(frozen=True)
class Stage:
    name: str
    pattern: str
    count: int
    mode: str
    rate: float
    workers: int
    max_output: int
    fixture_set: str


@dataclass(frozen=True)
class Config:
    url: str
    local: bool
    model: str
    credential_env: str | None
    seed: int
    max_requests: int
    runtime_s: float
    timeout_s: float
    max_concurrency: int
    max_rps: float
    dispatch_slack_s: float
    stages: tuple[Stage, ...]
    engine: str
    gpu_index: int | None
    slo: dict[str, tuple[float, float]]
    label: str
    max_response_bytes: int = 2_000_000
    evidence_mib: int = 64
    queue_limit: int = 0
    min_correct_share: float = 0.95
    min_on_time_share: float = 0.95
    max_error_share: float = 0.05
    required_context: int | None = None
    family_gates: dict[str, dict[str, float]] = field(default_factory=dict)


def load(path: Path) -> Any:
    bounded_file(path, 128_000)
    try:
        raw = path.read_text(encoding="utf-8-sig")
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(raw)):
            raise ValueError("YAML aliases are not supported in audit configuration.")
        return yaml.safe_load(raw)
    except (yaml.YAMLError, RecursionError):
        raise ValueError("Invalid YAML configuration.") from None


def parse(data: Any) -> Config:
    fields(
        data,
        {
            "target",
            "authorization",
            "limits",
            "stages",
            "seed",
            "engine",
            "gpu_index",
            "slo",
            "label",
            "qualification",
        },
    )
    target = fields(data.get("target"), {"url", "model", "credential_env"})
    auth = fields(data.get("authorization"), {"approved", "allowed_origins"})
    if auth.get("approved") is not True:
        raise ValueError("Explicit load authorization is required in configuration.")
    allowed = auth.get("allowed_origins", [])
    if not isinstance(allowed, list) or not all(isinstance(u, str) for u in allowed):
        raise ValueError("Allowed origins must be a list of URLs.")
    url, local = authorize(str(target.get("url", "")), allowed)
    model = target.get("model")
    env = target.get("credential_env")
    if not isinstance(model, str) or not model or len(model) > 256 or any(ord(c) < 32 for c in model):
        raise ValueError("A model ID is required.")
    if env is not None and (not isinstance(env, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,127}", env)):
        raise ValueError("Use the name of an environment variable for credentials.")
    limits = fields(
        data.get("limits"),
        {
            "max_requests",
            "runtime_s",
            "timeout_s",
            "max_concurrency",
            "max_rps",
            "dispatch_slack_s",
            "max_response_bytes",
            "evidence_mib",
            "queue_limit",
        },
    )
    max_requests = number(limits.get("max_requests"), 1, 20000, "request budget", True)
    max_rps = number(limits.get("max_rps"), 0.05, 20, "rate cap")
    concurrency = number(limits.get("max_concurrency"), 1, 32, "concurrency cap", True)
    runtime = number(limits.get("runtime_s"), 1, 7200, "runtime")
    timeout = number(limits.get("timeout_s", 15), 0.1, 120, "request timeout")
    slack = number(limits.get("dispatch_slack_s", 0.5), 0.01, 5, "admission deadline")
    if not isinstance(data.get("stages"), list) or not 1 <= len(data["stages"]) <= 64:
        raise ValueError("Use 1–64 benchmark stages.")
    stages = []
    for raw in data["stages"]:
        fields(raw, {"name", "pattern", "count", "mode", "rate", "workers", "max_output", "fixture_set"})
        name, pattern, mode = raw.get("name"), raw.get("pattern"), raw.get("mode", "open")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", name):
            raise ValueError("Use a simple stage identifier.")
        fixture_set = raw.get("fixture_set", name)
        if not isinstance(fixture_set, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", fixture_set):
            raise ValueError("Use a simple fixture-set identifier.")
        if pattern not in PATTERNS or mode not in ("open", "closed"):
            raise ValueError("Unknown workload pattern or scheduler mode.")
        workers = number(raw.get("workers", 1), 1, concurrency, "stage workers", True)
        if pattern in {"cold", "warm"} and workers != 1:
            raise ValueError("Cache probes require a single worker.")
        stages.append(
            Stage(
                name,
                pattern,
                number(raw.get("count"), 1, max_requests, "stage count", True),
                mode,
                number(raw.get("rate", max_rps), 0.05, max_rps, "stage rate"),
                workers,
                number(raw.get("max_output", 192), 1, 1024, "maximum output", True),
                fixture_set,
            )
        )
    if len({s.name for s in stages}) != len(stages):
        raise ValueError("Stage names must be unique.")
    if sum(s.count for s in stages) > max_requests:
        raise ValueError("Transaction count exceeds the request budget.")
    gpu = data.get("gpu_index")
    if gpu is not None:
        number(gpu, 0, 64, "GPU index", True)
        if not local:
            raise ValueError("Local GPU telemetry cannot represent a remote target.")
    engine = data.get("engine", "openai")
    if engine not in ("openai", "llama.cpp"):
        raise ValueError("Choose openai or llama.cpp explicitly.")
    if engine != "llama.cpp" and any(s.pattern in {"cold", "warm"} for s in stages):
        raise ValueError("Verified cold/warm controls currently require the llama.cpp adapter.")
    slo = DEFAULT_SLO.copy()
    for family, value in fields(data.get("slo", {}), set(FAMILIES)).items():
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("Supply [TTFT seconds, completion seconds] per family.")
        slo[family] = (number(value[0], 0.01, 120, "TTFT SLO"), number(value[1], 0.01, 600, "completion SLO"))
    label = data.get("label", "Inference target")
    if not isinstance(label, str) or len(label) > 80 or not re.fullmatch(r"[\w .()-]+", label):
        raise ValueError("Label must be a short shareable alias.")
    gates = fields(
        data.get("qualification", {}),
        {"min_correct_share", "min_on_time_share", "max_error_share", "required_context", "families"},
    )
    quality_keys = {"min_correct_share", "min_on_time_share", "max_error_share"}
    family_gates = {
        family: {key: number(value, 0, 1, key) for key, value in fields(rules, quality_keys).items()}
        for family, rules in fields(gates.get("families", {}), set(FAMILIES)).items()
    }
    required_context = gates.get("required_context")
    if required_context is not None:
        number(required_context, 128, 1_000_000, "required context", True)
    return Config(
        url,
        local,
        model,
        env,
        number(data.get("seed", 407), 0, 2**32 - 1, "seed", True),
        max_requests,
        runtime,
        timeout,
        concurrency,
        max_rps,
        slack,
        tuple(stages),
        engine,
        gpu,
        slo,
        label,
        number(limits.get("max_response_bytes", 2_000_000), 4096, 2_000_000, "response byte cap", True),
        number(limits.get("evidence_mib", 64), 1, 256, "evidence storage limit", True),
        number(limits.get("queue_limit", 0), 0, 64, "waiting client queue limit", True),
        number(gates.get("min_correct_share", 0.95), 0, 1, "correct-response gate"),
        number(gates.get("min_on_time_share", 0.95), 0, 1, "on-time gate"),
        number(gates.get("max_error_share", 0.05), 0, 1, "error gate"),
        required_context,
        family_gates,
    )
