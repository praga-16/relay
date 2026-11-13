import asyncio
import json
import re
import time
from dataclasses import dataclass
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from app.settings import load_config, ROOT
from app.retrieval.engine import RetrievalTool
from app.services.provider import Provider
from app.pipeline.engine import Engine, RequestManager
from app.monitoring.logger import Logger


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    setting: str = Field(default='A', pattern='^[ABC]$')


@dataclass
class SharedRequest:
    task: asyncio.Task
    fingerprint: tuple | None = None
    subscribers: int = 0
    abandoning: bool = False


class IdempotencyRegistry:
    def __init__(self):
        self.entries = {}
        self.lock = asyncio.Lock()

    async def subscribe(self, key, fingerprint, create_task):
        async with self.lock:
            entry = self.entries.get(key)
            if entry is not None and entry.fingerprint != fingerprint:
                raise ValueError('X-Idempotency-Key was already used for a different request')
            if entry is None or entry.abandoning:
                entry = SharedRequest(create_task(), fingerprint)
                self.entries[key] = entry
            entry.subscribers += 1
            if len(self.entries) > 256:
                done = [name for name, value in self.entries.items()
                        if name != key and value.task.done()]
                for name in done[:64]:
                    self.entries.pop(name, None)
            return entry

    async def unsubscribe(self, key, entry):
        async with self.lock:
            entry.subscribers -= 1
            if entry.subscribers == 0 and not entry.task.done():
                entry.abandoning = True
                entry.task.cancel()
                asyncio.create_task(self._remove_abandoned(key, entry))

    async def _remove_abandoned(self, key, entry):
        try:
            await entry.task
        except asyncio.CancelledError:
            pass
        finally:
            async with self.lock:
                if self.entries.get(key) is entry:
                    self.entries.pop(key, None)


def create_app(manager=None, config=None):
    cfg = config or load_config()
    @asynccontextmanager
    async def lifespan(app):
        nonlocal manager
        if manager is None:
            tool = await asyncio.to_thread(RetrievalTool)
            provider = Provider(cfg, persistent=True)
            manager = RequestManager(cfg, Engine(cfg, tool, provider), Logger(ROOT / 'results'))
        app.state.manager = manager
        await manager.start()
        yield
        await manager.close()
        await manager.engine.provider.close()
    app = FastAPI(title='The Relay', lifespan=lifespan)
    app.state.idempotency = IdempotencyRegistry()

    @app.get('/health')
    async def health():
        return {'source': cfg['source'], 'queue_length': manager.queue.qsize(),
                'peak_queue_length': manager.peak_queue, 'verified_excerpts_only': True}

    @app.get('/', response_class=HTMLResponse)
    async def home():
        return (ROOT / 'app/api/index.html').read_text(encoding='utf-8')

    @app.post('/ask')
    async def ask(body: Question, request: Request):
        idempotency_key = request.headers.get('X-Idempotency-Key')
        if idempotency_key and not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', idempotency_key):
            return HTMLResponse('Invalid X-Idempotency-Key', status_code=400)
        fingerprint = (body.question, body.setting)
        if idempotency_key:
            try:
                shared = await app.state.idempotency.subscribe(
                    idempotency_key, fingerprint,
                    lambda: asyncio.create_task(manager.submit(body.question, setting=body.setting)))
            except ValueError as exc:
                return JSONResponse({'detail': str(exc)}, status_code=409)
            task = shared.task
        else:
            shared = SharedRequest(asyncio.create_task(manager.submit(body.question, setting=body.setting)),
                                   subscribers=1)
            task = shared.task
        # Status events show progress but carry no unverified claims.
        async def events():
            started = time.perf_counter(); trace = None; first = None
            try:
                yield 'event: status\ndata: "Queued; retrieving and verifying evidence"\n\n'
                while not task.done():
                    if await request.is_disconnected():
                        return
                    await asyncio.sleep(.02)
                trace = await task
                yield 'event: metadata\ndata: ' + json.dumps({'request_id': trace['request_id'], 'status': trace['status']}) + '\n\n'
                answer = trace['answer']
                for offset in range(0, len(answer), 48):
                    if first is None: first = (time.perf_counter() - started) * 1000
                    yield 'event: answer\ndata: ' + json.dumps(answer[offset:offset + 48]) + '\n\n'
                    await asyncio.sleep(.005)
                yield 'event: done\ndata: {}\n\n'
            finally:
                if idempotency_key:
                    await app.state.idempotency.unsubscribe(idempotency_key, shared)
                    if shared.abandoning:
                        try: trace = await task
                        except asyncio.CancelledError: pass
                else:
                    shared.subscribers -= 1
                    if shared.subscribers == 0 and not task.done():
                        task.cancel()
                        try: trace = await task
                        except asyncio.CancelledError: pass
                if trace is None and task.done() and not task.cancelled():
                    try: trace = await task
                    except asyncio.CancelledError: pass
                if trace:
                    manager.finish(trace, first, (time.perf_counter() - started) * 1000)
        return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    return app
