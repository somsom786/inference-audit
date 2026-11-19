# Status

Inference Audit 0.2.0 is a local release candidate, conditionally ready for a limited customer-controlled staging pilot.

| Classification | Scope |
| --- | --- |
| Completed and verified | Authorized read-only CLI, bounded scheduling, SSE, token coverage, request and GPU evidence, offline verification and reporting, historical imports, stage-boundary resume, signed-scope procedure and synthetic evidence export |
| Completed and verified | Final Windows wheel, 47 Windows tests, 47 WSL tests, local TLS, local mock pilot and key-free Qwen and Gemma CUDA acceptance |
| Experimental | Owned llama.cpp ABBA slot comparison with fresh launches, fixed arguments, matched manifests and stricter tails |
| Partially implemented | Backend-specific profiling and capability coverage. NVIDIA board sampling and known llama.cpp counters are available. Kernel profiling and broader backend counters are deferred. |
| Deferred | Native Linux GPU integration, actual client network validation, production deployment changes and verified fleet economics |

Both final owned servers exited and their ports are free. Three local capture reports, the demo, release wheel and checksum are available. The research workspace and negative Phase 4 findings were preserved. The next customer activity requires signed scope and a monitored staging smoke. Publishing awaits user approval.

[Evidence and test results](VALIDATION.md) · [Release checklist](RELEASE_CHECKLIST.md) · [Pilot runbook](PILOT_RUNBOOK.md)
