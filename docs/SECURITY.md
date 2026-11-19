# Security model

The default audit reads selected API capabilities and issues bounded synthetic inference requests to an approved endpoint. The workload can affect other users even though the tool leaves server configuration untouched.

Run under an unprivileged operator account. Benchmarking requires policy approval in configuration and the explicit CLI load flag. Controlled mode has its own approval and owns its child processes. Keep that mode outside ordinary read-only staging engagements.

Targets use literal loopback or approved HTTPS with validated public DNS, address pinning, TLS identity verification and no proxy or redirect. For private environments, use a customer-controlled runner against an approved loopback listener. Keep the credential in a dedicated environment variable. The operator-facing inspection output may include configured service model identifiers. Share the sanitized report instead of that console output. Workload fixtures are synthetic and responses are held only for validation. No external resource is loaded by the HTML export.

Pick local evidence paths owned by the operator. The runner refuses links, oversized inputs, existing report files and unsupported configs. These controls complement local file permissions. Seals detect alteration and do not replace authenticated retention. The optional bundle export includes the exact synthetic prompt manifest.

See the [tested security boundaries](SECURITY_REVIEW.md) and [customer procedures](PILOT_RUNBOOK.md).
