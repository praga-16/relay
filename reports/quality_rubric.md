# Human-inspectable grading rubric

For each question, compare the entire answer with the expected facts, cited physical PDF pages and retrieved text. Inspect the original PDF for tables/equations. The expectation is a guide, not a keyword-only oracle; alternative supporting pages may be valid.

* `correct`: answerable question, all required facts covered accurately, authentic citations support the answer, no extra misleading claim.
* `wrong`: completed factual answer includes unsupported/irrelevant facts, omits a material part, or answers an unanswerable question by guessing. A true but irrelevant excerpt is wrong.
* `refused_correctly`: unanswerable question explicitly refuses to guess.
* `refused_wrongly`: answerable question refuses despite sufficient evidence in the three papers.

Timeouts/queue/provider errors have no factual answer to grade; leave grade blank, retain outcome status. Interactive and smoke questions are ungraded unless reviewed. Grades in the submission are assistant inspection, with evidence and rationale, pending candidate review; they are not claims of independent human grading.

All 20 questions in the current evaluation corpus are original for this project. Earlier historical quality runs used 18 questions and remain unchanged. q14/q17 request unsupported equivalences/universal claims; a safe correction could be acceptable only if it clearly rejects that claim and cites relevant distinctions. Our strict extractive response is graded wrong when it merely returns related text without resolving the premise.
