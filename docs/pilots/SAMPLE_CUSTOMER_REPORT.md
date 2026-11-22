# Sample Customer Staging Assessment Report *(Demonstration Only)*

> **DEMONSTRATION NOTICE — NOT A REAL CUSTOMER CASE STUDY**  
> This sample report illustrates the exact deliverable format a prospective customer receives after a **Free, Bounded Initial Staging Assessment**. Quantitative examples below combine our verified **Phase 9 RTX 4070 vLLM 0.34.0 lab evidence** (`public/evidence/vllm-phase9.json`) with our **Phase 9.1 end-to-end synthetic rehearsal** (`demo-vllm-pilot-rehearsal`). No real customer relationships, customer savings, or enterprise H100/H200/B200 measurements are claimed.

---

## Engagement Metadata

| Field | Value |
| :--- | :--- |
| **Report Type** | Free Bounded Initial Staging Assessment (Read-Only Demonstration) |
| **Target Stack (Lab Reference)** | `vLLM 0.34.0` + `vllm-gguf-plugin 0.0.5`, `Qwen3-8B Q4_K_M`, 1× RTX 4070 12 GB (WSL2) |
| **Baseline Flags** | `--enforce-eager --no-enable-extensible-kv-cache --max-model-len 1280 --gpu-memory-utilization 0.67` |
| **Observability Scope** | Approved `/metrics` on pinned loopback origin (SHA-256 hashed label IDs; zero raw labels stored) |
| **Evidence Verification** | Offline `inference-audit verify` passed (`SHA-256 integrity.json`) |

---

## 1. Executive Summary
- **Verdict:** **Capacity- and context-limited within tested bounds** (no stage met strict per-family qualification).
- **What performance was measured:** Closed-loop short chat scaled from **30.12 tok/s** (`c=1`) → **59.38 tok/s** (`c=2`) → **98.36 tok/s** (`c=4`). Mixed open-loop traffic delivered **26.84 tok/s** at 1 offer/s and **38.46 tok/s** at 2 offers/s.
- **How much useful capacity was available:** Peak correct, on-time goodput reached **1.100 tasks/s** at `c=4` closed-loop and **0.504 tasks/s** at `1 offer/s` mixed — **dropping to 0.471 tasks/s** at `2 offers/s` mixed as queuing and context-limit errors compounded. Strict qualification: **0.000 qualified RPS** (failed strict gates due to context rejections and HTTP 400s).
- **Primary takeaway:** Raising arrival rate from 1 → 2 offers/s increased raw output tokens/s by +43% (`26.84 → 38.46`), yet **reduced** useful correct on-time completions (`0.504 → 0.471 tasks/s`) while median TTFT nearly tripled (`0.195 s → 0.543 s`).

---

## 2. Measured Performance & Useful Capacity by Stage

| Stage | Mode | Offered | Output tok/s | Correct On-Time Goodput (tasks/s) | TTFT p50 (s) | Strict Qualification |
| :--- | :--- | ---: | ---: | ---: | ---: | :---: |
| `closed-c1` | Closed (1 worker) | 32 | 30.12 | 0.316 | 0.129 | Fail |
| `closed-c2` | Closed (2 workers) | 32 | 59.38 | 0.620 | 0.159 | Fail |
| `closed-c4` | Closed (4 workers) | 32 | 98.36 | 1.100 | 0.178 | Fail |
| `mixed-r1` | Open (1 offer/s) | 64 | 26.84 | 0.504 | 0.195 | Fail |
| `mixed-r2` | Open (2 offers/s) | 64 | 38.46 | 0.471 | 0.543 | Fail |

*Note: p95 is intentionally withheld below 40 completed samples per stage/family. All transport, HTTP 400, context-limit, and quality failures remain in the denominator.*

---

## 3. Queue Onset, Missed Targets & Observed Bottlenecks

- **Where queuing began:** Median TTFT remained flat (`0.129 → 0.178 s`) through `c=4` short chat, then jumped sharply between `mixed-r1` (`0.195 s`) and `mixed-r2` (`0.543 s`) as long-context prompts and concurrent tool requests saturated the 1,536-token KV pool.
- **Missed latency & contract targets:** `mixed-r1` recorded **9 context-limit** and **7 HTTP 400** failures under the constrained 1,280-token context window. `mixed-r2` missed interactive TTFT deadlines as queue depth grew.

### Structured Bottleneck Findings (8-Field Diagnostic Contract)

#### Finding 1: High KV Occupancy Coincided with Preemptions (`mixed-r2`)
- **Confidence:** Moderate in the tested stage.
- **Observed evidence:** Matching hashed label series approached KV saturation alongside positive `vllm:num_preemptions_total` deltas while `mixed-r2` goodput fell (`0.504 → 0.471 tasks/s`).
- **Why this suggests the hypothesis:** With only 1,536 total KV tokens allocated (1.20× a single 1,280-token sequence), concurrent mixed requests exhaust physical KV blocks, forcing preemption and recomputation.
- **Alternative explanations:** Client arrival clustering or oversized output caps on specific mixed requests.
- **Missing information:** Event-level simultaneity between preemption timestamps and individual tail requests; exact recompute token overhead.
- **Falsifiable experiment:** Replay `mixed-r2` on a dedicated replica with higher KV capacity (e.g., FP8 KV or larger VRAM GPU) holding model and workload constant.
- **Possible configuration changes:** Increase KV headroom (`--kv-cache-dtype fp8` where supported and quality-verified, right-size `--max-model-len`, or move to higher-VRAM GPU).
- **Potential regressions & trade-offs:** FP8 KV requires re-verifying long-context retrieval and strict tool calling; shrinking `--max-model-len` rejects legitimate long prompts.

#### Finding 2: Quality & Context Failures Reduced Qualified Goodput (`mixed-r1`, `mixed-r2`)
- **Confidence:** High for observed failure count; separate from raw decode speed.
- **Observed evidence:** 9 context-limit and 7 HTTP 400 outcomes occurred in `mixed-r1` alone.
- **Why this suggests the hypothesis:** Serving a workload with prompts exceeding `1,280` tokens makes speed tuning meaningless until context admission matches actual product requirements.
- **Alternative explanations:** Client prompt template inflation or overly permissive synthetic prompt lengths relative to production traffic.
- **Missing information:** Customer's true p99 production prompt + output token distribution.
- **Falsifiable experiment:** Replay failing task families at `c=1` with verified `--max-model-len` matching p99 workload length.
- **Possible configuration changes:** Provision sufficient VRAM/KV headroom for required `--max-model-len` before tuning batch budgets.
- **Potential regressions & trade-offs:** Larger context budget lowers peak concurrent sequences per GPU.

#### Finding 3: Prefix Caching Confirmed High Upside on Repeated Prefixes (Targeted Probe)
- **Confidence:** High for repeated-prefix TTFT; does **not** imply workload-wide throughput gain.
- **Observed evidence:** Across 3 fresh launches (54/54 receipts, ~1,132-token shared prefix), median TTFT dropped from **2.768–2.778 s** (cold) to **0.122–0.125 s** (warm, ~22×), while early-prefix-changed negative controls returned to **2.764–2.772 s** (`6,528` hits / `20,376` queries in bracket 1).
- **Why this suggests the hypothesis:** Identical leading blocks hit vLLM's PagedAttention prefix hash table and bypass prefill compute.
- **Alternative explanations:** None for the controlled triplet (early-change negative control ruled out warm-GPU artifacts).
- **Missing information:** Share of customer production traffic that actually reuses static leading prefixes, plus multi-replica router cache affinity.
- **Falsifiable experiment:** Audit real prompt templates for dynamic leading tokens (timestamps/IDs) and test prefix-aware routing on a 2-replica staging pool.
- **Possible configuration changes:** Place static system instructions and tool schemas at token 0; enable `--enable-prefix-caching` + prefix-aware routing.
- **Potential regressions & trade-offs:** Prefix-aware routing can skew load onto one replica if a single tenant dominates traffic.

---

## 4. What Remains Uncertain
1. **CUDA-graph vs eager gap:** Eager mode was required to fit inside the 12 GB RTX 4070 desktop margin; CUDA-graph speedup was not isolated on this GPU.
2. **Native fused quantization vs experimental GGUF:** Enterprise deployments using native FP8 or AWQ-Marlin weights on dedicated datacenter GPUs behave very differently from the experimental GGUF plugin.
3. **Multi-replica & production traffic:** No multi-GPU (TP/EP/DP) or disaggregated prefill/decode behavior was tested here.

---

## 5. Prioritized Controlled Experiments (Candidate Next Sprint)
1. **Experiment 1 — Native Fused Quantization + CUDA Graphs (Highest Leverage):** Compare native FP8 or AWQ-Marlin with CUDA graphs enabled against current baseline in an `A-B-A` bracket on customer staging hardware (pass gate: >= 95% per-family correctness + tool calls).
2. **Experiment 2 — Prefix-Cache Layout & Routing Audit:** Move static system/tool headers to token 0 and measure warm TTFT + `prefix_cache_hits_total` across realistic multi-turn sessions.
3. **Experiment 3 — Chunked Prefill Token-Budget Bracket:** Test `--max-num-batched-tokens` (`1024` vs `2048` vs `4096`) under representative mixed short+long load, keeping a short-only negative control (note: in our Phase 9 RTX 4070 bracket, `512` freed KV from `1,536 → 2,752` tokens but *regressed* c4 goodput `1.100 → 0.940`, proving why every lever must be bracket-tested!).

---

## 6. Conditional Financial Sensitivity (Illustrative Only — Not Guaranteed)

If a follow-on optimization sprint qualifies a throughput improvement of factor $g$ on **reducible scalable GPU spend** at fixed demand, required GPU-hours change by $1 - 1/g$:

| Monthly Scalable GPU Spend | Qualified Capacity Gain ($g$) | GPU-Hour Reduction ($1 - 1/g$) | Illustrative Annualized Reduction |
| ---: | ---: | ---: | ---: |
| `$25,000 / mo` | `+20%` (`1.20×`) | `16.7%` | `~$50,000 / yr` |
| `$50,000 / mo` | `+30%` (`1.30×`) | `23.1%` | `~$138,462 / yr` |
| `$100,000 / mo` | `+30%` (`1.30×`) | `23.1%` | `~$276,923 / yr` |

*Realizable savings depend on flexible/reducible billing, integer node increments, and mandatory N+1 failover headroom.*

---

## 7. Independent Verification
Every run delivered by Inference Audit Labs is cryptographically sealed and verifiable offline without trusting our summary:
```bash
inference-audit verify --run <run-name>
inference-audit report --run <run-name>
```
