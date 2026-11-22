"""Append-only records and independently verifiable local checksums."""

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Iterator, TextIO
import uuid

FILES = ("plan.json", "events.jsonl", "gpu.jsonl", "server.jsonl", "checkpoint.json")
MAX_FILE = 256 * 1024**2
MAX_LINE = 65536
PHASES = {"chat", "coding", "rag", "agent", "mixed", "decode", "cold", "warm", "concurrent", "burst"}
STATUSES = {
    "ok",
    "dispatch_deadline",
    "admission_limit",
    "interrupted",
    "runtime_budget",
    "incorrect_tool",
    "timeout",
    "http_transport",
    "expected_sse",
    "oversize",
    "oversize_line",
    "unexpected_content_encoding",
    "unterminated_line",
    "unterminated_event",
    "server_stream_error",
    "unexpected_choice",
    "invalid_tool_delta",
    "incomplete_stream",
    "missing_token_usage",
    "output_cap_exceeded",
    "token_accounting_mismatch",
    "cold_cache_unverified",
    "invalid_stream",
    "invalid_delta",
    "output_after_finish",
    "context_limit",
    "overload_429",
    "overload_503",
}


def safe_path(path: Path) -> None:
    """Refuse links, junctions and device paths in operator-selected evidence locations."""
    if ".." in path.parts or path.drive.startswith("\\\\"):
        raise ValueError("Use a local evidence path without parent traversal.")
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("Evidence paths may not contain links or reparse points.")


def new_directory(path: Path) -> None:
    safe_path(path)
    path.mkdir(parents=True)


def bounded_file(path: Path, maximum: int = MAX_FILE) -> None:
    safe_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise ValueError("Evidence requires a bounded regular file.")


@contextmanager
def exclusive_lease(path: Path) -> Iterator[None]:
    safe_path(path)
    with path.open("a+b") as handle:
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError("Another process owns the requested lease.") from None
        yield


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def atomic_text(path: Path, content: str) -> None:
    safe_path(path)
    tmp = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic(path: Path, value: Any) -> None:
    atomic_text(path, stable(value) + "\n")


def invalid_constant(_: str) -> Any:
    raise ValueError("Nonfinite JSON number.")


def read(path: Path, maximum: int = MAX_FILE) -> Any:
    bounded_file(path, maximum)
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=invalid_constant)
    except RecursionError:
        raise ValueError("Invalid structured evidence.") from None


def rows(path: Path, recover: bool = False) -> list[dict[str, Any]]:
    bounded_file(path)
    output: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        while line := stream.readline(MAX_LINE + 1):
            if len(line) > MAX_LINE or len(output) >= 40_000:
                raise ValueError("Evidence row limit exceeded.")
            if not line.endswith("\n") and recover:
                break
            try:
                item = json.loads(line, parse_constant=invalid_constant)
            except RecursionError:
                raise ValueError("Invalid structured evidence record.") from None
            if not isinstance(item, dict):
                raise ValueError("Invalid evidence record.")
            output.append(item)
    return output


def append(handle: TextIO, item: dict[str, Any]) -> None:
    handle.write(stable(item) + "\n")
    handle.flush()


def seal(run: Path) -> None:
    atomic(run / "integrity.json", {file: digest(run / file) for file in FILES})


def verify_steps(row: dict[str, Any], check: str, pattern: str) -> None:
    steps, status = row["steps"], row["status"]
    required = 2 if check in {"tool", "warm_receipt"} else 1
    if not isinstance(steps, list) or len(steps) > required:
        raise ValueError("Transaction step count contradicts the planned task.")
    if any(step["status"] != "ok" for step in steps[:-1]):
        raise ValueError("A failed request cannot precede a follow-up step.")
    if any(
        step["status"] == "ok" and step.get("finish") not in ("stop", "length", "tool_calls")
        for step in steps
    ):
        raise ValueError("Completed request has an invalid finish reason.")
    if len(steps) == 2 and check == "tool" and steps[0]["finish"] != "tool_calls":
        raise ValueError("The agent follow-up requires a tool-call finish.")

    if status == "ok":
        if len(steps) != required or steps[-1]["status"] != "ok":
            raise ValueError("Completed transaction is missing required successful steps.")
        if row["correct"]:
            finishes = [step["finish"] for step in steps]
            expected = ["tool_calls", "stop"] if check == "tool" else ["stop"] * required
            capped_decode = pattern in {"decode", "concurrent"} and finishes == ["length"]
            if finishes != expected and not capped_decode:
                raise ValueError("Correctness flag contradicts the recorded finish reasons.")
    elif status in {"admission_limit", "dispatch_deadline"}:
        if steps:
            raise ValueError("Undispatched transaction contains request steps.")
    elif status == "incorrect_tool":
        if check != "tool" or len(steps) != 1 or steps[0]["status"] != "ok":
            raise ValueError("Tool rejection contradicts the recorded request steps.")
    elif status == "runtime_budget":
        if (
            required != 2
            or len(steps) != 1
            or steps[0]["status"] != "ok"
            or (check == "tool" and steps[0]["finish"] != "tool_calls")
        ):
            raise ValueError("Follow-up deadline contradicts the recorded request steps.")
    elif status != "interrupted" and (not steps or steps[-1]["status"] != status):
        raise ValueError("Transaction failure contradicts the recorded request steps.")


def verify(run: Path) -> dict[str, Any]:
    index = read(run / "integrity.json", 4096)
    if not isinstance(index, dict) or set(index) != set(FILES):
        raise ValueError("Invalid evidence index.")
    for name in FILES:
        bounded_file(run / name)
        expected = index[name]
        if (
            not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or digest(run / name) != expected
        ):
            raise ValueError(f"Evidence digest mismatch in {name}.")
    plan, checkpoint = read(run / "plan.json"), read(run / "checkpoint.json", 131072)
    if plan.get("schema") not in {1, 2} or checkpoint["state"] not in {
        "complete",
        "incomplete",
        "interrupted",
    }:
        raise ValueError("Unsupported schema or unsealed run state.")
    if not isinstance(plan.get("label"), str) or not re.fullmatch(r"[\w .()-]{1,80}", plan["label"]):
        raise ValueError("Run label is not a shareable alias.")
    if plan.get("engine_hint") not in {"openai", "llama.cpp", "vllm"} or type(plan.get("seed")) is not int:
        raise ValueError("Invalid engine or seed.")
    if "server_observability" in plan:
        if plan["engine_hint"] != "vllm" or plan["server_observability"] != {
            "backend": "vllm",
            "schema": 1,
            "sample_interval_s": 5,
        }:
            raise ValueError("Invalid server observability contract.")
        from .vllm_metrics import validate_snapshots

        validate_snapshots(rows(run / "server.jsonl"))
    for key in ("parent_run", "tool_version"):
        value = plan.get(key)
        if value is not None and (
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value)
        ):
            raise ValueError("Invalid run provenance.")
    if set(plan["slo"]) != {"chat", "coding", "rag", "agent"} or any(
        not isinstance(bounds, list) or len(bounds) != 2 or not all(nonnegative(v) and v > 0 for v in bounds)
        for bounds in plan["slo"].values()
    ):
        raise ValueError("Invalid workload objectives.")
    for key in ("started_utc", "ended_utc"):
        try:
            if key in checkpoint and datetime.fromisoformat(checkpoint[key]).utcoffset() is None:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Invalid evidence timestamp.") from None
    stages = {stage["name"]: stage for stage in plan["stages"]}
    if len(stages) != len(plan["stages"]):
        raise ValueError("Duplicate stage names.")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) for name in stages):
        raise ValueError("Invalid stage identifier.")
    for stage in stages.values():
        if stage["pattern"] not in PHASES or stage["mode"] not in {"open", "closed"}:
            raise ValueError("Invalid stage pattern.")
        if not nonnegative(stage["rate"]) or stage["rate"] == 0:
            raise ValueError("Invalid stage rate.")
        if len(stage["tasks"]) != stage["count"] or len(stage["offsets_s"]) != stage["count"]:
            raise ValueError("Invalid stage manifest size.")
        if any(not nonnegative(value) for value in stage["offsets_s"]):
            raise ValueError("Invalid arrival schedule.")
    raw = rows(run / "events.jsonl")
    expected = {}
    for stage in stages.values():
        for task in stage["tasks"]:
            family, check, pattern = task["family"], task["check"], stage["pattern"]
            allowed = {
                "chat": ("receipt", "math", "json"),
                "coding": ("code",),
                "rag": ("warm_receipt",) if pattern == "warm" else ("receipt",),
                "agent": ("tool",),
            }
            if check not in allowed.get(family, ()) or (pattern == "warm" and family != "rag"):
                raise ValueError("Invalid planned task check for workload family.")
            expected[task["id"]] = (stage["name"], family, task["max_output"], check, pattern)
    if len(expected) != sum(len(stage["tasks"]) for stage in stages.values()):
        raise ValueError("Duplicate planned transaction ID.")
    expected_ids = set(expected)
    seen = set()
    for row in raw:
        key = row["id"]
        if key in seen or key not in expected_ids:
            raise ValueError("Unexpected or repeated transaction ID.")
        if (row["stage"], row["family"]) != expected[key][:2]:
            raise ValueError("Transaction is in the wrong workload stratum.")
        if row["family"] not in {"chat", "coding", "rag", "agent"} or not valid_status(row["status"]):
            raise ValueError("Invalid transaction classification.")
        first, elapsed = row.get("ttft_s"), row.get("latency_s")
        limits = plan["slo"][row["family"]]
        if not all(
            v is None or nonnegative(v)
            for v in (
                first,
                elapsed,
                row.get("scheduled_s"),
                row.get("dispatch_s"),
                row.get("end_s"),
                row.get("queue_s"),
            )
        ) or (first is not None and (elapsed is None or first > elapsed)):
            raise ValueError("Invalid transaction timing.")
        if (
            type(row["correct"]) is not bool
            or type(row["on_time"]) is not bool
            or (row["correct"] and row["status"] != "ok")
        ):
            raise ValueError("Invalid transaction outcome.")
        on_time = (
            row["status"] == "ok"
            and row["correct"]
            and first is not None
            and elapsed is not None
            and first <= limits[0]
            and elapsed <= limits[1]
        )
        if row["on_time"] is not bool(on_time):
            raise ValueError("Transaction SLO flags do not reconcile.")
        verify_steps(row, expected[key][3], expected[key][4])
        for step in row["steps"]:
            if not valid_status(step["status"]):
                raise ValueError("Invalid stream classification.")
            if step.get("token_status", "verified") not in {
                "verified",
                "missing_token_usage",
                "token_accounting_mismatch",
            }:
                raise ValueError("Invalid token evidence classification.")
            prompt, output, cached = (step[k] for k in ("prompt_tokens", "output_tokens", "cached_tokens"))
            if (
                step["status"] == "ok"
                and step.get("token_status", "verified") == "verified"
                and not (
                    type(prompt) is int
                    and prompt >= 0
                    and type(output) is int
                    and 0 < output <= expected[key][2]
                )
            ):
                raise ValueError("A completed stream has invalid token accounting.")
            if (
                plan["schema"] == 2
                and step.get("token_status") != "verified"
                and any(v is not None for v in (prompt, output, cached))
            ):
                raise ValueError("Unverified counts must be unavailable.")
            if (
                step["status"] == "ok"
                and cached is not None
                and (type(cached) is not int or type(prompt) is not int or not 0 <= cached <= prompt)
            ):
                raise ValueError("Invalid cached token accounting.")
            if plan["schema"] == 2 and step["status"] == "ok":
                cache_status = "unavailable" if cached is None else ("hit" if cached else "cold")
                if step.get("cache_status") != cache_status:
                    raise ValueError("Cached-token state contradicts the recorded count.")
            if not nonnegative(step["latency_s"]):
                raise ValueError("Invalid request latency.")
            marks = step.get("observed", {})
            if any(not nonnegative(v) or v > step["latency_s"] for v in marks.values()):
                raise ValueError("Invalid request phase timestamps.")
            ordered = [
                marks[k]
                for k in (
                    "request_start",
                    "response_headers",
                    "first_content",
                    "last_content",
                    "stream_complete",
                    "termination",
                )
                if k in marks
            ]
            if ordered != sorted(ordered):
                raise ValueError("Request phase timestamps are out of order.")
        seen.add(key)
    if checkpoint["state"] == "complete" and seen != expected_ids:
        raise ValueError("Completed run has missing transactions.")
    completed = checkpoint["completed_stages"]
    if len(set(completed)) != len(completed) or set(completed) - set(stages):
        raise ValueError("Invalid checkpoint stage.")
    if checkpoint["state"] == "complete" and set(completed) != set(stages):
        raise ValueError("Completed run has uncompleted stages.")
    for name in completed:
        if (
            not all(t["id"] in seen for t in stages[name]["tasks"])
            or not nonnegative(checkpoint["spans_s"].get(name))
            or checkpoint["spans_s"][name] <= 0
        ):
            raise ValueError("Completed stage is missing observations or elapsed time.")
    if plan["schema"] == 2:
        if checkpoint.get("recorded") != len(seen) or checkpoint.get("pending_planned") != len(
            expected
        ) - len(seen):
            raise ValueError("Checkpoint counts do not reconcile.")
        for row in raw:
            if row["stage"] in completed and row["status"] == "interrupted":
                raise ValueError("A completed stage contains an interrupted transaction.")
            start, end = row.get("dispatch_s"), row.get("end_s")
            if start is not None and (start < row["scheduled_s"] or end is not None and end < start):
                raise ValueError("Dispatch and completion are out of order.")
            for step in row["steps"]:
                if not nonnegative(step.get("dispatch_s")) or start is None or step["dispatch_s"] < start:
                    raise ValueError("Missing or invalid HTTP dispatch timestamp.")
    return {
        "state": checkpoint["state"],
        "recorded": len(seen),
        "planned": len(expected_ids),
        "algorithm": "SHA-256 local checksum",
        "source": "native",
    }


def nonnegative(value: Any) -> bool:
    return type(value) in (float, int) and 0 <= value < math.inf


def valid_status(value: Any) -> bool:
    return isinstance(value, str) and (
        value in STATUSES or re.fullmatch(r"http_[1-5][0-9]{2}", value) is not None
    )


def run_path(root: Path, key: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", key):
        raise ValueError("Invalid run ID.")
    path = root / key
    safe_path(path)
    return path
