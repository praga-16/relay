# Relay bug register

Final status meanings: PASS, FAIL, BLOCKED, PARTIAL, and NOT TESTED. PASS refers
to recorded local tests/artifact checks only, not unmeasured provider behavior.

| ID | Severity | Finding and root cause | Resolution / current evidence | Status |
|---|---|---|---|---|
| BR-01 | High | Retrieval chunking split every extraction block before packing, so paragraph boundaries were not preserved. | Chunks retain blocks that fit and split only oversized blocks. Focused chunk regression and final suite passed; current indexes were used without rebuilding. | PASS |
| BR-02 | High | A FAISS index could be stale after corpus, manifest, or embedding changes, or have unreadable/inconsistent vector data. | Startup checks compare corpus/manifest hashes, model/revision, readability, vector count, and dimension. Changed corpus/manifest/model, corrupt bytes, wrong count/dimension, and current-index checks passed. | PASS |
| BR-03 | High | Citation display could return normalized rather than original source spelling/whitespace. | Verified quote spans map to original source characters. Unicode/whitespace citation regression and final suite passed. | PASS |
| BR-04 | High | Reusing an idempotency key with a different request could stream HTTP 200 instead of 409. | Request fingerprint is checked before streaming. Same-body reuse and changed-body conflict regression passed. | PASS |
| BR-05 | Medium | Shutdown could strand queued callers while workers were cancelled. | Shutdown drains queued futures and cancels them; regression and final suite passed. | PASS |
| BR-06 | Medium | Monitoring schema checks used `assert`, which optimization can remove. | Logger raises `ValueError` for invalid row schemas. Invalid-row regression and final suite passed. | PASS |
| BR-07 | Medium | Stand-in transient failures only returned 503. | Validated configurable 500/502/503 responses; all three status regressions and final suite passed. | PASS |
| BR-08 | Medium | The first evaluation had only 18 questions. | The corpus has 20 questions; the isolated stand-in evaluation contains each question under A/B/C (60 rows). Preliminary assistant grades are recorded separately; independent human grading remains pending. | PASS |
| BR-09 | Medium | Setting C was described as lexical reranking without an explicit hybrid score. | C combines normalized FAISS and BM25 scores. Hybrid-score regression and the 60-row A/B/C run were recorded. No winner is claimed. | PASS |
| BR-10 | Medium | One disconnected subscriber could cancel shared idempotent work for other clients. | Shared tasks track active subscribers; a single disconnect only detaches that subscriber, while the last disconnect cancels and cleans up. Two-client disconnect, both-cancel cleanup, completion/cache, and idempotent reuse tests passed. | PASS |
| BR-11 | Medium | CPU embedding/retrieval runs in a thread and cannot be force-cancelled after it starts. | Bounded queue/deadline limits additional work, but active CPU work may finish after a client timeout. | PARTIAL |
| BR-12 | Medium | A simulator seed does not guarantee concurrent event order because scheduling changes random-number consumption. | Seed and scenario configuration are recorded; request-local random streams are not implemented. | PARTIAL |
| BR-13 | Medium | Synthetic 5xx responses consume stand-in capacity because reservation occurs before failure injection. | This remains a simulator behavior, not a claim about Groq. An explicit `charge_failures` configuration is not implemented. | PARTIAL |
| BR-14 | Medium | In-process locks and budgets do not coordinate multiple Uvicorn workers. | Intended deployment remains one worker; distributed coordination is outside this validation. | PARTIAL |
| BR-15 | High | Exact quote matching alone cannot establish claim relevance, semantic support, answer completeness, or table/math interpretation. | The 60-request review separates quote/page checks, passage relevance, claim support, and answer completeness. 79/85 generated quote strings match normalized cited-page text; six H-Net p. 3 diagram strings do not. Semantic entailment and full completeness remain unverified. | PARTIAL |
| BR-16 | Medium | PDF extraction can flatten mathematical notation, tables, figures, superscripts, and heading structure. | Attention pp. 4, 8; Moshi pp. 8, 9; and Dynamic Chunking p. 3 were visually compared with source text. The H-Net diagram issue affects six citation strings in the latest evaluation. Page-level findings and evaluation impact are in `reports/extraction_quality.md`. | PARTIAL |
| BR-17 | Medium | The required 12-column `results.csv` cannot encode queue peaks, phase timings, and experiment configuration. | CSV schema is unchanged; the latest run has separate queue, phase-timing, and experiment-configuration JSON. All historical and new CSV rows were checked. | PASS |
| BR-18 | High | Real provider concurrency, quota exhaustion/recovery, and tail behavior were not authorized for destructive/load testing. | No real load/quota test was run and no provider limits are inferred. | NOT TESTED |
| BR-19 | Medium | A prior full-test rerun raised Windows `MemoryError` importing NumPy. | The final-release complete run passed 45 tests, including real embedding/index tests. Earlier inspection found limited physical/virtual memory and page-file pressure; no process was terminated or page-file setting changed. The host resource-pressure cause is unresolved. | PARTIAL |

## Regression and measurement policy

Historical root `results.csv`, `results_ungraded.csv`, `results/tests.xml`, raw
diagnostics, and experiment results are preserved. Revised retrieval measurements
are written under separate `results/revised_retriever_*` directories. The latest
run is stand-in-only; its answer grades are in a separate assistant-preliminary
review artifact pending independent human review. It does not establish semantic
quality or a best retrieval setting. No new Groq measurement or provider limit is
claimed.
