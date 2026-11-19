# Measurement and interpretation

## Workload and clocks

Each run saves its exact synthetic fixtures, seed, generated schedules and caps. Keep the fixture set, payloads, count, scheduler, output allowance and concurrency fixed when varying offered rate. A matched cache probe uses the same fixture set. Cold observations require a verified zero-hit count. Warm observations require an identical same-slot prime/replay and a verified positive hit count. Aggregates identify how many completed probes actually met the intended cache condition.

The transaction clock starts at the scheduled arrival. Client dispatch delay includes waiting for a worker and local pacing. First output uses visible content for ordinary text and the initial tool delta for agents. First visible content is recorded separately. Request timestamps distinguish dispatch, headers, content events, final usage, stream completion and termination. Client observations cannot locate server queue time. Valid tool workflows are timed end to end across dependent steps.

The displayed rate divides by the measured stage span, including drain and scheduled idle periods. The open-loop arrival-window column describes the complete manifested offer separately. Closed-loop rates describe work served with feedback and establish no open-loop capacity. A planned transaction may be unreached, rejected, admitted but undispatched, dispatched, completed, correct or both correct and on time. Reports preserve these populations. The stage overlap is the observed overlap of recorded HTTP request intervals across workers, including failed returned steps.

## Output, usage and quality

A completed stream needs a recognized finish, nonempty output and a DONE marker. Usage is a separate measurement. Validate prompt/output totals, output caps, cache counts and llama.cpp prediction counters when present. A stage with unaccounted completed streams has unavailable output throughput. Timed-out, interrupted or rejected requests can still use GPU time. Server prefill is processed prompt tokens divided by the engine's measured prefill seconds. Server decode ms/token divides prediction duration by the matching engine output count. With generic servers, internally consistent API usage is evidence of provider accounting. SSE events count only as protocol frames.

Synthetic checks include exact retrieval, JSON/arithmetic, constrained code AST without execution, and verified tool arguments plus the final answer. Capped output fails normal task completion. The length cap is permitted in explicitly named decode/concurrent throughput panels. These checks have a narrow quality scope.

Offline verification checks local digests and the structure and consistency of stored observations, including the planned request chain and relevant finish reasons. Offline analysis recalculates metrics from those observations. Where response text or tool arguments were not retained, correctness is the recorded runtime result. Re-evaluating the answer requires the original response. Local digests establish consistency with the supplied index and provide no customer authentication or independent evidence of answer correctness.

## Uncertainty and capacity

P95 requires at least 40 samples and P99 at least 200. Completed-request tails should be read together with error and admission rates. Strict qualification requires at least 20 planned observations for each represented family, configured family quality/on-time/error gates and optional verified context. The highest passing tested goodput is an observed rate for that workload. Repeated launches or time windows are needed to establish repeatability.

Wilson intervals are descriptive under IID assumptions. Correlated requests from one launch are not treated as independent replications. Owned ABBA compares the weakest candidate launch with the strongest control and checks aggregate and per-family latency tails. Small or mismatched samples cannot pass. Customer audits should log exclusions and retain affected evidence.

Local NVIDIA data is total-device telemetry. The power integral uses covered intervals only. Board utilization describes active time. Memory bandwidth, compute efficiency and causal kernel diagnoses require other measurements.

## Historical imports

```powershell
inference-audit import --source ../inference-bench --phase 3 --run phase3-history
inference-audit verify --run phase3-history
inference-audit report --run phase3-history
```

The schema-specific imports preserve source checksums and caveats for Phase 1, 2 or 3. The Phase 3 eligible comparison excluded the interrupted original A2 and uses separate launches. See the [independent replication](../validation/INDEPENDENT_REPLICATION.md).
