# Inference Audit Labs

**vLLM staging audits (experimental on main).** The existing OpenAI-compatible benchmark can capture approved, same-origin vLLM metrics with phase-aligned queue, KV, preemption, prefix and latency evidence. [Local setup and configuration](docs/VLLM_LOCAL.md) · [Staging playbook](docs/VLLM_OPTIMIZATION_PLAYBOOK.md) · [Internals guide](docs/VLLM_INTERNALS_GUIDE.md) ? [RTX 4070 lab results](docs/case-study/VLLM_PHASE9.md) ? [Generated sample audit](https://somsom786.github.io/inference-audit/reports/vllm-qwen3-8b-audit.html)

**More inference. Same GPU budget.**

Inference Audit is a local-first CLI and research practice for self-hosted inference. It sends bounded, synthetic traffic to an authorized OpenAI-compatible endpoint, measures speed, correctness and deadline-qualified capacity, and rebuilds a shareable HTML report offline from the saved observations. We then qualify configuration changes against your workload before any claim is made.

**Why it matters financially.** Qualified throughput is the only throughput that reduces cost. As an illustrative conditional scenario, a **+30%** qualified throughput gain means **23.1% fewer GPU-hours** for the same demand (up to $138,462 a year on a $50K/month fleet). The scenario is arithmetic, not a measured saving: it holds only if the gain is qualified on your workload. [Economics model](https://somsom786.github.io/inference-audit/economics.html)

**Strongest new verified result.** Inkling-2-Mini (16.61 GB) on one RTX 4070 12 GB with loop-aware tensor placement: **+37.8% decode, +55.2% 8K prefill and −67% to −70% startup versus the safe auto-fit placement**, and **+110% decode and 8.1–8.2× prefill versus `--cpu-moe`**. It passed **6 of 6** local acceptance checks (not an officially accepted `local-ai-registry` recipe; vision, broader quality, production concurrency and customer infrastructure remain unverified). One machine, one stream, 16K context. [Technical report](docs/case-study/INKLING_HYBRID.md) · [Claim `P8-INKLING`](docs/publication/CLAIMS_LEDGER.md#p8-inkling)

[![Inkling-2-Mini on an RTX 4070: +37.8% decode, +55.2% 8K prefill, -67% to -70% startup versus auto-fit](public/assets/inkling-hybrid-social.png)](docs/case-study/INKLING_HYBRID.md)

[Labs website](https://somsom786.github.io/inference-audit/) · [Case study](https://somsom786.github.io/inference-audit/labs-case-study.html) · [Interactive measurements](https://somsom786.github.io/inference-audit/case-study.html) · [Sample audits](https://somsom786.github.io/inference-audit/samples.html) · [Public preview v0.2.1](https://github.com/somsom786/inference-audit/releases/tag/v0.2.1)

## Verified results from Inference Audit Labs

Every row below was measured by us. Click through to the evidence. Gains are workload-, hardware- and engine-specific.

| Hardware | Model | Engine | Before | After | Gain | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| RTX 4070 12 GB + 64 GB DDR5 | Inkling-2-Mini UD-Q4_K_M | llama.cpp b12588, loop-aware placement | auto-fit decode 25.14–25.15 tok/s | 34.34–34.66 tok/s | **+36.5% to +37.8%** (+108.2% to +110.1% vs `--cpu-moe`) | [Report](docs/case-study/INKLING_HYBRID.md) · [`P8-INKLING`](docs/publication/CLAIMS_LEDGER.md#p8-inkling) |
| RTX 4070 12 GB + 64 GB DDR5 | Inkling-2-Mini UD-Q4_K_M | llama.cpp b12588, loop-aware placement | auto-fit 8K prefill 496.09–514.49 tok/s; startup 11.73–12.25 s | 796.29–798.54 tok/s; startup 3.64–3.85 s | **+54.8% to +55.2% prefill; −67% to −70% startup** (8.1–8.2× prefill vs `--cpu-moe`) | [Evidence JSON](public/evidence/inkling-hybrid.json) |
| RTX 4070 12 GB | Forge Qwen3.5-9B Q4_K_M | Ollama 0.40.16 llama.cpp CUDA, native MTP k=1 | code decode 71.56–71.57 tok/s | 76.60 tok/s | **+7.0%** (repeat bracket) | [Report](docs/case-study/FORGE_MTP.md) · [`P7-FORGE-MTP`](docs/publication/CLAIMS_LEDGER.md#p7-forge-mtp) |
| RTX 4070 12 GB | Forge Qwen3.5-9B Q4_K_M | Ollama 0.40.16, MTP k=1, extended panels | structured Python 65.21–72.80 tok/s; 4K-context code 63.47–67.47 tok/s | 89.91 tok/s; 78.59 tok/s | **+23.5%; +16.5%** (19/19 identical outputs; k=2,3 regress; concurrency 2 no gain, +522 MiB) | [Extended qualification](docs/case-study/FORGE_MTP.md#extended-qualification-k--13-4k-context-functional-code-concurrency-2) · [`P8-FORGE-EXT`](docs/publication/CLAIMS_LEDGER.md#p8-forge-ext) |
| RTX 4070 12 GB | Qwen3-8B Q4_K_M | llama.cpp CUDA b12427, 2 → 4 slots | chat burst 143.77 tok/s | 226.70 tok/s | **+57.7%** (homogeneous chat burst) | [`P2-CHAT`](docs/publication/CLAIMS_LEDGER.md#p2-chat) |
| RTX 4070 12 GB | Qwen3-8B Q4_K_M | llama.cpp CUDA b12427, 2 → 4 slots | mixed trace 315–317 correct on time per 345 offers | 284–293 | **Negative result: useful work fell** | [`P4-GOODPUT`](docs/publication/CLAIMS_LEDGER.md#p4-goodput) |
| RTX 4070 12 GB | Qwen3-8B, Forge Qwen3.5-9B, Gemma 4 12B | llama.cpp CUDA, 2 → 4 slots | 114.35, 95.37, 71.33 tok/s | 136.32, 99.72, 78.07 tok/s | **+19.2%, +4.6%, +9.5%** (Forge and Gemma missed the 95% deadline target) | [`P3-MODELS`](docs/publication/CLAIMS_LEDGER.md#p3-models) |

For deadline-bound work, the mixed-trace row matters more than the burst row. Neither slot profile met the 95% target in every family.

## Published results from the wider inference optimization ecosystem

> **Independent third-party work. Not ours.** These results were published by **Sybil Solutions / 0xSero** in open-source repositories. Sybil Solutions is **not** a customer of, **not** affiliated with, and **not** endorsing Inference Audit Labs. We have **not reproduced** any of these hardware results. They are cited as verified published literature on what systematic inference engineering has achieved elsewhere. The hardware, models and engines differ from ours, so they are not comparable with the table above.

| Hardware | Model and engine | Published result | Source |
| --- | --- | --- | --- |
| Intel Arc B390 iGPU (64 GB unified) | Ornith-1.5-35B-A3B EXL3 4 bpw, SGLang XPU with MTP | 256K prefill 297 → 628 tok/s (2.1×); startup 113 → 43 s (−62%); 1-user decode 43.6 → 53 tok/s | [local-ai-registry PR 453](https://github.com/sybil-solutions/local-ai-registry/pull/453) |
| Intel Arc Pro B70 (32 GB) | Qwen3.8-27B EXL3 4 bpw, vLLM with custom XPU kernels | 91.2 tok/s 1-user decode (cross-stack; 25.0 tok/s llama.cpp Q4_K_M on the same card); 365 tok/s 16-user aggregate | [trellis-serve XPU README](https://github.com/sybil-solutions/trellis-serve/blob/main/xpu/README.md) |
| NVIDIA RTX 3090 (24 GB) | Flash-Next EXL3, 256K context, native MTP | Decode 45.5 → 65.6 tok/s (+44.2%) | [trellis-serve CUDA README](https://github.com/sybil-solutions/trellis-serve/blob/main/cuda/README.md) |
| 4× NVIDIA H200 NVL | DeepSeek-V4.1-Flash, vLLM with speculative decoding | Crashed under load → 229.1 tok/s decode, 17,546 tok/s prefill, 6/6 registry gates | [inference-optimisation-skill README](https://github.com/sybil-solutions/inference-optimisation-skill/blob/fda968e7fc1996aa23c67139c755fe541c9d4be0/README.md) |

Verified against upstream commit `fda968e7fc1996aa23c67139c755fe541c9d4be0`. An upstream fix for a concurrency double-count in the decode ceiling (pull request 3) is open and not merged. [Record in the claims ledger](docs/publication/CLAIMS_LEDGER.md#external-sybil) · [Technical report section](docs/case-study/LABS_TECHNICAL_REPORT.md#independent-external-research-context-sybil-solutions)

## Technical reports

[Inkling-2-Mini hybrid placement](docs/case-study/INKLING_HYBRID.md) · [Forge MTP](docs/case-study/FORGE_MTP.md) · [Qwen and Gemma technical report](docs/case-study/LABS_TECHNICAL_REPORT.md) · [Full research record](docs/case-study/INFERENCE_OPTIMIZATION_CASE_STUDY.md) · [Claims ledger](docs/publication/CLAIMS_LEDGER.md) · [Security model](docs/SECURITY.md)
## Quick start

Use Python 3.14 on Windows for the verified pilot setup. From a checkout of the public release, set the model ID and approved workload limits in [`configs/local.yaml`](configs/local.yaml). Benchmark traffic consumes real inference capacity.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\inference-audit.exe inspect --url http://127.0.0.1:8080
.\.venv\Scripts\inference-audit.exe benchmark --config configs/local.yaml --run first-local --approve-load
.\.venv\Scripts\inference-audit.exe verify --run first-local
.\.venv\Scripts\inference-audit.exe report --run first-local
```

Open `runs/first-local/report/audit.html`. On Linux, the corresponding executables are `.venv/bin/python` and `.venv/bin/inference-audit`. The [staging config](configs/staging.example.yaml) covers a generic approved target. A hosted Windows Python 3.12 run exposed an open-loop timing issue in v0.2.1. Run a bounded smoke test and verify captures before collecting pilot evidence. [Known issues](docs/KNOWN_ISSUES.md)

## Read an audit

- **Speed.** First-token and completion latency, plus output rate from available usage data.
- **Useful capacity.** Correct on-time transactions per second, with late, rejected and failed work kept in the offered population. Capacity is the highest passing point on the tested workload grid.
- **Evidence.** Saved observations, offline verification and report regeneration. With optional NVIDIA telemetry, the audit shows board-level memory, utilization, temperature, clocks and power.

The [Qwen load sweep](https://somsom786.github.io/inference-audit/reports/qwen3-8b-audit.html) and [Gemma compatibility audit](https://somsom786.github.io/inference-audit/reports/gemma4-12b-audit.html) are generated from real local captures. Copies in [`public/reports/`](public/reports/README.md) open offline. Read the [technical case study](docs/case-study/INFERENCE_OPTIMIZATION_CASE_STUDY.md) for the methods and the results that failed to transfer.

## Commercial staging pilots

Discuss an authorized endpoint, a representative workload, and the service target you need to check. [Contact on LinkedIn](https://www.linkedin.com/in/rayn-hasan/)

## Operating scope

The public preview targets scoped, customer-approved staging audits. It requires explicit load approval and leaves the serving configuration unchanged. Local CUDA acceptance covers pinned llama.cpp on Windows. Native Linux CUDA and customer production infrastructure remain unverified. The separate owned-process experiment mode is outside the public pilot scope. Evidence verification validates saved observations and calculations. It cannot re-grade answers that were withheld.

[Claims ledger](docs/publication/CLAIMS_LEDGER.md) · [Methodology](docs/METHODOLOGY.md) · [Security model](docs/SECURITY.md) · [Pilot runbook](docs/PILOT_RUNBOOK.md) · [Validation](docs/VALIDATION.md) · [Development](docs/DEVELOPMENT.md) · [MIT license](LICENSE) · [Issues](https://github.com/somsom786/inference-audit/issues)
