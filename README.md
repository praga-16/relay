# The Relay

A local, single-process, bounded RAG orchestration service over three exact arXiv PDFs.
Python 3.11.8 / Windows. Default provider is the local simulator. No Docker or external queue.

## Run on Windows PowerShell

```powershell
Set-Location D:\relay
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m scripts.prepare_papers
.\.venv\Scripts\python.exe -m scripts.build_indexes
.\.venv\Scripts\python.exe -m pytest -q
```

First model download needs internet access. Afterwards set `$env:HF_HUB_OFFLINE='1'` before commands to prevent network checks.
The pinned MiniLM revision is in `config/default.json`. Requirements lock records the actually installed environment. Embedding batch size is one to fit the constrained development host; avoid running multiple model instances during indexing.
Original PDFs remain in the workspace `pdf/`; the allowlisted package contains verified copies in `papers/` and the small indexes/extracted corpus needed for immediate use. If `pdf/` originals are absent, `prepare_papers` uses the packaged `papers/` copy and still checks its official hash when online verification is enabled. Preparation fails on any SHA-256 mismatch.

Open two terminals, both in `D:\relay`:

```powershell
# Terminal 1: separate simulated provider
.\.venv\Scripts\python.exe -m uvicorn app.models.standin:app --host 127.0.0.1 --port 8001
```

```powershell
# Terminal 2: Relay API and small browser client
$env:HF_HUB_OFFLINE='1'
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Visit http://127.0.0.1:8000. Ask a question, choose A/B/C, or cancel.
If port 8000 is occupied, use `--port 8002` and visit http://127.0.0.1:8002. This happened during the build; the unrelated service was left untouched.
`/docs` documents the API; `GET /health` reports queue length. `POST /ask` streams SSE status, metadata, verified answer chunks, then done.

```powershell
curl.exe -N -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" --data-raw '{"question":"What is Mimi?","setting":"A"}'
```

Use the browser client if your PowerShell/curl version rewrites JSON quotes.

## How the modules fit

1. **Ingestion** (`app/retrieval/ingest.py`) checks exact versions and hashes, then keeps PDF text blocks, page numbers, headings and coordinates. Layout blocks approximate paragraphs; they cannot reconstruct every equation or table.
2. **Retrieval** (`app/retrieval/engine.py`) makes page-and-section-bounded WordPiece chunks, keeping extraction blocks intact unless a single block exceeds the configured size. It embeds all subwindows and searches normalized vectors with FAISS. Character offsets preserve original text. A=200/top3; B=500/top5; C=500/top5 with deterministic BM25-plus-vector hybrid reranking. It is not a cross-encoder. Structured `RetrievalInput` / `RetrievalOutput` make retrieval an explicit callable tool, logged with arguments and results.
3. **Understanding and decisions** (`app/pipeline/engine.py`) identify topics/answer types, retrieve, check a configurable similarity floor, generate, and verify. Missing/failed evidence triggers expanded retrieval at most twice total. No evidence means no provider call. These intent heuristics are deliberately small and inspectable.
4. **Generation and verification** select exact evidence excerpts. The verifier rejects unknown chunk IDs and altered quotes, checks lexical overlap with the question, and requires each claim to be a verbatim span of its authenticated quote. It reports question-term coverage separately, but that is not semantic completeness or entailment. It renders title/version/page/section from trusted corpus metadata. It cannot establish table/math interpretation. This is a conservative extractive QA baseline, not a semantic entailment oracle or polished abstractive answerer. Human quality grades remain necessary.
5. **Provider** (`app/services/provider.py`) consumes SSE, records usage and content TTFT, classifies errors, retries transient failures with jitter and bounded attempts, and stops on daily quota/authentication failures. Groq credentials go only to the fixed Groq HTTPS origin; redirects are disabled by HTTPX defaults.
6. **Budgets** (`app/services/budget.py`) atomically reserve requests and conservative byte-based token estimates, then reconcile actual usage. Unknown usage retains the reservation. Rolling minute/day budgets intentionally err on the safe side. Groq request-limit headers refer to RPD; token-limit headers refer to TPM. Shared-account traffic can invalidate local estimates. Daily real usage survives process restart in `logs/real_budget.json`.
7. **Request manager** owns a bounded FIFO, fixed workers and semaphore. The deadline covers queueing plus work; cancellation cancels provider I/O. CPU retrieval already running in a thread cannot be forcibly interrupted. Use one Uvicorn worker: multiple processes would have independent queues/limits and unsafe shared log/state writers.
8. **Streaming** buffers all provider text until verification; only status events precede verification. User-visible TTFT is therefore later than provider TTFT. SSE delivery is paced in 48-character chunks; it improves progressive presentation, not generation latency.
9. **Monitoring** appends one CSV row per request and detailed JSONL diagnostics. Blank grade means not graded; blank usage means unavailable, never zero. A completed refusal has status `ok`; status is not a factual-quality grade.

## Real Groq gates and secrets

Only `D:\relay\.env` is read. `pdf/.env` is never loaded or packaged. `.env.example` has placeholders.
Never paste a key in chat. Configure the root file locally with `GROQ_API_KEY` and `GROQ_MODEL`.

Read-only discovery:

```powershell
.\.venv\Scripts\python.exe -m scripts.groq_probe
```

The models endpoint does not expose complete account limits. `config/real_approval.json` records the user's confirmed console limits and explicit experiment scope; it is not independent evidence for all limits. Existing approval records document this session, not blanket permission for future experiments. Ask for approval before another smoke or baseline run.

The approved smoke used one request with max completion 128, no retries. The approved baseline is capped at three requests, <=6000 tokens reserved each, max completion 500, 65 seconds apart, no provider or verification retries. `scripts/run_baseline.py` enforces those settings. Do not rerun it without new authorization.

Default real local budgets: RPM24 / TPM6400 / RPD800 / TPD160000, concurrency5, queue50, max retries2. These are 80% of user-confirmed starting values. The conservative UTF-8 reservation may reject large B/C prompts before any call; essential evidence is never silently removed to fit. No silent model switching. Rate-limit changes can reduce local caps; increases require deliberate configuration review.

## Reproduce simulated experiments

```powershell
$env:HF_HUB_OFFLINE='1'
.\.venv\Scripts\python.exe -m scripts.create_evaluation
.\.venv\Scripts\python.exe -m scripts.run_experiments --quality
.\.venv\Scripts\python.exe -m scripts.run_experiments
.\.venv\Scripts\python.exe -m scripts.export_review
.\.venv\Scripts\python.exe -m scripts.analyze
```

Results append rather than overwrite. Reruns get new request IDs and experiment configuration files. For a separate run, archive `results/` and `experiments/` first; don't silently delete old measurements.

The harness uses actual loopback TCP for provider streaming and measures verified delivery pacing in-process. It does not include the browser/network path to the Relay API; a separate API integration test checks that path. Defaults are intentionally accelerated synthetic limits and a smaller queue to expose overload quickly, not claimed Groq account behavior. Five scenarios use fresh simulator/budget instances; seed and effective configurations are saved per run. Arrival order under OS scheduling still affects randomness and timings.

Quality selection in the simulator is lexical and can be wrong even when quotes are authentic. Never present its quality percentages as Groq quality. The latest isolated run contains 20 questions under A/B/C (60 stand-in requests) in `results/revised_retriever_20261112_122922_1794486562840276600/`. Assistant preliminary grades and per-claim citation audits are separate in `reports/human_review_grades.json`; they are not independent human grades. The comparison and all 14 abstentions are documented in `reports/retrieval_comparison.md` and `reports/abstention_analysis.md`. Independent human review remains pending; no A/B/C winner or semantic-quality claim is established.

## Measurement definitions

`results/results.csv` has exactly the required 12 columns. `results/diagnostics.jsonl` preserves retrieved passages, decisions, candidates, errors and timing. Provider TTFT means first content delta, excluding reasoning-only deltas. Harness TTFT means first verified answer/error/refusal character exposed to the consumer. Raw smoke TTFT is provider TTFT and has its own scenario. The original smoke start wall-clock was not captured and is left blank.

Percentiles use NumPy `method='linear'`, only genuinely unmeasured values are excluded. Outcome denominators are all submitted requests. Quality denominators are all questions per setting, including unanswerable ones; correctly refused percentage is not refusal precision. `ok` means completed, not correct. Unknown grades are not zero-quality judgments.

CSV records latency/outcomes/tokens but its `answer_grade` cells remain blank for the latest revised run. Preliminary rubric grades are in a separate review JSON with answer, evidence, citations, and rationale. Peak queue, offered schedule/duration, provider limits, calibration and phase timings come from named diagnostic/config files: the mandated 12-column CSV has no fields for those quantities. Monetary cost is not measured; local simulation has no API charge but excludes hardware/electricity costs. No bill has been inspected.

Load tables aggregate two actual runs per scenario, including the short initial run. The second sustained-overload run offers traffic for 12 seconds. Saved configs distinguish them. Earlier results include `circuit_open` among local `rate_limited` outcomes; final code classifies circuit-open as an error. Limited outcomes also include queue rejection and local budgets, so they are not a count of provider HTTP 429 responses. The small paired retry experiment also triggers the circuit breaker; it is a reliability-policy comparison, not isolated backoff timing.

## Submission

Read `reports/report.pdf`, `reports/acceptance.md`, `reports/FINAL_VALIDATION.md`, `reports/BUG_REGISTER.md`, `reports/retrieval_comparison.md`, `reports/abstention_analysis.md`, `reports/extraction_quality.md`, `reports/quality_rubric.md` and `reports/conversation_records.md`. The two-page report is based on the latest stand-in run and the preserved historical measurements; it does not claim semantic correctness, independent human grades, production readiness, or real-provider limits. `scripts/package_submission.py` uses an explicit allowlist, scans actual ZIP members, and extracts the archive into a fresh temporary directory for verification. `.env`, original `pdf/`, the virtual environment, caches, and unnecessary indexes are excluded.
