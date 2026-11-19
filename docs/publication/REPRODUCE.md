# Reproduce the proof package

## Recalculate published figures without a model

From the repository root, in a Python environment with the publication dependencies installed:

```powershell
python -m pip install -r scripts/publication/requirements.txt
python scripts/publication/build_figures.py
python scripts/publication/build_site_pages.py
python scripts/publication/validate_publication.py
```

The [measurement JSON](../../public/evidence/measurements.json) contains the sanitized inputs. It includes all four launch rows at all mixed-load points, plus family breakdowns, selected Phase 1 panel measurements and per-launch Phase 2 quantities. The Phase 3 transfer chart uses the same within-model control groups declared in the original study.

## Replay from the original local archives

This step needs the separate research archive, native product captures and Phase 4 replication. It never starts a server or edits those archives. Install the original validated 0.2.1 wheel for the report step.

```powershell
python scripts/publication/collect_evidence.py --research ../inference-bench --replication validation/runs/replication-01
python -m pip install dist/inference_audit-0.2.1-py3-none-any.whl
python scripts/publication/build_reports.py --runs .runs
```

The collector verifies matching designs and source topic groups. It recounts eligible Phase 1 panels, Phase 2 launch pools, Phase 3 and 4 matched strata, and transfer counts against their original summaries. The report script compares the offline analysis to the archived report before applying the public aliases. Response bodies were omitted from the public export. Offline analysis cannot regrade withheld text.

## Preview the static site

```powershell
python -m http.server 8090 --bind 127.0.0.1 --directory public
```

Open `http://127.0.0.1:8090/`. The site also works by opening `public/index.html` directly. To run browser QA, supply the local Chromium/Chrome/Edge executable to `python scripts/publication/check_browser.py --browser PATH_TO_BROWSER`. It serves the static files on an ephemeral localhost port, uses software rendering, checks desktop and mobile viewports, and refreshes the cropped screenshot from the real Qwen report.

Review the [scope and approval checklist](PUBLICATION_CHECKLIST.md) before putting any files on a public host. Use the [project quick start](../../README.md#quick-start) to benchmark an authorized endpoint with a workload of your own.
