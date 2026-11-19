# Inference Audit

**Reproducible performance audits for self-hosted LLM inference.**

Run bounded synthetic workloads against an authorized OpenAI-compatible endpoint. Measure latency, throughput, scoped correctness and correct on-time goodput. Rebuild a shareable audit from the saved measurements.

[Project site](https://somsom786.github.io/inference-audit/) · [Technical case study](docs/case-study/INFERENCE_OPTIMIZATION_CASE_STUDY.md) · [Measured Qwen audit](https://somsom786.github.io/inference-audit/reports/qwen3-8b-audit.html) · [Claims ledger](docs/publication/CLAIMS_LEDGER.md)

## Why it exists

Serving more tokens can leave fewer requests correct and on time. On one RTX 4070, admitting more sequences improved homogeneous chat throughput. A fresh mixed workload exposed slower completions and lower correct on-time goodput. Benchmark a traffic mix and context budget together, then use the per-family results to decide what to deploy. [Research summary](docs/case-study/EXECUTIVE_SUMMARY.md)

## Quick start

Use Python 3.11 or later and an endpoint you operate or are authorized to test. Edit [`configs/local.yaml`](configs/local.yaml) to match the model ID and approved traffic limits. This example selects the llama.cpp adapter and optional NVIDIA telemetry.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\inference-audit.exe inspect --url http://127.0.0.1:8080
.\.venv\Scripts\inference-audit.exe benchmark --config configs/local.yaml --run first-local --approve-load
.\.venv\Scripts\inference-audit.exe verify --run first-local
.\.venv\Scripts\inference-audit.exe report --run first-local
```

On Linux use `.venv/bin/python` and `.venv/bin/inference-audit`. Use the [staging example](configs/staging.example.yaml) for a generic approved target. Benchmark traffic consumes real inference capacity.

Open `runs/first-local/report/audit.html`. Share the report directory for ordinary review. To regenerate it offline, run `report --run first-local --output another-report` with a fresh destination. To export the exact synthetic fixtures and observations, use `export --run first-local --output shared-evidence --include-synthetic-manifest`.

## What the audit measures

| Measure | How to interpret it |
| --- | --- |
| First-token and completion latency | Client-observed response timing. Admission delay is reported only when observable. |
| Output throughput | Server-reported usage, checked against engine counters where available. Missing usage prevents an output rate. |
| Correct on-time goodput | Scoped-correct, on-time transactions per second, with failed and rejected work retained in offered counts. |
| Capacity under load | Highest passing tested point under the declared workload-specific gates, when there is one. |
| NVIDIA telemetry | Board-level measurements of utilization, memory, clocks, temperature and power when accessible. |

`inspect` probes fixed discovery routes. Streaming and usage stay unverified until approved inference runs. `status` reads a checkpoint. Resume with the same config and tool version, a fresh run ID and `--resume-from OLD_ID`. Complete stages are skipped and the partial attempt stays separate. `import` reads supported historical summary revisions. [Methodology](docs/METHODOLOGY.md)

## Sample audit

The [Qwen load-sweep report](https://somsom786.github.io/inference-audit/reports/qwen3-8b-audit.html) and [Gemma compatibility report](https://somsom786.github.io/inference-audit/reports/gemma4-12b-audit.html) are generated from measured RTX 4070 captures with synthetic workloads. Copies in `public/reports/` open offline. The [sample export notes](public/reports/README.md) describe how the public files were derived from the original sealed observations.

## Operating scope

**0.2.1** is intended for scoped, customer-approved staging audits. This mode leaves server configuration unchanged and requires explicit load approval. Local CUDA acceptance covers pinned llama.cpp on Windows. The CPU-only suite was also exercised on WSL in 0.2.0. Native Linux CUDA, arbitrary adapter behavior and external production infrastructure remain unverified. The fixed local `experiment` mode requires separate process authorization. Native CUDA shutdown after the 0.2.1 changes remains unverified.

[Security model](docs/SECURITY.md) · [Pilot runbook](docs/PILOT_RUNBOOK.md) · [Validation](docs/VALIDATION.md) · [Known limitations](docs/KNOWN_ISSUES.md)

## Contributing and license

See [development](docs/DEVELOPMENT.md), [architecture](docs/ARCHITECTURE.md) and the [changelog](docs/CHANGELOG.md). The source is available under the [MIT license](LICENSE). Use [GitHub Issues](https://github.com/somsom786/inference-audit/issues) for defects and reproducibility questions.
