"""Recompute tables from immutable raw CSV plus explicitly identified diagnostic fields."""
import csv
import json
from collections import Counter
from pathlib import Path
from app.settings import ROOT
from app.monitoring.logger import FIELDS, SOURCES, STATUSES, GRADES, percentiles


def analyze():
    path=ROOT/'results/results.csv'
    with path.open(encoding='utf-8', newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != FIELDS: raise ValueError('CSV schema mismatch')
        rows=list(reader)
    ids=set()
    for row in rows:
        if row['request_id'] in ids: raise ValueError('Duplicate request ID')
        ids.add(row['request_id'])
        assert row['source'] in SOURCES and row['status'] in STATUSES
        assert row['answer_grade'] in GRADES or row['answer_grade']==''
    groups={}
    for row in rows: groups.setdefault((row['scenario'],row['source']),[]).append(row)
    tables=[]
    for (scenario,source),group in groups.items():
        n=len(group); counts=Counter(r['status'] for r in group)
        tables.append(dict(scenario=scenario,source=source,requests=n,
            first_token_ms=percentiles([r['first_token_ms'] for r in group]),
            total_ms=percentiles([r['total_ms'] for r in group]),
            success_pct=100*counts['ok']/n,rate_limited_pct=100*counts['rate_limited']/n,
            timeout_given_up_pct=100*(counts['timeout']+counts['error'])/n,
            retries_per_request=sum(int(r['retries']) for r in group)/n,
            tokens_per_successful_answer=(sum(float(r['tokens_in'] or 0)+float(r['tokens_out'] or 0) for r in group if r['status']=='ok')/
                                         counts['ok'] if counts['ok'] else None),
            cost_per_1000_answers='not measured'))
    retrieval=[]
    for setting in 'ABC':
        group=[r for r in rows if r['scenario']=='Retrieval quality' and r['retrieval_setting']==setting]
        grades=Counter(r['answer_grade'] for r in group); n=len(group)
        retrieval.append(dict(setting=setting,questions=n,graded=n-grades[''],
            correct_pct=100*grades['correct']/n if n else None,
            wrong_pct=100*grades['wrong']/n if n else None,
            refused_correctly_pct=100*grades['refused_correctly']/n if n else None,
            refused_wrongly_pct=100*grades['refused_wrongly']/n if n else None,
            first_token_ms=percentiles([r['first_token_ms'] for r in group]),total_ms=percentiles([r['total_ms'] for r in group]),
            tokens_per_answer=sum(float(r['tokens_in'] or 0)+float(r['tokens_out'] or 0) for r in group)/n if n else None))
    output=dict(denominators='All submitted requests per scenario; quality percentages use all questions per setting. Status ok means completed, not factually correct.',
                percentile_method='numpy linear; excludes genuinely unmeasured blanks only',
                latency_scope='Harness-observed verified delivery; NOT provider first-token latency. Includes refusals and error messages.',
                outcome_tables=tables,retrieval_table=retrieval)
    (ROOT/'results/summary.json').write_text(json.dumps(output,indent=2))
    print('Validated',len(rows),'request rows; wrote summary.json')
    return output


if __name__=='__main__': analyze()
