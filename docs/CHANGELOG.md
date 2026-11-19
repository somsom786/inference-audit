# Changelog

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
