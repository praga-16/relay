# Revised retrieval comparison

Evaluation source: local stand-in only. This is the 60-request run in
`results/revised_retriever_20261112_122922_1794486562840276600/` (20 questions
under each setting). The grades below are preliminary assistant rubric judgments,
not independent human grades. The request CSV remains ungraded; separate
per-request review records are in `human_review_grades.json`.

## Quality and evidence

| Setting | Complete retrieved rubric evidence / answerable questions | At least one materially relevant passage / all questions | Correct answers / answerable questions | Correct answers / generated answers | Correct refusals / unanswerable questions | Incorrect refusals / answerable questions | Grades: correct / wrong / refused correctly / refused wrongly |
|---|---:|---:|---:|---:|---:|---:|---|
| A | 11/16 (68.8%) | 18/20 (90.0%) | 1/16 (6.3%) | 1/14 (7.1%) | 3/4 (75.0%) | 3/16 (18.8%) | 1 / 13 / 3 / 3 |
| B | 13/16 (81.3%) | 18/20 (90.0%) | 0/16 (0%) | 0/16 (0%) | 3/4 (75.0%) | 1/16 (6.3%) | 0 / 16 / 3 / 1 |
| C | 11/16 (68.8%) | 18/20 (90.0%) | 0/16 (0%) | 0/16 (0%) | 3/4 (75.0%) | 1/16 (6.3%) | 0 / 16 / 3 / 1 |

Definitions:

* **Complete evidence recall** is the number of answerable questions whose retrieved
  candidate passages contained all rubric-required evidence, divided by 16. This is
  a manual, source-grounded completeness review, not a lexical-overlap score.
* **Passage relevance** is request-level: at least one retrieved passage materially
  addresses the requested fact, divided by all 20 requests. q15 (Groq account limits)
  and q16 (Redis configuration) have no materially relevant source evidence.
* Correct-answer rate counts only fully correct answers against all 16 answerable
  questions. Correct-answer rate among generated answers is also shown to make the
  denominator explicit. q14 is unanswerable and its related excerpt is graded wrong
  because it does not reject the false equivalence.
* Correct refusal rate uses the four unanswerable questions (q14-q17); incorrect
  refusal rate uses the 16 answerable questions. q18 A is globally graded
  `refused_wrongly` because the library contains an answer, although that run's
  incomplete cross-paper candidate pool made abstention locally cautious.

## Citation, latency, and token metrics

| Setting | Mechanically verifiable citations: exact quote / all claims | Retrieval latency p50 / p95 (ms) | Stand-in input tokens (total; mean per recorded request) | Stand-in output tokens (total; mean per recorded request) |
|---|---:|---:|---:|---:|
| A | 26/27 (96.3%) | 44.1 / 473.2 | 28,139; 1,481 over 19 requests | 3,308; 174 over 19 requests |
| B | 26/28 (92.9%) | 67.1 / 131.2 | 61,710; 3,086 over 20 requests | 3,615; 181 over 20 requests |
| C | 27/30 (90.0%) | 38.6 / 76.6 | 59,998; 3,000 over 20 requests | 3,851; 193 over 20 requests |

For all 85 generated claims, paper/version/page/section metadata matched the indexed
source passage and page numbers were in range. The exact quotation string appeared
in the cited page's extracted PDF text for 79/85 claims. The six exceptions are
noisy H-Net p. 3 diagram strings; the page citation points to the figure, but the
quotation is not an exact text-layer match. Section strings match index metadata;
section-boundary correctness was not independently established for every heuristic
heading. Citation metadata integrity does not prove claim support or answer
correctness.

Retrieval latency is the recorded retrieval phase (including any expanded pass),
not user-visible latency or provider TTFT. p95 is a small-sample statistic (n=20);
setting A includes a large cold/slow retrieval outlier. Token counts are stand-in
telemetry only, not Groq usage. A's missing token value is not imputed as zero.

## Interpretation

Setting B retrieved complete rubric evidence on more answerable questions in this
review, but produced no fully correct graded answer. A produced the only fully
correct response, while also making three answerable-question refusals. C had the
lowest observed retrieval p50/p95 and the weakest exact-quote fraction of the three
settings. These small, single-run, assistant-graded stand-in results do not justify
an A/B/C winner or a claim about Groq. Independent human grading remains pending.
