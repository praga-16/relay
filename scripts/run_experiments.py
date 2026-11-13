"""Actual loopback HTTP load. Never invokes Groq. Uses simulator per scenario."""
import argparse
import asyncio
import hashlib
import json
import socket
import time
from datetime import datetime, timezone
import httpx
import uvicorn
from app.settings import ROOT, load_config
from app.models.standin import create_standin
from app.services.provider import Provider
from app.pipeline.engine import Engine, RequestManager
from app.retrieval.engine import RetrievalTool
from app.monitoring.logger import Logger

SCENARIOS = {
 'Steady': dict(n=12, interval=.5),
 'Burst': dict(n=65, interval=0),
 'Sustained overload': dict(n=120, interval=.1),
 'Per-minute limit halved': dict(n=18, interval=.03, half=True),
 'Daily budget exhausted': dict(n=8, interval=.03, daily=True),
}


async def run_batch(tool, scenario, specification, quality=False, output_dir=None):
    cfg = load_config(); sc = load_config('config/standin.json')
    # Deliberately accelerated synthetic capacity; don't label as account limits.
    cfg.update(source='stand-in', rpm=200, tpm=1000000, rpd=10000, tpd=10000000,
               deadline_s=1.5 if not quality else 10, queue_size=15, concurrency=3,
               max_retries=2)
    cfg['max_retries']=specification.get('max_retries',cfg['max_retries'])
    if specification.get('always_fail'):sc['failure_probability']=1
    if quality:
        sc.update(rpm=1000, tpm=1000000, failure_probability=0, slow_probability=0, timeout_probability=0)
    if specification.get('half'): sc['rpm'] = 12
    if specification.get('daily'): sc['rpd'] = 2
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(128); sock.setblocking(False)
    cfg['base_url'] = f'http://127.0.0.1:{sock.getsockname()[1]}/openai/v1'
    standin_app = create_standin(sc)
    server = uvicorn.Server(uvicorn.Config(standin_app, log_level='error', lifespan='off'))
    server_task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        if server_task.done(): await server_task
        await asyncio.sleep(.01)
    provider = Provider(cfg)
    logger = Logger(output_dir or ROOT / 'results')
    manager = RequestManager(cfg, Engine(cfg, tool, provider), logger)
    await manager.start()
    questions = json.loads((ROOT/'data/evaluation/questions.json').read_text())
    start = time.perf_counter(); rows = []
    changes=[]
    async def halve():
        await asyncio.sleep(.15)
        standin_app.state.budget.cfg['rpm'] = 6
        standin_app.state.config['rpm'] = 6
        changes.append(dict(at_s=time.perf_counter()-start,from_rpm=12,to_rpm=6))
    async def request(index, question, setting='A', evaluation=None):
        target = start + index * specification['interval']
        await asyncio.sleep(max(0, target - time.perf_counter()))
        before = time.perf_counter()
        trace = await manager.submit(question, scenario, setting, evaluation)
        # Verified delivery simulation: first exposed answer character, then paced chunks.
        first = (time.perf_counter() - before) * 1000
        for offset in range(0, len(trace['answer']), 48): await asyncio.sleep(.005)
        manager.finish(trace, first, (time.perf_counter() - before) * 1000)
        rows.append(trace['request_id'])
    try:
        if quality:
            # Sequential so provider quality experiment isn't confounded by overload.
            for setting in ('A', 'B', 'C'):
                for q in questions:
                    await request(0, q['question'], setting, q)
        else:
            change_task=asyncio.create_task(halve()) if specification.get('half') else None
            tasks = [asyncio.create_task(request(i, questions[i % 13]['question'])) for i in range(specification['n'])]
            await asyncio.gather(*tasks)
            if change_task: await change_task
        run = dict(scenario=scenario, source='stand-in', duration_s=time.perf_counter()-start,
                   offered_requests=len(rows), offered_rate_rps=len(rows)/(time.perf_counter()-start),
                   scheduled_interval_s=specification['interval'], peak_queue_length=manager.peak_queue,
                   request_ids=rows, relay_config=cfg, standin_config=sc,
                   started_at=datetime.now(timezone.utc).isoformat(), calibrated=sc['calibrated'],
                   limit_changes=changes,
                   transport='loopback TCP to stand-in; verified delivery paced in harness')
        folder = ROOT/'experiments'; folder.mkdir(exist_ok=True)
        name = scenario.lower().replace(' ', '_').replace('-', '_')
        run_path = folder/f'{name}_{time.time_ns()}.json'
        run_path.write_text(json.dumps(run, indent=2))
        if quality:
            diagnostics = [json.loads(line) for line in logger.raw.read_text(encoding='utf-8').splitlines()]
            (logger.directory/'queue_diagnostics.json').write_text(json.dumps([
                {key: item.get(key) for key in ('request_id', 'evaluation_id', 'queue_wait_ms',
                                                'queue_length_at_admission', 'peak_queue_length')}
                for item in diagnostics], indent=2), encoding='utf-8')
            (logger.directory/'phase_timings.json').write_text(json.dumps([
                {key: item.get(key) for key in ('request_id', 'evaluation_id', 'retrieval_ms',
                                                'verification_ms', 'ready_ms', 'first_token_ms',
                                                'total_ms', 'provider_attempts')}
                for item in diagnostics], indent=2), encoding='utf-8')
            corpus = ROOT/'data/extracted/paragraphs.json'
            dataset = ROOT/'data/evaluation/questions.json'
            (logger.directory/'experiment_config.json').write_text(json.dumps({
                'source': 'stand-in', 'quality_scores_claimed': False,
                'retrieval_settings': ['A', 'B', 'C'],
                'question_ids': [item['id'] for item in questions],
                'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
                'corpus_sha256': hashlib.sha256(corpus.read_bytes()).hexdigest(),
                'index_metadata': json.loads((ROOT/'data/indexes/metadata.json').read_text(encoding='utf-8')),
                'relay_config': cfg, 'standin_config': sc,
                'experiment_record': str(run_path.relative_to(ROOT)),
                'output_directory': str(logger.directory.relative_to(ROOT)),
            }, indent=2), encoding='utf-8')
        print(scenario, 'requests',len(rows),'duration',round(run['duration_s'],2),'peak queue',manager.peak_queue)
    finally:
        await manager.close(); await provider.close()
        server.should_exit = True; await server_task


async def main(quality=False):
    tool = await asyncio.to_thread(RetrievalTool)
    if quality:
        run_id = time.strftime('%Y%m%d_%H%M%S', time.gmtime()) + '_' + str(time.time_ns())
        output_dir = ROOT/'results'/('revised_retriever_' + run_id)
        await run_batch(tool, 'Retrieval quality', dict(interval=0), True, output_dir)
    else:
        for name, spec in SCENARIOS.items(): await run_batch(tool, name, spec)
        await run_batch(tool,'Retry comparison no retry',dict(n=3,interval=.05,always_fail=True,max_retries=0))
        await run_batch(tool,'Retry comparison two retries',dict(n=3,interval=.05,always_fail=True,max_retries=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--quality', action='store_true')
    asyncio.run(main(parser.parse_args().quality))
