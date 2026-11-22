# Enterprise vLLM optimization playbook

The free initial assessment is a short discovery call followed by a written experiment outline. Request architecture, workload and billing summaries with sensitive values removed. A deeper pilot needs approval for the exact staging endpoint, test window, offered load and resource ceiling. No production changes or unrestricted network access are needed.

## Discovery call

1. Which task families matter and what constitutes a correct answer, safe tool call and complete response?
2. What are the TTFT, inter-token or completion deadlines by family? Which minimum pass rates and contexts must hold at peak demand?
3. What is the distribution of prompt length, output length, concurrent users, burst duration and prefix reuse?
4. Which model revision, quantization, template, speculative model and serving image are deployed?
5. Which GPUs, VRAM, link topology, host RAM and offload settings are in use? Are accelerator resources dedicated?
6. Are routes replicated or autoscaled? Where are queues, quotas and request cancellations enforced?
7. Can staging expose the approved API and metrics on a single origin? Can we use a dedicated replica with synthetic or replayable de-identified traffic?
8. How is spend billed? Which costs can fall, and what redundancy or rollback capacity is mandatory?

## Collect a baseline

Pin the workload, engine/container digest, model and tokenizer, all sampling flags, context limit, scheduler, KV dtype and attention backend. Record compiled graphs and runtime versions. Isolate the replica or record its other traffic. Warm kernels before collection. Retain cold starts as a separate cohort. Collect repeated controls and use matched single-stream, closed-loop and bounded open-loop stages. Keep deadline failures and rejected offers. Measure successful, correct and on-time cohorts separately. Scrape metrics only when explicitly approved. A scrape can include unrelated traffic or miss short spikes. Client and server timing have different clock boundaries.

| Evidence | Action to validate | Constraint |
| --- | --- | --- |
| Waiting rises with slower TTFT as goodput flattens | Repeat at arrival rates around queue onset. Separate downstream backpressure and connector waiting. | More admitted work can worsen tails. |
| KV occupancy near limit and preemption deltas rise on the same replica | Lower admission/context envelope or evaluate cache size/dtype and model-specific KV needs. | Preserve required context, quality and memory headroom. |
| Long prefill coincides with decode stalls | Compare token budgets at matched arrival schedule. Include a short-only negative control. | Small chunks can protect ITL and worsen long-prompt TTFT. |
| Repeated prefixes and low reuse | Replay exact token prefixes and early-changed controls. Inspect routing, hash span and eviction. | Verify tenant isolation and cache locality. |
| Persistent backlog with sparse GPU work | Trace scheduling, CPU tokenizer, copies and sampling using host and GPU timelines. | Device active time alone cannot identify a bandwidth or compute bottleneck. |
| Decode near its memory proxy | Test a supported quantized kernel or speculation under an unchanged contract. | Recheck output quality and draft overhead by prompt family. |

## GPU and topology choices

- A100 memory size and interconnect depend on SKU and node design. Verify whether the specific setup is PCIe or SXM before planning TP. [A100 datasheet](https://www.nvidia.com/content/dam/en-zz/Solutions/Data-Center/a100/pdf/nvidia-a100-datasheet.pdf)
- HGX H100/H200/B200 platforms have different HBM, fabric and operator requirements. H200's extra memory can change replica fit and KV admission without a kernel improvement. B200 enables newer precision and kernel paths when the actual stack supports them. Use vendor hardware references as design inputs. [NVIDIA HGX platform comparison](https://docs.nvidia.com/enterprise-reference-architectures/hgx-ai-factory-h100-h200-b200/latest/components.html)
- For TP check per-step collectives under decode loads. For pipeline parallel measure stage bubbles. For EP check all-to-all bandwidth and expert skew. For cross-node links inspect NIC binding and oversubscription. Data-parallel replicas add deployable capacity but can reduce prefix locality.
- Evaluate prefill/decode disaggregation only with independently sized traffic and measured KV transfer. Test recovery from an unavailable connector and full pool. Separate evidence from the single-GPU RTX 4070 study. [vLLM parallelism and scaling](https://docs.vllm.ai/en/latest/serving/parallelism_scaling/) · [Disaggregated prefill](https://docs.vllm.ai/en/latest/features/disagg_prefill/)

## Ship a recommendation

Pre-register pass criteria. Compare candidate with neighboring controls on representative traffic, including cold caches, long contexts, tool round trips, rare outputs and cancellations. Measure p95/p99 only with credible sample populations. Repeat a meaningful result independently. Provision headroom for startup/JIT, transient graph memory, demand variation and failover. Keep config and image rollback ready, start with canary replicas, watch per-family failures and restore immediately if gates regress. Report useful capacity, uncertainty, and formulas. Convert throughput to dollars only after a realistic deployment and billing model. Capture the full evidence digest and retain failures.
