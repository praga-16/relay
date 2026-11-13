import asyncio
import csv
import json
import time
import fitz
import httpx
import numpy as np
import pytest
from app.settings import load_config, ROOT, groq_credentials
from app.retrieval import ingest
from app.retrieval.ingest import PAPERS, inspect_pdf, sha256
from app.retrieval.engine import chunks, RetrievalOutput, RetrievalTool, RetrievalInput
from app.services.budget import Budget, Circuit, LimitError
from app.services.provider import Provider, ProviderError, classify
from app.models.standin import create_standin
from app.pipeline.verification import verify, check_evidence, render, REFUSAL
from app.pipeline.engine import Engine, RequestManager
from app.monitoring.logger import Logger, FIELDS, percentiles


def config(**updates):
    c = load_config(); c.update(rpm=1000, tpm=1000000, rpd=10000, tpd=10000000,
                               base_url='http://standin/openai/v1', **updates)
    return c


def passage():
    return dict(paper_title='Attention Is All You Need', arxiv_version='1706.03762v7',
                page=4, section='3.2 Attention', chunk_id='1706.03762v7:p4:test',
                text='Scaled dot-product attention uses the square root of the key dimension to avoid small gradients.',
                similarity_score=.8)


def tool(args):
    return RetrievalOutput('retrieve_papers', vars(args), [passage()])


def test_paper_manifest():
    data = json.loads((ROOT / 'paper_manifest.json').read_text())
    assert len(data) == 3
    for p, (identifier, version, _) in zip(data, PAPERS):
        path = ROOT / 'papers' / f'{identifier}{version}.pdf'
        assert inspect_pdf(path, identifier, version) == p['page_count']
        assert sha256(path.read_bytes()) == p['sha256'] == p['official_sha256']
        assert p['verification_status'] == 'official_sha256_match'


def test_extraction():
    rows = json.loads((ROOT / 'data/extracted/paragraphs.json').read_text(encoding='utf-8'))
    assert len(rows) > 1000
    assert all(p['page'] > 0 and p['section'] and p['text'] for p in rows)
    assert {p['arxiv_version'] for p in rows} == {i + v for i, v, _ in PAPERS}


def test_prepare_uses_verified_package_paper_when_originals_are_absent(tmp_path, monkeypatch):
    identifier, version, title = '9999.12345', 'v1', 'Packaged paper'
    name = identifier + version
    papers = tmp_path / 'papers'
    papers.mkdir()
    pdf = papers / f'{name}.pdf'
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), name)
    document.save(pdf)
    document.close()
    monkeypatch.setattr(ingest, 'ROOT', tmp_path)
    monkeypatch.setattr(ingest, 'PAPERS', [(identifier, version, title)])

    manifest = ingest.prepare(download=False)

    assert pdf.is_file()
    assert manifest[0]['title'] == title
    assert manifest[0]['verification_status'] == 'embedded_version_only'


class Tokenizer:
    def encode(self, t, **kw): return t.split()
    def decode(self, ids, **kw): return ' '.join(ids)
    def __call__(self, text, **kw):
        import re
        matches = list(re.finditer(r'\S+', text))
        return {'input_ids':[m.group() for m in matches], 'offset_mapping':[m.span() for m in matches]}


def test_chunks_are_bounded_and_unique():
    p = passage(); p.pop('chunk_id'); p['text'] = ' '.join('word' + str(i) for i in range(700))
    rows = chunks([p, dict(p, page=5)], 200, Tokenizer())
    assert max(p['chunk_tokens'] for p in rows) <= 200
    assert len({p['chunk_id'] for p in rows}) == len(rows)
    assert rows[-1]['text'].endswith('word699')
    original = dict(p, text='Mimi Uses Unicode: \u221a and CASE. ' * 50)
    assert chunks([original], 200, Tokenizer())[0]['text'].startswith('Mimi Uses Unicode: \u221a and CASE.')


def test_citations_and_claims():
    p = passage()
    raw = json.dumps({'claims': [{'claim': p['text'], 'quote': p['text'], 'chunk_id': p['chunk_id']}]})
    valid, _, claims = verify(raw, [p]); assert valid
    assert 'p. 4' in render(claims) and '1706.03762v7' in render(claims)
    assert not verify(raw.replace('square root', 'cube root'), [p])[0]
    assert not verify(raw.replace('p4:test', 'p99:test'), [p])[0]
    assert not verify('{"claims":[{"claim":null,"quote":null,"chunk_id":[]}] }', [p])[0]
    assert verify('{"claims":[]}', [p]) == (True, 'refused', [])
    assert render([]) == REFUSAL
    valid, _, _, checks = check_evidence(raw, [p], 'Why is dot-product attention scaled for large key dimensions?')
    assert valid
    assert checks['quote_authenticity'] == 'verified'
    assert checks['passage_relevance'] == 'lexical_heuristic_passed'
    assert checks['claim_support'] == 'verbatim_source_text_only'
    assert checks['answer_completeness']['status'] == 'not_semantically_verified'
    assert checks['answer_completeness']['term_coverage'] < 1
    irrelevant, _, _, checks = check_evidence(raw, [p], 'How do web crawlers deduplicate documents?')
    assert not irrelevant and checks['passage_relevance'] == 'lexical_heuristic_failed'
    altered_claim = json.dumps({'claims': [{'claim': 'The cubic root prevents small gradients.',
                                             'quote': p['text'], 'chunk_id': p['chunk_id']}]})
    supported, _, _, checks = check_evidence(altered_claim, [p], 'Why is dot-product attention scaled?')
    assert not supported and checks['quote_authenticity'] == 'verified'
    assert checks['claim_support'] == 'failed'
    multiline = dict(p, text='Exact source\n\nquote with  multiple spaces and Unicode \u221a.')
    raw = json.dumps({'claims': [{'claim': 'Exact source quote with multiple spaces and Unicode \u221a.',
                                  'quote': 'Exact source quote with multiple spaces and Unicode \u221a.',
                                  'chunk_id': p['chunk_id']}]})
    valid, _, claims = verify(raw, [multiline])
    assert valid and claims[0]['quote'] == multiline['text']


@pytest.mark.asyncio
async def test_budget_reserve_reconcile_and_expiry():
    now = [0.0]; cfg = dict(rpm=2, tpm=100, rpd=3, tpd=150)
    b = Budget(cfg, clock=lambda: now[0])
    t = await b.reserve(70)
    with pytest.raises(LimitError, match='minute_tokens'): await b.reserve(40)
    await b.reconcile(t, 20); await b.reserve(40)
    with pytest.raises(LimitError, match='minute_requests'): await b.reserve(1)
    now[0] = 61; await b.reserve(60)
    with pytest.raises(LimitError, match='daily_requests'): await b.reserve(1)
    now[0] = 86462; await b.reserve(100)


@pytest.mark.asyncio
async def test_atomic_reservations():
    b = Budget(dict(rpm=5, tpm=100, rpd=10, tpd=1000))
    results = await asyncio.gather(*(b.reserve(30) for _ in range(10)), return_exceptions=True)
    assert sum(isinstance(r, str) for r in results) == 3


@pytest.mark.asyncio
async def test_headers_and_persistence(tmp_path):
    cfg = dict(rpm=24, tpm=6400, rpd=800, tpd=160000, safety_margin=.2)
    b = Budget(cfg, state_path=tmp_path/'budget.json')
    await b.reserve(100)
    await b.observe({'x-ratelimit-limit-requests': '500', 'x-ratelimit-limit-tokens': '4000'})
    assert b.cfg['rpd'] == 400 and b.cfg['tpm'] == 3200 and b.cfg['rpm'] == 24
    assert len(Budget(cfg, state_path=tmp_path/'budget.json').events) == 1


def test_circuit():
    clock = [0]; c = Circuit(2, 10, lambda: clock[0])
    c.failure(); c.failure()
    with pytest.raises(LimitError): c.check()
    clock[0] = 11; c.check()
    with pytest.raises(LimitError): c.check()
    c.success(); c.check()


@pytest.mark.parametrize('code,body,kind', [(429, {'message': 'TPM exceeded'}, 'rate_limited'),
    (429, {'message': 'daily tokens exhausted'}, 'daily_quota'), (401, {}, 'authentication'),
    (503, {}, 'server_error'), (400, {}, 'invalid_request')])
def test_error_classes(code, body, kind): assert classify(code, body) == kind


@pytest.mark.asyncio
async def test_provider_retry_and_stream():
    calls = []
    async def handler(request):
        calls.append(request)
        if len(calls) == 1: return httpx.Response(503, json={'error': 'temporary'})
        text = 'data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: {"usage":{"prompt_tokens":5,"completion_tokens":2}}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=text)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    p = Provider(config(), client); trace = {}
    result = await p.generate([{'role': 'user', 'content': 'hi'}], trace)
    assert result.text == 'hello' and result.tokens_in == 5 and trace['retries'] == 1
    assert len(p.budget.events) == 2
    await p.close()


@pytest.mark.asyncio
async def test_daily_quota_not_retried():
    calls = []
    async def handler(r):
        calls.append(r); return httpx.Response(429, json={'error': {'message': 'RPD daily quota'}})
    p = Provider(config(), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError, match='daily_quota'): await p.generate([], {})
    with pytest.raises(LimitError): await p.generate([], {})
    assert len(calls) == 1
    await p.close()


@pytest.mark.asyncio
async def test_timeout_retries():
    async def handler(r): raise httpx.ReadTimeout('test', request=r)
    p = Provider(config(max_retries=1), httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    trace = {}
    with pytest.raises(ProviderError, match='timeout'): await p.generate([], trace)
    assert trace['retries'] == 1
    await p.close()


@pytest.mark.asyncio
async def test_standin_and_five_stages(tmp_path):
    sc = load_config('config/standin.json'); sc.update(failure_probability=0, timeout_probability=0, slow_probability=0)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_standin(sc)))
    cfg = config()
    p = Provider(cfg, client)
    trace = {}; answer = await Engine(cfg, tool, p).run('Why is dot-product attention scaled by the key dimension?', trace)
    assert 'p. 4' in answer
    assert set(trace['stages']) == {'understand', 'retrieval', 'decision_tool_execution', 'generation', 'verification'}
    assert trace['tool_calls'][0]['tool'] == 'retrieve_papers'
    await p.close()


@pytest.mark.asyncio
async def test_refusal_and_bounded_loop():
    class Never:
        async def generate(self, *a): raise AssertionError('no provider call expected')
    def empty(args): return RetrievalOutput('retrieve_papers', vars(args), [])
    cfg = config(); trace = {}
    assert await Engine(cfg, empty, Never()).run('Unanswerable question', trace) == REFUSAL
    assert len(trace['tool_calls']) == 2
    assert trace['verification'][0]['checks']['answer_completeness'] == 'abstained'


@pytest.mark.asyncio
async def test_queue_deadline_overflow_concurrency(tmp_path):
    active, peak = 0, 0
    class Slow:
        async def run(self, *args):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            try: await asyncio.sleep(.1); return REFUSAL
            finally: active -= 1
    cfg = config(concurrency=1, queue_size=1, deadline_s=.04)
    m = RequestManager(cfg, Slow(), Logger(tmp_path)); await m.start()
    first = asyncio.create_task(m.submit('test'))
    await asyncio.sleep(.01)
    rows = await asyncio.gather(m.submit('second'), m.submit('third'), first)
    assert any(r['error'] == 'queue_full' for r in rows)
    assert any(r['status'] == 'timeout' for r in rows)
    await asyncio.sleep(.01)
    assert peak == 1 and active == 0
    for row in rows: m.finish(row)
    assert len(list(csv.DictReader((tmp_path/'results.csv').open()))) == 3
    await m.close()


def test_logger_and_percentiles(tmp_path):
    logger = Logger(tmp_path)
    assert next(csv.reader(logger.csv.open())) == FIELDS
    with pytest.raises(ValueError, match='schema mismatch'):
        logger.record({field: None for field in FIELDS[:-1]}, {})
    assert percentiles([1, 2, 3, 4]) == {'p50': 2.5, 'p95': 3.8499999999999996, 'p99': 3.9699999999999998}
    assert percentiles([]) is None


def test_hybrid_reranker_combines_vector_and_bm25(monkeypatch):
    import sys
    from types import SimpleNamespace

    class Encoder:
        def encode(self, texts): return np.zeros((len(texts), 384), dtype=np.float32)

    class Index:
        ntotal = 2
        def search(self, _query, _count):
            return np.array([[0.5, 0.4]], dtype=np.float32), np.array([[0, 1]])

    monkeypatch.setitem(sys.modules, 'faiss', SimpleNamespace())
    tool_instance = RetrievalTool(Encoder())
    rows = [dict(paper_title='Paper', arxiv_version='v1', page=1, section='S',
                 chunk_id='first', text='alpha evidence'),
            dict(paper_title='Paper', arxiv_version='v1', page=2, section='S',
                 chunk_id='second', text='beta evidence')]
    tool_instance.cache[500] = (Index(), rows)
    result = tool_instance(RetrievalInput('beta', 'C'))
    assert result.passages[0]['chunk_id'] == 'second'
    assert result.passages[0]['hybrid_score'] > result.passages[1]['hybrid_score']


def test_no_real_without_approval():
    cfg = config(); cfg['source'] = 'real'
    with pytest.raises(RuntimeError, match='approval'): Provider(cfg)
