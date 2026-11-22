# Useful inference capacity on a 12 GB GPU

This report accompanies the [executive case study](https://somsom786.github.io/inference-audit/labs-case-study.html) and extends the [full technical research record](INFERENCE_OPTIMIZATION_CASE_STUDY.md). Hardware, weights, benchmark definitions and negative results are traceable in the [claims ledger](../publication/CLAIMS_LEDGER.md) and [data projection](../../public/evidence/measurements.json).

## Capacity and time to useful work

The central comparison changes one launch setting, from two serving slots to four, with a 16,384-position f16 KV pool and the same Qwen3-8B Q4_K_M artifact on an RTX 4070. It changes the per-slot context allowance from 8,192 to 4,096. The comparison is valid for the common request window. Larger four-slot requests require a different memory configuration and separate qualification.

| Experiment | Scope | Baseline | Candidate | Interpretation |
| --- | --- | --- | --- | --- |
| Phase 2 | Homogeneous 48-offer chat bursts | 143.77 tok/s | 226.70 tok/s | +57.7% output throughput on that trace |
| Phase 4 | Mixed trace, 1.15 offers/s, 345 offers per launch | 315–317 correct on time | 284–293 correct on time | Four slots lost useful work under the measured deadline contract |
| Phase 4 | Same mixed trace and launches | 1.616–1.741 s p95 TTFT | 0.753 s p95 TTFT | First tokens arrived sooner |
| Phase 4 | Same mixed trace and launches | 3.714–3.820 s p95 completion | 4.523–4.678 s p95 completion | Completions took longer at the tail |

The burst result pools three control and two candidate launches. The mixed comparison uses two fresh launches per profile in A–B–B–A order at each offered-load window. Both profiles failed at least one workload-family requirement at each tested rate. Lower TTFT is valuable for interactive feedback, but the full answer still has to make its application deadline. No network-level customer performance or financial savings were measured.

## Limits and rejected levers

Native probes measured 431 GB/s of device-copy traffic (both directions counted) and 64.45 TFLOP/s of FP16 GEMM. At a modeled 4.6718 GB of scan bytes, 431/4.6718 gives a short-context decode reference of about 92.3 tok/s before KV reads, launch, sampling and kernel differences. The older test measured about 84.6 tok/s from its control at short context. Parallel decode shares weights across sequences, so the single-stream reference is not an aggregate serving cap. The supplied upstream calculator counts concurrency twice, a defect independently reproduced in the Phase 7 offline screen.

The initial Flash Attention gain used a disabled-feature baseline. The later phase verified that the ordinary engine configuration already enabled it. N-gram speculation accelerated an exact-copy fixture without comparable novel-prose improvement. The learned draft penalized novel decode and mixed TTFT despite accepting many proposals. GPU-resident sampling improved one screen by around 1.1%, below the minimum material effect. Cross-model transfer was workload- and engine-specific. Details and reproduction are in the [full research record](INFERENCE_OPTIMIZATION_CASE_STUDY.md).

## Phase 6 and Phase 7

A lab archive contains a completed six-hour Qwen3-8B run with 13,926 scheduled and completed transactions and 13,155 correct on time. Its older agent fixture missed the per-family objective in each stage, with 776 of 1,392 agent transactions correct. The completed run is separate from an earlier disk-budget abort and the Phase 3 Windows suspend. [Recount and source hashes](../../public/evidence/labs-endurance.json) · [Evidence scope](../publication/CLAIMS_LEDGER.md#p6-recount)

A later bounded V2 compatibility study used distinct hidden tool receipts and explicitly requested a tool-choice representation supported by the pinned llama.cpp Jinja backend. Equal scores and equal output token totals in each arm established a protocol fix on that endpoint without a speed or model-quality claim. The unpublished experimental source and underlying session captures are outside this site update.

Phase 7 then verified the installed Forge Qwen3.5-9B head and tested native MTP with the bundled CUDA backend in Ollama 0.40.16. One-token drafting improved median single-stream code decode by 6.9% and 7.0% in two fresh launch brackets, with near-full retrieval passing. Four-token drafting was slower, and the result did not generalize to novel prose. The [dedicated report](FORGE_MTP.md) shows the baseline, output checks, memory and limitations. No registry-qualified recipe resulted. Inkling 2 Mini, large Qwen variants and cross-engine quantizations remain separate feasibility questions.

## Reproduce and interpret

Open the [experiment evidence](https://somsom786.github.io/inference-audit/evidence.html), [historical results](https://somsom786.github.io/inference-audit/research.html) or [sample audit](https://somsom786.github.io/inference-audit/samples.html). Regenerate the Labs poster by running the [poster builder](../../scripts/publication/build_labs.py), which uses the public measurement projection. Financial results use hypothetical qualified throughput changes and depend separately on billing and worker granularity. See the [economics model](../../public/economics.html).
