# Final validation

The release is reviewed against recorded local evidence. This status is not a production-readiness claim.

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
| Submission ZIP | PASS | 103 current allowlisted members; fresh extraction and actual ZIP secret scan passed |

## Unresolved bug register entries

BR-11, BR-12, BR-13, BR-14, BR-15, BR-16, BR-18, BR-19

## Release decision

PARTIAL. The two-page report and allowlisted ZIP are checked when their rows above say PASS. Human answer grading, semantic entailment, PDF extraction limitations, real Groq behavior, and the operational items listed above remain unresolved or untested. No upload or submission was performed.
