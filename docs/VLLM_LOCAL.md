# Local and staging vLLM audit

Phase 9 adds an experimental source integration beyond the tagged 0.2.1 binary. It accepts standard chat completions. To collect vLLM server metrics, set `engine: vllm` and `server_observability: {vllm_metrics_approved: true}` after the owner explicitly approves scraping. Metrics use the target's existing pinned origin, credentials and no-redirect policy. The only scrape destination is `/metrics` on that origin. No series label values, response bodies or auth headers are retained. Stable derived label IDs preserve identity while avoiding raw labels. Values inferred from a guessable label may still be linkable, so review reports before sharing.

A successful scrape says which known names were observed. The collector recognizes the current KV gauge and a legacy GPU-cache alias, preserving wire names and types in evidence. Unknown values remain unavailable. Counter and histogram deltas require neighboring compatible samples within the same stage. Detected decreases and missing intervals are skipped. A reset whose counter climbs past the earlier value between scrapes cannot be detected from those samples. A percentile bucket interval represents server events for that series, including any unrelated traffic. No incompatible bucket schemas or model/replica series are combined.

Recreate normalized metrics and charts offline with the ordinary verify and report commands. Raw normalized observations are in server.jsonl with vLLM schema 1, scrape start/end timestamps and an outcome state. Coverage can be empty for a short stage or unavailable endpoint. A partial stage compares only its captured intervals. Prefix hit fractions require paired counters in the same label series. Queue and KV findings describe observations and suggest follow-up experiments. Attribution to a specific request, transport stall or hardware unit requires additional evidence.

## Isolated WSL environment

Requires an already configured WSL2 distribution, Python 3.12, uv and a Windows NVIDIA driver with working WSL CUDA support. Do not install a second driver in the guest. The local experiment installed vLLM 0.34.0, vllm-gguf-plugin 0.0.5 and Torch 2.14.0 CUDA 13.0. The plugin is explicitly experimental. [GPU installation](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/) · [GGUF support](https://docs.vllm.ai/en/latest/features/quantization/gguf/)

The [observed dependency lock](../configs/vllm-requirements.lock) records the isolated lab environment. In WSL, from the repository root:

```bash
uv venv --python 3.12 ~/.local/share/inference-audit-vllm/env
uv pip install --python ~/.local/share/inference-audit-vllm/env/bin/python vllm==0.34.0 vllm-gguf-plugin==0.0.5
uv pip freeze --python ~/.local/share/inference-audit-vllm/env/bin/python
bash scripts/vllm_local.sh metadata
bash scripts/vllm_local.sh compute
export INFERENCE_AUDIT_GGUF="$HOME/models/Qwen3-8B-Q4_K_M.gguf"
export INFERENCE_AUDIT_VLLM_CONTEXT=1280
bash scripts/vllm_local.sh serve --enforce-eager --no-enable-extensible-kv-cache
```

Set INFERENCE_AUDIT_GGUF to the actual existing artifact path, including the WSL mount path if the file is on Windows. The metadata command fetches only the exact tokenizer and config files from Qwen3-8B at b968826d9c46dd6066d109eabc6255188de91218. The server is offline for model resolution, starts on loopback, preserves the source GGUF and checks idle board headroom. Close other GPU work voluntarily first. Eager mode and static KV are narrow memory diagnostic settings. They are not a general production recommendation. The lab is not configured for unauthenticated external access.

In a separate shell, `bash scripts/vllm_local.sh health`, `models` or `metrics` targets only the local port. The OpenAI-style chat endpoint is `http://127.0.0.1:18091/v1/chat/completions` and the alias is `audit-qwen3-8b`. If Windows forwarding is unavailable, run the client inside WSL. After all authorized workload streams finish and the queue is empty, use Ctrl+C in the owning terminal. Destroying WSL as a whole would affect other processes. To remove this environment, shut down its owning process and remove only the isolated inference-audit-vllm environment directory. Keep the existing GGUF, user-wide caches and other engines.

## Run a bounded audit

Build from the source checkout containing this feature. The previous release wheel does not include it.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\inference-audit.exe inspect --url http://127.0.0.1:18091
.\.venv\Scripts\inference-audit.exe benchmark --config configs/vllm.local.yaml --run local-vllm --approve-load
.\.venv\Scripts\inference-audit.exe verify --run local-vllm
.\.venv\Scripts\inference-audit.exe report --run local-vllm
```

The audit report is in runs/local-vllm/report/audit.html. For an approved remote pilot, use HTTPS and the exact approved origin. Opt in only after the operator confirms the metrics scope. Before production use, validate context requirements, load admission and relevant tool/quality fixtures on a dedicated staging replica. The local smoke config includes deliberate workload diversity. A context or tool failure is evidence and stays in the denominator.

## Existing checkpoints

| Artifact | Relevant compatibility check | Phase 9 status |
| --- | --- | --- |
| Qwen3-8B Q4_K_M | 5,027,783,488-byte GGUF resolved as Qwen3ForCausalLM using the plugin and separate pinned tokenizer. Loaded on CUDA with FA2. | The constrained local baseline candidate. See the Phase 9 report for runtime outcomes. |
| Forge Qwen3.5-9B | 6,594,462,816-byte GGUF with Ollama legacy MTP tensor layout. The model family has vLLM entries, but that does not verify this export or its head in the plugin. | Unrun. Keep the established Ollama CUDA path. |
| Gemma 4 12B QAT | 6,975,877,728-byte text GGUF layer. The runtime registers Gemma4, including multimodal variants. The Ollama blob and projector semantics are a separate compatibility question. | Unrun. Keep the established local path. |
| Inkling-2-Mini UD-Q4_K_M | 16,610,543,328-byte Unsloth root GGUF needs hybrid placement even before KV. vLLM registers Inkling Transformers model classes. That is no evidence for this vendor GGUF, loop-aware placement, or its projector in the plugin. | Unrun. Preserve the qualified Unsloth llama.cpp launch. |
| Qwen3.8-27B and its derivatives | The 16,810,714,464-byte blob is larger than device VRAM. Host offload adds a separate compatibility and latency contract. | Unrun on vLLM. |
| EmbeddingGemma | Embedding model, outside the chat benchmark contract. | Out of scope. |
