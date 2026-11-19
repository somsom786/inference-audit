# Development

```powershell
python -m venv .venv-dev
.\.venv-dev\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv-dev\Scripts\python.exe -m pytest -q
.\.venv-dev\Scripts\python.exe -m ruff check .
.\.venv-dev\Scripts\python.exe -m ruff format --check src tests examples
.\.venv-dev\Scripts\python.exe -m mypy src
.\.venv-dev\Scripts\python.exe -m pip check
.\.venv-dev\Scripts\python.exe -m pip wheel --no-deps --wheel-dir dist .
```

Ubuntu uses the same Python commands under `.venv-dev/bin`. CI exercises deterministic fake endpoints and has no GPU dependency. The test suite's mock pilot covers endpoint inspection, scoped traffic, verification, bundle export and offline report recreation.

For an approved local GPU acceptance, substitute your own executable and model paths. The launcher uses an owned server bound to loopback with guarded VRAM and temperature.

```powershell
.\.venv-dev\Scripts\python.exe examples/live_acceptance.py --engine "C:/path/to/llama-server.exe" --model "C:/path/to/model.gguf" --id acceptance-new --approve-local-processes
```

On Linux run this command with the Linux CUDA build and key-free model path in an approved environment. Verify placement, telemetry, offline reconstruction and process exit. Windows VRAM and driver numbers cannot predict Linux performance.
