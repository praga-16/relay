# Extraction inspection

All three official downloads matched local SHA-256 on 2026-11-12. Original PDFs were preserved. See `paper_manifest.json`.
All 120 pages contain extracted text; no U+FFFD replacements were found in the preliminary scan. This does NOT establish correct equations.

On 2026-11-12, the following physical PDF pages were rendered and visually compared with their extracted page blocks and source-page text: Attention pp. 4 and 8, Moshi pp. 8 and 9, and Dynamic Chunking p. 3. The images are in `data/qa/`, including the Moshi p. 8 image rendered for this inspection.

For these pages, concatenated extracted-block character counts were within one character of PyMuPDF's source-page text extraction: Attention p. 4 (2507 vs. 2508), p. 8 (3193 vs. 3194); Moshi p. 8 (2145 vs. 2146), p. 9 (3629 vs. 3630); Dynamic Chunking p. 3 (1427 vs. 1428). Targeted headings and prose were present in both. Near-equal text length does not imply preservation of visual layout or mathematical meaning.

Observed defects, confirmed against the rendered originals:

* Attention p. 4: the attention equation and footnote are split across blocks. The rendered fraction and square-root notation flatten in text; denominator scope and summation/order semantics are unsafe to infer from extraction. Nearby prose about large dot products and small gradients remains readable. Do not evaluate or reproduce the formula from plain text alone.
* Attention p. 8: the BLEU/training-cost table is flattened into text rows, so EN-DE/EN-FR and FLOP columns may be detached from a value. The label-smoothing value and prose are readable; table associations still require the page image.
* Moshi p. 8: the hyperparameter table's model/phase columns flatten into successive text lines. A number can become detached from its header/model. Do not infer a model/value association without inspecting the PDF. Accented author names also decompose into accent marks and letters.
* Moshi p. 9: prose and section 3.3 are readable, but superscripts in the encoder mapping are flattened and line-end hyphenation remains.
* Dynamic Chunking p. 3: diagram labels are emitted as disconnected characters and symbols. The caption is usable; the rendered diagram is necessary for interpreting arrows/equations. The indexed text contains this noise.
* Repeated running headers, page numbers, references and related-work mentions remain. They are a deliberate retriever challenge, not proof of a paper's own design.

## Final evaluation page cross-check

The previously affected pages were re-opened visually and compared with the
extracted page text and the latest evaluation's retrieved passages. Page numbers
below are physical PDF pages; arXiv versions are fixed by `paper_manifest.json`.

| Paper/version/page | Defect confirmed against the original | Retrieval or citation effect | Effect on latest 20-question evaluation |
|---|---|---|---|
| Attention Is All You Need, `1706.03762v7`, p. 4 | Equation fraction/square-root scope is flattened in extracted text; the nearby prose about large dot products and small softmax gradients is readable. | Formula-only interpretation is unsafe; prose can support q01. | q01 retrieved this page but the stand-in answer omitted the key explanation. The extraction defect is not established as the cause. |
| Attention Is All You Need, `1706.03762v7`, p. 8 | Results table values/columns are flattened; label-smoothing value and effect are readable in adjacent prose. | Table associations need the page image; q05's relevant prose remains extractable. | q05 retrieved direct evidence but returned an empty-claims refusal in A/B/C. The table defect is not established as the cause. |
| Moshi, `2410.00037v1`, p. 8 | Hyperparameter table phase/model columns can detach from values; the page image shows the original associations and frame-rate row. | Numbers must not be assigned to a model/phase from flattened text alone. | A q04 retrieved this as a distractor. Its answer is wrong; the extraction issue may contribute ambiguity, but causality is not established. |
| Moshi, `2410.00037v1`, p. 9 | Semantic/acoustic tokenization prose is readable; line-end hyphenation remains. | The semantic-distillation evidence is usable; hyphenation can disrupt exact phrase matching. | q06 A/B/C retrieved this page. Answers remain incomplete; no defect was shown to cause the missing first-RVQ-level detail. |
| Dynamic Chunking, `2507.07955v2`, p. 3 | Diagram labels are visually legible, but their text-layer extraction is disconnected/noisy. | Six of the 85 generated quote strings do not exactly match the cited page's extracted text: q11 B/C, q13 C, and q20 A/B/C. Their physical page and section metadata match the indexed passage; exact quotation authenticity is not established by text matching. | Yes. These diagram-derived excerpts appear in the latest evaluation and are not exact page-text quotes. The page citations themselves are in range and point to the diagram; the responses are incomplete/wrong regardless. |

Across all 85 generated claims, 79 quote strings exactly match normalized text
from their cited PDF page; the six exceptions are the H-Net p. 3 diagram strings
above. All 85 paper/version/page/section tuples match the indexed source metadata,
but this does not independently validate every heuristic section boundary or
prove semantic support.

Extraction retains block coordinates and approximates paragraph boundaries. Heading detection is heuristic, including headings whose number and title are on separate lines. Physical PDF page numbers are used, not an inferred journal pagination scheme. No OCR or equation parser was introduced.

The first audit used globally installed PyMuPDF 1.28; the pinned environment uses 1.26.3. Its final extraction contains 2,251 blocks. Font checks avoid mistaking numeric table cells for headings; CMCSC small caps and appendix letters are recognized. Earlier measured answers retain their original evidence/section labels in JSONL and are not silently relabeled after extraction fixes.

Mitigation: exact excerpts, page citations and a human-inspectable corpus; no claim that quote matching establishes numeric-table interpretation or semantic relevance. Further improvements would tag table/figure blocks and exclude running headers with documented validation.
