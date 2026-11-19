# Publication checklist

The release surface is the curated repository snapshot, the static `public/` tree and the preserved 0.2.1 wheel. Private working history and the review handoff remain local.

| Gate | Status | Evidence |
| --- | --- | --- |
| Case study and traceable claims | Passed | The case study, executive summary and ledger preserve the Flash Attention control, smaller context windows, workload-specific failures and interrupted exposure. |
| Numerical replay | Passed | Recomputed Phase 1 panels, Phase 2 pools and default probes, Phase 3 matched and transfer results, and the independent local workload replication. Phase 3 and Phase 4 each reconcile 60 arm/window/family strata. |
| Native Qwen and Gemma sample re-renders | Passed | Installed 0.2.1 analysis matches the archived original metrics before redaction. JSON reports validate against the published Draft 2020-12 schema. The public reports omit raw dialogue. |
| Unit and regression suite | Passed | Reran 78 Windows tests. Ruff lint/format, mypy package checks, verified wheel checksum and dependency check passed. |
| Fresh installation and authorized CLI workflow | Passed | Fresh Windows Python environment installed from the repository. Source install and preserved wheel each ran an authorized loopback fake-server smoke. Inspect, benchmark, export, verify and offline report replay matched. |
| Browser layout and local links | Passed | Checked Chrome at 1,440, 390 and 320 CSS pixels with software rendering. Inspected desktop and mobile captures. Checked keyboard skip/focus, links, image loading, overflow and file preview. |
| Release privacy and distribution | Passed | Selected source, generated outputs and preserved wheel passed content scans. The publication surface excludes native run inputs, credentials, machine identifiers, model weights and local Git history. ZIP manifests and checksums support local integrity checks. |
| License and provenance | Passed | MIT license retained. Original charts and report screenshot, versioned dependencies and system fonts. |
| Native CUDA controlled shutdown | Not applicable | Outside read-only pilot scope. Native behavior after the patch remains unverified. |
| Public source host, canonical URL and contact | Passed | The release snapshot uses the approved repository and includes canonical Pages metadata and a GitHub Issues link. |
| Public release authorization | Passed | The owner approved release of the curated source, the verified wheel and the static Pages site. |

## Final review lenses

**Inference engineer.** The flagship places the chat burst gain next to the negative fresh-mix result. Figures provide denominators, window sizes and eligible comparisons. Setup and data disclosures distinguish per-client workers, serving slots and KV allocation. The retained sleep limitation limits endurance claims.

**Infrastructure founder.** The landing page shows what the audit measures, provides a real report, and names the conditions for a bounded staging pilot. No production guarantee, customer adoption or savings figure is claimed.

**Open-source maintainer.** The source and immutable validated wheel install separately. The compact public projection supports figure regeneration, and local raw replay needs the archived research as documented. Links, schema and safety checks run without a GPU. The working research archive stays separate from the release snapshot.

[Evidence inventory](EVIDENCE_INVENTORY.md) · [Reproduction](REPRODUCE.md) · [Publishing procedure](PUBLISH.md)
