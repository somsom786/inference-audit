"""Target adapter and bounded OpenAI-style SSE transport."""

import asyncio
from dataclasses import dataclass, field
import ipaddress
import json
import math
import os
import re
import socket
import time
from typing import Any, AsyncIterator, Protocol

import httpx

from .config import Config
from .workload import Task, TOOLS


class StreamError(Exception):
    pass


@dataclass
class Reply:
    status: str
    elapsed: float
    ttft: float | None
    finish: str | None
    prompt: int | None
    output: int | None
    cached: int | None
    text: str = field(repr=False)
    calls: list[dict[str, Any]] = field(repr=False)
    timing: dict[str, int | float] = field(default_factory=dict)
    observed: dict[str, float] = field(default_factory=dict)
    first_output: float | None = None
    token_status: str = "verified"
    cache_status: str = "unavailable"


class Engine(Protocol):
    async def send(self, task: Task, messages: list[dict[str, Any]], tool: bool, timeout: float) -> Reply: ...


async def events(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    data: list[str] = []
    for_count = 0
    async for line in lines:
        for_count += len(line) + 1
        if for_count > 2_000_000:
            raise StreamError("oversize")
        if not line:
            if data:
                yield "\n".join(data)
                data.clear()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        raise StreamError("unterminated_event")


async def bounded_lines(response: httpx.Response, maximum: int = 2_000_000) -> AsyncIterator[str]:
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        raise StreamError("unexpected_content_encoding")
    tail = b""
    seen = 0
    async for chunk in response.aiter_raw():
        seen += len(chunk)
        if seen > maximum:
            raise StreamError("oversize")
        parts = (tail + chunk).split(b"\n")
        tail = parts.pop()
        if len(tail) > 262_144:
            raise StreamError("oversize_line")
        for part in parts:
            if len(part) > 262_144:
                raise StreamError("oversize_line")
            yield part.rstrip(b"\r").decode("utf-8-sig")
    if tail:
        raise StreamError("unterminated_line")


def count(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped or ip.sixtofour or ip.teredo or ip in ipaddress.ip_network("64:ff9b::/96"):
            return False
    return ip.is_global and not (ip.is_multicast or ip.is_reserved) and "%" not in address


class PinnedHTTPS(httpx.AsyncBaseTransport):
    """Use one validated public address for the entire client and verify the original TLS name."""

    def __init__(self, target: httpx.URL):
        self.target = target
        self.inner = httpx.AsyncHTTPTransport(trust_env=False, retries=0)
        self.address: str | None = None
        self.lock = asyncio.Lock()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (request.url.scheme, request.url.host, request.url.port) != (
            self.target.scheme,
            self.target.host,
            self.target.port,
        ):
            raise httpx.ConnectError("Destination outside the approved origin.")
        async with self.lock:
            if self.address is None:
                try:
                    answers = await asyncio.get_running_loop().getaddrinfo(
                        self.target.host, self.target.port or 443, type=socket.SOCK_STREAM
                    )
                    addresses = {answer[4][0] for answer in answers}
                    if not addresses or not all(public_address(a) for a in addresses):
                        raise ValueError("Unsafe DNS answer.")
                    self.address = sorted(addresses, key=lambda a: (":" in a, a))[0]
                except (OSError, ValueError):
                    raise httpx.ConnectError("Remote address policy or resolution failed.") from None
        request.url = request.url.copy_with(host=self.address)
        request.extensions["sni_hostname"] = self.target.host
        # HTTPX has already set Host from the original URL.
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def client_for(url: str, env: str | None = None) -> httpx.AsyncClient:
    from .config import origin

    url, local = origin(url)
    if not local and not url.startswith("https:"):
        raise ValueError("Remote targets require HTTPS.")
    if env is not None and not re.fullmatch(r"[A-Z_][A-Z0-9_]{0,127}", env):
        raise ValueError("Use an approved credential environment variable name.")
    secret = os.environ.get(env) if env else None
    if env and (not secret or len(secret) > 4096 or any(not 32 < ord(c) < 127 for c in secret)):
        raise ValueError("Credential environment variable is empty or invalid.")
    headers = {"Accept-Encoding": "identity"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return httpx.AsyncClient(
        base_url=url,
        headers=headers,
        follow_redirects=False,
        trust_env=False,
        timeout=None,
        transport=None if local else PinnedHTTPS(httpx.URL(url)),
    )


async def get_json(
    client: httpx.AsyncClient, path: str, request: dict[str, Any] | None = None
) -> tuple[int, Any]:
    try:
        async with (
            asyncio.timeout(4),
            client.stream("GET" if request is None else "POST", path, json=request) as response,
        ):
            if response.status_code != 200:
                return response.status_code, None
            body = bytearray()
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                return 406, None
            async for chunk in response.aiter_raw():
                body.extend(chunk)
                if len(body) > 262_144:
                    return 413, None
            return 200, json.loads(body)
    except (TimeoutError, httpx.HTTPError, ValueError, UnicodeError, RecursionError):
        return 0, None


async def inspect(client: httpx.AsyncClient) -> dict[str, Any]:
    models, health, metrics = await asyncio.gather(
        get_json(client, "/v1/models"), get_json(client, "/health"), metrics_status(client)
    )
    available = models[1].get("data", []) if isinstance(models[1], dict) else []
    ids = (
        [
            v["id"]
            for v in available[:128]
            if isinstance(v, dict)
            and isinstance(v.get("id"), str)
            and re.fullmatch(r"[A-Za-z0-9._:/-]{1,256}", v["id"])
        ]
        if isinstance(available, list)
        else []
    )
    return {
        "models_http": models[0],
        "models": ids,
        "health_http": health[0],
        "metrics_http": metrics,
        "streaming": "unverified without authorized inference",
        "token_usage": "unverified without authorized inference",
        "tool_calls": "unverified without authorized inference",
        "context_tokens": None,
        "cache": "unverified without authorized inference",
    }


async def metrics_status(client: httpx.AsyncClient) -> int:
    try:
        async with asyncio.timeout(4), client.stream("GET", "/metrics") as response:
            return response.status_code
    except (TimeoutError, httpx.HTTPError):
        return 0


async def llama_counters(client: httpx.AsyncClient) -> dict[str, int | float] | None:
    selected = {
        "requests_processing",
        "requests_deferred",
        "prompt_tokens_total",
        "tokens_predicted_total",
    }
    try:
        async with asyncio.timeout(1), client.stream("GET", "/metrics") as response:
            if response.status_code != 200:
                return None
            values: dict[str, int | float] = {}
            async for line in bounded_lines(response):
                pieces = line.split()
                if not pieces or not pieces[0].startswith("llamacpp:"):
                    continue
                name = pieces[0].split(":", 1)[1]
                if name not in selected:
                    continue
                if len(pieces) != 2 or name in values:
                    return None
                value = float(pieces[1])
                if not math.isfinite(value) or value < 0:
                    return None
                values[name] = value
            return values or None
    except (StreamError, TimeoutError, httpx.HTTPError, ValueError):
        return None


class OpenAI:
    def __init__(self, client: httpx.AsyncClient, config: Config):
        self.client, self.config = client, config

    async def counters(self) -> dict[str, int | float] | None:
        if self.config.engine != "llama.cpp":
            return None
        return await llama_counters(self.client)

    async def send(self, task: Task, messages: list[dict[str, Any]], tool: bool, timeout: float) -> Reply:
        params: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": task.max_output,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        llama = self.config.engine == "llama.cpp"
        if llama:
            params.update(seed=self.config.seed, chat_template_kwargs={"enable_thinking": False})
            if task.cache is not None:
                params.update(cache_prompt=task.cache, id_slot=0)
        if tool:
            params.update(
                tools=TOOLS, tool_choice={"type": "function", "function": {"name": "lookup_receipt"}}
            )
        elif task.check == "tool":
            params.update(tools=TOOLS, tool_choice="none")
        start = time.monotonic()
        observed = {"request_start": start}
        first_output: float | None = None
        usage_conflict = False
        event_number = last_output_event = 0
        usage_event = -1
        first = finish = None
        done = False
        text: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        prompt = output = cached = None
        timing: dict[str, int | float] = {}
        status = "ok"
        try:
            async with (
                asyncio.timeout(timeout),
                self.client.stream("POST", "/v1/chat/completions", json=params) as response,
            ):
                observed["response_headers"] = time.monotonic()
                if response.status_code != 200:
                    raise StreamError(await classify_http(response))
                if "text/event-stream" not in response.headers.get("content-type", "").lower():
                    raise StreamError("expected_sse")
                async for event in events(bounded_lines(response, self.config.max_response_bytes)):
                    event_number += 1
                    if event == "[DONE]":
                        done = True
                        observed["stream_complete"] = time.monotonic()
                        break
                    item = json.loads(event)
                    if "error" in item:
                        raise StreamError("server_stream_error")
                    usage = item.get("usage")
                    if isinstance(usage, dict) and usage:
                        usage_event = event_number
                        observed["usage_event"] = time.monotonic()
                        next_prompt, next_output = (
                            count(usage.get("prompt_tokens")),
                            count(usage.get("completion_tokens")),
                        )
                        total = count(usage.get("total_tokens"))
                        usage_conflict |= (
                            (prompt is not None and next_prompt != prompt)
                            or (output is not None and next_output != output)
                            or (
                                "total_tokens" in usage
                                and (
                                    next_prompt is None
                                    or next_output is None
                                    or total != next_prompt + next_output
                                )
                            )
                        )
                        prompt, output = next_prompt, next_output
                        details = usage.get("prompt_tokens_details")
                        cached = count(details.get("cached_tokens")) if isinstance(details, dict) else None
                    if llama and isinstance(item.get("timings"), dict):
                        timing.update(
                            {
                                k: x
                                for k, x in item["timings"].items()
                                if type(x) in (int, float)
                                and -1e9 <= x <= 1e9
                                and k in {"prompt_n", "predicted_n", "prompt_ms", "predicted_ms", "cache_n"}
                            }
                        )
                    for choice in item.get("choices", []):
                        if choice.get("index", 0) != 0:
                            raise StreamError("unexpected_choice")
                        delta = choice.get("delta", {})
                        value = delta.get("content")
                        segments = delta.get("tool_calls", [])
                        if value is not None and not isinstance(value, str) or not isinstance(segments, list):
                            raise StreamError("invalid_delta")
                        if finish is not None and (value or segments or choice.get("finish_reason")):
                            raise StreamError("output_after_finish")
                        if value or segments:
                            last_output_event = event_number
                            instant = time.monotonic()
                            first_output = instant - start if first_output is None else first_output
                        if value:
                            observed["last_content"] = instant
                            if first is None:
                                observed["first_content"] = instant
                                first = instant - start
                            text.append(value)
                        for part in segments:
                            idx = part.get("index", 0)
                            if (
                                type(idx) is not int
                                or not 0 <= idx < 16
                                or part.get("type", "function") != "function"
                            ):
                                raise StreamError("invalid_tool_delta")
                            call = calls.setdefault(
                                idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                            )
                            call["id"] += part.get("id") or ""
                            for key in ("name", "arguments"):
                                call["function"][key] += part.get("function", {}).get(key) or ""
                        finish = choice.get("finish_reason") or finish
                if not done or finish not in {"stop", "length", "tool_calls"} or first_output is None:
                    raise StreamError("incomplete_stream")
                if output is not None and output > task.max_output:
                    raise StreamError("output_cap_exceeded")
        except (TimeoutError, httpx.TimeoutException):
            status = "timeout"
        except httpx.HTTPError:
            status = "http_transport"
        except StreamError as e:
            status = str(e)
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError, OverflowError):
            status = "invalid_stream"
        observed["termination"] = time.monotonic()
        token_status = "verified"
        if prompt is None or output is None or usage_event < last_output_event:
            token_status = "missing_token_usage"
        elif (
            usage_conflict
            or output < 1
            or (cached is not None and cached > prompt)
            or ("predicted_n" in timing and timing["predicted_n"] != output)
            or (
                "prompt_n" in timing
                and "cache_n" in timing
                and timing["prompt_n"] + timing["cache_n"] != prompt
            )
            or any(x < 0 for x in timing.values())
        ):
            token_status = "token_accounting_mismatch"
        if token_status != "verified" or status != "ok":
            prompt = output = cached = None
        cache_status = "unavailable" if cached is None else ("hit" if cached else "cold")
        return Reply(
            status,
            observed["termination"] - start,
            first,
            finish,
            prompt,
            output,
            cached,
            "".join(text),
            list(calls.values()),
            timing,
            {key: value - start for key, value in observed.items()},
            first_output,
            token_status,
            cache_status,
        )


async def classify_http(response: httpx.Response) -> str:
    if response.status_code in {429, 503}:
        return f"overload_{response.status_code}"
    if response.status_code in {400, 413, 422}:
        body = bytearray()
        if response.headers.get("content-encoding", "identity").lower() == "identity":
            async for chunk in response.aiter_raw():
                if len(body) + len(chunk) > 8192:
                    break
                body.extend(chunk)
        payload = body.lower()
        if any(
            marker in payload
            for marker in (
                b"context_length_exceeded",
                b"exceeds the available context",
                b"exceeds the context",
                b"maximum context length",
                b"exceed_context_size_error",
            )
        ):
            return "context_limit"
    return f"http_{response.status_code}"


def verified_tool(reply: Reply, task: Task) -> dict[str, Any] | None:
    if reply.finish != "tool_calls" or len(reply.calls) != 1:
        return None
    call = reply.calls[0]
    try:
        if (
            re.fullmatch(r"[\w-]{1,128}", call["id"])
            and call["function"]["name"] == "lookup_receipt"
            and json.loads(call["function"]["arguments"]) == {"case": task.expected}
        ):
            return call
    except (ValueError, TypeError, KeyError, RecursionError):
        pass
    return None
