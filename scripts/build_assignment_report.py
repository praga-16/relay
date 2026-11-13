"""Create the compact assignment-compliant two-page report from preserved evidence."""
import csv, json, math, statistics, xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape
import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from app.settings import ROOT

RUN = ROOT / "results/revised_retriever_20261112_122922_1794486562840276600"
HEADINGS = [
    "1 What I built and why.", "2 The real service and my stand-in.", "3 Results.",
    "4 Where the time goes.", "5 When a limit is hit.", "Retrieval: quality versus cost.",
    "How this library will mislead a naive retriever.", "Your feedback on Vaani.",
    "6 Retries.", "7 What the person sees.",
    "8 What I'm unsure about, what I left out, what I learned.",
    "How I worked with the assistant.",
]
SCENARIOS = ["Steady", "Burst", "Sustained overload", "Per-minute limit halved", "Daily budget exhausted"]

def pct(values, fraction):
    values = sorted(values)
    if not values: return None
    p = (len(values)-1)*fraction; a, b = math.floor(p), math.ceil(p)
    return values[a] + (values[b]-values[a])*(p-a)

def n(value): return "not measured" if value is None else f"{value:.1f}"
def triple(d): return " / ".join(n(d[k]) for k in ("p50", "p95", "p99"))
def pair(values): return f"{n(statistics.median(values))} / {n(pct(values,.95))}"

def footer(canvas, doc):
    canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#1d4f7a")); canvas.line(30, 23, A4[0]-30, 23)
    canvas.setFont("Helvetica", 6.5); canvas.setFillColor(colors.HexColor("#335b7c"))
    canvas.drawString(30, 13, "THE RELAY | assignment evidence report | stand-in results explicitly labelled")
    canvas.drawRightString(A4[0]-30, 13, f"Page {doc.page}"); canvas.restoreState()

def main():
    summary = json.loads((ROOT / "results/summary.json").read_text(encoding="utf-8"))
    outcome = {r["scenario"]: r for r in summary["outcome_tables"]}
    experiments = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "experiments").glob("*.json")]
    review = json.loads((ROOT / "reports/human_review_grades.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((RUN / "results.csv").open(encoding="utf-8", newline="")))
    phase = json.loads((RUN / "phase_timings.json").read_text(encoding="utf-8"))
    phase_by_id = {r["request_id"]: r for r in phase}
    tests = ET.parse(ROOT / "reports/pytest_final_release_20261112.xml").getroot().find(".//testsuite")
    test_text = (ROOT / "reports/pytest_final_release_20261112.log").read_text(encoding="utf-8", errors="replace")
    test_count, failures = int(tests.attrib["tests"]), int(tests.attrib["failures"])+int(tests.attrib["errors"])
    warning_count = 7 if "7 warnings" in test_text else "not measured"

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="T", fontName="Helvetica-Bold", fontSize=13.2, leading=14.5, textColor=colors.HexColor("#123a5d"), spaceAfter=4))
    styles.add(ParagraphStyle(name="H", fontName="Helvetica-Bold", fontSize=9.5, leading=11.1, textColor=colors.HexColor("#123a5d"), spaceBefore=5.5, spaceAfter=2.2))
    styles.add(ParagraphStyle(name="B", fontName="Helvetica", fontSize=9.0, leading=10.7, spaceAfter=4.8))
    styles.add(ParagraphStyle(name="C", fontName="Helvetica", fontSize=6.2, leading=7.35))
    styles.add(ParagraphStyle(name="K", fontName="Helvetica-Bold", fontSize=7.0, leading=8.2, textColor=colors.HexColor("#123a5d")))
    styles.add(ParagraphStyle(name="D", fontName="Helvetica", fontSize=6.75, leading=8.0))
    story=[]
    def h(t): story.append(Paragraph(escape(t), styles["H"]))
    def p(t): story.append(Paragraph(escape(t), styles["B"]))
    def table(data, widths):
        cells=[[Paragraph(escape(str(x)),styles["C"]) for x in row] for row in data]
        x=Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        x.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dceaf6")),("TEXTCOLOR",(0,0),(-1,0),colors.HexColor("#123a5d")),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#b9cede")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),("TOPPADDING",(0,0),(-1,-1),1.4),("BOTTOMPADDING",(0,0),(-1,-1),1.4)]))
        story.extend([x, Spacer(1,2)])
    def callout(data, widths):
        cells=[[Paragraph(escape(str(x)), styles["K"] if row == 0 else styles["D"])
                for x in items] for row, items in enumerate(data)]
        x=Table(cells, colWidths=widths, hAlign="LEFT")
        x.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#dceaf6")),
            ("BACKGROUND",(0,1),(-1,-1),colors.HexColor("#f6f9fc")),
            ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#8fb1ca")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),
            ("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.extend([x, Spacer(1,5)])

    story.append(Paragraph("THE RELAY | evidence-first RAG orchestration", styles["T"]))
    h(HEADINGS[0]); p("Python 3.11/FastAPI service over three hash-pinned arXiv papers. Intent -> page-aware FAISS retrieval tool -> evidence decision -> provider/stand-in -> quote/citation verification -> SSE answer or refusal. The shaping decision is to refuse rather than invent evidence: performance work never drops essential evidence merely to reduce tokens.")
    table([["REQUEST", "INTENT", "RETRIEVE", "DECIDE", "GENERATE", "VERIFY / SSE"], ["deadline/id", "topic/type", "FAISS + A/B/C", "expand/refuse", "Groq or stand-in", "quotes/pages"]],[81,72,90,72,93,104])
    h(HEADINGS[1]); p("Real provider: Groq openai/gpt-oss-20b. Preserved authorized data: one smoke and three baseline attempts; two completed samples calibrated stand-in first-content delay/stream cadence. Stand-in additionally injects load delay, 5xx, 429, daily exhaustion and streaming; those behaviours are synthetic and are least like real concurrent provider behaviour.")
    table([["Table 1: real-service limit", "Value found", "How found", "Confidence"], ["Requests/min", "30", "user-confirmed account page", "medium"], ["Tokens/min", "8,000", "user confirmation + headers", "high"], ["Requests/day", "1,000", "user-confirmed account page", "medium"], ["Tokens/day", "200,000", "user-confirmed account page", "medium"], ["In flight", "not measured", "not induced", "low"], ["Limit response", "not measured", "real 429 not induced", "low"], ["Recovery", "not measured", "real reset not induced", "low"]],[105,108,208,111])
    h(HEADINGS[2]); p(f"Final local tests: {test_count-failures} passed, {warning_count} warnings, {failures} failures. Revised evaluation: 60 stand-in requests (20 questions x A/B/C); preliminary assistant review is 1 correct, 45 wrong, 9 correctly refused, 5 wrongly refused. These are not independent human grades or semantic-accuracy scores. Table sources: results.csv + experiments JSON; duration/rate/queue are supplementary because the required CSV lacks those fields.")
    scenario_experiments = [e for e in experiments if "scenario" in e]
    table([["Table 2a: scenario", "Source", "N", "Duration s", "Offered/min", "First p50/p95/p99 ms", "Total p50/p95/p99 ms"]] + [[s, outcome[s]["source"], outcome[s]["requests"], n(sum(e["duration_s"] for e in scenario_experiments if e["scenario"]==s)), n(sum(e["offered_requests"] for e in scenario_experiments if e["scenario"]==s)/sum(e["duration_s"] for e in scenario_experiments if e["scenario"]==s)*60), triple(outcome[s]["first_token_ms"]), triple(outcome[s]["total_ms"])] for s in SCENARIOS], [104,42,20,47,52,131,136])
    table([["Table 2b: scenario", "Success %", "Limited %", "Timeout/give-up %", "Retries/req", "Peak queue", "Tokens/answer", "Cost/1k"]] + [[s, n(outcome[s]["success_pct"]), n(outcome[s]["rate_limited_pct"]), n(outcome[s]["timeout_given_up_pct"]), n(outcome[s]["retries_per_request"]), max(e["peak_queue_length"] for e in scenario_experiments if e["scenario"]==s), n(outcome[s]["tokens_per_successful_answer"]), "not measured"] for s in SCENARIOS], [104,52,52,71,54,48,66,63])
    h(HEADINGS[3]); p("Slow real baseline: incomplete-stream request ae2eb56d took 1,137.3 ms total. Queue wait 0.2 ms; retrieval 20.3 ms; retry wait 0.0 ms; remaining 1,116.9 ms was provider/verification/delivery work. No provider content token arrived, so its first-content-token phase is not measured; the visible error was delayed before first useful content. This is a diagnostic residual, not an attribution of provider internal work.")
    h(HEADINGS[4]); p("Per-minute reservation, token reservation, bounded FIFO, deadline, semaphore, retry cap and circuit breaker protect callers. Under stand-in daily exhaustion, 87.5% of 16 requests were rate-limited; queued/new callers get an explicit unavailable status, not a weaker answer. At a real 3 PM exhausted budget, the same local response is intended, but real Groq daily exhaustion was not induced.")
    callout([["EVIDENCE-FIRST", "OVERLOAD POLICY", "MEASUREMENT DISCIPLINE"],
             ["Only source spans with paper/page citations are returned. Missing library evidence becomes a refusal.",
              "Reserve capacity before calls; bound queue and retries; surface rate-limit/deadline outcomes instead of a weaker answer.",
              "Real observations, local stand-in results, preliminary grades, and unmeasured fields are labelled separately."]], [166,166,166])
    callout([["OBSERVED LOCAL LOAD SIGNAL", "WHAT IT MEANS FOR THE DESIGN"],
             ["Steady: 58.3% completed; peak queue 4.", "The bounded queue absorbs a small burst, but the 1.5 s request deadline still gives up slow work."],
             ["Burst: 76.9% limited; peak queue 15.", "Admission control rejects excess work promptly instead of allowing an unbounded queue to make every caller wait."],
             ["Daily exhaustion: 87.5% limited; peak queue 1.", "Daily-budget checks happen before provider work, so unavailable capacity is explicit and does not consume more tokens."]], [170,328])
    story.append(PageBreak())
    h(HEADINGS[5]);
    rtable=[]
    for setting, spec in [("A","200 / 3 / no"),("B","500 / 5 / no"),("C","500 / 5 / hybrid")]:
        grade=[x for x in review["records"] if x["retrieval_setting"]==setting]; req=[x for x in rows if x["retrieval_setting"]==setting]; timings=[phase_by_id[x["request_id"]] for x in req]
        valid=[x for x in req if x["tokens_in"] and x["tokens_out"]]; tokens=sum(int(x["tokens_in"])+int(x["tokens_out"]) for x in valid)
        rtable.append([f"{setting}: {spec}",20,f"{sum(x['grade']=='correct' for x in grade)/20*100:.1f}%",f"{sum(x['grade']=='wrong' for x in grade)/20*100:.1f}%",f"{sum(x['grade']=='refused_correctly' for x in grade)/20*100:.1f}%",f"{tokens/len(valid):.0f} ({len(valid)}/20)",pair([x['first_token_ms'] for x in timings]),pair([x['total_ms'] for x in timings])])
    table([["Table 3: setting", "Questions", "Correct+cited*", "Wrong*", "Correct refusal*", "Tokens/answer", "First p50/p95", "Total p50/p95"]]+rtable,[102,38,61,43,65,72,75,75])
    p("*Preliminary assistant rubric review; not independent human grading. C is hybrid normalized FAISS+BM25. B had higher complete-evidence recall (13/16 answerable questions) but no independently defensible winner; choose B only as a retrieval-evidence candidate, not a quality claim. Near limits, retain evidence and reject work conservatively rather than silently reducing it.")
    callout([["EVALUATION AUDIT", "WHAT THE NUMBER SUPPORTS", "WHAT IT DOES NOT SUPPORT"],
             ["79/85 generated quote strings matched normalized cited-page text.", "Citation location and source-span metadata are largely mechanically traceable.", "A claim of semantic entailment, complete answer coverage, or correct table interpretation."],
             ["Six unmatched strings came from H-Net p. 3 diagram extraction.", "The source PDF visual should be inspected when diagrams/equations carry the fact.", "Treating diagram text-layer noise as an authentic verbatim quote."]], [166,166,166])
    h(HEADINGS[6]); p("Three traps: q04's Transformer warmup can retrieve Moshi's unrelated training rates; q14 confuses H-Net learned sequence segmentation with fixed PDF chunks; q17 overreads Moshi Inner Monologue as every LLM's private reasoning. Flattened Attention/Moshi tables detach headers from values; H-Net p.3 diagram labels create six non-exact quote strings. Authentic page metadata is not semantic support.")
    h(HEADINGS[7]); p("Recorded assistant text-fetch, not a personal product session: Vaani's turn-taking/language-switching framing stood out; zero-valued animated metrics beside an approximately 450 ms p90 claim were confusing and may be a fetch/animation artifact. Suggested change: static metric fallbacks plus a stated latency workload/boundary.")
    h(HEADINGS[8]); p("Transient failures use bounded retries with exponential backoff+jitter; auth/daily-quota errors do not retry. In the synthetic always-5xx pair, no-retry total p50 was 63.3 ms; two-retry p50 was 254.1 ms with no recovery - retries made failure slower.")
    h(HEADINGS[9]); p("The client receives status, then only verified excerpts and paper/page citations. At a simulated 3 PM daily-budget exhaustion it receives an explicit unavailable/rate-limited outcome; it is not silently queued forever or given unsupported text. Buffering until verification means user-visible first token can be later than provider TTFT.")
    h(HEADINGS[10]); p("Least-certain assumption: extractive quote/page checks approximate grounding; if wrong, well-cited answers can still be incomplete or irrelevant. Deliberately omitted: distributed multi-worker budgets and forced cancellation of active CPU retrieval. New lesson from this build: latency percentiles can look fast when immediate rejections dominate, so useful-answer outcomes must be reported separately. Real concurrency/quota recovery, semantic entailment, and independent grades remain untested.")
    callout([["ESTABLISHED", "MEASURED, BUT SYNTHETIC", "NOT ESTABLISHED"],
             ["Exact paper versions; page/quote metadata checks; 45 local tests; CSV and package validation.",
              "Five load scenarios, 60 A/B/C stand-in requests, retry comparison, and daily-budget-exhaustion behaviour.",
              "Independent human answer quality, semantic entailment, real quota recovery, provider concurrency, or production tails."]], [166,166,166])
    h(HEADINGS[11]); p("The preserved record is partial, not a reconstructed chat. Three decisive prompts: audit-first gating; exact paper/budget/CSV requirements; and approval of a three-request real baseline. The assistant caught quotation alteration from tokenizer decoding and replaced it with offset slicing; it is not claimed the candidate caught it. The user overruled the original Python 3.12 target by using the available Python 3.11.8. User-owned choices include corpus versions, limits, load scenarios and approvals; implementation details are attributed in conversation_records.md.")
    callout([["SUBMISSION EVIDENCE TRAIL", "READER CHECK", "SCOPE"],
             ["results/results.csv + experiments/*.json", "Recompute scenario latency/outcomes; duration, offered rate and peak queue live in scenario JSON because CSV columns are fixed.", "Historical and stand-in load measurements."],
             ["revised_retriever.../ + human_review_grades.json", "Inspect all 20 questions under A/B/C, cited passages, preliminary grades, and timing phases.", "Stand-in-only retrieval evaluation; not independent human grading."],
             ["pytest_final_release XML/log + package audit", "Check the 45-pass local suite, archive integrity, fresh extraction, exact CSV schema, and secret scan.", "Local validation; no production-readiness claim."]], [166,166,166])
    doc=SimpleDocTemplate(str(ROOT/"reports/report.pdf"),pagesize=A4,leftMargin=29,rightMargin=29,topMargin=22,bottomMargin=29)
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    with fitz.open(ROOT/"reports/report.pdf") as pdf:
        if len(pdf)!=2: raise RuntimeError(f"Expected exactly two pages, got {len(pdf)}")
        text="\n".join(p.get_text() for p in pdf); positions=[text.find(x) for x in HEADINGS]
        if any(x<0 for x in positions) or positions!=sorted(positions): raise RuntimeError("Headings missing/out of order")
        qa=ROOT/"data/qa/report"; qa.mkdir(parents=True,exist_ok=True)
        for i,page in enumerate(pdf): page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(qa/f"page-{i+1}.png")
    print("Built assignment-compliant report.pdf (2 pages).")

if __name__ == "__main__": main()
