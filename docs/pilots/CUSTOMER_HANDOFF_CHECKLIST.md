# Customer Handoff & Closeout Checklist

Use this checklist at the end of every free staging assessment or paid optimization sprint.

---

## 1. Evidence & Integrity
- [ ] Every reported run passed `inference-audit verify --run <run-name>` with zero digest or schema errors.
- [ ] `audit.html`, `audit.md`, and executive summary report match the verified JSON numbers exactly.
- [ ] All failures, timeouts, context rejections, and quality errors remain visible in the denominator.
- [ ] Any observability gaps, scrape failures, counter resets, or series truncations are explicitly disclosed.

## 2. Security & Privacy Cleanliness
- [ ] Confirmed zero API keys, bearer tokens, raw customer prompts, or raw Prometheus label values exist in any delivered file.
- [ ] Confirmed customer revoked temporary staging credentials and closed any temporary firewall/staging access.
- [ ] Confirmed zero customer artifacts or private correspondence were placed in any public Git repository.

## 3. Handoff Package Delivered
- [ ] Executive Staging Assessment Report (Markdown / PDF / HTML).
- [ ] Self-contained offline `audit.html` and `audit.md` for each run.
- [ ] Sealed evidence folder (`plan.json`, `checkpoint.json`, `events.jsonl`, `gpu.jsonl`, `server.jsonl`, `integrity.json`) + verification commands.
- [ ] Exact config diff and rollback checklist (if paid optimization sprint).

## 4. Commercial & Retention Closeout
- [ ] Walkthrough call scheduled (15–30 minutes) to review findings and answer engineering questions.
- [ ] If clear optimization upside exists, attach `OPTIMIZATION_PROPOSAL_TEMPLATE.md` as an optional next step.
- [ ] Record 30-day private data deletion date (unless customer requests retention for an active follow-on engagement).
