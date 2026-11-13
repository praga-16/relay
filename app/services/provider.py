import asyncio
import json
import random
import time
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from app.services.budget import Budget, Circuit, LimitError
from app.settings import groq_credentials, ROOT


class ProviderError(Exception):
    def __init__(self, kind, status=None, retry_after=0):
        self.kind, self.status, self.retry_after = kind, status, retry_after
        super().__init__(kind)


@dataclass
class Completion:
    text: str
    tokens_in: int | None
    tokens_out: int | None
    first_token_ms: float | None
    total_ms: float


def classify(status, body):
    message = json.dumps(body).lower()
    if status == 429:
        if any(x in message for x in ('tokens per day', 'requests per day', 'daily', 'rpd', 'tpd', 'insufficient_quota')):
            return 'daily_quota'
        return 'rate_limited'
    if status in (401, 403):
        return 'authentication'
    if status >= 500:
        return 'server_error'
    return 'invalid_request'


class Provider:
    def __init__(self, cfg, client=None, persistent=False):
        self.cfg = cfg
        self.key = None
        if cfg['source'] == 'real':
            if not cfg.get('real_calls_approved'):
                raise RuntimeError('Real smoke/baseline requires explicit approval')
            if cfg['base_url'] != 'https://api.groq.com/openai/v1':
                raise RuntimeError('Groq credentials may only be sent to the intended API')
            self.key, model = groq_credentials()
            if model != cfg['model']:
                raise RuntimeError('Configured model differs from root .env; no silent switching')
        elif urlparse(cfg['base_url']).hostname not in ('127.0.0.1', 'localhost', 'standin'):
            raise RuntimeError('Stand-in must be local')
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(
            cfg['read_timeout_s'], connect=cfg['connect_timeout_s']))
        state = ROOT / 'logs/real_budget.json' if persistent and cfg['source'] == 'real' else None
        self.budget = Budget(cfg, state_path=state)
        self.circuit = Circuit(cfg['circuit_threshold'], cfg['circuit_cooldown_s'])
        self.random = random.Random(cfg['seed'])

    async def close(self):
        await self.client.aclose()

    async def generate(self, messages, trace):
        # UTF-8 byte count is conservative for byte-level LLM tokenizers, unlike len/4.
        estimate = len(json.dumps(messages, ensure_ascii=False).encode('utf-8')) + 128 + self.cfg['max_completion_tokens']
        total_in, total_out = 0, 0
        remaining_retries=max(0,self.cfg['max_retries']-trace.get('retries',0))
        for attempt in range(remaining_retries + 1):
            self.circuit.check()
            ticket = None
            started = time.perf_counter()
            record = dict(attempt=attempt, http_status=None, model=self.cfg['model'],
                          first_token_ms=None, tokens_in=None, tokens_out=None, headers={})
            trace.setdefault('provider_attempts', []).append(record)
            try:
                ticket = await self.budget.reserve(estimate)
                trace['provider_requests'] = trace.get('provider_requests', 0) + 1
                headers = {'Authorization': f'Bearer {self.key}'} if self.key else {}
                body = dict(model=self.cfg['model'], messages=messages, stream=True,
                            max_completion_tokens=self.cfg['max_completion_tokens'], temperature=0,
                            stream_options={'include_usage': True})
                if self.cfg['source'] == 'real' and self.cfg['model'].startswith('openai/gpt-oss-'):
                    body.update(reasoning_effort='low', include_reasoning=False,
                                response_format={'type': 'json_object'})
                    record['reasoning_effort'] = 'low'
                text, first, usage, done = '', None, None, False
                async with self.client.stream('POST', self.cfg['base_url'] + '/chat/completions',
                                              json=body, headers=headers) as response:
                    record['http_status'] = response.status_code
                    record['headers'] = {k: v for k, v in response.headers.items()
                                         if k.startswith('x-ratelimit-') or k in ('retry-after', 'x-request-id')}
                    await self.budget.observe(record['headers'])
                    if response.status_code >= 400:
                        raw = await response.aread()
                        try:
                            error = json.loads(raw)
                        except ValueError:
                            error = {'error': 'non-JSON provider response'}
                        kind = classify(response.status_code, error)
                        # Keep only classified/code details, never raw request echoes or credentials.
                        record['error'] = kind
                        detail = json.dumps(error)
                        if self.key: detail = detail.replace(self.key, '[REDACTED]')
                        import re
                        detail = re.sub(r'gsk_[A-Za-z0-9_-]+', '[REDACTED]', detail)
                        record['error_detail'] = detail[:800]
                        if kind == 'daily_quota':
                            await self.budget.block_daily()
                        raise ProviderError(kind, response.status_code, float(response.headers.get('retry-after', 0)))
                    async for line in response.aiter_lines():
                        if not line.startswith('data: '):
                            continue
                        if line[6:] == '[DONE]':
                            done = True; break
                        item = json.loads(line[6:])
                        choices = item.get('choices') or []
                        if choices and choices[0].get('finish_reason'):
                            record['finish_reason'] = choices[0]['finish_reason']
                        content = choices[0].get('delta', {}).get('content') if choices else None
                        if content:
                            if first is None:
                                first = (time.perf_counter() - started) * 1000
                            text += content
                        usage = item.get('usage') or item.get('x_groq', {}).get('usage') or usage
                tin = usage.get('prompt_tokens') if usage else None
                tout = usage.get('completion_tokens') if usage else None
                record.update(tokens_in=tin, tokens_out=tout, first_token_ms=first)
                await self.budget.reconcile(ticket, tin + tout if tin is not None and tout is not None else None)
                if not done or not text:
                    raise ProviderError('completion_limit' if record.get('finish_reason')=='length' else 'incomplete_stream', 502)
                if tin is not None: total_in += tin
                if tout is not None: total_out += tout
                self.circuit.success()
                return Completion(text, total_in if usage else None, total_out if usage else None,
                                  first, (time.perf_counter() - started) * 1000)
            except asyncio.CancelledError:
                record['error'] = 'cancelled'; self.circuit.release_probe(); raise
            except LimitError:
                self.circuit.release_probe(); raise
            except (ProviderError, httpx.HTTPError, ValueError) as exc:
                if isinstance(exc, httpx.TimeoutException): kind = 'timeout'
                elif isinstance(exc, httpx.HTTPError): kind = 'connection'
                else: kind = getattr(exc, 'kind', 'invalid_stream')
                record['error'] = kind
                retryable = kind in ('rate_limited', 'timeout', 'connection', 'server_error', 'incomplete_stream')
                if kind in ('timeout', 'connection', 'server_error', 'incomplete_stream'):
                    self.circuit.failure()
                else:
                    self.circuit.release_probe()
                if not retryable or attempt >= remaining_retries:
                    raise ProviderError(kind, getattr(exc, 'status', None)) from None
                trace['retries'] = trace.get('retries', 0) + 1
                delay = max(getattr(exc, 'retry_after', 0), min(4, .15 * 2 ** attempt) + self.random.uniform(0, .08))
                before = time.perf_counter(); await asyncio.sleep(delay)
                trace['retry_wait_ms'] = trace.get('retry_wait_ms', 0) + (time.perf_counter() - before) * 1000
            finally:
                record['total_ms'] = (time.perf_counter() - started) * 1000
