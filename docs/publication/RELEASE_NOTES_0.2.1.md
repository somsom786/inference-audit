# Inference Audit 0.2.1

Inference Audit runs bounded synthetic workloads against authorized OpenAI-compatible endpoints and replays the results offline. This package combines the validated 0.2.1 wheel with a public case study, source snapshot, local demonstration audits and a static project site.

[Project site](https://somsom786.github.io/inference-audit/) · [Technical case study](https://somsom786.github.io/inference-audit/case-study.html) · [Measured Qwen audit](https://somsom786.github.io/inference-audit/reports/qwen3-8b-audit.html)

The patch checks expected dependent steps against their planned task contracts, including tool round trips and warm-cache probes. Experimental owned-server shutdown stops admission and requires observable drain before a bounded graceful stop. Busy or unverifiable shutdowns require operator intervention. Native CUDA shutdown remains unverified. Keep the experimental mode disabled for the read-only staging workflow.

The case study compares a homogeneous chat gain with a fresh workload where four slots reduced first-token latency and lowered correct on-time goodput. The long run is a segmented replay after Windows suspend. The three model studies have separate load and context assumptions. No fleet saving or production capacity is claimed.

The stage includes the original pure-Python wheel, SHA-256 checksums, a curated source ZIP and a self-contained site ZIP. The website and reports require no external services. Source and publication docs are MIT licensed. Models and CUDA runtimes are distributed separately.

Install locally from the unpacked release folder:

```powershell
python -m pip install inference_audit-0.2.1-py3-none-any.whl
inference-audit --version
```

Use the README in the source ZIP to run your first approved local audit. Open `index.html` in the site ZIP to preview the public material.
