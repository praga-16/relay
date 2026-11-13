"""Build the two-page report from the latest preserved evaluation artifacts."""
import csv
import json
import math
import re
import statistics
from pathlib import Path
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

from app.settings import ROOT


RUN = ROOT / "results/revised_retriever_20261112_122922_1794486562840276600"
HEADINGS = [
    "1 What I built and why.",
    "2 The real service and my stand-in.",
    "3 Results.",
    "4 Where the time goes.",
    "5 When a limit is hit.",
    "6 Retrieval: quality versus cost.",
    "7 How this library will mislead a naive retriever.",
    "8 Your feedback on Vaani.",
    "9 Retries.",
    "10 What the person sees.",
    "11 What I'm unsure about, what I left out, what I learned.",
    "How I worked with the assistant.",
]


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def main():
    review = json.loads((ROOT / "reports/human_review_grades.json").read_text(encoding="utf-8"))
    phase = json.loads((RUN / "phase_timings.json").read_text(encoding="utf-8"))
    queue = json.loads((RUN / "queue_diagnostics.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((RUN / "results.csv").open(encoding="utf-8", newline="")))
    if len(review["records"]) != 60 or len(rows) != 60 or len(phase) != 60 or len(queue) != 60:
        raise ValueError("The latest revised evaluation must have 60 rows in every diagnostic.")
    test_xml_files = sorted(ROOT.glob("reports/pytest_final_release_*.xml"), key=lambda path: path.stat().st_mtime)
    if not test_xml_files:
        raise FileNotFoundError("Run and record the final-release test suite before building the report.")
    test_xml = test_xml_files[-1]
    suite = ET.parse(test_xml).getroot().find(".//testsuite")
    if suite is None:
        raise ValueError("Final-release test XML has no testsuite.")
    test_count = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0)) + int(suite.attrib.get("errors", 0))
    test_log_bytes = test_xml.with_suffix(".log").read_bytes()
    test_log = (test_log_bytes.decode("utf-16", errors="replace") if b"\x00" in test_log_bytes[:64]
                else test_log_bytes.decode("utf-8", errors="replace"))
    warning_match = re.search(r"\d+ passed,\s*(\d+) warnings?", test_log)
    warning_count = warning_match.group(1) if warning_match else "not recorded"

    historical = list(csv.DictReader((ROOT / "results/results.csv").open(encoding="utf-8", newline="")))
    smoke = next((r for r in historical if r["source"] == "real" and r["scenario"] == "Smoke"), None)
    baseline = [r for r in historical if r["source"] == "real" and r["scenario"] == "Real baseline"]
    successful = [r for r in baseline if r["status"] == "ok" and r["tokens_in"] and r["tokens_out"]]
    failed = [r for r in baseline if r["status"] != "ok"]
    if smoke is None or len(successful) != 2 or len(failed) != 1:
        raise ValueError("Historical real-provider sample records do not match the preserved evidence.")

    def real_sample(row):
        return (f"{int(row['tokens_in']):,}/{int(row['tokens_out']):,} tokens, "
                f"{float(row['first_token_ms']):.0f}/{float(row['total_ms']):.0f} ms")

    grade_counts = review["grade_counts"]
    by_setting = {}
    for setting in "ABC":
        grades = [r for r in review["records"] if r["retrieval_setting"] == setting]
        timing = [r for r in phase if next(x["retrieval_setting"] for x in rows if x["request_id"] == r["request_id"]) == setting]
        csv_rows = [r for r in rows if r["retrieval_setting"] == setting]
        citations = [c for r in grades for c in r["citations"]]
        input_tokens = [int(r["tokens_in"]) for r in csv_rows if r["tokens_in"]]
        output_tokens = [int(r["tokens_out"]) for r in csv_rows if r["tokens_out"]]
        answerable = sum(r["answerable_in_three_papers"] for r in grades)
        unanswerable = len(grades) - answerable
        by_setting[setting] = {
            "records": grades,
            "complete_evidence": sum(r["retrieved_evidence_completeness"] == "complete" for r in grades if r["answerable_in_three_papers"]),
            "relevant_requests": sum(r["passage_relevance"] == "materially_relevant" for r in grades),
            "correct_answers": sum(r["grade"] == "correct" for r in grades),
            "answerable": answerable,
            "unanswerable": unanswerable,
            "correct_refusals": sum(r["grade"] == "refused_correctly" for r in grades),
            "wrong_refusals": sum(r["grade"] == "refused_wrongly" for r in grades),
            "exact_quotes": sum(c["quote_exact_in_source_pdf_page_text"] for c in citations),
            "citation_count": len(citations),
            "retrieval_p50": statistics.median(r["retrieval_ms"] for r in timing),
            "retrieval_p95": percentile([r["retrieval_ms"] for r in timing], 0.95),
            "verification_p50": statistics.median(r["verification_ms"] for r in timing if r["verification_ms"] is not None),
            "first_token_p50": statistics.median(r["first_token_ms"] for r in timing if r["first_token_ms"] is not None),
            "tokens_in": sum(input_tokens),
            "tokens_out": sum(output_tokens),
            "token_requests": len(input_tokens),
        }

    abstentions = review["grade_counts"]["refused_correctly"] + review["grade_counts"]["refused_wrongly"]
    citation_audit = review["citation_audit"]
    verification_medians = [data["verification_p50"] for data in by_setting.values()]
    first_token_medians = [data["first_token_p50"] for data in by_setting.values()]
    retrieval_summary = ", ".join(
        f"{setting} {data['retrieval_p50']:.0f}/{data['retrieval_p95']:.0f}"
        for setting, data in by_setting.items()
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RelayBody", fontName="Helvetica", fontSize=8.7, leading=10.4, spaceAfter=4))
    styles.add(ParagraphStyle(name="RelayHead", fontName="Helvetica-Bold", fontSize=10, leading=11.5, spaceBefore=5, spaceAfter=2))
    styles.add(ParagraphStyle(name="RelayTitle", fontName="Helvetica-Bold", fontSize=14, leading=16, spaceAfter=6))
    styles.add(ParagraphStyle(name="RelayCell", fontName="Helvetica", fontSize=6.8, leading=8))
    story = []

    def paragraph(text):
        story.append(Paragraph(escape(text), styles["RelayBody"]))

    def heading(text):
        story.append(Paragraph(escape(text), styles["RelayHead"]))

    def table(data, widths):
        converted = [[Paragraph(escape(str(cell)), styles["RelayCell"]) for cell in row] for row in data]
        element = Table(converted, colWidths=widths, repeatRows=1, hAlign="LEFT")
        element.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3ced9")),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.extend([element, Spacer(1, 3)])

    story.append(Paragraph("THE RELAY | Final quality evaluation | 12 November 2026", styles["RelayTitle"]))
    heading(HEADINGS[0])
    paragraph("A Windows/Python 3.11 single-process FastAPI service over three version-pinned papers. Ingestion checks source hashes; page-aware chunks feed FAISS retrieval; bounded generation is followed by exact-quote, lexical-relevance, and source-span checks. This is an inspectable orchestration baseline, not a production-ready research assistant.")
    heading(HEADINGS[1])
    paragraph(f"Groq is the real provider; the latest 20-question A/B/C evaluation used only the local stand-in. Preserved authorized real samples: smoke {real_sample(smoke)}; three RAG attempts yielded two successes ({real_sample(successful[0])}; {real_sample(successful[1])}) and one error with usage missing. These tiny samples are not tail estimates. All A/B/C figures below are stand-in/local, not Groq quality, quota, or provider-limit measurements.")
    heading(HEADINGS[2])
    paragraph(f"Final local test record: {test_count - failures} passed, {warning_count} warnings, {failures} failures. The stand-in run completed 60 requests (20 questions x A/B/C) with {abstentions} abstentions. Preliminary assistant rubric review: {grade_counts['correct']} correct, {grade_counts['wrong']} wrong, {grade_counts['refused_correctly']} refused correctly, {grade_counts['refused_wrongly']} refused wrongly. No independent human grades are claimed; confirmation remains pending.")
    heading(HEADINGS[3])
    paragraph(f"Recorded retrieval p50/p95 was {retrieval_summary} ms; verification p50 was {min(verification_medians):.1f}-{max(verification_medians):.1f} ms. Stand-in first-token p50 was {min(first_token_medians):.0f}-{max(first_token_medians):.0f} ms, mostly the configured simulated provider delay. A's retrieval p95 includes one slow/cold outlier. Local measurements do not predict network or Groq latency.")
    heading(HEADINGS[4])
    paragraph("No provider limit was hit in the revised quality run; injected failure probability was zero. Separate overload/limit scenarios exercise a simulator, not Groq. Real account limits, recovery, and quota exhaustion were not tested and are not inferred.")
    heading(HEADINGS[5])
    table([
        ["Setting", "Evidence recall", "Correct / answerable", "Correct refusal / 4", "False refusal / 16", "Exact quote / claims", "Input/output tokens"],
        *[[
            setting,
            f"{data['complete_evidence']}/16",
            f"{data['correct_answers']}/16",
            f"{data['correct_refusals']}/4",
            f"{data['wrong_refusals']}/16",
            f"{data['exact_quotes']}/{data['citation_count']}",
            f"{data['tokens_in']:,}/{data['tokens_out']:,}",
        ] for setting, data in by_setting.items()],
    ], [42, 64, 69, 72, 64, 67, 94])
    paragraph(f"Evidence recall counts answerable questions with every rubric fact in the candidate pool; relevance counts requests with at least one materially relevant passage. B retrieved more complete evidence but produced no fully correct answer; A produced the only correct answer. This single assistant-reviewed run does not establish a winner. Citation tuples match index metadata for {citation_audit['citation_metadata_matches_index']}/{citation_audit['generated_claim_count']} claims; {citation_audit['exact_quote_matches_in_cited_pdf_page_text']}/{citation_audit['generated_claim_count']} quotes exactly match cited-page text. The six exceptions are noisy H-Net p. 3 diagram strings. Full denominators and caveats are in reports/retrieval_comparison.md.")
    story.append(PageBreak())

    heading(HEADINGS[6])
    paragraph("The same terms can conceal different mechanisms: Transformer attention, Moshi audio streams, and H-Net learned chunking are not interchangeable. q14 received related H-Net content-aware text but did not reject the false comparison with fixed 500-token PDF passages. Attention and Moshi tables flatten numeric associations; H-Net diagram text can look like a quote while losing its visual structure. A valid page citation alone does not establish relevance or claim support.")
    heading(HEADINGS[7])
    paragraph("No product session or voice call was performed. An assistant text-fetch of vaani.dev showed turn-taking/language-switching material and inconsistent zero-valued animated metrics beside an approximately 450 ms p90 claim. This may be a fetch/animation artifact, not the normal visual page. A static fallback and a clear latency measurement boundary would help; this is not personal customer feedback.")
    heading(HEADINGS[8])
    retry_totals = {
        setting: sum(int(r["retries"]) for r in rows if r["retrieval_setting"] == setting)
        for setting in "ABC"
    }
    paragraph(f"The stand-in CSV records retry totals A {retry_totals['A']}, B {retry_totals['B']}, C {retry_totals['C']}. Repeated empty-claim generation did not recover q05, q13 A, or q18 A. Retries are bounded; these local outcomes do not establish how Groq retries or recovers.")
    heading(HEADINGS[9])
    paragraph("The client exposes progress, then buffers provider text until verification and sends only accepted excerpts with citations. A refusal or deadline is explicit. Because content is buffered, user-visible time is longer than provider TTFT; the UI identifies the stand-in.")
    heading(HEADINGS[10])
    paragraph("The verifier authenticates quotes and checks lexical relevance and source-span support, but does not establish semantic entailment, full answer completeness, or math/table correctness. Six diagram quotes fail exact page-text matching. The 60 grades are preliminary assistant inspection, not human judgment. Only two successful real RAG calibration samples exist; real quota/recovery and large-sample tails are unmeasured. CPU work already running in a thread cannot be forcibly cancelled; budgets are process-local; Windows memory pressure remains unresolved. This is not a production-readiness claim.")
    heading(HEADINGS[11])
    paragraph("The preserved conversation record is partial. It documents the user’s Python 3.11, source-version, budget, schema, and real-call decisions and assistant implementation work. No complete chat export, personal Vaani experience, independent human grading, or candidate learning story is inferred. See reports/conversation_records.md.")

    output = ROOT / "reports/report.pdf"
    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=30, leftMargin=30, topMargin=22, bottomMargin=22)
    doc.build(story)
    with fitz.open(output) as pdf:
        if len(pdf) > 2:
            raise RuntimeError(f"Report exceeds two pages: {len(pdf)}")
        extracted = "\n".join(page.get_text() for page in pdf)
        positions = [extracted.find(text) for text in HEADINGS]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            raise RuntimeError("Required report headings are missing or out of order.")
        qa = ROOT / "data/qa/report"
        qa.mkdir(parents=True, exist_ok=True)
        for index, page in enumerate(pdf):
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(qa / f"page-{index + 1}.png")
        page_count = len(pdf)
    print(f"Built report.pdf with {page_count} pages.")


if __name__ == "__main__":
    main()
