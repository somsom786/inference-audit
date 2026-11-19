# Architecture

Inference Audit uses a single Python CLI and asynchronous HTTP runner. Configuration validation separates target policy, workload planning, resource admission and task gates from engine-specific fields.

| Module | Responsibility |
| --- | --- |
| `config`, `targets` | Scope validation, destination policy, lightweight capability probes and bounded OpenAI SSE parsing |
| `workload`, `runner` | Synthetic tasks, seeded scheduling, dependent steps, client admission pacing, cancellation and checkpoints |
| `telemetry` | Optional asynchronous NVIDIA board sampling |
| `evidence`, `legacy` | Bounded native files, SHA-256 checksums, semantic validation and independent historical schemas |
| `analysis`, `economics`, `reporting` | Offline metrics, evidence-based diagnostics, conditional estimates and shareable exports |
| `controlled` | Explicitly owned local llama.cpp ABBA brackets |

The runner depends on the small `Engine` and `Telemetry` interfaces. Standard inference uses HTTPX and typed configuration uses PyYAML. The pinned HTTP core supplies the TLS server-name override. Reports require no web connection, paid LLM or frontend runtime. A run is an ordinary directory with an append-only observation stream and atomic phase checkpoint. Resume writes a new directory and references its parent run.
