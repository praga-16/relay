"""OpenAI-compatible local simulator; extractive selection is NOT an LLM quality proxy."""
import asyncio
import json
import random
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.settings import load_config
from app.services.budget import Budget, LimitError


def select_excerpts(messages):
    try:
        data = json.loads(messages[-1]['content'])
        question, passages = data['question'], data['passages']
    except (ValueError, KeyError, IndexError):
        return json.dumps({'claims': []})
    stop = set('what why how does do is are the a an in of to for and from paper model describe explain according'.split())
    terms = set(re.findall(r'[a-z0-9]+', question.lower())) - stop
    candidates = []
    for passage in passages:
        sentences = re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', passage['text']))
        for sentence in sentences:
            words = set(re.findall(r'[a-z0-9]+', sentence.lower()))
            overlap = len(terms & words) / max(1, len(terms))
            if overlap >= .32 and 35 <= len(sentence) <= 1000:
                candidates.append((overlap, sentence, passage['chunk_id']))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return json.dumps({'claims': [{'claim': s, 'quote': s, 'chunk_id': cid}
                                  for _, s, cid in candidates[:2]]})


def create_standin(config=None):
    cfg = dict(config or load_config('config/standin.json'))
    failure_status = int(cfg.get('failure_status', 500))
    if failure_status not in (500, 502, 503):
        raise ValueError('failure_status must be 500, 502, or 503')
    rng = random.Random(cfg['seed'])
    budget = Budget(dict(cfg, safety_margin=0))
    active = 0
    app = FastAPI(title='Relay stand-in (synthetic, uncalibrated)' if not cfg['calibrated'] else 'Relay stand-in')
    app.state.config = cfg; app.state.budget = budget

    @app.get('/health')
    async def health():
        return {'source': 'stand-in', 'calibrated': cfg['calibrated'], 'active': active}

    @app.get('/openai/v1/models')
    async def models():
        return {'data': [{'id': 'openai/gpt-oss-20b'}]}

    @app.post('/openai/v1/chat/completions')
    async def completion(request: Request):
        nonlocal active
        body = await request.json()
        if body.get('model') != 'openai/gpt-oss-20b':
            return JSONResponse({'error': {'message': 'unknown model'}}, status_code=400)
        output = select_excerpts(body['messages'])
        tin = max(1, len(json.dumps(body['messages'])) // 4)
        tout = max(1, len(output) // 4)
        try:
            ticket = await budget.reserve(tin + body.get('max_completion_tokens', 500))
        except LimitError as exc:
            return JSONResponse({'error': {'message': exc.kind, 'code': exc.kind}}, status_code=429,
                                headers={'retry-after': str(round(exc.retry_after, 3))})
        await budget.reconcile(ticket, tin + tout)
        failure, slow, timeout = rng.random(), rng.random(), rng.random()
        jitter = rng.uniform(0, cfg['latency_jitter_s'])
        if failure < cfg['failure_probability']:
            return JSONResponse({'error': {'message': 'simulated transient error'}}, status_code=failure_status)
        delay = cfg['first_token_s'] + jitter + cfg['load_delay_s'] * active
        if slow < cfg['slow_probability']: delay += cfg['slow_delay_s']
        if timeout < cfg['timeout_probability']: delay += cfg['timeout_delay_s']
        headers = {'x-ratelimit-limit-requests': str(cfg['rpd']),
                   'x-ratelimit-limit-tokens': str(cfg['tpm']),
                   'x-ratelimit-remaining-requests': str(max(0, cfg['rpd'] - len(budget.events))),
                   'x-ratelimit-remaining-tokens': str(max(0, cfg['tpm'] - sum(v[1] for v in budget.events.values() if time.time() - v[0] < 60)))}
        async def stream():
            nonlocal active
            active += 1
            try:
                await asyncio.sleep(delay)
                for start in range(0, len(output), 32):
                    item = {'choices': [{'delta': {'content': output[start:start + 32]}}]}
                    yield 'data: ' + json.dumps(item) + '\n\n'
                    await asyncio.sleep(cfg['token_interval_s'])
                yield 'data: ' + json.dumps({'choices': [], 'usage': {'prompt_tokens': tin, 'completion_tokens': tout}}) + '\n\n'
                yield 'data: [DONE]\n\n'
            finally:
                active -= 1
        return StreamingResponse(stream(), media_type='text/event-stream', headers=headers)
    return app


app = create_standin()
