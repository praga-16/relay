"""Explicitly approved, bounded real baseline. No automatic retries, no load testing."""
import asyncio
import json
import time
from app.settings import ROOT, load_config
from app.retrieval.engine import RetrievalTool, RetrievalInput
from app.pipeline.engine import Engine, RequestManager, SYSTEM
from app.services.provider import Provider
from app.monitoring.logger import Logger


async def main():
    approval=json.loads((ROOT/'config/real_approval.json').read_text())
    if not approval.get('baseline_approved'): raise RuntimeError('Baseline approval missing')
    cfg=load_config()
    cfg.update(source='real',base_url='https://api.groq.com/openai/v1',real_calls_approved=True,
               max_retries=0,verification_attempts=1,max_completion_tokens=500,deadline_s=45)
    tool=await asyncio.to_thread(RetrievalTool)
    provider=Provider(cfg,persistent=True)
    manager=RequestManager(cfg,Engine(cfg,tool,provider),Logger(ROOT/'results'));await manager.start()
    dataset=json.loads((ROOT/'data/evaluation/questions.json').read_text())
    selected=[next(q for q in dataset if q['id']==i) for i in ('q01','q07','q11')]
    existing=[]
    raw=ROOT/'results/diagnostics.jsonl'
    if raw.exists():
        existing=[json.loads(l) for l in raw.read_text().splitlines()
                  if json.loads(l).get('scenario')=='Real baseline']
    already_sent=sum(r.get('provider_requests',0) for r in existing)
    if already_sent>=3:
        await provider.close();await manager.close()
        raise RuntimeError('Approved three-request baseline already consumed; new approval required')
    selected=selected[already_sent:]
    before_run=time.perf_counter(); ids=[r['request_id'] for r in existing]
    (ROOT/'experiments').mkdir(exist_ok=True)
    try:
        for index,q in enumerate(selected):
            if index:
                for _ in range(3): await asyncio.sleep(65/3)
            result=await asyncio.to_thread(tool,RetrievalInput(q['question'],'A'))
            evidence=[p for p in result.passages if p['similarity_score']>=cfg['min_similarity']]
            messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps({'question':q['question'],'passages':evidence},ensure_ascii=False)}]
            reserve=len(json.dumps(messages,ensure_ascii=False).encode('utf-8'))+128+500
            if reserve>6000: raise RuntimeError(f'Preflight reservation {reserve} exceeds approved 6000; no call made')
            started=time.perf_counter()
            trace=await manager.submit(q['question'],'Real baseline','A',q)
            first=(time.perf_counter()-started)*1000
            for offset in range(0,len(trace['answer']),48):await asyncio.sleep(.005)
            manager.finish(trace,first,(time.perf_counter()-started)*1000)
            ids.append(trace['request_id'])
            print('Baseline',q['id'],trace['status'],'ready_ms',round(first,1),flush=True)
            if trace['status']!='ok':
                print('Stopping baseline after provider failure; no further calls',flush=True);break
    finally:
        await manager.close();await provider.close()
        (ROOT/'experiments/real_baseline.json').write_text(json.dumps(dict(source='real',request_ids=ids,
            duration_s=time.perf_counter()-before_run,approved_request_cap=3,approved_reservation_cap=18000,
            relay_config=cfg),indent=2))


if __name__=='__main__':asyncio.run(main())
