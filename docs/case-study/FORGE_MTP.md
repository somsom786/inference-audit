# Native MTP on Forge Qwen3.5-9B

On one RTX 4070, a single speculative draft token improved median single-stream code decode by **6.9% and 7.0%** against the faster neighboring default in two fresh-launch brackets. The same change left median novel-prose decode roughly flat. A four-token draft regressed both panels. The result is specific to Forge, its native head, the bundled CUDA runner and these prompts.

## Protocol

Tested the preinstalled Forge Qwen3.5-9B Q4_K_M blob SHA-256 dec52a44569a2a25341c4e4d3fee25846eed4f6f0b936278e3a3c900bb99d37c, NVIDIA RTX 4070 12 GB, driver 621.24 and Ollama 0.40.16 with its bundled llama.cpp CUDA runner. The artifact has 15 legacy mtp.* tensors. The runner recognized the layout and reported native draft acceptance. Each arm started an owned instance and drained at shutdown. The default omitted draft_num_predict. Set it to 4 or 1 only in the candidate. Retained automatic Flash Attention, single-stream context 8,192, temperature 0 and identical seeds, prompts and output caps. Full layer offload and GPU residency were checked on startup.

Each cell is the server-reported median for eight novel prompts with 128 emitted tokens each. Client-visible timings corroborated the direction of the code gain. Fixed output length bounds the speed screen. It does not establish successful code-task completion or a registry speed gate. The [projection](../../public/evidence/forge-mtp.json) includes individual launch medians, capture hashes and exact-match counts.

| Bracket | Draft length | Code tok/s, default → draft → default | Prose tok/s, same order |
| --- | ---: | --- | --- |
| Initial | 4 | 71.66 → 55.91 → 71.55 | 71.77 → 50.94 → 71.79 |
| Short draft | 1 | 71.52 → 76.51 → 71.59 | 71.74 → 71.73 → 71.87 |
| Fresh context check | 1 | 71.57 → 76.60 → 71.56 | 71.80 → 71.62 → 71.82 |

## Why length mattered

Four-token MTP accepted 666 of 5,539 proposals and spent about 10.0 ms per draft round, including warmup. With one-token MTP, the final bracket accepted 559 of 1,543 proposals and spent about 2.6 ms per draft round. These cumulative runner statistics are explanatory evidence averaged across the whole launch. The shorter drafts cut proposal cost and kept the best downstream throughput on code. The result does not isolate target verification kernel time.

## Qualification and limits

In each one-token bracket, the eight visible code answers matched both neighboring controls byte for byte. In the fresh context check the candidate found both near-full-context receipts at 7,795 and 7,812 prompt tokens, plus the 4,090-token probe. The prose median decode rate remained within 0.3% of the repeated controls in that bracket. Four-token MTP matched only three of eight code answers per control and failed the performance criterion. Output equality is a replay check on capped responses, without functional evaluation of generated code.

The fresh candidate’s code median end-to-end time was **1.748 s**, versus **1.858–1.865 s** on controls. Code TTFT was **76.3 ms**, between **68.5 ms and 78.3 ms**. Peak board allocation was **8,935 MiB**, versus **8,475–8,499 MiB**. No production rollout, multiple serving slots or all-family deadline qualification was tested. The nine owned launches ran for about 6.7 minutes of board telemetry in total. The measurement is a focused workload-specific optimization, not a whole-service recommendation, a verified saving or a registry-qualified recipe.

## Reproduce

With the pinned local Forge tag, Ollama 0.40.16, a quiet compatible board and one isolated runner, use the native chat API with think false and options num_ctx 8192, num_predict 128 and temperature 0. Compare the normal default with options draft_num_predict 1 while keeping all other inputs fixed. Repeat the default on a fresh process. Capture final eval_count and eval_duration, client first-visible TTFT, completion time, exact replay, board telemetry and deep-context receipts. The bundled llama-server executable had SHA-256 740af7a7897cc7848cc9d8ee58e91889c10341f364c437f9b62bf4e254b4e7ac. The [benchmark projection](../../public/evidence/forge-mtp.json) pins and identifies the [screening](../../public/evidence/forge-screen-fixtures.json) and [context-check](../../public/evidence/forge-qual-fixtures.json) manifests. [Ollama option resolution](https://github.com/ollama/ollama/blob/v0.40.16/server/routes.go) · [Ollama native draft wiring](https://github.com/ollama/ollama/blob/v0.40.16/llm/llama_server.go)
