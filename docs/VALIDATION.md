# 0.2.0 verification record

## Independent historical validation

Recomputed 60 eligible Phase 3 strata from the archived request evidence. All fields in the archived recount matched. Its recount predates the two stop-only sensitivity columns produced by the current script. Recomputed all 60 Phase 4 strata and matched the stored recount exactly. The Phase 3 A2 run that crossed Windows sleep remains excluded. Four slots reduced first-token latency in Phase 4, while correct on-time goodput dropped 7–10% at 1.15 offered transactions/s. Neither profile met the strict per-family contract. [Independent replication](../validation/INDEPENDENT_REPLICATION.md)

The 0.2.0 CLI exercised all three historical imports and verified 20, 58 and 79 imported rows, respectively. The imports retain separate schemas and provenance. Original evidence remains in the research workspace.

## Final package and software gates

- Windows 11 and Python 3.14. An empty virtual environment installed the final wheel, passed dependency checks, started the CLI, and reconstructed the previously exported bundle offline.
- Ubuntu 24.04 on WSL and Python 3.12 passed the same offline tests against the release source. Native Linux GPU serving remains unverified.
- 47 automated tests passed on both platforms. Repository-wide Ruff lint, targeted Ruff formatting and package mypy passed. The wheel ZIP validated. Local TLS verified the original certificate name while connecting to a test-resolved numeric address and rejected the mismatched name.
- The simulated customer audit passed on the installed wheel. It inspected an authorized local fake endpoint, adhered to the approved caps, exported synthetic evidence and rebuilt the sanitized report after the fake server exited.
- The final wheel is `dist/inference_audit-0.2.0-py3-none-any.whl`. SHA-256 `ff016fe664640a18a9662bc59964912735a9d90fcaac8242c9206075194778c4`.

## Qwen mixed-load sweep

The installed interim 0.2.0 wheel completed 446 planned transactions and 490 successful streams over 531 seconds using the RTX 4070, Qwen3-8B Q4_K_M and pinned llama.cpp b12427. Every successful stream's output usage matched the prediction counter. The 344 board samples peaked at 7,541 MiB and 61.9°C. The owned two-slot server exposed 4,096 context tokens per slot. The stage measured 83.27 output tok/s with one client worker and 139.10 with four. Peak observed concurrent HTTP intervals reached four, and the server still had two serving slots. This reproduces the approximate 0.1.0 throughput scale.

| Offered txn/s | Completed / offered | Correct and on time | Correct on-time goodput txn/s | P95 first output s | P95 completion s | Agent correct and on time |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.65 | 210/210 | 198/210 | 0.614 | 0.499 | 1.200 | 10/20 |
| 1.10 | 210/210 | 200/210 | 1.048 | 0.507 | 1.327 | 12/20 |

Agent quality failed the strict contract at both rates. No qualified capacity point or fleet saving follows from the aggregate goodput. The illustrative low-load scenario gives roughly $12.88 per million generated tokens at $0.50/GPU-hour and 50% productive utilization. Required worker count and billing savings remain unavailable.

The first sweep's launcher exited on exact report-object disagreement while development was ongoing. A separately implemented recount still matched the original and the final renderer's request counts, throughput, tail latency and GPU peak. Two short frozen analyses then completed all scheduled work. Their launcher initially missed CUDA placement in the process log. Plain INFO/TRACE capture fixed the placement verification, and the final acceptance checked it before sending benchmark traffic. The failed launcher outputs and captures remain in `.runs`. Results above are preserved as measurement evidence rather than treated as successful launch acceptance.

[Qwen sweep report](../reports/local-qwen-020/audit.html) · [Independent recount](../reports/local-qwen-020/recount.json)

## Final real GPU acceptance

The final wheel generated the HTML, JSON and Markdown reports key-free, and reproduced the analysis offline. Each launch checked configured context, CUDA placement, completion, usage, quality, GPU telemetry and safe shutdown. Infinities, partial usage, malformed streams and unsupported metrics are covered separately by the fake server.

| Model | One client tok/s | Four clients tok/s | Mixed correct / offered | Peak device VRAM | CUDA offload |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen3-8B Q4_K_M | 82.83 | 138.22 | 23/24 | 7,533 MiB | 37/37 |
| Gemma 4 12B IT QAT | 53.83 | 90.36 | 21/24 | 9,683 MiB | 49/49 |

The matched Qwen cache probe observed 4/4 verified cold samples and 4/4 positive-hit warm samples. Median server prefill was 354.21 ms cold and 12.91 ms warm, with request TTFT of 389.63 and 16.45 ms. These are proof-of-function points on a pinned same-slot replay. They do not estimate gains on diverse traffic or the effect of serving slots. The short stages offer too few samples for p95 latency and strict capacity qualification.

Gemma verified four cold and four warm probes, with medians of 715.35 and 62.74 ms server prefill. Both final runs reconciled all 56 streamed output counts and used 4,096 contexts per slot. Both owned processes exited, the test ports were clear, and sampled board use returned to 1,634 MiB at 0% GPU utilization. The acceptance captures totaled about 13 minutes of measured GPU workload including diagnostic attempts. The preplanned 15–30 minute target was advisory, and the shorter scope established the acceptance behavior without repeating endurance work.

[Qwen restart report](../reports/local-qwen-restart-020/audit.html) · [Gemma report](../reports/local-gemma-020/audit.html) · [Qwen recount](../reports/local-qwen-restart-020/recount.json) · [Gemma recount](../reports/local-gemma-020/recount.json)

## Reproduce offline

From the repository root with the final wheel installed, use a fresh output directory.

```powershell
inference-audit --runs-dir .runs verify --run qwen-020
inference-audit --runs-dir .runs report --run qwen-020 --output reports/check-new
python validation/verify_release_capture.py .runs/qwen-020 --report reports/check-new/audit.json
```

The HTML output was previewed in Chrome. The shareable report excludes model storage paths, endpoint credentials and generated reply bodies. The detailed evidence bundle is separate and includes the deterministic synthetic fixtures.
