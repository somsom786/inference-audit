# Paid Optimization Engagement Proposal Template

> **Client:** `[Customer Name]`  
> **Prepared by:** Rayn Hasan, Inference Audit Labs  
> **Basis:** Follows completed Free Initial Staging Assessment (`[Run ID]`, `[Date]`)

---

## 1. Context & Observed Opportunity
In the initial staging assessment of `[Model ID]` on `[GPU Hardware]`, we observed:
- `[Key baseline finding #1 — e.g., queue onset at X RPS, KV occupancy at Y%, or prefill/decode interference]`
- `[Key baseline finding #2 — e.g., prefix reuse gap or context/quality failure rate]`

While no speedup is guaranteed before controlled testing, the baseline evidence points to `[1–3]` concrete, falsifiable configuration hypotheses worth testing in an interleaved staging bracket.

## 2. Proposed Scope of Work (Fixed-Scope Sprint)
**Duration:** `[e.g., 1–2 weeks]`  
**Environment:** Customer-controlled dedicated staging replica (zero production edits by Inference Audit Labs).

### Deliverables
1. **Pre-registered Experiment Matrix:** Exact control-candidate-control (`A-B-A`) brackets changing one lever at a time (e.g., batch token budget, KV dtype/memory utilization, prefix-cache layout, attention/quantization backend, speculative decoding, or worker topology).
2. **Controlled Staging Execution & Qualification:** Run matched synthetic + customer-approved representative traces under strict per-family correctness, tool-calling, context, and tail-latency gates.
3. **Negative-Result & Boundary Documentation:** Document both winning configs and exact failure/regression cliffs (e.g., where concurrency or context breaks).
4. **Canary & Rollback Runbook:** Exact recommended flags, canary promotion gates, monitoring alerts, and instant rollback procedure for customer engineers.
5. **Final Executive & Engineering Report:** Verified sealed evidence bundles, reproducible commands, and updated unit-economics sensitivity based on actual measured qualified goodput.

## 3. Customer Responsibilities
- Provision and operate the isolated staging replica(s) and apply agreed configuration changes between test arms.
- Retain sole ownership of production deployments, canary rollouts, and rollbacks.
- Provide representative de-identified workload distributions and quality acceptance criteria.

## 4. Commercial Terms (Example Structure — Adjust Per Client)
- **Fee:** `[Fixed sprint fee, e.g., €3,500 – €6,500]` (50% upon kickoff, 50% upon delivery of final verified report & runbook).
- **No-surprise boundary:** If baseline re-verification shows the existing configuration is already near hardware limits, we deliver the proof and stop cleanly without padding scope.
- **IP & Confidentiality:** All customer-specific configurations, reports, and evidence belong exclusively to the customer. Nothing is published without separate written consent.

## 5. Acceptance
- **Customer Approver:** `_______________________` · **Date:** `YYYY-MM-DD`
- **Inference Audit Labs:** `Rayn Hasan` · **Date:** `YYYY-MM-DD`
