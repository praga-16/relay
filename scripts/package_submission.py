"""Build an explicit, secret-scanned submission archive and verify extraction."""
import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from app.settings import ROOT, groq_credentials


TOP_FILES = [
    "README.md", "requirements.txt", "requirements-lock.txt", ".env.example",
    ".gitignore", "pytest.ini", "main.py", "paper_manifest.json",
    "config/default.json",
]
SOURCE_DIRECTORIES = ["app", "scripts", "tests", "papers", "data/extracted",
                      "data/indexes", "data/evaluation", "experiments"]
REPORT_FILES = [
    "report.pdf", "BUG_REGISTER.md", "FINAL_VALIDATION.md", "acceptance.md",
    "ASSIGNMENT_COMPLIANCE.md", "SUBMISSION_RELEASE.md",
    "abstention_analysis.md", "extraction_quality.md", "retrieval_comparison.md",
    "quality_rubric.md", "conversation_records.md", "website_observations.md",
    "human_review_grades.json", "pytest_final_20261112.xml",
    "pytest_final_20261112.log", "pytest_final_release_20261112.xml",
    "pytest_final_release_20261112.log",
]
LATEST_RUN = "results/revised_retriever_20261112_122922_1794486562840276600"
LATEST_RUN_FILES = [
    "results.csv", "diagnostics.jsonl", "queue_diagnostics.json",
    "phase_timings.json", "experiment_config.json",
]
FORBIDDEN_PATH_PARTS = {".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}


def _included(path):
    relative = path.relative_to(ROOT).as_posix()
    parts = set(path.relative_to(ROOT).parts)
    if parts.intersection(FORBIDDEN_PATH_PARTS):
        return False
    if path.suffix.lower() in {".pyc", ".pyo", ".tmp", ".bak", ".swp"}:
        return False
    if path.name == ".env" or (path.name.startswith(".env") and path.name != ".env.example"):
        return False
    if relative == "submission.zip" or relative.startswith("pdf/"):
        return False
    return True


def submission_files():
    files = [ROOT / name for name in TOP_FILES if (ROOT / name).is_file()]
    for folder in SOURCE_DIRECTORIES:
        directory = ROOT / folder
        if directory.is_dir():
            files.extend(path for path in directory.rglob("*") if path.is_file() and _included(path))
    for name in ("results/results.csv", "results/results_ungraded.csv"):
        if (ROOT / name).is_file():
            files.append(ROOT / name)
    for name in LATEST_RUN_FILES:
        path = ROOT / LATEST_RUN / name
        if path.is_file():
            files.append(path)
    for name in REPORT_FILES:
        path = ROOT / "reports" / name
        if path.is_file():
            files.append(path)
    prompt = ROOT / "reports/prompt_records/final_build_instruction.txt"
    if prompt.is_file():
        files.append(prompt)
    return sorted(set(path for path in files if _included(path)))


def _secret_findings(files, key):
    findings = []
    key_bytes = key.encode() if key else None
    key_pattern = re.compile(rb"gsk_[A-Za-z0-9_-]{20,}")
    for path in files:
        content = path.read_bytes()
        try:
            label = path.relative_to(ROOT).as_posix()
        except ValueError:
            label = path.as_posix()
        if key_bytes and key_bytes in content:
            findings.append(label + ": configured key detected")
        if key_pattern.search(content):
            findings.append(label + ": key-like value detected")
    return findings


def _verify_members(names):
    for name in names:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError(f"Unsafe archive path: {name}")
        parts = set(path.parts)
        if parts.intersection(FORBIDDEN_PATH_PARTS) or path.suffix.lower() in {".pyc", ".pyo", ".tmp", ".bak", ".swp"}:
            raise RuntimeError(f"Forbidden cache or temporary file in archive: {name}")
        if path.name == ".env" or (path.name.startswith(".env") and path.name != ".env.example"):
            raise RuntimeError(f"Environment file in archive: {name}")
        if name.startswith("pdf/"):
            raise RuntimeError(f"Original PDF directory must not be packaged: {name}")


def main():
    try:
        key, _ = groq_credentials()
    except RuntimeError:
        key = None

    files = submission_files()
    required = {
        "README.md", "reports/report.pdf", "reports/BUG_REGISTER.md",
        "reports/FINAL_VALIDATION.md", "reports/ASSIGNMENT_COMPLIANCE.md", "reports/acceptance.md",
        "reports/human_review_grades.json", "reports/abstention_analysis.md",
        "reports/retrieval_comparison.md", "results/results.csv",
        f"{LATEST_RUN}/results.csv", f"{LATEST_RUN}/diagnostics.jsonl",
        "data/indexes/200.faiss", "data/indexes/500.faiss",
    }
    member_names = [path.relative_to(ROOT).as_posix() for path in files]
    missing = required.difference(member_names)
    if missing:
        raise RuntimeError("Required submission files are missing: " + ", ".join(sorted(missing)))
    findings = _secret_findings(files, key)
    if findings:
        raise RuntimeError("Source secret scan failed: " + ", ".join(findings))

    descriptor, temporary_zip_name = tempfile.mkstemp(prefix=".relay-submission-", suffix=".zip", dir=ROOT)
    os.close(descriptor)
    temporary_zip = Path(temporary_zip_name)
    try:
        with zipfile.ZipFile(temporary_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(ROOT).as_posix())

        with zipfile.ZipFile(temporary_zip, "r") as archive:
            names = archive.namelist()
            _verify_members(names)
            if len(names) != len(set(names)):
                raise RuntimeError("Duplicate archive member names")
            zip_findings = []
            key_bytes = key.encode() if key else None
            key_pattern = re.compile(rb"gsk_[A-Za-z0-9_-]{20,}")
            for name in names:
                content = archive.read(name)
                if key_bytes and key_bytes in content:
                    zip_findings.append(name + ": configured key detected")
                if key_pattern.search(content):
                    zip_findings.append(name + ": key-like value detected")
            if zip_findings:
                raise RuntimeError("Actual ZIP secret scan failed: " + ", ".join(zip_findings))

            with tempfile.TemporaryDirectory(prefix="relay-zip-verify-") as directory:
                extraction_root = Path(directory)
                archive.extractall(extraction_root)
                extracted = sorted(path.relative_to(extraction_root).as_posix()
                                   for path in extraction_root.rglob("*") if path.is_file())
                if extracted != sorted(names):
                    raise RuntimeError("Fresh extraction contents do not match archive members")
                extracted_paths = [extraction_root / name for name in extracted]
                extracted_findings = _secret_findings(extracted_paths, key)
                if extracted_findings:
                    raise RuntimeError("Extracted ZIP secret scan failed")

        target = ROOT / "submission.zip"
        os.replace(temporary_zip, target)
        audit = {
            "archive": target.name,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "member_count": len(member_names),
            "actual_zip_secret_scan": "PASS",
            "fresh_temporary_extraction": "PASS",
            "extracted_member_count": len(extracted),
            "configured_key_present_in_environment": bool(key),
            "secrets_found": 0,
            "original_pdf_directory_included": False,
            "virtual_environment_or_cache_included": False,
            "indexes_included_because_runtime_requires_them": True,
            "historical_measurements_overwritten": False,
        }
        (ROOT / "reports/package_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        print(f"Packaged and verified {len(member_names)} files; ZIP and extracted-content secret scans passed.")
    finally:
        if temporary_zip.exists():
            temporary_zip.unlink()


if __name__ == "__main__":
    main()
