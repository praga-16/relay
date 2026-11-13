"""Single-process rolling budgets. Persistence protects daily usage across restarts."""
import asyncio
import json
import time
import uuid
from pathlib import Path


class LimitError(Exception):
    def __init__(self, kind, retry_after=0):
        self.kind, self.retry_after = kind, retry_after
        super().__init__(kind)


class Budget:
    def __init__(self, config, clock=time.time, state_path=None):
        self.cfg = dict(config); self.clock = clock
        self.lock = asyncio.Lock(); self.events = {}; self.blocked_until = 0
        self.blocked_kind = 'provider_cooldown'
        self.state_path = Path(state_path) if state_path else None
        if self.state_path and self.state_path.exists():
            saved = json.loads(self.state_path.read_text())
            self.events = saved.get('events', saved)
            self.blocked_until = saved.get('blocked_until', 0) if 'events' in saved else 0
            self.blocked_kind = saved.get('blocked_kind', 'provider_cooldown')

    def _save(self):
        if self.state_path:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix('.tmp')
            tmp.write_text(json.dumps(dict(events=self.events, blocked_until=self.blocked_until,
                                           blocked_kind=self.blocked_kind)))
            tmp.replace(self.state_path)

    async def block_daily(self, seconds=86400):
        async with self.lock:
            self.blocked_until = self.clock() + seconds
            self.blocked_kind = 'daily_provider_quota'
            self._save()

    async def reserve(self, tokens):
        async with self.lock:
            now = self.clock()
            self.events = {k: v for k, v in self.events.items() if now - v[0] < 86400}
            if now < self.blocked_until:
                raise LimitError(self.blocked_kind, self.blocked_until - now)
            for seconds, request_limit, token_limit, label in [
                (86400, self.cfg['rpd'], self.cfg['tpd'], 'daily'),
                (60, self.cfg['rpm'], self.cfg['tpm'], 'minute')]:
                recent = [v for v in self.events.values() if now - v[0] < seconds]
                if len(recent) >= request_limit or sum(v[1] for v in recent) + tokens > token_limit:
                    kind = label + ('_requests' if len(recent) >= request_limit else '_tokens')
                    wait = max(0, seconds - (now - min((v[0] for v in recent), default=now)))
                    raise LimitError(kind, wait)
            ticket = uuid.uuid4().hex
            self.events[ticket] = [now, tokens]; self._save()
            return ticket

    async def reconcile(self, ticket, actual_tokens=None):
        async with self.lock:
            if ticket in self.events and actual_tokens is not None:
                self.events[ticket][1] = actual_tokens
            # Unknown usage retains reservation; failed attempts still count as requests.
            self._save()

    async def observe(self, headers):
        async with self.lock:
            margin = 1 - self.cfg.get('safety_margin', .2)
            # Groq requests header is DAILY, tokens header is per MINUTE.
            for header, field in [('x-ratelimit-limit-requests', 'rpd'), ('x-ratelimit-limit-tokens', 'tpm')]:
                try:
                    self.cfg[field] = min(self.cfg[field], max(1, int(int(headers[header]) * margin)))
                except (KeyError, ValueError):
                    pass
            try:
                retry = float(headers.get('retry-after', 0))
                self.blocked_until = max(self.blocked_until, self.clock() + retry)
            except ValueError:
                pass


class Circuit:
    def __init__(self, threshold=3, cooldown=10, clock=time.monotonic):
        self.threshold, self.cooldown, self.clock = threshold, cooldown, clock
        self.failures = 0; self.opened = None; self.probe = False

    def check(self):
        if self.opened is not None:
            if self.clock() - self.opened < self.cooldown or self.probe:
                raise LimitError('circuit_open', self.cooldown)
            self.probe = True

    def success(self):
        self.failures = 0; self.opened = None; self.probe = False

    def failure(self):
        self.failures += 1; self.probe = False
        if self.failures >= self.threshold:
            self.opened = self.clock()

    def release_probe(self):
        self.probe = False
