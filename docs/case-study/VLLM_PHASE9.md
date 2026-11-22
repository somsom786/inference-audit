# Phase 9 vLLM lab report

## Scope

The lab reused Qwen3-8B Q4_K_M, 5,027,783,488 bytes, SHA-256 d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785. The RTX 4070 (12 GB) was on Windows 11 with NVIDIA 621.24 and Ubuntu 22.04 under WSL2. vLLM 0.34.0 and the experimental vllm-gguf-plugin 0.0.5 ran on Torch 2.14.0+cu130 and CUDA 13.0. A CUDA tensor operation and the stable LibTorch extension succeeded. The model used the original tokenizer/config revision b968826d9c46dd6066d109eabc6255188de91218. Only its metadata was downloaded. Serving used FP16 model execution, FA2, one GPU, built-in prefix caching and chunked prefill. The model weights remained GGUF. The test ran from a separate environment and bound to loopback.

## The startup failures defined the baseline

| Launch | Result at the same 0.67 device budget |
| --- | --- |
| Default graphs and extensible KV, 4,096 context | Initial planner had about 0.24 GiB for KV and needed 0.56 GiB. Model load reached about 7.5 GiB, so the API never became ready. |
| Default graphs and extensible KV, 1,536 context | Initial reservation was sufficient but the cache did not fit after warmup. |
| Eager and extensible KV, 1,536 context | Initial estimate fit at most 1,472 tokens. |
| Eager and extensible KV, 1,280 context | Post-warmup reservation growth reduced usable blocks to zero. The logged transient allowance was 0.47 GiB. |
| Eager and static KV, 1,280 context | One ready API, 1,536 cache tokens and 1.20× capacity at full 1,280-token context. |

The KV estimate uses 36 × 2 × 8 × 128 × 2 = 147,456 bytes/token. A 1,536-token allocation is 216 MiB of payload. At 4,096 tokens it is 576 MiB. We kept the desktop margin and did not raise the device budget to make the default launch pass. Eager and static KV are a constrained fallback, with no performance comparison against a working graph-enabled control. Torch's profiled allocation is not the same as GGUF file size or driver board telemetry. Windows nvidia-smi sampled the whole board. FlashInfer fallback and unavailable pinned host memory were logged; their performance impact was not isolated.

## Measured prefix reuse

Six independent prefixes were each probed cold, repeated with a changed final receipt, and repeated with an early prefix change as a negative control. The first bracket returned all 18 exact receipts. Median first-visible-token latency was 2.778 s cold, 0.125 s warm and 2.772 s on the early-change control. Server counters increased by 6,528 hits out of 20,376 queries across that probe. The HTTP responses did not expose per-request cache-token details. This is a targeted replay with reusable inputs. It does not establish a workload-wide speedup, and a warm TTFT is not uncached prefill throughput.

## Initial load sweep

The lab used the same closed-loop short chat fixture set at one, two and four workers with 32 offers per stage. A separate mixed panel used 64 offers at each of 1 and 2 offers/s, including long inputs and tool requests. The product retains transport, cap, correctness, deadline and admission outcomes separately. Values below are aggregate rates over stage elapsed time including drain. p95 is withheld below 40 completed samples.

| Stage | Output tok/s | Correct on-time tasks/s | TTFT p50 |
| --- | ---: | ---: | ---: |
| c1 closed | 30.12 | 0.316 | 0.129 s |
| c2 closed | 59.38 | 0.620 | 0.159 s |
| c4 closed | 98.36 | 1.100 | 0.178 s |
| Mixed, 1 offer/s | 26.84 | 0.504 | 0.195 s |
| Mixed, 2 offers/s | 38.46 | 0.471 | 0.543 s |

No stage met strict qualification. The first mixed stage had nine context-limit and seven HTTP 400 outcomes, among other failures. The faster mixed arrivals increased rejected and late work while useful goodput fell. Sampled KV occupancy and preemption deltas corroborate resource pressure in the observed windows. They do not assign every error to KV. There was no authorized control change to the model's quality contract. The single-stream client-visible decode proxy was 32.66 tok/s for counted streams after the first visible event. It uses terminal output counts and elapsed first-to-last visible event time. It does not count SSE chunks as tokens or reconstruct distinct per-token timestamps.

Sampled peak board memory was 10,436 MiB and temperature 64.56°C. One RTX 4070, one runtime and synthetic workloads limit transfer to production. There is no qualified capacity or cost claim, and no multi-GPU or profiling claim. All endpoint failures are retained in private evidence. [Reproduction and integration](../VLLM_LOCAL.md)

## Bounded batch-budget bracket

Each vLLM arm used a fresh process, six matched prefix triplets and the same 224-offer load manifest. The only launch change in the middle arm was a 512-token batch budget. The controls left this setting at the engine default.

| Arm in run order | Allocated KV tokens | c4 output tok/s | c4 correct on-time tasks/s | Mixed 1 offer/s goodput | Mixed 2 offers/s goodput | Mixed 2 median TTFT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial control | 1,536 | 98.36 | 1.100 | 0.504 | 0.471 | 0.543 s |
| Batch budget 512 | 2,752 | 90.71 | 0.940 | 0.504 | 0.533 | 0.289 s |
| Repeated control | 1,536 | 93.69 | 1.035 | 0.567 | 0.566 | 0.184 s |

The smaller budget increased the available cache pool under the same configured device budget. It lost to both controls on four-worker throughput and goodput. The faster mixed workload showed enough control variation that the candidate did not establish an improvement. No arm qualified under the strict service objectives. Board memory peaked between 10,434 and 10,436 MiB across the three arms. Performance at longer contexts, tuning above four workers, graph-enabled execution and hardware-level attribution remain open.

Prefix reuse survived the fresh launches. Across arms, median TTFT ranged from 2.768 to 2.778 s cold, 0.122 to 0.125 s warm and 2.764 to 2.772 s with an early prefix change. All 54 probes returned the expected receipt. These probes establish repeatable cache behavior for the tested prefix design and do not measure a mixed workload capacity improvement.

## Same-artifact cross-stack check

The CUDA llama.cpp b12427 arm used the same existing GGUF, prompt fixtures, output caps and thinking-off greedy workload at one, two and four closed-loop workers. Its four slots each allowed 1,280 tokens. The vLLM reference ran in WSL and llama.cpp ran on Windows. Engine tokenization and template handling, implementation, transport and cache allocation can differ. The mixed open-loop workload was outside this comparison.

| Closed-loop workers, 32 offers each | vLLM control output tok/s | llama.cpp output tok/s | vLLM control correct on-time tasks/s | llama.cpp correct on-time tasks/s |
| --- | ---: | ---: | ---: | ---: |
| 1 | 30.12 | 78.28 | 0.316 | 0.819 |
| 2 | 59.38 | 77.63 | 0.620 | 0.866 |
| 4 | 98.36 | 154.77 | 1.100 | 1.723 |

At four workers, median TTFT was 0.178 s in the first vLLM control and 0.264 s in llama.cpp. The single llama.cpp run peaked at 7,439 MiB of board memory. No closed-loop stage in either stack qualified. These are descriptive measurements of two local launches, including a constrained vLLM fallback and one llama.cpp run. They leave general engine performance, distributed behavior and fleet economics unverified.

The four sealed audits cover 768 offers. The derived public export contains phase summaries, prefix observations, source hashes and server metric projections. Original request evidence stays local. Read the [evidence projection](../../public/evidence/vllm-phase9.json), [generated local audit](../../public/reports/vllm-qwen3-8b-audit.html) and [local setup](../VLLM_LOCAL.md).
