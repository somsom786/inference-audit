# Staging Test Plan Template

> **Project:** `[Customer Name]` — Staging Inference Assessment  
> **Date:** `[YYYY-MM-DD]` · **Prepared by:** Rayn Hasan, Inference Audit Labs

---

## 1. Objective
Measure useful capacity (correct, on-time transactions per second), latency distributions, and server-side bottleneck signals on `[Model ID]` served by `[Engine + Version]` on `[GPU SKU x Count]` under bounded, reproducible synthetic traffic.

## 2. Target & Hard Safety Envelope
- **Origin:** `https://[approved-staging-host]` (dedicated staging replica, isolated from production)
- **Engine adapter:** `vllm` / `openai` / `llama.cpp`
- **vLLM `/metrics` scraping:** `Enabled (approved)` / `Disabled`
- **Hard caps:** `max_requests = [N]`, `runtime_s = [T]`, `max_concurrency = [C]`, `max_rps = [R]`, `timeout_s = [TO]`

## 3. Service-Level Objectives & Qualification Gates
A stage **strictly qualifies** only if ALL active task families meet:
- Offered sample count `>= 20` per family
- On-time & correct share `>= 95%` (or customer-specified gate)
- Error share `<= 5%`
- Verified context window `>= required_context` (when specified)

| Task Family | Max TTFT (s) | Max Completion (s) | Correctness Check |
| :--- | ---: | ---: | :--- |
| `chat` | `1.5` | `8.0` | Exact receipt / format check |
| `coding` | `2.0` | `12.0` | Valid structured code / syntax check |
| `rag` | `3.0` | `15.0` | Grounded retrieval needle check |
| `agent` | `2.5` | `15.0` | Strict tool-call schema & counterfactual check |

## 4. Staged Workload Design

| Stage | Mode | Pattern | Workers | Rate (RPS) | Offers | Max Output | Purpose |
| :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| `closed-c1` | Closed | `chat` | 1 | — | 32 | 64 | Single-stream latency & decode baseline |
| `closed-c2` | Closed | `chat` | 2 | — | 32 | 64 | Low-concurrency scaling check |
| `closed-c4` | Closed | `chat` | 4 | — | 32 | 64 | Moderate concurrency & batching efficiency |
| `mixed-r1` | Open | `mixed` | 4 | 1.0 | 64 | 96 | Representative mixed chat/RAG/tool load |
| `mixed-r2` | Open | `mixed` | 4 | 2.0 | 64 | 96 | Queue-onset & deadline stress test |

*(Optional: Add a bounded 18-request cold/warm/early-change prefix probe if prefix caching is a primary hypothesis.)*

## 5. Observability & Evidence Plan
- Client captures per-request dispatch, headers, first-visible-event, completion, HTTP status, finish reason, and terminal usage tokens.
- Server scrapes `/metrics` every 5 seconds (if approved) with allowlisted `vllm:*` metrics and SHA-256 hashed label IDs.
- All outputs sealed with SHA-256 (`integrity.json`) and verified offline via `inference-audit verify`.

## 6. Abort & Stop Conditions
Stop the run immediately if:
- Customer signals stop via emergency contact.
- Error rate exceeds `25%` across any 10 consecutive requests.
- Staging endpoint returns `502/503/504` persistently or fails `/health`.
