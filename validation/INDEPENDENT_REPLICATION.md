# Independent replication of Phase 3

## Decision

On the fresh, low-reuse workload, four slots reproduced the first-token latency benefit and **reduced correct on-time goodput**. Neither profile qualified at any tested rate under the 95% per-family contract. The four-slot configuration trades earlier first tokens for slower chat completion on this workload. The data do not establish higher strict capacity or lower infrastructure cost.

## Design and integrity

Four freshly owned llama.cpp b12427 CUDA launches followed the A1/B1/B2/A2 order. A uses two slots and B uses four. All used the same Qwen3-8B Q4_K_M weights, f16 KV, 16,384 total positions, greedy sampling, and byte-matched request manifests. Required context was capped at 3,800 tokens including the response allowance. Tokenizer preflight found a maximum of **3,133**. The experiment qualifies both arms only for that request contract. There is no equivalence claim for workloads needing more than 4,096 per slot.

Each arm spent five minutes at 0.8, 1.0 and 1.15 offered transactions/s. Across the four arms, this was **60 scheduled minutes**, 3,540 offered transactions, 3,823 raw rows including dependent steps, 2,419 GPU samples and 345 metrics samples. The controller ran for 60.74 minutes excluding earlier model hashing and smoke setup. All owned launches exited. Sampled device memory and temperature stayed within the approved envelope at peaks of **8,085 MiB** and **69.5°C**. GPU telemetry measures board activity, including the desktop. The result does not establish overnight stability.

The selected synthetic task deck used unique receipts, varied document bodies, two-code-function manifests and short dependent agent transcripts. Cache share across the panels was approximately **0.9–1.0%**. This changes both cache locality and workload composition relative to Phase 3. A causal attribution of the different results to caching alone would require a separate experiment.

## Matched results by load

Each cell pairs the two independent launches of the profile. The goodput denominator is the scheduled 300 seconds per load window. All offered transactions are included. P95 uses the completed-transaction sample, as in the independent historical recount.

| Offered txn/s | Two slots on time | Four slots on time | Two-slot P95 TTFT | Four-slot P95 TTFT | Output tok/s across profiles |
| ---: | --- | --- | --- | --- | --- |
| 0.80 | 232/240 · 232/240 | 229/240 · 227/240 | 0.684–0.692 s | 0.669–0.687 s | 71.9–72.1 |
| 1.00 | 286/300 · 287/300 | 265/300 · 264/300 | 0.856–0.858 s | 0.703–0.715 s | 89.5–90.1 |
| 1.15 | 317/345 · 315/345 | 284/345 · 293/345 | 1.616–1.741 s | 0.753 s | 103.8–104.0 |

At 1.15/s, two slots achieved **1.050–1.057** correct on-time transactions/s, versus **0.947–0.977** with four. In every possible launch pairing this is a decline of about **7–10%**. P50 TTFT fell from **0.549–0.568 s to 0.205–0.213 s**. P95 completion rose from **3.714–3.820 s to 4.523–4.678 s**. P95 client dispatch delay was about **24 ms** in all four arms. This cannot explain the completion regression.

The chat family illustrates the trade. At 1.15/s, p95 first-token time fell from **1.41–1.48 s to 0.19–0.25 s**, while p95 completion grew from **3.99–4.23 s to 5.08–5.17 s**. Median server chat decode time per output token rose from **13.5–13.7 ms to 20.4–21.6 ms**. This supports a concurrent decode contention hypothesis. Per-request timings under mixed scheduling cannot isolate kernel causality.

Coding and retrieval met the scoped correctness and latency targets in the high-rate windows on all four launches. The agent family missed the target in every window, primarily because of response format and wrong receipts rather than transport. There were 77 failed first agent steps and 80 failed tool-result steps across the four arms, with no recorded HTTP, timeout or admission errors. Testing actual structured tool calling and a separate workload-specific task evaluation is the next discriminating experiment. Relaxing the fixture gate after looking at results would change the contract.

The Phase 4 primary recount uses the original scoped task checks. A stricter sensitivity rejects capped streams even when a receipt is present. At 1.15/s it counts **305–309/345** on time for two slots and **279–287/345** for four. The direction persists. This does not qualify general response quality.

## Historical audit

The Phase 3 paired comparison was recalculated from source transaction rows. All 60 arm/rate/family strata reconciled offer, validity, on-time counts, sampled latency, output token throughput, and goodput. Stream counts reconciled with the server's prediction and cache fields. Client arrivals, dispatch, first token, and completion were checked in order. Rejections and failed responses remained in denominators. For dependent turns, Phase 3 and this replication gate each step separately. The product also exposes an explicit end-to-end transaction SLO, which is a different contract.

The interrupted original A2 recorded about **10,031 wall-clock seconds** for a nominal 1,800-second window during Windows suspend. Its original completion flag was insufficient. The eligible history excludes that window and uses the fresh A2. The retained windows have matching plans, close elapsed and wall durations, complete accounting and owned process shutdown. The comparison remains eligible as a **segmented replay**. The original history did not establish uninterrupted endurance. Across-session GPU process residency and drift remain limitations.

## Evidence and reproduction

- [Phase 3 independent recount](phase3-recount.json) and [Phase 4 independent recount](replication-recount.json)
- `validation/runs/replication-01/` contains the local raw streams, matched schedule, fixtures, board observations, launch commands, shutdowns, charts and verification.
- `python validation/replicate.py NEW_ID --smoke` qualifies the harness. Omitting `--smoke` schedules the full 60 minutes against the sibling research workspace.
- `python validation/recount.py` and `python validation/recount.py --replication validation/runs/replication-01` reproduce the comparisons without starting a model.

