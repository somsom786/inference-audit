# Changelog

## Unreleased

- Add opt-in, same-origin vLLM metrics for approved benchmarks. Reports show bounded stage observations, separate label series, and histogram bucket intervals. The 0.2.1 release asset is unchanged.

## Unreleased (experimental on main)

- **Phase 9.1 — Audit hardening, 8-field diagnostics & customer pilot kit:**
  - Hardened `vllm_metrics.py`: guarded missing/invalid histogram `le` labels without dropping sibling metrics, accepted empty/whitespace `Content-Encoding: identity` headers, enforced `MAX_RECORD` byte cap in `validate_snapshots()`, prevented lone trailing histogram schema changes from discarding prior stage observations, added `p50_bucket` alongside `p95_bucket`, and added `matched_intervals` / `skipped_intervals` tracking to `prefix_reuse()`.
  - Upgraded `vllm_metrics.findings()` with a structured 8-field customer diagnostic contract covering observability gaps, queue saturation, KV pressure with/without preemptions, low prefix-cache reuse, prefill/decode interference, low-GPU-utilization queueing, and quality/error goodput separation.
  - Updated `reporting.py` to display `p50_bucket`, series-truncation warnings, and prefix matched/skipped interval counts.
  - Added complete operational customer pilot kit under `docs/pilots/` (discovery questionnaire, staging scope agreement, pre-flight checklist, test plan template, report template, optimization proposal template, handoff checklist, and clearly labeled sample demonstration report).
  - Substantially expanded `docs/VLLM_INTERNALS_GUIDE.md` and `docs/VLLM_OPTIMIZATION_PLAYBOOK.md`.
- **Phase 9 — Opt-in vLLM observability:** Added allowlisted `/metrics` scraping on pinned origin, SHA-256 label-set hashing, sealed `server.jsonl` verification, local WSL vLLM setup, and RTX 4070 Qwen3-8B evidence.

## 0.2.1

- Reject resealed observations with missing or extra dependent steps, contradictory transport outcomes, invalid finishes, or inconsistent cache claims. Agent tool round trips and warm-cache receipt probes are covered.
- Drain owned llama.cpp servers on a bounded schedule before sending a graceful signal. Preserve shutdown evidence and require operator intervention on uncertain or unsafe outcomes.
- Document that stored observations and local digests support consistency checks and offline recalculation. Answer correctness is a recorded observation when response content was not retained.

## 0.2.0

- Separate transport, token accounting, cache qualification and answer correctness.
- Add phase timestamps, bounded response/evidence storage, configurable waiting queue, strict per-family acceptance and context gating.
- Pin approved HTTPS targets to a validated public address while retaining TLS identity. Harden filesystem, report and import boundaries.
- Add semantic evidence verification, stage-boundary resume checkpoints, offline status and an explicit synthetic evidence export.
- Report measured arrival coverage, dispatch, observed overlap, usage coverage, board sampling and conditional cost assumptions. Preserve Phase 1–4 provenance.
- Require matched ABBA workload signatures and per-family p95 guards in experimental owned mode.
- Add deterministic adverse wire scenarios, evidence tests, independent Windows and WSL checks, and a customer-controlled staging runbook.

## 0.1.0

Initial local CLI, synthetic workloads, GPU sampling, historical imports, evidence verification and reports.
