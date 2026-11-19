# Next task

Use the [pilot scope template](PILOT_RUNBOOK.md) to agree on one customer-controlled staging endpoint. Before a capacity sweep, perform an authorized compatibility smoke and have the operator demonstrate cancellation and offline reconstruction. Keep the read-only approval, model and traffic ceilings attached to the audit evidence.

For additional local verification, install the wheel from `dist/`, run `inference-audit --runs-dir .runs verify --run qwen-020-release`, and follow the recreation steps in [validation](VALIDATION.md). No benchmark requires resumption.
