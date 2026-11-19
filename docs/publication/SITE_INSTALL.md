# Install and run a scoped audit

Inference Audit 0.2.1 is a Python CLI released under the [MIT license](../../LICENSE). [View source on GitHub](https://github.com/somsom786/inference-audit) · [Download the release assets](https://github.com/somsom786/inference-audit/releases/tag/v0.2.1)

From the repository root, use Python 3.11 or later. Set the model and traffic limits in `configs/local.yaml` to match an endpoint approved for the workload. This example enables the llama.cpp adapter.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\inference-audit.exe inspect --url http://127.0.0.1:8080
.\.venv\Scripts\inference-audit.exe benchmark --config configs/local.yaml --run first-local --approve-load
.\.venv\Scripts\inference-audit.exe verify --run first-local
.\.venv\Scripts\inference-audit.exe report --run first-local
```

On Linux use `.venv/bin/python` and `.venv/bin/inference-audit`. Review the approved rate, concurrency and runtime before starting. Inference requests can affect other users. Open `runs/first-local/report/audit.html` when the run finishes.

[Read the case study](../case-study/INFERENCE_OPTIMIZATION_CASE_STUDY.md) · [View the generated sample audit](../../public/reports/qwen3-8b-audit.html)

## Contact

Use [GitHub Issues](https://github.com/somsom786/inference-audit/issues) for technical questions and reproducibility reports.
