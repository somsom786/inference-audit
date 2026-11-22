# Customer Discovery Questionnaire — Inference Audit Labs

> **Use:** Send before or fill out during a 20–30 minute discovery call.  
> **Privacy rule:** Do not include API keys, production customer prompts, PII, or internal hostnames. Summaries and ranges are sufficient.

---

## 1. Workload & Business Objectives
1. **Primary task families:** (e.g., interactive chat, long-context RAG, code generation, multi-step tool/agent workflows, batch processing)
2. **Quality & correctness contract:** What makes a response acceptable? (exact JSON/tool-call schema, citation faithfulness, max truncation rate, thinking/reasoning toggle)
3. **Service-level objectives (SLOs) per family:**
   - Target p95 TTFT (time to first visible token): `____ s`
   - Target p95 ITL / TPOT (inter-token latency): `____ ms`
   - Target p95 end-to-end completion: `____ s`
   - Minimum correct & on-time pass share: `____ %` (default gate: `95%`)
   - Maximum error share: `____ %` (default gate: `5%`)
4. **Traffic shape:**
   - Typical & p95 prompt length (tokens): `____ / ____`
   - Typical & p95 output length (tokens): `____ / ____`
   - Peak concurrent users / requests per second: `____`
   - Shared prefix reuse (system prompts, tool schemas, document chunks): `High / Medium / Low / Unknown`

## 2. Model & Serving Stack
5. **Model(s) in scope:** Exact model name, parameter count, quantization (FP16/BF16, FP8, AWQ/GPTQ, GGUF), and revision/digest.
6. **Serving engine & version:** (`vLLM`, `SGLang`, `llama.cpp`, `TensorRT-LLM`, `TGI`, `Ollama`, or custom) + container image tag/digest.
7. **Key serving flags currently active:** `--max-model-len`, `--max-num-seqs`, `--max-num-batched-tokens`, `--gpu-memory-utilization`, `--enable-prefix-caching`, `--enable-chunked-prefill`, `--kv-cache-dtype`, `--enforce-eager`, speculative decoding flags, tool-call parser.

## 3. Hardware & Topology
8. **GPU hardware:** GPU SKU (e.g., L40S, A100, H100, H200, B200, RTX 4090/PRO 6000), VRAM per GPU, GPUs per replica, interconnect (PCIe vs NVLink/NVSwitch).
9. **Parallelism & routing:** TP / PP / EP / DP degrees, number of replicas, load balancer routing policy (round-robin, least-outstanding, prefix-aware), autoscaling policy.
10. **Host environment:** Dedicated bare metal, VM, or Kubernetes; CPU cores/RAM; any host offloading or shared noisy neighbors.

## 4. Staging Access & Observability
11. **Staging endpoint availability:** Can we test against a dedicated **staging** OpenAI-compatible HTTPS endpoint (never production)?
12. **Authorized `/metrics` scope:** If running vLLM, can staging expose `/metrics` on the same pinned HTTPS origin (explicitly approved in writing)?
13. **Traffic & runtime caps:** What maximum request count, RPS, concurrency, and test window (UTC) are approved?

## 5. Economics & Commercial Context
14. **Billing model:** Per-GPU-hour on-demand, reserved cluster, owned hardware, or hybrid?
15. **Reducible vs fixed costs:** If qualified capacity improves by 20–40%, would that reduce billable GPU-hours, defer hardware purchases, or unlock higher tenant density?
16. **Mandatory headroom:** Required N+1 redundancy, failover reserve, or canary capacity.
