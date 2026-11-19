# Customer-controlled staging pilot

## Approval record

Record these values in the signed scope or the customer's ticket before running inference. Keep any credentials and private identifiers in the customer's approved system.

| Approval item | Customer entry |
| --- | --- |
| Authorized operator and person who can stop the test | |
| Approved staging origin and network route | |
| Model revision, chat template, context and output cap | |
| Start/end window and time zone | |
| Approved maximum HTTP requests/s, concurrent clients, waiting queue, HTTP steps and runtime | |
| Per-family TTFT and completion objectives, minimum quality and maximum error share | |
| Synthetic fixture mix and permitted telemetry | |
| Stop conditions for impact, errors, GPU safety and cancellation | |
| Credential injection, report recipients and retention or deletion date | |
| Explicit approval of load against this target | |

## Execute

1. Run under a dedicated unprivileged staging account in a customer-controlled environment. Use an approved local listener for private deployments. Keep the output folder private and writable only by the runner.
2. Start with GET-only inspection. Verify the model, test window, available context, streaming compatibility and expected usage with a handful of authorized requests. Unsupported capabilities go in the audit scope.
3. Review the exact synthetic workload and limits with the operator. Rate caps apply to all HTTP inference steps including tool follow-ups. The request budget and concurrent limits include follow-up traffic. Deploy external resource monitoring and keep a stop contact for live impact. When board telemetry is unavailable, use the customer's operating guardrails.
4. Run the approved rate bracket with fresh IDs. Cancel with Ctrl+C or create a `STOP` file in the active run directory. Remember that the server may continue executing work after a client disconnect.
5. Verify and render the saved run offline. Review the offered and completed populations, token coverage and failed families. Repeat any material claim on independently launched or scheduled windows with the same workload. Preserve excluded runs and document their reason.
6. Share the three report files after reviewing redaction. Use `export --include-synthetic-manifest` only when the scope permits sharing the generated fixtures and detailed timings.
7. Present conditional cost scenarios separately from measured rates and archive the scope, evidence checksum and analysis version under the agreed retention policy.

The local pilot simulation uses the controlled fake server and the read-only CLI. For actual staging, rerun the compatibility smoke against the customer's network path and backend before offering a measured capacity assessment. The owned experiment command is outside a standard read-only engagement.

Keep experimental process control disabled throughout the pilot. Run only the read-only audit commands against the approved service. Offline checks validate the retained records and recalculate metrics. Answer quality is the recorded runtime result when the response itself was not retained.
