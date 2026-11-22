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

Phase 7 then verified the installed Forge Qwen3.5-9B head and tested native MTP with the bundled CUDA backend in Ollama 0.40.16. One-token drafting improved median single-stream code decode by 6.9% and 7.0% in two fresh launch brackets, with near-full retrieval passing. Four-token drafting was slower, and the result did not generalize to novel prose. The [dedicated report](FORGE_MTP.md) shows the baseline, output checks, memory and limitations. No registry-qualified recipe resulted on that first screen. Large Qwen variants and cross-engine quantizations remain separate feasibility questions.

## Inkling-2-Mini: loop-aware placement on a 12 GB GPU

Inkling-2-Mini (Unsloth UD-Q4_K_M, 16.61 GB) does not fit in 12 GB of VRAM, so placement decides throughput. Twelve of its 24 physical blocks (`blk.6..17`) execute three times per token and carry 72.3% of active expert bytes in 6.88 GB, a 3.0× return per GiB of VRAM compared with the once-executed prelude and postlude. On the RTX 4070 with 64 GB DDR5 and llama.cpp b12588, loading 11 of the 12 core blocks on the GPU with no-mmap and a 512-token microbatch gave, in a qualified interleaved comparison:

| Metric | Auto-fit | `--cpu-moe` | Loop-aware winner | Gain |
| --- | ---: | ---: | ---: | --- |
| Decode tok/s | 25.14–25.15 | 16.45–16.50 | **34.34–34.66** | +36.5% to +37.8% vs auto-fit; +108.2% to +110.1% vs `--cpu-moe` |
| 8K prefill tok/s | 496.09–514.49 | 97.03–97.96 | **796.29–798.54** | +54.8% to +55.2% vs auto-fit; 8.1–8.2× vs `--cpu-moe` |
| Startup, s | 11.73–12.25 | 7.51–7.76 | **3.64–3.85** | −67% to −70% vs auto-fit |

The winner passed all six local-ai-registry gates and a six-request soak (33.62 tok/s in the 30-second uncapped test, 13,926-token needle at 85% of context). A twelve-block variant decoded at 37.00 tok/s but left only 954 MiB free on a desktop board and is recorded as the boundary, not the recommendation. The GGUF has no embedded DSpark tensors, so speculative drafting was deferred. Full method, screens and launch command: [Inkling report](INKLING_HYBRID.md). Claim: [`P8-INKLING`](../publication/CLAIMS_LEDGER.md#p8-inkling).

## Forge MTP, extended

A follow-up swept draft lengths 1 to 3 with a 4,098-token code prompt, a four-task functional panel and a two-slot bracket. One draft token remained best: structured Python +23.5% (89.91 against 65.21–72.80 tok/s) and 4K-context code +16.5% (78.59 against 63.47–67.47 tok/s), with 19 of 19 byte-identical outputs and the same 2 of 4 executable tests as the default. Two and three draft tokens regressed on short code and prose. At concurrency 2 the one-token arm did not beat the faster default (115.87 against 111.14–121.88 pooled code tok/s) and added 522 MiB of peak VRAM. See [Forge MTP](FORGE_MTP.md#extended-qualification-k--13-4k-context-functional-code-concurrency-2) and [`P8-FORGE-EXT`](../publication/CLAIMS_LEDGER.md#p8-forge-ext).

## Independent external research context (Sybil Solutions)

> **Non-affiliation and scope.** The results in this section were published independently by Sybil Solutions / 0xSero in open-source repositories. Sybil Solutions is **not** a customer of Inference Audit Labs, is **not** affiliated with it, and this section is **not** an endorsement of either party. Inference Audit Labs has **not** reproduced any of these external hardware benchmarks. We cite them as verified published literature, checked against the linked sources, to show what systematic inference engineering has achieved on other GPUs and architectures. Hardware, models, engines and methods differ from ours, so they are not comparable with the RTX 4070 results above.

| Hardware | Model and engine | Published result | Source |
| --- | --- | --- | --- |
| Intel Arc B390 iGPU (64 GB unified) | Ornith-1.5-35B-A3B, EXL3 4 bpw, SGLang XPU with MTP | 256K prefill 297 → 628 tok/s (2.1×); startup 113 → 43 s (−62%); 1-user decode 43.6 → 53 tok/s | [local-ai-registry PR 453](https://github.com/sybil-solutions/local-ai-registry/pull/453) |
| Intel Arc Pro B70 (32 GB) | Qwen3.8-27B, EXL3 4 bpw, vLLM with custom XPU kernels | 91.2 tok/s 1-user decode (cross-stack versus 25.0 tok/s llama.cpp Q4_K_M on the same card); 16-user aggregate 365 tok/s | [trellis-serve XPU README](https://github.com/sybil-solutions/trellis-serve/blob/main/xpu/README.md) |
| NVIDIA RTX 3090 (24 GB) | Flash-Next EXL3, 256K context | Single-stream decode with MTP 45.5 → 65.6 tok/s (+44.2%) | [trellis-serve CUDA README](https://github.com/sybil-solutions/trellis-serve/blob/main/cuda/README.md) |
| 4× NVIDIA H200 NVL | DeepSeek-V4.1-Flash, vLLM with speculative decoding | Crashed under load → 229.1 tok/s decode, 17,546 tok/s prefill, all 6 registry gates | [inference-optimisation-skill README at `fda968e`](https://github.com/sybil-solutions/inference-optimisation-skill/blob/fda968e7fc1996aa23c67139c755fe541c9d4be0/README.md) |

Upstream methodological note: the repository head verified for this section is `fda968e7fc1996aa23c67139c755fe541c9d4be0` (2026-11-16). Upstream pull request 3 (fix double-counted concurrency in the decode ceiling) has an independent verification comment from a third party with four regression cases, and is still **open** and not merged. Claim record: [`EXTERNAL-SYBIL`](../publication/CLAIMS_LEDGER.md#external-sybil).

## Reproduce and interpret

Open the [experiment evidence](https://somsom786.github.io/inference-audit/evidence.html), [historical results](https://somsom786.github.io/inference-audit/research.html) or [sample audit](https://somsom786.github.io/inference-audit/samples.html). Regenerate the Labs poster by running the [poster builder](../../scripts/publication/build_labs.py), which uses the public measurement projection. Financial results use hypothetical qualified throughput changes and depend separately on billing and worker granularity. See the [economics model](../../public/economics.html).
