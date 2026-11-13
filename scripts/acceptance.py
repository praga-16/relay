"""Verify release artifacts and write the final status reports."""
import csv
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import fitz

from app.settings import ROOT
from scripts.build_report import HEADINGS, RUN
from scripts.package_submission import submission_files


EXPECTED_COLUMNS = [
    "request_id", "scenario", "source", "start_time", "first_token_ms",
    "total_ms", "status", "retries", "tokens_in", "tokens_out",
    "retrieval_setting", "answer_grade",
]
ALLOWED_STATUSES = {"PASS", "FAIL", "BLOCKED", "PARTIAL", "NOT TESTED"}


def _csv_status():
    paths = [ROOT / "results/results.csv", ROOT / "results/results_ungraded.csv"]
    paths.extend(sorted((ROOT / "results").glob("revised_retriever_*/results.csv")))
    count = 0
    for path in paths:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != EXPECTED_COLUMNS:
                return "FAIL", f"{path.relative_to(ROOT)} has a different column schema"
            for row in reader:
                if None in row or set(row) != set(EXPECTED_COLUMNS):
                    return "FAIL", f"{path.relative_to(ROOT)} contains a malformed row"
                count += 1
    return "PASS", f"{count} rows across {len(paths)} historical/current CSV files have the exact 12-column schema"


def _latest_run_status():
    records = [json.loads(line) for line in (RUN / "diagnostics.jsonl").read_text(encoding="utf-8").splitlines()]
    config = json.loads((RUN / "experiment_config.json").read_text(encoding="utf-8"))
    if len(records) != 60 or len({record["evaluation_id"] for record in records}) != 20:
        return "FAIL", "Latest run does not contain 60 requests across 20 questions"
    if config.get("retrieval_settings") != ["A", "B", "C"] or config.get("source") != "stand-in":
        return "FAIL", "Latest run configuration does not identify the expected stand-in A/B/C evaluation"
    for name in ("queue_diagnostics.json", "phase_timings.json"):
        if len(json.loads((RUN / name).read_text(encoding="utf-8"))) != 60:
            return "FAIL", f"{name} does not contain 60 records"
    return "PASS", "60 stand-in requests cover 20 question IDs under A/B/C; separate queue, phase, and experiment diagnostics are present"


def _grade_status():
    artifact = json.loads((ROOT / "reports/human_review_grades.json").read_text(encoding="utf-8"))
    records = artifact["records"]
    allowed = {"correct", "wrong", "refused_correctly", "refused_wrongly", "pending_review"}
    if len(records) != 60 or len({record["request_id"] for record in records}) != 60:
        return "FAIL", "Grade artifact does not contain one unique record for each request"
    if any(record["grade"] not in allowed for record in records):
        return "FAIL", "Grade artifact contains an unsupported grade"
    citation_audit = artifact["citation_audit"]
    if citation_audit["generated_claim_count"] != 85 or citation_audit["citation_metadata_matches_index"] != 85:
        return "FAIL", "Citation/index audit does not match the recorded 85 claims"
    if artifact["human_review_status"] != "pending":
        return "FAIL", "Human-review status is not explicit"
    counts = artifact["grade_counts"]
    summary = ", ".join(f"{counts[key]} {key}" for key in ("correct", "wrong", "refused_correctly", "refused_wrongly", "pending_review"))
    return "PARTIAL", f"Assistant preliminary grades: {summary}; independent human review remains pending"


def _test_status():
    candidates = sorted(ROOT.glob("reports/pytest_final_release_*.xml"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        return "NOT TESTED", "No final-release pytest XML record exists"
    path = candidates[-1]
    root = ET.parse(path).getroot()
    suite = root.find(".//testsuite")
    if suite is None:
        return "FAIL", "Final pytest XML has no testsuite"
    tests = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    skipped = int(suite.attrib.get("skipped", 0))
    log_path = path.with_suffix(".log")
    warnings = None
    if log_path.is_file():
        raw_log = log_path.read_bytes()
        log_text = (raw_log.decode("utf-16", errors="replace") if b"\x00" in raw_log[:64]
                    else raw_log.decode("utf-8", errors="replace"))
        match = re.search(r"(\d+) passed,\s*(\d+) warnings?", log_text)
        if match:
            warnings = int(match.group(2))
    if failures or errors:
        return "FAIL", f"{tests} tests; {failures} failures; {errors} errors; {skipped} skipped"
    return "PASS", f"{tests - skipped} passed, {warnings if warnings is not None else 'warning count not recorded'} warnings, 0 failures ({path.relative_to(ROOT)})"


def _report_status():
    path = ROOT / "reports/report.pdf"
    if not path.is_file():
        return "FAIL", "reports/report.pdf is missing"
    with fitz.open(path) as document:
        text = "\n".join(page.get_text() for page in document)
        if len(document) > 2:
            return "FAIL", f"Report has {len(document)} pages"
        positions = [text.find(heading) for heading in HEADINGS]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            return "FAIL", "Required headings are missing or out of order"
        return "PASS", f"Report has {len(document)} pages and all 12 required headings in order"


def _package_status():
    archive_path = ROOT / "submission.zip"
    audit_path = ROOT / "reports/package_audit.json"
    if not archive_path.is_file() or not audit_path.is_file():
        return "NOT TESTED", "No verified final ZIP and package audit are present"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    current_files = submission_files()
    current = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in current_files}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            if names != set(current):
                return "FAIL", "ZIP member list differs from the current allowlist"
            for name, content in current.items():
                if archive.read(name) != content:
                    return "FAIL", f"ZIP contains stale content for {name}"
            if any(name == ".env" or name.startswith(".env/") or name.startswith("pdf/") for name in names):
                return "FAIL", "ZIP includes a forbidden environment or original-PDF path"
            for name in names:
                if re.search(rb"gsk_[A-Za-z0-9_-]{20,}", archive.read(name)):
                    return "FAIL", f"ZIP member {name} contains a key-like string"
    except (OSError, zipfile.BadZipFile) as error:
        return "FAIL", f"Cannot read final ZIP: {error}"
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if audit.get("sha256") != digest or audit.get("actual_zip_secret_scan") != "PASS" or audit.get("fresh_temporary_extraction") != "PASS":
        return "FAIL", "Package audit does not verify the current ZIP"
    return "PASS", f"{len(current)} current allowlisted members; fresh extraction and actual ZIP secret scan passed"


def main():
    statuses = {
        "Regression suite": _test_status(),
        "Results CSV schema": _csv_status(),
        "Latest A/B/C run": _latest_run_status(),
        "Grading and citation audit": _grade_status(),
        "Two-page report": _report_status(),
        "PDF extraction": ("PARTIAL", "Known table/math/diagram defects remain; six figure quotes are not exact page-text matches"),
        "Semantic verification": ("PARTIAL", "Lexical relevance and verbatim source-span checks do not prove entailment or completeness"),
        "Real provider limits and quality": ("NOT TESTED", "No new Groq evaluation, quota exhaustion, or provider-limit test was run"),
        "Submission ZIP": _package_status(),
    }
    if any(status not in ALLOWED_STATUSES for status, _ in statuses.values()):
        raise ValueError("An acceptance result uses an unsupported final status")
    lines = [
        "# Acceptance",
        "",
        "Final local release gate. PASS means only that the recorded artifact/test check passed; it is not production readiness or semantic correctness.",
        "",
        "| Check | Status | Evidence |",
        "|---|---|---|",
    ]
    for name, (status, evidence) in statuses.items():
        lines.append(f"| {name} | {status} | {evidence} |")
    lines.extend([
        "",
        "## Unresolved issues",
        "",
        "* Independent human grading is pending; the 60 labels are preliminary assistant inspection.",
        "* Semantic entailment, full answer completeness, math/table interpretation, and section-boundary correctness are not established.",
        "* Six H-Net p. 3 diagram-derived quotes are not exact page-text matches; other extraction limits are documented in `extraction_quality.md`.",
        "* Real Groq quota/recovery/concurrency behavior, real A/B/C quality, and large-sample real latency tails were not tested.",
        "* BR-11 through BR-14 and BR-19 remain known operational limitations; see `BUG_REGISTER.md`.",
        "",
        "Release readiness: PARTIAL. The validated package can be reviewed, but it is not presented as production-ready or semantically perfect.",
        "",
    ])
    (ROOT / "reports/acceptance.md").write_text("\n".join(lines), encoding="utf-8")

    bug_register = (ROOT / "reports/BUG_REGISTER.md").read_text(encoding="utf-8")
    unresolved = [
        line.split("|")[1].strip()
        for line in bug_register.splitlines()
        if line.startswith("| BR-") and line.split("|")[-2].strip() in {"PARTIAL", "NOT TESTED", "BLOCKED", "FAIL"}
    ]
    validation = [
        "# Final validation",
        "",
        "The release is reviewed against recorded local evidence. This status is not a production-readiness claim.",
        "",
        "| Check | Status | Evidence |",
        "|---|---|---|",
    ]
    for name, (status, evidence) in statuses.items():
        validation.append(f"| {name} | {status} | {evidence} |")
    validation.extend([
        "",
        "## Unresolved bug register entries",
        "",
        (", ".join(unresolved) if unresolved else "None."),
        "",
        "## Release decision",
        "",
        "PARTIAL. The two-page report and allowlisted ZIP are checked when their rows above say PASS. Human answer grading, semantic entailment, PDF extraction limitations, real Groq behavior, and the operational items listed above remain unresolved or untested. No upload or submission was performed.",
        "",
    ])
    (ROOT / "reports/FINAL_VALIDATION.md").write_text("\n".join(validation), encoding="utf-8")

    print("Acceptance report written:")
    for name, (status, evidence) in statuses.items():
        print(f"{status}: {name} — {evidence}")


if __name__ == "__main__":
    main()
