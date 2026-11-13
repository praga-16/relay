import asyncio
import json
import hashlib
import asyncio
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.settings import ROOT, load_config
from app.retrieval.engine import Encoder, RetrievalTool, RetrievalInput
from app.models.standin import create_standin
from app.services.provider import Provider
from app.pipeline.engine import Engine, RequestManager
from app.monitoring.logger import Logger
from app.api.server import create_app
from app.api.server import Question
from tests.test_core import config, tool


@pytest.mark.asyncio
async def test_api_verified_stream(tmp_path):
    cfg=config(); sc=load_config('config/standin.json')
    sc.update(failure_probability=0,slow_probability=0,timeout_probability=0)
    provider=Provider(cfg,httpx.AsyncClient(transport=httpx.ASGITransport(app=create_standin(sc))))
    manager=RequestManager(cfg,Engine(cfg,tool,provider),Logger(tmp_path))
    # TestClient owns a separate event loop; construct/start shared async primitives there.
    with TestClient(create_app(manager,cfg)) as client:
        assert client.get('/').status_code==200
        assert client.get('/health').json()['source']=='stand-in'
        r=client.post('/ask',json={'question':'Why is dot-product attention scaled by the key dimension?'})
        assert r.status_code==200
        assert r.text.index('event: status') < r.text.index('event: answer')
        assert 'event: done' in r.text and 'p. 4' in r.text
        assert client.post('/ask',json={'question':'x','setting':'D'}).status_code==422
    records=[json.loads(x) for x in (tmp_path/'diagnostics.jsonl').read_text().splitlines()]
    assert len(records)==1 and records[0]['verification'][0]['valid']


@pytest.mark.asyncio
async def test_idempotency_reuses_completed_result_once(tmp_path):
    cfg=config(); sc=load_config('config/standin.json')
    sc.update(failure_probability=0,slow_probability=0,timeout_probability=0)
    provider=Provider(cfg,httpx.AsyncClient(transport=httpx.ASGITransport(app=create_standin(sc))))
    manager=RequestManager(cfg,Engine(cfg,tool,provider),Logger(tmp_path))
    with TestClient(create_app(manager,cfg)) as client:
        headers={'X-Idempotency-Key':'repeatable-1'}
        one=client.post('/ask',json={'question':'Why is dot-product attention scaled by the key dimension?'},headers=headers)
        two=client.post('/ask',json={'question':'Why is dot-product attention scaled by the key dimension?'},headers=headers)
        assert one.status_code==two.status_code==200
        assert one.text == two.text
        changed=client.post('/ask',json={'question':'A different question'},headers=headers)
        assert changed.status_code == 409
        assert changed.json()['detail'].startswith('X-Idempotency-Key')
    assert len((tmp_path/'diagnostics.jsonl').read_text().splitlines())==1


@pytest.mark.asyncio
async def test_one_disconnected_idempotent_client_does_not_cancel_other(tmp_path):
    class Manager:
        def __init__(self):
            self.started = asyncio.Event()
            self.complete = asyncio.Event()
            self.calls = 0
            self.finished = []

        async def submit(self, question, setting=None):
            self.calls += 1
            self.started.set()
            await self.complete.wait()
            return dict(request_id='shared-request', status='ok', answer='shared answer')

        def finish(self, trace, *args):
            self.finished.append(trace)

    class Request:
        headers = {'X-Idempotency-Key': 'shared-client-key'}
        disconnected = False

        async def is_disconnected(self):
            return self.disconnected

    manager = Manager()
    app = create_app(manager, config())
    endpoint = next(route.endpoint for route in app.routes if getattr(route, 'path', None) == '/ask')
    first_request, second_request = Request(), Request()
    first = await endpoint(Question(question='shared question'), first_request)
    second = await endpoint(Question(question='shared question'), second_request)
    first_stream, second_stream = first.body_iterator, second.body_iterator
    await first_stream.__anext__()
    await second_stream.__anext__()
    await manager.started.wait()
    shared = app.state.idempotency.entries['shared-client-key']
    first_request.disconnected = True
    with pytest.raises(StopAsyncIteration):
        await first_stream.__anext__()
    assert shared.subscribers == 1 and not shared.task.cancelling()
    assert manager.calls == 1

    manager.complete.set()
    remaining = [part async for part in second_stream]
    assert any('shared answer' in part for part in remaining)
    assert shared.task.done() and len(manager.finished) == 1


@pytest.mark.integration
def test_real_embeddings_and_indexes():
    if not (ROOT/'data/indexes/metadata.json').exists(): pytest.skip('Build indexes first')
    encoder=Encoder()
    vectors=encoder.encode(['Mimi audio codec', 'position-wise feed-forward network'])
    assert vectors.shape==(2,384)
    assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5)
    tool=RetrievalTool(encoder)
    results=[]
    for setting in 'ABC':
        result=tool(RetrievalInput('What is Mimi audio codec?',setting))
        assert len(result.passages)==(3 if setting=='A' else 5)
        assert any(p['arxiv_version']=='2410.00037v1' for p in result.passages)
        assert all(p['page']>0 and p['section'] and p['chunk_id'] for p in result.passages)
        assert all(p['chunk_tokens']<=(200 if setting=='A' else 500) for p in result.passages)
        results.extend(result.passages)
    rows=json.loads((ROOT/'data/extracted/paragraphs.json').read_text(encoding='utf-8'))
    for p in results:
        source='\n\n'.join(r['text'] for r in rows if r['arxiv_version']==p['arxiv_version'] and r['page']==p['page'] and r['section']==p['section'])
        assert p['text'] in source


def test_stale_index_metadata_is_rejected(tmp_path, monkeypatch):
    import app.retrieval.engine as module
    copied = tmp_path / 'data' / 'indexes'; copied.mkdir(parents=True)
    for name in ('200.faiss', '200.json', '500.faiss', '500.json', 'metadata.json'):
        (copied / name).write_bytes((ROOT / 'data' / 'indexes' / name).read_bytes())
    metadata = json.loads((copied / 'metadata.json').read_text())
    metadata['extraction_sha256'] = 'stale'
    (copied / 'metadata.json').write_text(json.dumps(metadata))
    original_root = module.ROOT
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / 'paper_manifest.json').write_bytes((original_root / 'paper_manifest.json').read_bytes())
    extracted = tmp_path / 'data' / 'extracted'; extracted.mkdir(parents=True)
    (extracted / 'paragraphs.json').write_bytes((original_root / 'data' / 'extracted' / 'paragraphs.json').read_bytes())
    class TinyEncoder:
        def encode(self, texts): return np.zeros((len(texts), 384), dtype=np.float32)
    with pytest.raises(RuntimeError, match='stale or incompatible'):
        module.RetrievalTool(TinyEncoder())(module.RetrievalInput('question', 'A'))


def _copy_index_fixture(tmp_path, monkeypatch):
    import shutil
    import app.retrieval.engine as module
    folder = tmp_path / 'data' / 'indexes'
    folder.mkdir(parents=True)
    for name in ('200.faiss', '200.json', '500.faiss', '500.json', 'metadata.json'):
        shutil.copyfile(ROOT / 'data' / 'indexes' / name, folder / name)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / 'paper_manifest.json').write_bytes((ROOT / 'paper_manifest.json').read_bytes())
    extracted = tmp_path / 'data' / 'extracted'; extracted.mkdir(parents=True)
    (extracted / 'paragraphs.json').write_bytes((ROOT / 'data' / 'extracted' / 'paragraphs.json').read_bytes())
    return module, folder


@pytest.mark.parametrize('change', ['corpus', 'manifest', 'embedding_model', 'revision'])
def test_index_rejects_changed_corpus_manifest_or_model(tmp_path, monkeypatch, change):
    module, folder = _copy_index_fixture(tmp_path, monkeypatch)
    if change == 'corpus':
        path = tmp_path / 'data' / 'extracted' / 'paragraphs.json'
        path.write_bytes(path.read_bytes() + b' ')
    elif change == 'manifest':
        path = tmp_path / 'paper_manifest.json'
        path.write_bytes(path.read_bytes() + b' ')
    else:
        original_config = module.load_config()
        original_config['embedding_model' if change == 'embedding_model' else 'embedding_revision'] = 'changed'
        monkeypatch.setattr(module, 'load_config', lambda: original_config)

    class TinyEncoder:
        def encode(self, texts): return np.zeros((len(texts), 384), dtype=np.float32)

    with pytest.raises(RuntimeError, match='stale or incompatible'):
        module.RetrievalTool(TinyEncoder())(module.RetrievalInput('question', 'A'))


@pytest.mark.parametrize('corruption', ['bytes', 'vector_count', 'dimension'])
def test_index_rejects_corruption_and_vector_shape_mismatch(tmp_path, monkeypatch, corruption):
    import sys
    from types import SimpleNamespace
    module, folder = _copy_index_fixture(tmp_path, monkeypatch)
    class TinyEncoder:
        def encode(self, texts): return np.zeros((len(texts), 384), dtype=np.float32)

    if corruption == 'bytes':
        (folder / '200.faiss').write_bytes(b'not a FAISS index')
        expected = 'Index files are unreadable'
    elif corruption == 'vector_count':
        rows = json.loads((folder / '200.json').read_text(encoding='utf-8'))
        (folder / '200.json').write_text(json.dumps(rows[:-1]), encoding='utf-8')
        expected = 'Index/vector metadata mismatch'
    else:
        rows = json.loads((folder / '200.json').read_text(encoding='utf-8'))
        fake_faiss = SimpleNamespace(read_index=lambda _path: SimpleNamespace(ntotal=len(rows), d=128))
        monkeypatch.setitem(sys.modules, 'faiss', fake_faiss)
        expected = 'Index/vector metadata mismatch'

    with pytest.raises(RuntimeError, match=expected):
        module.RetrievalTool(TinyEncoder())(module.RetrievalInput('question', 'A'))


def test_latest_indexes_match_current_metadata_and_dimensions(monkeypatch):
    import app.retrieval.engine as module
    class TinyEncoder:
        def encode(self, texts): return np.zeros((len(texts), 384), dtype=np.float32)
    tool = module.RetrievalTool(TinyEncoder())
    for setting in 'ABC':
        assert tool(module.RetrievalInput('index compatibility check', setting)).passages


@pytest.mark.parametrize('status', [500, 502, 503])
def test_standin_emits_configured_server_failure(status):
    settings = load_config('config/standin.json')
    settings.update(failure_probability=1, failure_status=status, timeout_probability=0,
                    slow_probability=0)
    with TestClient(create_standin(settings)) as client:
        response = client.post('/openai/v1/chat/completions', json={
            'model': 'openai/gpt-oss-20b',
            'messages': [{'role': 'user', 'content': '{"question":"test","passages":[]}'}],
            'max_completion_tokens': 20,
        })
    assert response.status_code == status
