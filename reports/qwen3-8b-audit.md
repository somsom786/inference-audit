# Local demonstration audit — NVIDIA RTX 4070 — synthetic workloads &#40;Qwen3-8B Q4&#95;K&#95;M&#41;

**COMPLETE** · Measured synthetic service on the stated contract&#46; Latency uses completed streams&#46; Token rates require complete usage coverage&#46;

## Audit scope and verdict

| Scope item | Value |
| --- | --- |
| Verdict | Performance or measurement issue identified |
| Run | qwen3-8b-audit |
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
| completed&#95;streams | 490 |
| usage&#95;accounted&#95;streams | 490 |
| cache&#95;counter&#95;streams | 490 |
| successful&#95;tool&#95;delta&#95;streams | 40 |
| requests | 540 |
| runtime&#95;s | 730 |
| concurrency | 4 |
| rps | 4 |
| response&#95;bytes | 2000000 |
| evidence&#95;mib | 64 |
| client&#95;queue | 4 |
| timeout&#95;s | 18 |
| dispatch&#95;slack&#95;s | 1&#46;200 |

## Measured service

| Stage | Pattern | Offered | Admitted | Dispatched | Completed | Correct | On time | Goodput txn/s | Output tok/s | Cache share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | decode | 6 | 6 | 6 | 6 | 6 | 6 | 0&#46;869 | 83&#46;270 | 0&#46;109 |
| parallel | concurrent | 12 | 12 | 12 | 12 | 12 | 12 | 1&#46;968 | 139&#46;098 | 0&#46;129 |
| cold | cold | 4 | 4 | 4 | 4 | 4 | 4 | 2&#46;324 | 27&#46;312 | 0&#46;000 |
| warm | warm | 4 | 4 | 4 | 4 | 4 | 4 | 1&#46;373 | 34&#46;323 | 0&#46;501 |
| mixed&#95;low | mixed | 210 | 210 | 210 | 210 | 198 | 198 | 0&#46;614 | 21&#46;568 | 0&#46;077 |
| mixed&#95;high | mixed | 210 | 210 | 210 | 210 | 200 | 200 | 1&#46;048 | 36&#46;372 | 0&#46;078 |

## Workloads and token coverage

| Stage | Mode | Planned txn/s | Arrival window txn/s | Workers | Peak HTTP overlap | Elapsed including drain, s | Accounted streams | Completed streams | Passing family gate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | closed | 4 | Unavailable | 1 | 1 | 6&#46;905 | 6 | 6 | False |
| parallel | closed | 4 | Unavailable | 4 | 4 | 6&#46;096 | 12 | 12 | False |
| cold | closed | 4 | Unavailable | 1 | 1 | 1&#46;721 | 4 | 4 | False |
| warm | closed | 4 | Unavailable | 1 | 1 | 2&#46;913 | 8 | 8 | False |
| mixed&#95;low | open | 0&#46;650 | 0&#46;648 | 4 | 2 | 322&#46;701 | 230 | 230 | False |
| mixed&#95;high | open | 1&#46;100 | 1&#46;097 | 4 | 2 | 190&#46;781 | 230 | 230 | False |

## Response latency

| Stage | P50 first output s | P95 first output s | P99 first output s | P50 visible content s | P50 response headers s | P50 completion s | P95 completion s | P99 completion s | P95 client dispatch delay s | P50 server decode ms/token | P50 server prefill tok/s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| single | 0&#46;027 | Unavailable | Unavailable | 0&#46;027 | 0&#46;006 | 1&#46;232 | Unavailable | Unavailable | Unavailable | 11&#46;671 | 1985&#46;857 |
| parallel | 0&#46;841 | Unavailable | Unavailable | 0&#46;841 | 0&#46;660 | 1&#46;689 | Unavailable | Unavailable | Unavailable | 12&#46;582 | 1163&#46;230 |
| cold | 0&#46;253 | Unavailable | Unavailable | 0&#46;253 | 0&#46;019 | 0&#46;378 | Unavailable | Unavailable | Unavailable | 11&#46;355 | 4606&#46;680 |
| warm | 0&#46;481 | Unavailable | Unavailable | 0&#46;481 | 0&#46;004 | 0&#46;751 | Unavailable | Unavailable | Unavailable | 11&#46;496 | 81&#46;367 |
| mixed&#95;low | 0&#46;065 | 0&#46;499 | 0&#46;595 | 0&#46;065 | 0&#46;007 | 0&#46;507 | 1&#46;200 | 1&#46;562 | 0&#46;015 | 11&#46;552 | 2066&#46;116 |
| mixed&#95;high | 0&#46;057 | 0&#46;507 | 0&#46;573 | 0&#46;057 | 0&#46;009 | 0&#46;482 | 1&#46;327 | 1&#46;613 | 0&#46;015 | 11&#46;542 | 2058&#46;894 |

## Cold and warm cache probes

| Cache probe | Verified samples | Completed probe streams | Median request TTFT s | Median server prefill ms |
| --- | --- | --- | --- | --- |
| cold | 4 | 4 | 0&#46;253 | 214&#46;840 |
| warm | 4 | 4 | 0&#46;016 | 12&#46;949 |

## Workload objectives

| Stage | Family | Correct, on time | Offered | SLO pass share | Family gate | P95 first output s | P95 completion s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| single | chat | 6 | 6 | 1&#46;000 | False | Unavailable | Unavailable |
| parallel | chat | 12 | 12 | 1&#46;000 | False | Unavailable | Unavailable |
| cold | rag | 4 | 4 | 1&#46;000 | False | Unavailable | Unavailable |
| warm | rag | 4 | 4 | 1&#46;000 | False | Unavailable | Unavailable |
| mixed&#95;low | agent | 10 | 20 | 0&#46;500 | False | Unavailable | Unavailable |
| mixed&#95;low | chat | 81 | 83 | 0&#46;976 | True | 0&#46;084 | 1&#46;389 |
| mixed&#95;low | coding | 53 | 53 | 1&#46;000 | True | 0&#46;092 | 0&#46;346 |
| mixed&#95;low | rag | 54 | 54 | 1&#46;000 | True | 0&#46;595 | 0&#46;726 |
| mixed&#95;high | agent | 12 | 20 | 0&#46;600 | False | Unavailable | Unavailable |
| mixed&#95;high | chat | 81 | 83 | 0&#46;976 | True | 0&#46;084 | 1&#46;592 |
| mixed&#95;high | coding | 53 | 53 | 1&#46;000 | True | 0&#46;076 | 0&#46;244 |
| mixed&#95;high | rag | 54 | 54 | 1&#46;000 | True | 0&#46;573 | 0&#46;749 |

## Capacity qualification

No stage established the strict per-family capacity gate.

## Failures and exclusions

| Stage | Outcome | Transactions |
| --- | --- | --- |
| mixed&#95;low | quality&#95;failures | 12 |
| mixed&#95;high | quality&#95;failures | 10 |

## GPU telemetry · sampled maxima where applicable

| GPU metric | Value |
| --- | --- |
| state | measured |
| samples | 344 |
| unavailable&#95;samples | 0 |
| scope | total device; includes other resident processes |
| model | NVIDIA GeForce RTX 4070 |
| driver | 621&#46;24 |
| compute&#95;capability | 8&#46;9 |
| thermal&#95;slowdown&#95;samples | 0 |
| power&#95;limited&#95;samples | 28 |
| total&#95;mib | 12282&#46;000 |
| used&#95;mib | 7541&#46;000 |
| free&#95;mib | 4494&#46;000 |
| temp&#95;c | 61&#46;900 |
| busy&#95;pct | 100&#46;000 |
| sm&#95;mhz | 2790&#46;000 |
| mem&#95;mhz | 9801&#46;000 |
| power&#95;w | 189&#46;880 |
| board&#95;sample&#95;joules | 52915&#46;148 |
| energy&#95;covered&#95;s | 530&#46;270 |
| observed&#95;median&#95;sample&#95;interval&#95;s | 1&#46;546 |

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
