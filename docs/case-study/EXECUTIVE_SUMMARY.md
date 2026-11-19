# More tokens, less useful work

On an RTX 4070, we tuned CUDA inference for Qwen3-8B, tested the serving changes across three models, and challenged those results with a fresh workload. The strongest result and the strongest limitation both came from changing how many requests the server could admit.

| Experiment | What changed | What the result supports |
| --- | --- | --- |
| Qwen homogeneous chat bursts | Two to four serving slots at fixed total f16 KV allocation | **143.77 → 226.70 output tok/s** with smaller per-request context and this particular repeated burst trace. [P2-CHAT](../publication/CLAIMS_LEDGER.md#p2-chat) |
| Qwen fresh mixed-workload replication | Same weights and total KV allocation, with fresh launches at **1.15 offered txn/s** | P95 TTFT **1.616–1.741 → 0.753 s**. Correct on-time goodput **1.050–1.057 → 0.947–0.977 txn/s**. Neither profile qualified under the strict family targets. [P4-TAIL](../publication/CLAIMS_LEDGER.md#p4-tail) · [P4-GOODPUT](../publication/CLAIMS_LEDGER.md#p4-goodput) |
| Transfer across models | Within-model two- and four-slot comparisons at separate high-load points | **+19.2% Qwen**, **+4.6% Forge**, **+9.5% Gemma** output throughput. Different loads, model formats and builds prevent a causal cross-model ranking. [P3-MODELS](../publication/CLAIMS_LEDGER.md#p3-models) |
| Extended Qwen replay | Matched load windows plus overload and recovery | **180 scheduled minutes in segments**. Windows sleep interrupted the original control, which was replaced and excluded from matched results. [P3-RUN](../publication/CLAIMS_LEDGER.md#p3-run) |

The original Flash Attention comparison explicitly disabled it in the control. Follow-up runs with automatic Flash Attention were already close to the tuned recipe. The product acceptance runs check the audit workflow and retain their own serving contract. None of the results establishes production capacity or verified fleet savings. [P2-DEFAULT](../publication/CLAIMS_LEDGER.md#p2-default) · [DEMO](../publication/CLAIMS_LEDGER.md#demo)

[Technical case study](INFERENCE_OPTIMIZATION_CASE_STUDY.md) · [Generated sample audit](../../public/reports/qwen3-8b-audit.html) · [Evidence and claims](../publication/CLAIMS_LEDGER.md)
