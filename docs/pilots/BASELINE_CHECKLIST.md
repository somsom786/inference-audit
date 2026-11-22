# Staging Baseline Pre-Flight Checklist

Complete every item before running `inference-audit benchmark --approve-load` on an external staging endpoint.

---

## 1. Authorization & Access
- [ ] Written `STAGING_ASSESSMENT_SCOPE.md` signed/confirmed by customer technical owner.
- [ ] Staging origin is HTTPS (`https://...`), resolves to public IPs only (or explicitly approved private tunnel), and is **confirmed non-production**.
- [ ] Temporary scoped staging API token stored in environment variable only (`$env:STAGING_AUDIT_TOKEN`); never committed or pasted into YAML.
- [ ] If `vllm_metrics_approved: true`, customer confirmed `/metrics` is exposed on the **exact same origin** with identity encoding (uncompressed) and no proxy redirect.

## 2. Environment & Configuration Capture (Customer-Supplied)
- [ ] Exact serving engine name, version, and container image SHA-256 digest recorded.
- [ ] Exact model ID, quantization format, and revision/weights hash recorded.
- [ ] Full launch flags recorded (`--max-model-len`, `--max-num-seqs`, `--max-num-batched-tokens`, `--gpu-memory-utilization`, `--enable-prefix-caching`, `--enable-chunked-prefill`, `--kv-cache-dtype`, `--enforce-eager`, speculative flags, tool-call parser).
- [ ] Hardware recorded: GPU SKU, count, VRAM, TP/PP/EP/DP settings, replica count, and whether staging replica is isolated from other traffic.

## 3. Read-Only Endpoint Inspection
- [ ] Run `inference-audit inspect --url https://<staging-host> --credential-env STAGING_AUDIT_TOKEN`.
- [ ] Confirm `/v1/models` returns `200` and lists the exact approved model ID.
- [ ] Confirm `/health` returns `200`.
- [ ] Confirm `/metrics` was **not** probed during `inspect` (only enabled during `benchmark` if `vllm_metrics_approved: true`).

## 4. Benchmark Config & Safety Bounds
- [ ] `authorization.approved: true` set in run YAML only after written approval.
- [ ] `limits.max_requests`, `limits.runtime_s`, `limits.max_concurrency`, `limits.max_rps`, and `limits.timeout_s` are **less than or equal to** the signed scope limits.
- [ ] `seed` pinned for deterministic workload reproducibility.
- [ ] Per-family SLO thresholds (`chat`, `coding`, `rag`, `agent`) and `qualification` gates match the agreed discovery targets.
- [ ] Local disk has sufficient free space (> 50 MiB) for sealed evidence bundle.

## 5. Post-Run Verification
- [ ] Confirm benchmark exited cleanly (`checkpoint.json` state `complete`).
- [ ] Run `inference-audit verify --run <run-name>` and confirm SHA-256 `integrity.json` passes with zero errors.
- [ ] Run `inference-audit report --run <run-name>` and visually inspect `audit.html` and `audit.md` for privacy (zero raw labels, zero prompt text, zero credentials).
- [ ] Notify customer to revoke the temporary staging bearer token.
