# Assignment compliance audit

Audit basis: the four-page assignment brief, project artifacts dated 12 November
2026, and the final-release test record. A PASS means that a local artifact supports
the requirement; it does not claim semantic correctness or unmeasured Groq behavior.

| Requirement | Required evidence | Actual artifact | Status | Missing information / action required |
|---|---|---|---|---|
| Four-plus pipeline steps, tool, branch/loop | Runnable source and tests | Intent, `retrieve_papers`, decision, generation, verification, bounded expansion/retry; `app/` and tests | PASS | None. |
| Only exact three arXiv papers | Version/hash record and PDFs | `paper_manifest.json`, `papers/`, hash validation | PASS | None. |
| Page citations and refusal | Evidence/citation behavior and tests | verifier, evaluation q14-q17, citations | PARTIAL | Exact quote/page metadata is checked; semantic support/completeness is not proven. |
| Real Groq free-tier model | Authorized real calls and raw observations | smoke + three baseline rows/diagnostics | PASS | Too small for meaningful tails or load behavior. |
| Discover real limits from docs/headers | Account confirmation and observed headers | `config/real_approval.json`, diagnostics headers | PARTIAL | RPM/RPD/TPM/TPD are user-confirmed; concurrency, real 429 response and recovery were not measured. |
| Stand-in: slow/fail/429/daily/stream/load | Config, service, tests | `app/models/standin.py`, stand-in config and scenario files | PASS | Its concurrent ordering and 5xx charging are synthetic limitations. |
| Stand-in calibrated from real service | Calibration inputs and method | two successful real samples recorded in stand-in config | PARTIAL | Only two samples; failure/quota/load shape is synthetic. |
| Modest real experiment | Raw real rows | one smoke + three approved baseline attempts | PASS | No intentional real limit exhaustion, by design. |
| At least three load shapes | Scenario raw results | steady, burst, sustained overload plus two limit scenarios | PASS | Stand-in only. |
| Required five scenarios | CSV/config/diagnostics | five named scenarios in results/experiments | PASS | Table fields beyond mandated CSV require supplementary JSON. |
| Fifteen-plus original questions | Question set and quality review | 20 questions x A/B/C = 60 local requests | PASS | Grades are preliminary assistant review, not independent human grades. |
| Three retrieval settings | Settings and comparison | A 200/top3; B 500/top5; C 500/top5 hybrid | PASS | No independently established winner. |
| Required CSV schema | Root CSV and schema check | `results/results.csv`, package validation | PASS | Queue/duration/limits are not encodable in the required 12 columns. |
| Required results tables | Two-page report tables and raw sources | report + `results/summary.json`, experiments, revised run | PASS | Cost remains `not measured`; documented rather than estimated. |
| Slow-request latency breakdown | Diagnostic trace | real baseline incomplete stream trace; queue/retry/retrieval/provider timings | PARTIAL | Working is derived as residual; provider first content token was absent for that failed stream. |
| Retry-worse case | Paired measured experiment | retry comparison no-retry vs two-retry stand-in runs | PASS | Synthetic 5xx, not a Groq causal estimate. |
| 3 PM daily-budget experience | Implementation/config + scenario | daily-budget-exhausted stand-in scenario; refusal/status behavior | PARTIAL | Scenario simulates exhausted budget; no real Groq daily exhaustion was induced. |
| Vaani feedback | Recorded visit/observation | `reports/website_observations.md` | PARTIAL | Assistant text-fetch observation only; no personal product session is claimed. |
| Assistant-work record | Preserved prompt/history and attribution | `conversation_records.md`, prompt record | PARTIAL | No full uncleaned chat export is available. |
| Two-page report | PDF page count, headings, tables | `reports/report.pdf` validation | PASS after this release | Report deliberately distinguishes measured, simulated, and not-measured values. |
| Clean secret-free ZIP | Archive scan/extraction | package audit and `submission.zip` | PASS after this release | Must be re-run after any later change. |

## Raw-source map

* Tables 1 and real samples: `config/real_approval.json`, `results/diagnostics.jsonl`, and root `results/results.csv`.
* Tables 2a/2b: root `results/results.csv`, `results/summary.json`, and scenario JSON in `experiments/`. Duration, offered rate, and peak queue come from the scenario JSON because the fixed CSV schema has no such columns.
* Table 3: `results/revised_retriever_20261112_122922_1794486562840276600/` plus `reports/human_review_grades.json`. These labels are preliminary assistant review.
* Tests: `reports/pytest_final_release_20261112.xml` and matching log.

## Compliance decision

The submission is **PARTIAL but defensible**: required build, raw-data, load-scenario,
and packaging evidence exists, while semantic verification, independent human grading,
full conversation export, and real-provider limit/concurrency behavior remain explicitly
unmeasured. The report must preserve those limits instead of converting them into claims.
