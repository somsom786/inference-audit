# Limitations

Inference Audit 0.2.0 is designed for a limited customer-controlled staging pilot. The primary route is an authorized, bounded and read-only audit of an OpenAI-compatible text SSE endpoint.

The correct scope of each measurement depends on streaming usage, fixtures, tested load, context, latency gates and independent replications. NVIDIA board samples include other processes and cannot identify kernel causality. Supported llama.cpp counters can show sampled pending work. Client timings give no exact server queue delay.

See [known issues](KNOWN_ISSUES.md) for backend and recovery limitations and [validation](VALIDATION.md) for the boundaries verified on Windows and WSL.
