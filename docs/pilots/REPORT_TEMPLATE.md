# Customer Staging Assessment Report Template

> **Client:** `[Customer Name]`  
> **Endpoint & Model:** `[Staging Alias]` · `[Model ID]` · `[Engine Version]` · `[GPU Hardware]`  
> **Assessment Date:** `[YYYY-MM-DD]` · **Prepared by:** Rayn Hasan, Inference Audit Labs  
> **Evidence Bundle SHA-256:** `[integrity.json digest]`

---

## 1. Executive Summary
- **Verdict:** `[Healthy / Capacity-limited / Reliability problem / Inconclusive within tested bounds]`
- **Highest Qualified Goodput:** `[X.XXX correct on-time tasks/s]` (or `None — no stage met all strict per-family gates`)
- **Primary Bottleneck Hypothesis:** `[1–2 sentence plain-English summary]`
- **Top Recommended Next Experiment:** `[Single highest-leverage controlled test]`

## 2. Measured Performance by Stage

| Stage | Offered | Completed | Error Share | Quality Failures | Goodput (tasks/s) | Output tok/s | TTFT p50 / p95 (s) | E2E p50 / p95 (s) | Strict Gate |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| `closed-c1` | | | | | | | | | |
| `closed-c2` | | | | | | | | | |
| `closed-c4` | | | | | | | | | |
| `mixed-r1` | | | | | | | | | |
| `mixed-r2` | | | | | | | | | |

## 3. Queue Onset, Missed Deadlines & Failures
- **Where queuing began:** `[State exact stage/rate where waiting gauge or client queue latency rose]`
- **Missed SLO targets:** `[List exact task families and percentiles that missed targets]`
- **Reliability & contract failures:** `[HTTP 400s, context-limit rejections, tool-parse failures, timeouts — always counted in denominator]`

## 4. Server-Side Observability Summary (If Approved)
- **Scrape coverage:** `[Observed scrapes / total scrapes; note any transport failures, resets, or series truncation]`
- **KV cache & preemptions:** `[Peak KV usage fraction per label series; preemption counter deltas]`
- **Prefix reuse:** `[Hits / queries, observed hit fraction, matched vs skipped intervals]`
- **Server latency histograms:** `[p50 and p95 bucket bounds for TTFT, prefill, ITL/TPOT, queue time]`

## 5. Structured Bottleneck Diagnosis
*(Repeat for each finding — never claim causation from correlation alone.)*

- **Finding:** `[Title]`
- **Confidence:** `[High / Moderate / Low — scoped explicitly]`
- **Observed evidence:** `[Exact metrics and stages]`
- **Why this suggests the hypothesis:** `[Mechanism]`
- **Alternative explanations:** `[What else could produce this signature]`
- **Missing information:** `[What was not measured in this bounded run]`
- **Falsifiable experiment:** `[Exact A/B test to prove or disprove]`
- **Possible configuration changes:** `[Specific flags/knobs]`
- **Potential regressions & trade-offs:** `[What could worsen if changed]`

## 6. What Remains Uncertain
- `[Explicit list of untested contexts, concurrency regimes, multi-replica routing effects, or hardware profiling gaps]`

## 7. Prioritized Controlled Experiments
1. **Experiment 1 (Highest leverage):** `[Single change, control bracket, expected signal, pass/fail gate]`
2. **Experiment 2:** `[Single change, control bracket, expected signal, pass/fail gate]`
3. **Experiment 3:** `[Single change, control bracket, expected signal, pass/fail gate]`

## 8. Conditional Financial Impact (Illustrative — Not Guaranteed)
Assuming fixed demand and fully reducible scalable GPU billing, improving qualified goodput by factor $g$ reduces required GPU-hours by $1 - 1/g$:

| Current Monthly Scalable GPU Spend | Qualified Capacity Gain ($g$) | GPU-Hour Reduction ($1 - 1/g$) | Illustrative Annualized Reduction |
| ---: | ---: | ---: | ---: |
| `$25,000 / mo` | `+20%` (`1.20×`) | `16.7%` | `~$50,000 / yr` |
| `$50,000 / mo` | `+30%` (`1.30×`) | `23.1%` | `~$138,462 / yr` |
| `$100,000 / mo` | `+30%` (`1.30×`) | `23.1%` | `~$276,923 / yr` |

*Constraints: Fixed reserved capacity, integer node counts, N+1 redundancy, and failover reserves reduce realizable savings.*

## 9. Offline Verification
Verify the sealed evidence bundle independently with:
```bash
inference-audit verify --run <run-name>
inference-audit report --run <run-name>
```
