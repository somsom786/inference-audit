# Local demonstration audit — NVIDIA RTX 4070 — synthetic workloads &#40;Gemma 4 12B IT QAT &#40;text Q4&#95;0&#41;&#41;

**COMPLETE** · Measured synthetic service on the stated contract&#46; Latency uses completed streams&#46; Token rates require complete usage coverage&#46;

## Audit scope and verdict

| Scope item | Value |
| --- | --- |
| Verdict | Performance or measurement issue identified |
| Run | gemma4-12b-audit |
| Capture version | 0&#46;2&#46;0 |
| Started UTC | Unavailable |
| Ended UTC | Unavailable |
| Stop reason | Unavailable |
| Engine adapter | llama&#46;cpp |
| Verified slot context, tokens | 4096 |
| Highest passing tested goodput, transactions/s | Unavailable |
| models&#95;http | 200 |
| listed&#95;models | 1 |
| health&#95;http | 200 |
| metrics&#95;http | 200 |
| context&#95;tokens | 4096 |
| completed&#95;streams | 56 |
| usage&#95;accounted&#95;streams | 56 |
| cache&#95;counter&#95;streams | 56 |
| successful&#95;tool&#95;delta&#95;streams | 2 |
| requests | 72 |
| runtime&#95;s | 160 |
| concurrency | 4 |
| rps | 4 |
| response&#95;bytes | 2000000 |
| evidence&#95;mib | 64 |
| client&#95;queue | 0 |
| timeout&#95;s | 18 |
| dispatch&#95;slack&#95;s | 1&#46;200 |

## Measured service

| Stage | Pattern | Offered | Admitted | Dispatched | Completed | Correct | On time | Goodput txn/s | Output tok/s | Cache share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | decode | 6 | 6 | 6 | 6 | 6 | 6 | 0&#46;509 | 53&#46;832 | 0&#46;017 |
| parallel | concurrent | 12 | 12 | 12 | 12 | 12 | 3 | 0&#46;258 | 90&#46;361 | 0&#46;019 |
| cold | cold | 4 | 4 | 4 | 4 | 4 | 4 | 1&#46;016 | 11&#46;685 | 0&#46;000 |
| warm | warm | 4 | 4 | 4 | 4 | 4 | 4 | 1&#46;427 | 32&#46;823 | 0&#46;998 |
| mixed | mixed | 24 | 24 | 24 | 24 | 21 | 21 | 0&#46;570 | 24&#46;704 | 0&#46;031 |

## Workloads and token coverage

| Stage | Mode | Planned txn/s | Arrival window txn/s | Workers | Peak HTTP overlap | Elapsed including drain, s | Accounted streams | Completed streams | Passing family gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | closed | 4 | Unavailable | 1 | 1 | 11&#46;796 | 6 | 6 | False |
| parallel | closed | 4 | Unavailable | 4 | 4 | 11&#46;631 | 12 | 12 | False |
| cold | closed | 4 | Unavailable | 1 | 1 | 3&#46;937 | 4 | 4 | False |
| warm | closed | 4 | Unavailable | 1 | 1 | 2&#46;803 | 8 | 8 | False |
| mixed | open | 0&#46;650 | 0&#46;633 | 4 | 2 | 36&#46;836 | 26 | 26 | False |

## Response latency

| Stage | P50 first output s | P95 first output s | P99 first output s | P50 visible content s | P50 response headers s | P50 completion s | P95 completion s | P99 completion s | P95 client dispatch delay s | P50 server decode ms/token | P50 server prefill tok/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 0&#46;068 | Unavailable | Unavailable | 0&#46;068 | 0&#46;012 | 2&#46;024 | Unavailable | Unavailable | Unavailable | 17&#46;841 | 846&#46;886 |
| parallel | 1&#46;771 | Unavailable | Unavailable | 1&#46;771 | 1&#46;622 | 3&#46;369 | Unavailable | Unavailable | Unavailable | 19&#46;555 | 494&#46;868 |
| cold | 0&#46;769 | Unavailable | Unavailable | 0&#46;769 | 0&#46;051 | 0&#46;981 | Unavailable | Unavailable | Unavailable | 17&#46;720 | 2407&#46;751 |
| warm | 0&#46;227 | Unavailable | Unavailable | 0&#46;227 | 0&#46;004 | 0&#46;708 | Unavailable | Unavailable | Unavailable | 17&#46;254 | 16&#46;039 |
| mixed | 0&#46;150 | Unavailable | Unavailable | 0&#46;150 | 0&#46;010 | 0&#46;685 | Unavailable | Unavailable | Unavailable | 17&#46;447 | 822&#46;138 |

## Cold and warm cache probes

| Cache probe | Verified samples | Completed probe streams | Median request TTFT s | Median server prefill ms |
| --- | --- | --- | --- | --- |
| cold | 4 | 4 | 0&#46;769 | 715&#46;349 |
| warm | 4 | 4 | 0&#46;067 | 62&#46;744 |

## Workload objectives

| Stage | Family | Correct, on time | Offered | SLO pass share | Family gate | P95 first output s | P95 completion s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| single | chat | 6 | 6 | 1&#46;000 | False | Unavailable | Unavailable |
| parallel | chat | 3 | 12 | 0&#46;250 | False | Unavailable | Unavailable |
| cold | rag | 4 | 4 | 1&#46;000 | False | Unavailable | Unavailable |
| warm | rag | 4 | 4 | 1&#46;000 | False | Unavailable | Unavailable |
| mixed | agent | 2 | 2 | 1&#46;000 | False | Unavailable | Unavailable |
| mixed | chat | 7 | 10 | 0&#46;700 | False | Unavailable | Unavailable |
| mixed | coding | 6 | 6 | 1&#46;000 | False | Unavailable | Unavailable |
| mixed | rag | 6 | 6 | 1&#46;000 | False | Unavailable | Unavailable |

## Capacity qualification

No stage established the strict per-family capacity gate.

## Failures and exclusions

| Stage | Outcome | Transactions |
| --- | --- | --- |
| mixed | quality&#95;failures | 3 |

## GPU telemetry · sampled maxima where applicable

| GPU metric | Value |
| --- | --- |
| state | measured |
| samples | 44 |
| unavailable&#95;samples | 0 |
| scope | total device; includes other resident processes |
| model | NVIDIA GeForce RTX 4070 |
| driver | 621&#46;24 |
| compute&#95;capability | 8&#46;9 |
| thermal&#95;slowdown&#95;samples | 0 |
| power&#95;limited&#95;samples | 4 |
| total&#95;mib | 12282&#46;000 |
| used&#95;mib | 9683&#46;000 |
| free&#95;mib | 2354&#46;000 |
| temp&#95;c | 61&#46;550 |
| busy&#95;pct | 100&#46;000 |
| sm&#95;mhz | 2790&#46;000 |
| mem&#95;mhz | 9801&#46;000 |
| power&#95;w | 174&#46;100 |
| board&#95;sample&#95;joules | 8645&#46;367 |
| energy&#95;covered&#95;s | 66&#46;509 |
| observed&#95;median&#95;sample&#95;interval&#95;s | 1&#46;545 |

## Evidence-backed diagnoses

### Server observed requests waiting for admission

- stage — run observation
- confidence — high for sampled queue existence
- evidence — Known engine reported up to 2 deferred requests&#46;
- caveat — The gauge covers the server and may include other customers&#46; Peaks can occur between samples&#46;
- experiment — Repeat at matched load with a supported, context-qualified slot change&#46;
- tradeoff — Extra slots compete for the context budget and can increase decode contention&#46;
- falsifier — Dedicated replay reports no deferred work while the first-token tail remains elevated&#46;

## Method and evidence

P95 is withheld below 40 completed samples and P99 below 200. Strict gates apply to each represented family with at least 20 planned transactions. Rates use stage elapsed time including drain. Agent first output includes the first tool delta. Visible content is recorded separately. Requests within one launch can be correlated. Board utilization measures active time. Task checks cover synthetic receipts, simple code structure, tool calls, JSON or arithmetic.

Seed 241105. See the saved plan, events, GPU samples and checksum index.
