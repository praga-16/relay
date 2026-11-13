"""Conservative extractive contract: generated prose cannot masquerade as verified facts."""
import json
import re

REFUSAL = "The three-paper library does not contain sufficient evidence to answer this question."


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip()


def original_excerpt(text, normalized_quote):
    """Map a whitespace-normalized model quote back to the exact source characters."""
    direct = text.find(normalized_quote)
    if direct >= 0:
        return text[direct:direct + len(normalized_quote)]
    source = normalize(text)
    start = source.find(normalized_quote)
    if start < 0:
        return None
    normalized = []
    positions = []
    in_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if not in_space:
                normalized.append(' '); positions.append(index)
            in_space = True
        else:
            normalized.append(char); positions.append(index); in_space = False
    normalized_text = ''.join(normalized).strip()
    # The normalized quote was found above, so positions are safe after leading trim.
    leading = len(''.join(normalized)) - len(''.join(normalized).lstrip())
    begin = positions[start + leading]
    end = positions[start + leading + len(normalized_quote) - 1] + 1
    return text[begin:end]


def verify(raw, passages):
    valid, reason, checked, _audit = check_evidence(raw, passages)
    return valid, reason, checked


def check_evidence(raw, passages, question=None):
    audit = dict(quote_authenticity='not_assessed', passage_relevance='not_assessed',
                 claim_support='not_assessed', answer_completeness='not_verified')
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        audit.update(quote_authenticity='failed', claim_support='failed')
        return False, 'invalid_json', [], audit
    if not isinstance(data, dict) or set(data) != {'claims'} or not isinstance(data['claims'], list):
        audit.update(quote_authenticity='failed', claim_support='failed')
        return False, 'invalid_schema', [], audit
    if not data['claims']:
        audit.update(quote_authenticity='not_applicable', passage_relevance='not_applicable',
                     claim_support='not_applicable', answer_completeness='abstained')
        return True, 'refused', [], audit
    if len(data['claims']) > 6:
        audit.update(quote_authenticity='failed', claim_support='failed')
        return False, 'too_many_claims', [], audit
    lookup = {p['chunk_id']: p for p in passages}
    checked = []
    relevance = []
    support = []
    authenticity = []
    answer_terms = set()
    stop_words = set('what why how does do is are the a an in of to for and from paper model '
                     'describe explain according with this that these those it be was were'.split())
    query_terms = set(re.findall(r'[a-z0-9]+', question.lower())) - stop_words if question else set()
    for claim in data['claims']:
        if not isinstance(claim, dict) or set(claim) != {'claim', 'quote', 'chunk_id'}:
            audit.update(quote_authenticity='failed', claim_support='failed')
            return False, 'invalid_claim', [], audit
        if not all(isinstance(claim[key], str) for key in ('claim', 'quote', 'chunk_id')):
            audit.update(quote_authenticity='failed', claim_support='failed')
            return False, 'invalid_claim_types', [], audit
        passage = lookup.get(claim['chunk_id'])
        quote = normalize(claim['quote'])
        source_quote = original_excerpt(passage['text'], quote) if passage else None
        if not passage or len(quote) < 20 or len(quote) > 1400 or source_quote is None:
            audit.update(quote_authenticity='failed', claim_support='failed')
            return False, 'unsupported_quote_or_citation', [], audit
        authenticity.append(True)
        claim_text = normalize(claim['claim'])
        quote_normalized = normalize(source_quote)
        textually_supported = bool(claim_text) and claim_text in quote_normalized
        support.append(textually_supported)
        answer_terms.update(re.findall(r'[a-z0-9]+', claim_text.lower()))
        if query_terms:
            claim_terms = set(re.findall(r'[a-z0-9]+', claim_text.lower()))
            matched = len(query_terms & claim_terms)
            relevant = matched >= 1 and matched / len(query_terms) >= 0.15
            relevance.append(relevant)
        else:
            relevant = None
        # Render citation metadata from trusted index, never from model output.
        checked.append(dict(quote=source_quote, claim=claim_text,
                            **{k: passage[k] for k in
                               ('paper_title', 'arxiv_version', 'page', 'section', 'chunk_id')}))
    audit['quote_authenticity'] = 'verified' if all(authenticity) else 'failed'
    audit['passage_relevance'] = ('lexical_heuristic_passed' if all(relevance) else 'lexical_heuristic_failed'
                                  if relevance else 'not_assessed')
    audit['claim_support'] = ('verbatim_source_text_only' if all(support) else 'failed')
    if query_terms:
        matched_terms = sorted(query_terms & answer_terms)
        completeness = dict(status='not_semantically_verified',
                            method='query-term coverage only; not semantic completeness',
                            matched_terms=matched_terms,
                            missing_terms=sorted(query_terms - answer_terms),
                            term_coverage=len(matched_terms) / len(query_terms))
    else:
        completeness = dict(status='not_semantically_verified',
                            method='no question supplied; completeness not assessed')
    audit['answer_completeness'] = completeness
    valid = (all(authenticity) and all(support) and
             (not relevance or all(relevance)))
    reason = 'textually_grounded_excerpts_only' if valid else 'claim_evidence_check_failed'
    return valid, reason, checked, audit


def render(claims):
    if not claims:
        return REFUSAL
    return '\n\n'.join(f'"{c["quote"]}" [{c["paper_title"]}; arXiv:{c["arxiv_version"]}; '
                        f'p. {c["page"]}; {c["section"]}; {c["chunk_id"]}]' for c in claims)
