"""Small-sample empirical fit, not a claim that simulator reproduces Groq."""
import json
import math
import statistics
from app.settings import ROOT


def main():
    rows=[json.loads(x) for x in (ROOT/'results/diagnostics.jsonl').read_text().splitlines()]
    attempts=[(r,a) for r in rows if r.get('scenario')=='Real baseline'
              for a in r.get('provider_attempts',[]) if a.get('first_token_ms') is not None]
    if not attempts: raise RuntimeError('No actual baseline samples; keep synthetic defaults')
    first=[a['first_token_ms']/1000 for _,a in attempts]
    gaps=[]
    for r,a in attempts:
        raw=r.get('candidate_answers',[''])[0]
        chunks=max(1,math.ceil(len(raw)/32))
        gaps.append(max(0,(a['total_ms']-a['first_token_ms'])/1000/max(1,chunks-1)))
    cfg=json.loads((ROOT/'config/standin.json').read_text())
    cfg.update(first_token_s=statistics.median(first),token_interval_s=statistics.median(gaps),
        calibrated=True,calibration_source='Measured real baseline provider content TTFT and stream duration; small sample, includes network',
        calibration_samples=len(attempts),calibration_request_ids=[r['request_id'] for r,_ in attempts])
    (ROOT/'config/standin.json').write_text(json.dumps(cfg,indent=2))
    print('Calibrated from',len(attempts),'real requests; synthetic failure/load probabilities unchanged')


if __name__=='__main__':main()
