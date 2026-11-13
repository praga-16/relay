import asyncio
import httpx
import pytest
from app.services.budget import Budget, LimitError
from app.services.provider import Provider
from app.pipeline.engine import RequestManager
from app.api.server import IdempotencyRegistry
from app.monitoring.logger import Logger
from tests.test_core import config


@pytest.mark.asyncio
async def test_daily_block_persists_and_names_cause(tmp_path):
    cfg=dict(rpm=24,tpm=6400,rpd=800,tpd=160000)
    b=Budget(cfg,state_path=tmp_path/'budget.json')
    await b.block_daily()
    restored=Budget(cfg,state_path=tmp_path/'budget.json')
    with pytest.raises(LimitError,match='daily_provider_quota'):await restored.reserve(10)


@pytest.mark.asyncio
async def test_user_cancellation_is_recordable_and_worker_survives(tmp_path):
    finished=asyncio.Event()
    class Slow:
        async def run(self,*a):
            try:await asyncio.sleep(1)
            finally:finished.set()
    m=RequestManager(config(),Slow(),Logger(tmp_path));await m.start()
    task=asyncio.create_task(m.submit('cancel this'))
    await asyncio.sleep(.02);task.cancel()
    trace=await task
    assert trace['status']=='timeout' and trace['error']=='cancelled'
    await asyncio.wait_for(finished.wait(),1)
    assert all(not w.done() for w in m.workers)
    m.finish(trace)
    await m.close()


@pytest.mark.asyncio
async def test_shared_retry_allowance_not_reset_on_generation():
    calls=[]
    async def fail(r):calls.append(r);return httpx.Response(503,json={'error':'temporary'})
    cfg=config();trace={'retries':2}
    p=Provider(cfg,httpx.AsyncClient(transport=httpx.MockTransport(fail)))
    from app.services.provider import ProviderError
    with pytest.raises(ProviderError):await p.generate([],trace)
    assert len(calls)==1 and trace['retries']==2
    await p.close()


@pytest.mark.asyncio
async def test_usage_retained_on_empty_content():
    async def empty(r):
        return httpx.Response(200,text='data: {"choices":[{"delta":{},"finish_reason":"length"}],"usage":{"prompt_tokens":7,"completion_tokens":10}}\n\ndata: [DONE]\n\n')
    p=Provider(config(max_retries=0),httpx.AsyncClient(transport=httpx.MockTransport(empty)));trace={}
    from app.services.provider import ProviderError
    with pytest.raises(ProviderError,match='completion_limit'):await p.generate([],trace)
    assert trace['provider_attempts'][0]['tokens_out']==10
    assert next(iter(p.budget.events.values()))[1]==17
    await p.close()


@pytest.mark.asyncio
async def test_shutdown_cancels_queued_callers(tmp_path):
    class Slow:
        async def run(self, *args): await asyncio.sleep(10)
    cfg = config(concurrency=1, queue_size=3, deadline_s=20)
    manager = RequestManager(cfg, Slow(), Logger(tmp_path)); await manager.start()
    first = asyncio.create_task(manager.submit('first'))
    second = asyncio.create_task(manager.submit('second'))
    await asyncio.sleep(.02)
    await manager.close()
    assert (await first)['status'] == 'timeout'
    assert (await second)['status'] == 'timeout'
    assert manager.workers == []


@pytest.mark.asyncio
async def test_shared_idempotent_task_cancellation_and_completion():
    registry = IdempotencyRegistry()
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def work():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    first = await registry.subscribe('shared', ('question', 'A'), lambda: asyncio.create_task(work()))
    second = await registry.subscribe('shared', ('question', 'A'), lambda: pytest.fail('must reuse task'))
    assert first is second and first.subscribers == 2
    await started.wait()
    await registry.unsubscribe('shared', first)
    assert first.subscribers == 1 and not first.task.cancelling()
    await registry.unsubscribe('shared', second)
    await cancelled.wait()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert 'shared' not in registry.entries

    completed = asyncio.Event()
    finished = await registry.subscribe(
        'completed', ('another question', 'B'),
        lambda: asyncio.create_task(_complete_when_released(completed)))
    await registry.subscribe('completed', ('another question', 'B'), lambda: None)
    completed.set()
    assert await finished.task == 'done'
    await registry.unsubscribe('completed', finished)
    await registry.unsubscribe('completed', finished)
    assert registry.entries['completed'] is finished


async def _complete_when_released(event):
    await event.wait()
    return 'done'
