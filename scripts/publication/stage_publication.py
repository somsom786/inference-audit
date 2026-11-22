"""Stage and verify a public release snapshot without copying Git history or raw runs."""

import argparse
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
SINGLE = {
    ".gitattributes",
    ".gitignore",
    ".github/workflows/ci.yml",
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "scripts/probe_vllm_prefix.py",
    "scripts/vllm_local.sh",
}
TREES = {"src", "tests", "configs", "examples", "docs", "public"}
SOURCE_REPORTS = {"local-qwen-020", "local-qwen-restart-020", "local-gemma-020"}
VALIDATION = {
    "INDEPENDENT_REPLICATION.md",
    "phase3-recount.json",
    "recount.py",
    "replicate.py",
    "replication-recount.json",
    "verify_release_capture.py",
}
TEXT_SUFFIXES = {
    ".html",
    ".svg",
    ".css",
    ".js",
    ".txt",
    ".md",
    ".json",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
    ".lock",
    ".sh",
    "",
}
SECRET = (
    (
        "provider token",
        re.compile(
            r"(?i)\b(?:sk-(?:proj-|svcacct-)?[a-z0-9_-]{22,}|gh[pousr]_[a-z0-9]{30,}|github_pat_[a-z0-9_]{40,}|AKIA[A-Z0-9]{16}|xox[baprs]-[a-z0-9-]{12,})\b"
        ),
    ),
    ("private key", re.compile(r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("bearer value", re.compile(r"(?i)\bbearer\s+[a-z0-9._~-]{24,}\b")),
    (
        "home, project or WSL path",
        re.compile(r"(?i)(?:[a-z]:[/\\]+(?:users|ai)[/\\]+|/(?:home|mnt/[a-z])/[a-z_0-9-]+[/\\])"),
    ),
    (
        "email address",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?!(?:example|invalid)\b)[A-Za-z]{2,}\b"),
    ),
)
KNOWN_HOSTS = {
    "127.0.0.1",
    "localhost",
    "json-schema.org",
    "www.w3.org",
    "creativecommons.org",
    "purl.org",
    "matplotlib.org",
    "www.json.org",
    "docs.github.com",
    "github.com",
    "docs.vllm.ai",
    "docs.nvidia.com",
    "huggingface.co",
    "www.nvidia.com",
    "somsom786.github.io",
    "www.linkedin.com",
}
URL = re.compile(r"https?://[^\s\"'<>),\x60\\]+")
EXPECTED_WHEEL = "ccfd1f812ae86ced5aea94fac9af1d5ced2fa7a32548185a827a688663851843"


def approved(relative):
    parts = relative.parts
    if relative.as_posix() in SINGLE or parts[0] in TREES or parts[:2] == ("scripts", "publication"):
        return True
    if parts[0] == "validation":
        return len(parts) == 2 and parts[1] in VALIDATION
    return (
        len(parts) == 3
        and parts[0] == "reports"
        and parts[1] in SOURCE_REPORTS
        and parts[2]
        in {
            "audit.json",
            "audit.html",
            "recount.json",
        }
    )


def select():
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT
    ).decode("utf-8")
    for name in sorted(set(output.split("\0")) - {""}):
        rel = PurePosixPath(name)
        if approved(rel):
            source = ROOT.joinpath(*rel.parts)
            if not source.is_file() or source.is_symlink() or source.resolve() != source.absolute():
                raise ValueError(f"Invalid export input: {rel}")
            if source.suffix not in TEXT_SUFFIXES | {".png"} or source.stat().st_size > 5_000_000:
                raise ValueError(f"Unexpected export input type or size: {rel}")
            yield rel, source


def scan_text(name, source):
    issues = [category for category, pattern in SECRET if pattern.search(source)]
    private_urls = []
    for match in URL.finditer(source):
        value = match.group().rstrip(".;]")
        try:
            url = urlsplit(value)
            host = url.hostname
        except ValueError:
            if name.startswith("tests/"):
                continue
            issues.append("malformed URL")
            continue
        if host in KNOWN_HOSTS or host and (host.endswith((".invalid", ".example")) or host.startswith("{")):
            if url.username and name != "tests/test_audit.py":
                issues.append("credential in URL")
        else:
            private_urls.append(host or "<unresolved>")
    if private_urls:
        issues.append("unreviewed URL hosts " + ", ".join(sorted(set(private_urls))))
    if name.startswith("public/") and name.endswith(".json"):
        if re.search(
            r'"(?:messages|content|text|authorization|api_key|host_id|hostname|prompt_text|raw_response)"\s*:',
            source,
            re.I,
        ):
            issues.append("private payload field")
    if issues:
        raise ValueError(f"{name}: {', '.join(sorted(set(issues)))}")


def digest(file):
    return sha256(file.read_bytes()).hexdigest()


def archive_tree(directory, zip_path):
    if zip_path.exists():
        raise FileExistsError(zip_path)
    files = sorted(p for p in directory.rglob("*") if p.is_file())
    with ZipFile(zip_path, "x", ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in files:
            name = path.relative_to(directory).as_posix()
            info = ZipInfo(name, date_time=(2026, 11, 19, 0, 0, 0))
            bundle.writestr(info, path.read_bytes(), compress_type=ZIP_DEFLATED, compresslevel=9)
    with ZipFile(zip_path) as bundle:
        if bundle.testzip() or len(bundle.namelist()) != len(files):
            raise ValueError(f"ZIP failed validation: {zip_path}")
        for path in files:
            archived = bundle.read(path.relative_to(directory).as_posix())
            if sha256(archived).hexdigest() != digest(path):
                raise ValueError(f"ZIP checksum mismatch: {path.name}")
    return len(files)


def review_archive(output, review_path):
    folder = review_path.with_name("Inference Audit 0.2.1 Public Proof")
    if review_path.exists() or folder.exists():
        raise FileExistsError("Use a fresh release review path.")
    shutil.copytree(output / "repository", folder / "repository")
    supporting = folder / "github-release"
    supporting.mkdir()
    for file in (output / "github-release").iterdir():
        if ".zip" not in file.name:
            shutil.copyfile(file, supporting / file.name)
    review_note = output / "repository/docs/publication/REVIEW_HANDOFF.md"
    shutil.copyfile(review_note, folder / "START_HERE.md")
    lines = [
        f"{digest(file)}  {file.relative_to(folder).as_posix()}"
        for file in sorted(folder.rglob("*"))
        if file.is_file()
    ]
    (folder / "ARCHIVE_MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    count = archive_tree(folder, review_path)
    if review_path.stat().st_size >= 512_000_000:
        raise ValueError("Review ZIP exceeds the shareable size limit")
    review_path.with_suffix(".zip.sha256").write_text(
        f"{digest(review_path)}  {review_path.name}\n", encoding="utf-8"
    )
    print(f"Verified ChatGPT review ZIP ({count} files, {review_path.stat().st_size} bytes).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/publication/release-0.2.1")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    selected = list(select())
    issues = []
    for relative, source in selected:
        if source.suffix in TEXT_SUFFIXES:
            try:
                scan_text(relative.as_posix(), source.read_text(encoding="utf-8-sig"))
            except ValueError as error:
                issues.append(str(error))
    if issues:
        raise ValueError("Publication scan failed:\n" + "\n".join(issues))
    print(f"Scanned {len(selected)} allowlisted repository files.")
    wheel = ROOT / "dist/inference_audit-0.2.1-py3-none-any.whl"
    if digest(wheel) != EXPECTED_WHEEL:
        raise ValueError("Preserved wheel checksum differs")
    with ZipFile(wheel) as bundle:
        if bundle.testzip():
            raise ValueError("Corrupt wheel")
        for name in bundle.namelist():
            if PurePosixPath(name).suffix in TEXT_SUFFIXES:
                scan_text(name, bundle.read(name).decode("utf-8"))
    if args.check_only:
        print("Preserved wheel passed checksum, CRC, and public-text checks.")
        return
    output.mkdir(parents=True, exist_ok=False)
    repository = output / "repository"
    for relative, source in selected:
        target = repository.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    payload = output / "github-release"
    payload.mkdir()
    shutil.copyfile(wheel, payload / wheel.name)
    (payload / f"{wheel.name}.sha256").write_text(f"{EXPECTED_WHEEL}  {wheel.name}\n", encoding="utf-8")
    shutil.copyfile(ROOT / "docs/publication/RELEASE_NOTES_0.2.1.md", payload / "RELEASE_NOTES.md")
    source_count = archive_tree(repository, payload / "inference-audit-0.2.1-source.zip")
    site_count = archive_tree(repository / "public", payload / "inference-audit-0.2.1-site.zip")
    for filename in sorted(payload.glob("*.zip")):
        filename.with_suffix(".zip.sha256").write_text(
            f"{digest(filename)}  {filename.name}\n", encoding="utf-8"
        )
    print(
        f"Verified source archive ({source_count} files), site archive ({site_count} files), and preserved wheel."
    )
    if args.review:
        review_archive(output, args.review.resolve())


if __name__ == "__main__":
    main()
