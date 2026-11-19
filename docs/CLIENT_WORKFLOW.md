# Client workflow

1. Agree on staging target, experiment window, request ceilings, data retention and stop conditions using the [pilot runbook](PILOT_RUNBOOK.md).
2. Collect configuration identity from the customer and inspect the authorized endpoint with GET-only probes. Start with a narrow synthetic smoke. Verify token counts, finish reasons, available context and internal metrics where supported.
3. Run a preapproved load bracket and preserve all outcomes, including overload and correctness failures. Use independent launches or time windows for material claims.
4. Verify and render the evidence offline. Confirm that measured goodput and per-family objectives support each capacity claim.
5. Review sanitized HTML/JSON/Markdown reports. Export raw synthetic fixtures and observations only with scope approval.
6. Present conditional scenarios for cost and capacity. Real hosting bills, traffic distributions and deployment constraints determine whether a scenario can become a savings claim.

A first paid pilot can offer a reproducible measurement and diagnosis of one approved staging endpoint. GPU telemetry and engine-specific counters depend on the customer environment.
