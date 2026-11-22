# Staging Assessment Scope & Authorization Agreement

> **Engagement:** Free, Bounded Initial Inference Assessment (Read-Only Staging)  
> **Provider:** Inference Audit Labs (independent engineering practice)  
> **Purpose:** Establish written boundaries, safety caps, and clear commercial expectations before any request touches customer infrastructure.

---

## 1. What the Free Initial Assessment Includes
- One 20–30 minute discovery call and review of the completed `DISCOVERY_QUESTIONNAIRE.md`.
- One bounded, **read-only** baseline benchmark run against **one approved staging endpoint and one model** using synthetic, de-identified workloads (`inference-audit` open-source CLI).
- Optional scraping of `/metrics` on the exact same pinned HTTPS origin **only if explicitly approved below**.
- Cryptographically sealed evidence bundle (`integrity.json` SHA-256 manifest) verifiable offline by the customer.
- A concise written **Staging Assessment Report** covering measured latency, goodput, queue onset, bottleneck hypotheses (with explicit uncertainty), conditional financial modeling, and 1–3 prioritized controlled experiments.

## 2. What It Does NOT Include
- **No production traffic or production endpoints.**
- **No server access, SSH, Kubernetes credentials, or configuration edits.** All infrastructure remains 100% under customer control.
- **No unlimited free engineering or iterative tuning sprints.** Implementing and validating configuration changes is scoped separately as a paid optimization engagement only if clear upside exists.
- **No guaranteed speedup or guaranteed cost savings.** Outcomes depend on workload, hardware, and existing configuration.

## 3. Written Authorization & Hard Limits (Customer Completes)

| Field | Approved Value |
| :--- | :--- |
| **Customer / Organization** | `[Company Name]` |
| **Technical Approver (Name & Email)** | `[Name <email>]` |
| **Approved Staging Origin (HTTPS only)** | `https://[exact-staging-host]` |
| **Approved Model ID** | `[exact-model-id]` |
| **Authorized Window (UTC)** | `[YYYY-MM-DD HH:MM – HH:MM UTC]` |
| **Maximum Total Requests** | `[e.g., 240]` |
| **Maximum Concurrency / Workers** | `[e.g., 8]` |
| **Maximum Offered Rate (RPS)** | `[e.g., 4.0]` |
| **Maximum Total Runtime** | `[e.g., 480 s (8 minutes)]` |
| **Per-Request Timeout** | `[e.g., 30 s]` |
| **vLLM `/metrics` Scraping Approved?** | `[ ] Yes (same pinned HTTPS origin only)   [ ] No` |
| **Emergency Stop Contact** | `[Slack / Email / On-call contact]` |

## 4. Safety, Privacy & Data Retention
- **Read-only transport:** The audit client uses single-origin DNS pinning, HTTPS-only remote transport, `follow_redirects=False`, and `trust_env=False`.
- **No sensitive payloads:** Benchmarks use deterministic synthetic prompts. Raw response text, auth headers, and raw Prometheus label values are **never** written to evidence files (Prometheus label sets are hashed with SHA-256).
- **Credential handling:** Any staging bearer token is supplied via a temporary local environment variable (`credential_env`), never written to disk, logs, or reports, and revoked by the customer immediately after the window.
- **Retention & confidentiality:** Customer evidence and reports are kept strictly private and deleted within 30 days of delivery unless the customer requests retention for a follow-on engagement. Nothing is published without explicit written permission.

## 5. Rollback & Operational Responsibility
- Because the free assessment makes **zero changes** to customer infrastructure, rollback is simply terminating the client run (or revoking the staging bearer token).
- During any future paid optimization engagement, the customer retains sole authority to apply, canary, and roll back server configuration changes.

## 6. Commercial Next Steps
If the initial assessment identifies credible, measurable optimization headroom, Inference Audit Labs will submit a fixed-scope **Paid Optimization Proposal** (`OPTIMIZATION_PROPOSAL_TEMPLATE.md`) with pre-registered pass criteria, interleaved A/B validation, and a clear fee structure. There is zero obligation to proceed.

**Approved by (Customer):** `_______________________` · **Date:** `YYYY-MM-DD`  
**Acknowledged by (Inference Audit Labs):** `Rayn Hasan` · **Date:** `YYYY-MM-DD`
