# Public claims ledger

Research paths below are relative to the local `inference-bench` archive. Product paths are relative to this repository. The [public measurement projection](../../public/evidence/measurements.json) contains sanitized values for recalculation. Confidence describes the evidence within its workload and hardware scope.

## ENV

**Claim.** RTX 4070 with nominal 12 GB VRAM, Ryzen 7 7800X3D with nominal 64 GB RAM, Windows 11 Home build 26300. Qwen3-8B Q4_K_M and Gemma 4 12B IT QAT text Q4_0 used llama.cpp b12427 at `1719dbb0ee7bdaf56de083079d3613bb670160a5`. Forge Qwen3.5 9B Q4_K_M used the text-export loader at `e4ee2d21a8ceae24aecdc7c3a229a48ad3b34ee5`. Qwen's c2/c4 partitions were 8,192/4,096 positions at 16,384 total. Forge and Gemma were 4,096/2,048 at 8,192 total. The modeled resource is the f16 KV allocation.

**Evidence / method.** `results/{cpu,os,ram,provenance,model-metadata}.json`, `results/gpu-inventory.csv`, and `phase3/configs/cross-model-inventory.json`. Build and GGUF digests are in each selected run's `environment.json`. Startup records under `phase3/results/{endurance-02,endurance-resume-02,forge-transfer-01,gemma-transfer-01}/runs/*/{launch.json,server.log}` confirm slot counts, per-slot context and f16 cache. The Qwen A2 startup comes from the resumed run. High confidence for these configurations. Cross-model control does not isolate architecture, quantization or loader effects. Used in the case study, figures, inventory and site framing.

## P1-TUNING

**Claim.** Original Flash Attention-off control vs selected Flash Attention-on and physical microbatch 512 recipe (previously 256): median decode 81.03 → 84.11 output tok/s, cold 7,168-token client prefill 2,291 → 4,207 prompt tok/s.

**Evidence / method.** `results/raw/{baseline,qualification-best}-{decode-*,prefill-7168-*}.json`, adjacent `qualification-baseline` and `results/summary.csv`. Six decode prompts and three verified cold prompts per launch. Decode is (generated token count − 1) / (wall time − client TTFT). Cold prefill is prompt tokens / client TTFT, including HTTP and first emission. Recomputed from observations. High confidence for the disabled-feature control. No inference about the gain relative to the binary default. Used in the case study.

## P2-DEFAULT

**Claim.** Automatic Flash Attention resolved to on. Two context-normalized default launches obtained 4,197–4,209 prompt tok/s at 7,168 cold tokens. The explicit Phase 1 recipe obtained 4,200 prompt tok/s in the follow-up.

**Evidence / method.** `phase2/BASELINE.md`, `phase2/data/{default-a,default-b,prior-a}/requests.jsonl` and startup logs, `phase2/data/summary.json` at each launch's `cold.effective_prefill_tps`. Six cold samples per launch, median of prompt tokens / client TTFT. Context-normalized fixes 16,384 total and two slots, while preserving auto placement and Flash Attention for the default. High confidence within this build and probe. Used in the case study and executive summary.

## P2-PROFILE

**Claim.** Quantized GEMV contributed 93.3% of summed short-decode kernel time. Quantized GEMM contributed 75.4% of summed cold-prefill kernel time.

**Evidence / method.** `phase2/data/serving-trace/phase-trace.json` at `windows.short_decode` and `windows.cold_prefill`, `phase2/BOTTLENECKS.md`, `phase2/profiles/counter-check.txt`. One Nsight capture with separate isolated windows. Share uses summed clipped GPU kernel durations by symbol family. Hardware counters were unavailable. These shares characterize traced work and do not measure DRAM bandwidth, occupancy or transferable runtime speedup. Moderate confidence for the mechanism on this trace. Used in the case study.

## P2-CHAT

**Claim.** On Qwen homogeneous chat bursts, two → four serving slots increased pooled output 143.77 → 226.70 tok/s (+57.7%).

**Evidence / method.** `phase2/data/{chat-before,chat-after,chat-control-final,chat-four,chat-four-confirm}/requests.jsonl` and `run.json`, `phase2/data/pooled.json` at `Chat burst standard c2` and `Chat burst selected c4`. Launches share a manifest digest. Three control and two candidate launches, 48 requests each (144/96 offered). Recount eligible output tokens / sum of first arrival to last result spans per profile. Relative change = 100 × (candidate / control − 1). Two-slot production control, f16 16,384 total context. High confidence in the scoped repeated burst pattern. The candidate halves per-request context and the launch sample covers one machine/session. Used in the case study, executive summary, landing page and burst figure.

## P2-MIX

**Claim.** For complete-output V3, production c2 → c4 goodput rose from 1.155 to 1.418 scoped requests/s, while output was 92.24 → 90.55 tok/s. The context-normalized default scored 1.160 scoped requests/s.

**Evidence / method.** `phase2/data/{v3-before,v3-after,v3-control-final,v3-four,v3-four-confirm,v3-default}/requests.jsonl` and `run.json`; V3 pools in `phase2/data/pooled.json`. Same matched manifest. Goodput counts eligible requests satisfying both family deadlines divided by total pooled launch duration. Control/candidate/default sample 210/140/70 requests from three/two/one launches. Agents are scored per request step, unlike later transaction-level reporting. High confidence for the measured contrast, conditional on the workload and fixture gates. Used in the case study.

## P2-METHOD

**Claim.** Reused prefixes avoided most prefill work on the exact-repeat probe. The host cache-off screen reduced prefix hit share on a capped-code mix. N-gram speculation improved throughput for repetitive V3, and the learned draft increased first-token latency and memory. Four-slot long-context q8 KV used a larger cache pool and lower precision than the f16 slot comparison.

**Evidence / method.** `phase2/BASELINE.md`, `phase2/EXPERIMENTS.md`, `phase2/data/summary.json` cache, q8 and speculation panels, `phase2/data/{four-spec-a,four-spec-confirm,draft-a}/requests.jsonl`. Warm probes reuse a same-slot prefix. Four-slot V3 n-gram has 70 requests on each of two candidate launches with retained controls. The learned-draft and early host-cache results are scoped screens, while the q8 result checks retrieval under its own contract. These are qualitative statements about workload-specific effects. Moderate confidence for transfer. Used in the case study.

## P3-MODELS

**Claim.** Qwen +19.2%, Forge +4.6% and Gemma +9.5% output rate on four slots versus their own two-slot production controls. The table in the case study reports 114.35 → 136.32, 95.37 → 99.72 and 71.33 → 78.07 output tok/s, respectively. Forge and Gemma missed the aggregate 95% deadline target at their high rates.

**Evidence / method.** `phase3/results/{endurance-segmented,forge-transfer-01,gemma-transfer-01}/{requests.jsonl,schedule.json,summary.csv,verification.json}`. Recounted planned cohort, output usage, valid counts and on-time counts. Medians of individual window rates, then 100 × (candidate / control − 1). Qwen uses A1/A2 and B1/B2 at 1.400 offered txn/s in 600 s windows (840 offered per launch). Forge and Gemma use A1/A2/A3 and B1/B2 in 150 s windows (142/111 offered per launch or 0.947/0.740 txn/s). Candidate pools were 1,680/1,680, 284/284 and 222/222 valid/offered. Transfer controllers recorded 45 scheduled minutes each. Extra cache/batch/n-gram rows are retained as separate screens. High confidence for the given model and load, limited evidence for other serving conditions. Used in the case study, executive summary and transfer figure.

## P3-RUN

**Claim.** Qwen retained 180 scheduled minutes in segments. The excluded A2 took 10,031 wall seconds for a nominal 1,800-second block because Windows suspended. Peak sampled board temperature 69.7 °C, peak VRAM 8,086 MiB, 639 outstanding-limit outcomes. The subsequent 1.1 txn/s recovery stage completed 1,302/1,320 on time without changing the overload server.

**Evidence / method.** `phase3/results/endurance-02/{suspend-event.json,runs/A2-window.json}`; `phase3/results/endurance-segmented/{verification.json,runs/A2-window.json,gpu-telemetry.csv,requests.jsonl,summary.csv}`. Sum retained achieved stage durations, compare original/replacement wall-to-schedule times, take device-wide maxima across 7,191 samples and count explicit rejection rows. Recovery count is the all-family row over 1,200 s. High confidence for the measured segments. No uninterrupted endurance claim. Used in the case study and executive summary.

## P3-SLO

**Claim.** Both Qwen profiles qualified up to 0.8 offered txn/s on the per-family grid. Aggregating families moves the four-slot passing point to 1.1 txn/s, while two-slot still qualifies at 0.8.

**Evidence / method.** `phase3/results/endurance-segmented/{requests.jsonl,summary.csv,verification.json}`, `phase3/CAPACITY.md`, [archived recount](../../validation/phase3-recount.json). Both launches must reach 95% on time and at most 1% transport/admission failure. Evaluate per-family and aggregate separately. Two fresh arms per profile across three 600 s windows (480/660/840 offers per arm). High confidence for these grid points. No continuous capacity estimate or verified fleet saving. Used in the case study.

## P4-DESIGN

**Claim.** The fresh mixed Qwen replication had 60 scheduled minutes and 3,540 offers. Four launches × three 300 s windows had 240/300/345 offers per window. Prompt-token hit share was approximately 0.9–1.0%.

**Evidence / method.** Product `validation/runs/replication-01/{requests.jsonl,schedule.json,verification.json}`, [independent local replication](../../validation/INDEPENDENT_REPLICATION.md), [recount](../../validation/replication-recount.json). Sum scheduled duration and offers, divide cached prompt tokens by all prompt tokens. Recomputed 60 aggregate/family strata. High confidence in the run contract. A fresh workload on the same machine does not isolate prefix reuse or substitute for external validation. Used in the case study and replication figures.

## P4-TAIL

**Claim.** At 1.15 offered mixed txn/s, p95 TTFT was 1.616–1.741 s (two slots) vs 0.753 s on both four-slot launches. P95 end-to-end completion was 3.714–3.820 s vs 4.523–4.678 s. Output rate varied around 104 tok/s.

**Evidence / method.** P4-DESIGN source, `window=3`, `family=all`, all four A1/B1/B2/A2 launch rows. Nearest-rank p95 on complete transactions, 345 offers per launch; output tokens / 300 s scheduled. Report min–max of independent launch summaries rather than a confidence interval over pooled traffic. High confidence in direction for this paired setting. Used in the case study, executive summary, landing page and tail-latency figure.

## P4-GOODPUT

**Claim.** At 1.15 offered mixed txn/s, two slots completed 1.050–1.057 correct on-time txn/s, versus 0.947–0.977 on four. The same direction holds when capped streams are excluded.

**Evidence / method.** P4-DESIGN source. On-time counts A1/A2 = 317/315 and B1/B2 = 284/293, 345 offered per launch. Goodput divides count by the scheduled 300 seconds. Stop-only sensitivity is under `on_time_stop_only` in the recount. Figure includes all three offered rates. High confidence in direction within the tested synthetic mix. Used in the case study, executive summary, landing page and goodput figure.

## P4-FAMILY

**Claim.** Neither profile passed 95% correct and on time in every family at any tested rate. At 1.15 txn/s, code and retrieval met their scoped thresholds. Chat and dependent agents missed.

**Evidence / method.** P4-DESIGN source. At the highest rate there are 137 chat, 86 coding, 86 retrieval and 36 agent offers per launch. Family pass share uses correct on-time / all offered transactions. Dependent agent steps receive their own deadlines. Inspect all launch/family cells and retain all failures. High confidence for these gates, with narrow synthetic correctness checks. Used in the case study, executive summary, landing page and SLO figure.

## P6-RECOUNT

**Claim.** The completed Phase 6 Qwen3-8B synthetic study recorded 13,926 completed transactions, of which 13,156 passed correctness and 13,155 passed correctness and deadlines. Among the 1,392 agent transactions, 776 passed correctness and 775 passed both. These fixtures are distinct from the later agent-receipt V2 probes.

**Evidence / method.** [Aggregate and source hashes](../../public/evidence/labs-endurance.json) · [CPU recount](../../scripts/publication/verify_endurance_summary.py). The completed archive is identified as phase6-endurance-01. The private transaction ledger and archived summary and SLO match their sealed hashes. The recount verified unique transaction IDs and counted stored flags by family. This reflects recorded verdicts on one lab host. The underlying answers are not recoverable from the aggregate and the count cannot establish general model quality. The earlier abort and Phase 3 suspended segment are separate records.

## P7-FORGE-MTP

**Claim.** One-token native MTP on Forge Qwen3.5-9B increased median single-stream code decode by 6.9% and 7.0% against the faster control in two fresh brackets, with 71.56–71.57 → 76.60 tok/s in the second. Code output matched both controls across the eight prompts in each bracket. Both near-full retrieval checks passed. Novel prose decode was broadly unchanged. Four-token MTP regressed code and prose.

**Evidence / method.** [Per-launch metrics and hashes](../../public/evidence/forge-mtp.json) · [Protocol and limits](../case-study/FORGE_MTP.md). Eight 128-output-token prompts per panel per launch. Eight code outputs per arm compared byte for byte. Same artifact, context, decode options and CUDA path. One RTX 4070 and one engine release. Excludes production, concurrent and all-family qualification. The calculator uses a separate hypothetical service-throughput assumption.

## DEMO

**Claim.** The Qwen and Gemma public reports are offline re-renders through the 0.2.1 product from 0.2.0 captures of 446 and 50 transactions. Report tables/plots use the original measured observations. The Qwen sweep used a fixed two-slot server; its parallel decode probe scales client workers. The archived sweep and the final short restart are separate captures.

**Evidence / method.** Product `.runs/{qwen-020,gemma-020}`, `reports/{local-qwen-020,local-gemma-020}/audit.json`, [acceptance verification](../../docs/VALIDATION.md), [public reports](../../public/reports/README.md). Native loader verifies local integrity and step structure and replays all metrics. The export substitutes a public label and alias, omits precise wall-clock timestamps and host identifiers, and excludes the optional cost scenario. Rendered values and distributions come from the replay. High confidence in provenance and numeric output agreement; correctness remains the stored scoped check. Used in the case study, executive summary, README and landing page.

## RELEASE

**Claim.** Inference Audit 0.2.1. Seventy-eight test cases passed in a fresh rerun of the 0.2.1 source suite on Windows during public preparation. Local native CUDA shutdown remains unverified.

**Evidence / method.** Installed wheel hash, CLI version and `pytest -q` test output are recorded in [publication checks](PUBLICATION_CHECKLIST.md). Wheel and source version match. This is a local rerun; external reviews and native CUDA process control are separate claims. Used in the checklist and release notes.
