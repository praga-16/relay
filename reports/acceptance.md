# Acceptance

Final local release gate. PASS means only that the recorded artifact/test check passed; it is not production readiness or semantic correctness.

| Check | Status | Evidence |
|---|---|---|
| Regression suite | PASS | 45 passed, 7 warnings, 0 failures (reports\pytest_final_release_20261112.xml) |
| Results CSV schema | PASS | 709 rows across 5 historical/current CSV files have the exact 12-column schema |
| Latest A/B/C run | PASS | 60 stand-in requests cover 20 question IDs under A/B/C; separate queue, phase, and experiment diagnostics are present |
| Grading and citation audit | PARTIAL | Assistant preliminary grades: 1 correct, 45 wrong, 9 refused_correctly, 5 refused_wrongly, 0 pending_review; independent human review remains pending |
| Two-page report | PASS | Report has 2 pages and all 12 required headings in order |
| PDF extraction | PARTIAL | Known table/math/diagram defects remain; six figure quotes are not exact page-text matches |
| Semantic verification | PARTIAL | Lexical relevance and verbatim source-span checks do not prove entailment or completeness |
| Real provider limits and quality | NOT TESTED | No new Groq evaluation, quota exhaustion, or provider-limit test was run |
| Submission ZIP | PASS | 100 current allowlisted members; fresh extraction and actual ZIP secret scan passed |

## Unresolved issues

* Independent human grading is pending; the 60 labels are preliminary assistant inspection.
* Semantic entailment, full answer completeness, math/table interpretation, and section-boundary correctness are not established.
* Six H-Net p. 3 diagram-derived quotes are not exact page-text matches; other extraction limits are documented in `extraction_quality.md`.
* Real Groq quota/recovery/concurrency behavior, real A/B/C quality, and large-sample real latency tails were not tested.
* BR-11 through BR-14 and BR-19 remain known operational limitations; see `BUG_REGISTER.md`.

Release readiness: PARTIAL. The validated package can be reviewed, but it is not presented as production-ready or semantically perfect.
