# Abstention analysis

Run reviewed: `results/revised_retriever_20261112_122922_1794486562840276600/`.
The 14 refusals below are from the local stand-in, not Groq. Root causes were
traced through each request's candidate passages, generation attempts, and
verification record. The grades are preliminary assistant judgments; independent
human review is still pending.

| Question | Setting | Root cause | Was refusal justified? | Evidence and recommendation |
|---|---|---|---|---|
| q05 | A | Generator/selector returned empty claims twice despite direct label-smoothing evidence on Attention p. 8. | No; answerable and evidence was retrieved. | Not a retrieval-threshold failure. Keep the threshold; improve claim selection for table-adjacent prose and preserve the source-backed p. 8 value/effect. |
| q05 | B | Same empty-claims outcome; p. 8 evidence was in the candidate pool on both attempts. | No. | Do not lower thresholds. Improve structured extraction and require coverage of value, perplexity, and BLEU before answering. |
| q05 | C | Same empty-claims outcome; p. 8 evidence was retrieved. | No. | Same fix as A/B; add a focused regression for this question shape. |
| q13 | A | Generator/selector returned empty claims twice although H-Net p. 9, the relevant causal-processing passage, was retrieved. | No; answerable with available evidence. | Not a threshold failure. Improve evidence selection for causal boundary/smoothing questions; retain exact-quote verification. |
| q18 | A | Expanded retrieval remained incomplete across both papers: it found partial Transformer/H-Net passages but not the needed complete positional-encoding and H-Net causality evidence. The generator also returned empty claims twice. | Locally cautious given the incomplete pool; globally wrong under the rubric because the library contains an answer. | Use a per-paper evidence checklist and keep searching until both source requirements are met or report a retrieval failure. Do not force an answer from partial evidence. |
| q15 | A | Genuine absence: the Moshi paper does not report a Groq free-tier RPM limit. Retrieved Moshi passages are unrelated to provider account limits. | Yes. | Preserve the refusal; identify the corpus boundary rather than inventing a provider limit. |
| q16 | A | Genuine absence plus retrieval rejection: no Redis RAG-cache configuration exists in the papers; retrieval found no usable evidence and did not generate an answer. | Yes. | Preserve abstention. Improve out-of-domain messaging; do not lower the threshold to admit unrelated passages. |
| q17 | A | Genuine absence of the universal claim. Moshi describes its own Inner Monologue, not private reasoning for every hosted LLM. | Yes. | Preserve the refusal and explicitly distinguish the paper's terminology from a universal claim. |
| q15 | B | Same as q15 A: the paper contains no account RPM limit. | Yes. | Preserve the refusal; do not infer provider limits from a paper. |
| q16 | B | Genuine absence: the retrieved Attention/H-Net passages do not describe Redis. The generator returned empty claims after two attempts. | Yes. | Preserve abstention and improve out-of-domain messaging, not the threshold. |
| q17 | B | Same as q17 A: the paper does not support a universal hosted-LLM chain-of-thought claim. | Yes. | Preserve the refusal. |
| q15 | C | Same as q15 A: the paper contains no account RPM limit. | Yes. | Preserve the refusal; do not infer provider limits from a paper. |
| q16 | C | Same genuine-absence cause as q16 A; retrieved H-Net/Attention passages do not describe Redis. | Yes. | Preserve abstention and improve out-of-domain messaging, not the threshold. |
| q17 | C | Same as q17 A: the paper does not support a universal hosted-LLM chain-of-thought claim. | Yes. | Preserve the refusal. |

The table above contains 14 request records (q05 A/B/C, q13 A, q18 A, and q15/q16/q17
under A/B/C). The distinction matters: q05 and q13 are answerable selector failures;
q18 A is a multi-passage retrieval failure followed by a conservative refusal; and
the nine q15-q17 refusals correctly reject unsupported claims. None supports
lowering the evidence threshold as a general answer-rate fix.
