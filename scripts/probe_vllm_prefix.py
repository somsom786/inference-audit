"""Local, bounded prefix-cache probe. Verify cache evidence and strict receipts."""

import argparse
import asyncio
import json
from pathlib import Path
from statistics import median
from typing import Any

from inference_audit.config import parse
from inference_audit.targets import OpenAI, client_for
from inference_audit.vllm_metrics import collect
from inference_audit.workload import Task


def prefix(seed: int, changed: bool) -> str:
    first = f"Unique namespace for book {seed}: {'negative' if changed else 'shared'}."
    lines = [f"Ledger line {i}: bell {seed + i * 123} recorded ordinary condition." for i in range(65)]
    return "\n".join([first, *lines])


async def probe(port: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}"
    cfg = parse(
        {
            "label": "Local vLLM prefix probe",
            "target": {"url": url, "model": "audit-qwen3-8b"},
            "engine": "vllm",
            "authorization": {"approved": True},
            "limits": {
                "max_requests": 18,
                "runtime_s": 150,
                "max_concurrency": 1,
                "max_rps": 1,
                "dispatch_slack_s": 1,
            },
            "stages": [{"name": "prefix", "pattern": "rag", "count": 18}],
        }
    )
    evidence = []
    async with asyncio.timeout(150), client_for(cfg.url) as client:
        engine = OpenAI(client, cfg)
        initial = await collect(client)
        for seed in range(600, 606):
            for index, (part, changed) in enumerate((("cold", False), ("warm", False), ("changed", True))):
                receipt = f"VR{seed}{index}K7"
                prompt = (
                    prefix(seed, changed)
                    + f"\nThe approved receipt is {receipt}. Answer with only the receipt."
                )
                task = Task(
                    f"{seed}-{part}",
                    "rag",
                    [{"role": "user", "content": prompt}],
                    "receipt",
                    receipt,
                    24,
                    None,
                )
                reply = await engine.send(task, task.messages, False, 12)
                evidence.append(
                    {
                        "id": task.id,
                        "cohort": part,
                        "status": reply.status,
                        "ttft_s": reply.ttft,
                        "elapsed_s": reply.elapsed,
                        "prompt_tokens": reply.prompt,
                        "output_tokens": reply.output,
                        "cached_tokens": reply.cached,
                        "token_status": reply.token_status,
                        "passed": reply.text.strip() == receipt and reply.status == "ok",
                    }
                )
                await asyncio.sleep(0.1)
        final = await collect(client)
    summary = {}
    for part in ("cold", "warm", "changed"):
        rows = [r for r in evidence if r["cohort"] == part]
        summary[part] = {"requests": len(rows), "correct": sum(r["passed"] for r in rows)}
        for name in ("ttft_s", "elapsed_s", "cached_tokens"):
            values = [r[name] for r in rows if r[name] is not None]
            summary[part][name] = median(values) if values else None
    return {"samples": evidence, "summary": summary, "metrics_before": initial, "metrics_after": final}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--port", type=int, default=18091)
    args = cli.parse_args()
    data = asyncio.run(probe(args.port))
    with args.output.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, indent=2)
        file.write("\n")
