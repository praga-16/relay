"""Credential-safe discovery; smoke requires explicit command flag AND root approval record."""
import argparse
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
import httpx
from app.settings import ROOT, load_config, groq_credentials
from app.services.provider import Provider
from app.monitoring.logger import Logger


async def main(smoke=False):
    if smoke and (ROOT/'results/groq_smoke.json').exists():
        raise RuntimeError('This session smoke approval has been consumed; obtain new approval before another experiment')
    key, model = groq_credentials()
    folder = ROOT/'results'; folder.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.get('https://api.groq.com/openai/v1/models', headers={'Authorization': 'Bearer '+key})
        if response.status_code in (401,403):
            raise RuntimeError('Key rejected/revoked; stop real calls until replaced')
        response.raise_for_status()
        ids = [row['id'] for row in response.json()['data']]
        discovery = {'model': model, 'available': model in ids, 'http_status': response.status_code,
                     'account_limits_independently_verified': False,
                     'note': 'Models endpoint does not expose full account limits. Record console evidence separately.'}
        (folder/'groq_discovery.json').write_text(json.dumps(discovery, indent=2))
        print(json.dumps(discovery, indent=2))
    if not smoke: return
    if model not in ids: raise RuntimeError('Configured model unavailable')
    approval_path = ROOT/'config/real_approval.json'
    if not approval_path.exists(): raise RuntimeError('No approval record; do not make smoke request')
    approval = json.loads(approval_path.read_text())
    if not approval.get('approved') or not approval.get('account_limits_confirmed'):
        raise RuntimeError('Smoke approval and actual account limits confirmation required')
    cfg = load_config(); cfg.update(source='real', base_url='https://api.groq.com/openai/v1',
                                    model=model, real_calls_approved=True, max_retries=0,
                                    max_completion_tokens=128)
    trace = {'purpose': 'approved_smoke', 'source': 'real', 'retries': 0,
             'request_id': uuid.uuid4().hex, 'start_time': datetime.now(timezone.utc).isoformat()}
    provider = Provider(cfg, persistent=True)
    try:
        started=time.perf_counter()
        result = await provider.generate([{'role':'user','content':'Reply with the single word READY.'}], trace)
        trace['total_ms']=(time.perf_counter()-started)*1000
        trace['answer']=result.text
        Logger(folder).record(dict(request_id=trace['request_id'], scenario='Smoke', source='real',
            start_time=trace['start_time'], first_token_ms=result.first_token_ms, total_ms=trace['total_ms'],
            status='ok', retries=0, tokens_in=result.tokens_in, tokens_out=result.tokens_out,
            retrieval_setting='none', answer_grade=None), trace)
    finally:
        await provider.close()
        (folder/'groq_smoke.json').write_text(json.dumps(trace, indent=2))
    print('Smoke completed. Measurements saved; no credentials logged.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--smoke', action='store_true')
    asyncio.run(main(p.parse_args().smoke))
