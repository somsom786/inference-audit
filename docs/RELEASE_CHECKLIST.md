# Release checklist

Use this checklist with the [validation record](VALIDATION.md) and the [security review](SECURITY_REVIEW.md).

## Review handoff for every version

Before marking a version finished, create `dist/review/Inference Audit VERSION/` and its matching `dist/review/Audit VERSION.zip` for ChatGPT review. Include a `START_HERE.md` with the review prompt and evidence map, the release verdict, the reviewed source and tests, the wheel and its checksum, and the evidence needed to reproduce the release claims. Keep private logs, credentials, environments and model weights out of the bundle. Check the ZIP contents and per-file checksums, keep it under 512 MB, and share the local link with the release verdict.

## 0.2.1 patch gates

- [x] Reproduce the missing tool-result acceptance on a copy of Qwen transaction `mixed-00012` with a recomputed checksum index. Verify the patch rejects that same copy.
- [x] Run 78 Windows tests and the Ruff lint, formatting and mypy checks. The regression suite covers altered agent and warm-cache handshakes and CPU-only shutdown behavior.
- [x] Verify the seven original native Qwen and Gemma captures and reproduce both final 0.2.0 reports offline.
- [x] Install the 0.2.1 wheel in a fresh Windows environment. Check dependencies, verify the wheel archive and rerun the fake-server read-only customer export and offline replay workflow.
- [x] Preserve the 0.2.0 wheel, review ZIP and raw benchmark evidence. The existing release artifact hashes match.
- [ ] Validate native CUDA process shutdown before qualifying experimental process control. Read-only pilot operation keeps that mode disabled.
- [ ] Obtain explicit approval before public publication.

The 0.2.1 artifact is `dist/inference_audit-0.2.1-py3-none-any.whl`. The SHA-256 is in its adjacent `.whl.sha256` file. All 0.2.1 checks used CPU-only fixtures or reread saved observations.

## 0.2.0 baseline

- [x] Audit the baseline and retain its evidence and local Git history.
- [x] Record security and measurement findings and add targeted regressions.
- [x] Build a pure-Python wheel, install in a clean Windows environment and verify dependencies.
- [x] Validate the controlled fake-server workflow, evidence export and offline report reconstruction.
- [x] Recount historic Phase 3 and Phase 4 populations without modifying the research workspace.
- [x] Record bounded Qwen and Gemma GPU acceptance and reconcile both final reports.
- [x] Record source/package verification and the final wheel SHA-256.
- [ ] Complete the signed authorization, compatibility smoke and traffic review before any customer run.
- [ ] Obtain explicit approval before public publication.
