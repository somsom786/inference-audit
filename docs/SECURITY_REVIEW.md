# Security review

The benchmark applies two approvals before sending inference traffic. The configuration declares the approved target and ceilings, and the operator passes `--approve-load`. These controls enforce a local operator workflow. Access to the workspace and network credentials remains the customer's responsibility.

| Boundary | Enforcement and regression coverage |
| --- | --- |
| Target origin | HTTP and HTTPS loopback, or explicitly allowlisted HTTPS origins. Reject URL credentials, paths, queries, fragments and malformed ports. Translate localhost to numeric IPv4. |
| DNS and redirects | Validate all remote DNS answers for public unicast, reject mixed/private/special destinations, pin one address per client and retain the original Host/TLS identity. Proxies and redirects are disabled. Fake resolution/transport tests keep the destination local to the test process. |
| Credentials | Resolve an approved environment variable. Accept a bounded bearer value, omit it from evidence and never dump response bodies, headers or URLs in operational errors. Keep HTTP debug logging disabled in the runner. |
| Work and storage | Separate HTTP step, rate, concurrency, waiting queue, output, response byte, runtime and disk limits. Explicit rejection records, free-space preflight and a live disk guard. |
| Files and reports | Limit input files and JSONL rows, reject traversal, symlinks, Windows junctions and unsafe imports. Refuse existing report files. HTML escapes rendered values and uses a restrictive Content Security Policy. Markdown neutralizes active formatting in data fields. |
| Owned processes | Separate approval and exclusive use of a dedicated loopback port. Only a graceful signal to an owned child is available after drain confirmation. Unverified activity or shutdown requires operator intervention. |
| Evidence | Offline checks validate local digests, plan-to-step structure, status and finish consistency, and cached-token state. Offline analysis recalculates metrics. Digests match the supplied index without authenticating customers or independently proving answer correctness. |

### Owned shutdown procedure

The controlled runner ends its own inference admissions and closes its benchmark client. On the dedicated loopback port, shutdown polls `/slots` and the documented llama.cpp processing and deferred request gauges from `/metrics`. It allows up to 15 seconds to see all expected slots idle and both gauges at zero in two samples separated by at least 250 ms. The operator must keep other clients off the port during an owned run. The observations establish server-reported drain at the sampled times.

After drain confirmation the runner requests graceful exit with CTRL+BREAK for the owned Windows process group or SIGTERM for the owned POSIX child. It allows up to eight seconds to observe exit. It never escalates to a force-kill of the inference process. On active or unknown work, signal failure, or missing exit confirmation, the bracket stops before any further arm or rollback. Inspect the arm's shutdown JSON for the PID, observed activity, reason and signal. Confirm the process identity and consult the operator before taking further action. An early or spontaneous exit is reported separately as unverified.

Experimental process control remains outside the read-only customer pilot. Tests simulate drain, queued work, missing signals, missing evidence and failure to exit, and verify that an unreaped CPU test fixture survives event-loop shutdown. Native CUDA shutdown was not exercised for this patch.

Stored correctness flags come from the runtime validation. Offline verification cannot independently reevaluate private response text or tool arguments that were not retained.

The HTTPS tests verify the selected address and exercise a real loopback TLS handshake. A generated test certificate matched the original TLS name and a mismatched name was rejected. A real customer certificate, DNS topology and network route require an approved staging smoke. Private non-loopback addresses, proxies and redirects are outside this release scope. A hostile same-user process with write access to the run directory can race file operations or replace data. Keep workspace permissions limited. Review sanitized reports before sharing and avoid placing confidential details in operator-supplied labels. No customer prompt or response ingestion is enabled.
