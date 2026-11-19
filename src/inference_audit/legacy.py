"""Import published Phase 1–3 summaries without mutating the source project."""

import csv
import math
from pathlib import Path
import re
from typing import Any

from .evidence import atomic, bounded_file, digest, new_directory, read

SOURCES = {
    1: "results/summary.csv",
    2: "phase2/data/service.csv",
    3: "phase3/results/endurance-segmented/summary.csv",
}
COLUMNS = {
    1: (
        "run",
        "valid_for_comparison",
        "decode_tps",
        "c2_tps",
        "prefill_4096_tps",
        "prefill_7168_tps",
        "peak_device_mib",
    ),
    2: (
        "launch",
        "status",
        "requests",
        "success",
        "req_s",
        "output_tok_s",
        "ttft_p95_s",
        "e2e_p95_s",
        "slo_goodput",
        "peak_vram_mib",
    ),
    3: (
        "stage",
        "window",
        "family",
        "offered",
        "completed",
        "valid",
        "on_time",
        "output_tps",
        "ttft_p95",
        "e2e_p95",
        "goodput_rps",
        "peak_mib",
    ),
}
WARNINGS = {
    1: "Published Phase 1 summary. Comparison eligibility comes from the historical adjudication.",
    2: "Published Phase 2 summary. Different workload revisions and profiles must be interpreted separately.",
    3: "Published Phase 3 segmented result. The original A2 crossed a sleep boundary and is excluded. This does not establish uninterrupted endurance.",
}


def clean(value: str) -> str | float | None:
    try:
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    except ValueError:
        return value if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value) else None


def import_summary(source: Path, phase: int, run: Path) -> None:
    selected = source / SOURCES[phase]
    bounded_file(selected, 10_000_000)
    before = digest(selected)
    with selected.open(encoding="utf-8-sig", newline="") as file:
        csv_rows = csv.DictReader(file)
        headers = csv_rows.fieldnames or []
        if len(headers) != len(set(headers)) or not set(COLUMNS[phase]) <= set(headers):
            raise ValueError("Legacy summary columns do not match the selected phase.")
        values = [{k: clean(r[k] or "") for k in COLUMNS[phase]} for r in csv_rows]
    if not values or before != digest(selected):
        raise ValueError("Legacy summary is empty or changed during import.")
    data = {
        "schema": 1,
        "source": "legacy_summary",
        "phase": phase,
        "rows": values,
        "columns": COLUMNS[phase],
        "source_relative": SOURCES[phase],
        "origin_sha256": before,
        "caveat": WARNINGS[phase],
        "state": "imported summary, original evidence not revalidated",
    }
    new_directory(run)
    atomic(run / "legacy.json", data)
    atomic(run / "legacy-integrity.json", {"sha256": digest(run / "legacy.json")})


def verify_import(run: Path) -> dict[str, Any]:
    checksum = read(run / "legacy-integrity.json", 4096)
    bounded_file(run / "legacy.json", 24_000_000)
    if digest(run / "legacy.json") != checksum.get("sha256"):
        raise ValueError("Imported summary digest mismatch.")
    data = read(run / "legacy.json", 24_000_000)
    phase = data.get("phase")
    if (
        data.get("schema") != 1
        or data.get("source") != "legacy_summary"
        or type(phase) is not int
        or phase not in SOURCES
        or data.get("source_relative") != SOURCES[phase]
        or data.get("caveat") != WARNINGS[phase]
        or data.get("state") != "imported summary, original evidence not revalidated"
        or not re.fullmatch(r"[a-f0-9]{64}", data.get("origin_sha256", ""))
        or data.get("columns") != list(COLUMNS[phase])
        or not isinstance(data.get("rows"), list)
        or not all(
            isinstance(row, dict)
            and set(row) == set(COLUMNS[phase])
            and all(
                value is None
                or type(value) in (int, float)
                and -math.inf < value < math.inf
                or isinstance(value, str)
                and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value)
                for value in row.values()
            )
            for row in data["rows"]
        )
    ):
        raise ValueError("Invalid historical summary schema.")
    return {
        key: data[key]
        for key in (
            "schema",
            "source",
            "phase",
            "columns",
            "rows",
            "source_relative",
            "origin_sha256",
            "caveat",
            "state",
        )
    }
