# Actual conversation records and authorship

This is a partial record, not an invented full transcript. The attachment is preserved verbatim in `prompt_records/final_build_instruction.txt`. The client has not provided an uncleaned full conversation export. Do not describe this file as that export.

Three important actual prompts:

1. The initial assignment required a project audit and said: "Wait for my confirmation before moving to the first implementation milestone." This prevented premature implementation and exposed Python/environment/key problems.
2. The attached final build instruction said: "Do not stop at planning. Implement the actual project and produce the required deliverables." It explicitly selected Python 3.11.8, preserving originals and restricting keys to the root .env. This authorized the full offline build and overruled the earlier Python 3.12 target.
3. The user approved the concrete real baseline with: "Approve three-request baseline" after the assistant proposed three requests, <=18000 reserved tokens total, <=500 completion tokens each, no retries and >=65-second spacing. This separated modest real measurement from simulated stress testing.

Other actual user replies:

> D:\relay\\.env

> Approve smoke; those account limits are confirmed with no separate token caps

Actual assistant statements include:

> The active Python is 3.11.8 rather than the requested 3.12, and pip reports an invalid `~ransformers` installation.

> The first RAG baseline request returned HTTP 200 but no usable answer content. That failure is preserved in the raw results, and I did not retry it.

Mistakes caught by the assistant and tools (not claimed to have been caught by the candidate):

* Initial chunk construction decoded uncased tokenizer IDs back into text. Code review caught that this could lowercase quotations and alter symbols; character-offset slicing replaced it, and a regression test checks preserved case/Unicode.
* First indexing attempt used batch size 32 and failed with a real CPU allocation error. Batch size 4 and two Torch threads completed indexing.
* A later index rebuild with a live model server exhausted host memory. The server was stopped; final indexing uses batch size one. Port 8000 was already occupied by an unrelated service, so the live Relay check uses 8002.
* The original smoke logger missed the wall-clock start timestamp. It remains blank rather than being inferred from file time. Its actual token and latency measurements are preserved.
* The first real baseline response had no usable content. Initial parser also discarded usage on that failure. Usage is now captured before validating stream content; the lost historical usage remains blank.
* An experiment metadata directory was absent after the first failed baseline. The exception was visible; the script now creates it and preserves the failed request in CSV/JSONL.
* Final packaging detected a credential in .env.example and refused to create an archive. The example was restored to placeholders without printing its contents or changing the root .env; the scan was rerun before packaging.

One user override: Python 3.11.8 instead of the earlier 3.12 requirement. No fabricated anecdote about disagreeing with a model or personally finding a bug is included.

Distinctly user-owned decisions: the project objective; exact three arXiv versions; Windows/Python/Groq constraints; local-only infrastructure; A/B/C starting settings; budget values/safety margin; the fixed CSV schema; five required load scenarios; real-call gates and their approvals; report headings and honesty rules.

Assistant implementation decisions: HTTPX rather than Groq SDK; page/section chunks with WordPiece offset slicing; normalized MiniLM subwindow pooling and FAISS inner product; conservative extractive answer schema; rolling-window local budgets; FIFO workers; JSONL diagnostics; lexical stand-in selector and reranker. These should not be claimed as candidate-originated ideas without an actual candidate contribution.

Candidate personal learning, product experience and independent grading are not inferable from this conversation. They remain for the candidate to review and describe in their own words. Website observations are explicitly the assistant's text-fetch inspection, not a claimed customer experience.
