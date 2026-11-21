"""Recount private historical transaction evidence into a shareable aggregate."""

from argparse import ArgumentParser
from collections import Counter
from hashlib import file_digest
import json
from pathlib import Path


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def main():
    cli = ArgumentParser(description=__doc__)
    cli.add_argument("archive", type=Path)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    archive = args.archive
    names = ("requests.jsonl", "summary.json", "SLO.md")
    integrity = json.loads((archive / "integrity.json").read_text(encoding="utf-8"))
    hashes = {name: digest(archive / name) for name in names}
    if any(hashes[name] != integrity[name] for name in names):
        raise ValueError("Archive checksum mismatch")

    states = Counter()
    families = {}
    unique = set()
    with (archive / "requests.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["id"] in unique:
                raise ValueError("Duplicate transaction")
            unique.add(row["id"])
            states[row["status"]] += 1
            counts = families.setdefault(row["family"], Counter())
            counts["observed"] += 1
            counts["correct"] += bool(row["correct"])
            counts["correct_on_time"] += bool(row["correct"] and row["on_time"])
    data = {
        "scope": "Projected aggregate from the archived six-hour Qwen3-8B synthetic study",
        "source_sha256": hashes,
        "states": states,
        "families": families,
        "total": {
            key: sum(r[key] for r in families.values()) for key in ("observed", "correct", "correct_on_time")
        },
    }
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write("\n")


if __name__ == "__main__":
    main()
