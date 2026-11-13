# Submission release

## Report

- Final PDF: `D:\relay\reports\report.pdf`
- Page count: 2
- Heading validation: PASS - all twelve required headings, including `How I worked with the assistant.`, were found in the required order.
- Number verification: PASS - 45 passed / 7 warnings / 0 failures comes from `reports/pytest_final_release_20261112.xml` and its matching log. The revised evaluation is 60 local stand-in requests over 20 questions and A/B/C. The citation review records 79/85 normalized page-text matches and six H-Net p. 3 diagram exceptions.
- Assignment tables: PASS - Table 1 (real-service limits), Tables 2a/2b (five load scenarios), and Table 3 (A/B/C retrieval settings) are present. Fields unavailable from evidence are explicitly `not measured`.
- PDF extraction validation: PASS for openability, heading extraction, mandatory-table presence, and page count. Both rendered pages were visually inspected for clipping/overlap. The report itself discloses corpus extraction limitations.

## Package

- Final ZIP: `D:\relay\submission.zip`
- ZIP size: 7,275,350 bytes
- Included files: 103 allowlisted members with no duplicate paths. Exact ZIP size and SHA-256 are recorded by the final package audit.
- Required files present: README, final PDF, bug register, final validation, extraction-quality record, root results CSV, latest revised-run artifacts, source, tests, dependencies, configuration example, and verified papers/indexes.
- Excluded: `.env`, other environment files, original `pdf/`, virtual environments, caches, temporary files, and compiled Python artifacts.
- Archive integrity: PASS (`ZipFile.testzip()` returned no error).
- Fresh extraction: PASS. The extracted PDF opens with two pages and the extracted root results CSV has the exact required 12-column schema.

## Security

- Secret scan: PASS. The exact ZIP members and fresh extraction were scanned for the configured Groq key and `gsk_` key-like values; zero findings.
- Environment files: PASS. Only `.env.example` is included.
- Credential handling: the configured key was detected only as present in the local environment for comparison; it was never printed, stored in this report, or included in the archive.

## Evidence integrity

- Historical measurements are preserved; this release did not rewrite historical CSV data.
- The latest standalone revised-retriever run was used for the 20-question A/B/C discussion.
- The final-release test evidence used is `pytest_final_release_20261112.xml`/`.log`, not the earlier 44-test record.
- `ASSIGNMENT_COMPLIANCE.md` is included and maps every brief requirement to evidence and status.
- No Groq load, quota exhaustion, or new real-provider measurement is claimed.
- No semantic-correctness or independent-human-grade claim is made.

## Remaining limitations

- Semantic entailment, full answer completeness, and table/math interpretation are not fully verified.
- PDF text extraction has known table, notation, figure, heading, and H-Net diagram limitations.
- The 60 evaluation grades are preliminary assistant review; independent human grading is pending.
- Real provider concurrency, quota exhaustion/recovery, and tail behavior remain untested.
- The deployment is single-worker; budgets and locks are process-local.
- Stand-in concurrent scheduling is not fully deterministic, and active CPU thread work cannot be forcibly cancelled.
- Windows host memory/page-file pressure remains a documented operational limitation despite the passing final regression run.

## Final release decision

READY FOR MANUAL SUBMISSION

The package is structurally valid, secret-scanned, and includes the required evidence. “Ready” means ready for the user to submit manually; it does not remove the limitations above or authorize any upload.
