"""Apply the inspected rubric to observed completed load answers; preserve raw snapshot."""
import csv
import json
from app.settings import ROOT
from app.monitoring.logger import FIELDS


def main():
    dataset={q['question']:q for q in json.loads((ROOT/'data/evaluation/questions.json').read_text())}
    raw=[json.loads(l) for l in (ROOT/'results/diagnostics.jsonl').read_text().splitlines()]
    decisions=[]
    for r in raw:
        if r.get('scenario') in ('Retrieval quality','Real baseline','Smoke') or r.get('status')!='ok':continue
        q=dataset.get(r['question'])
        if not q:continue
        if r.get('refused'):
            grade='refused_wrongly' if q['answerable'] else 'refused_correctly'
            rationale='Explicit refusal inspected against question answerability.'
        elif q['id']=='q09' and 'do both at once' in r['answer'] and 'PAD tokens' in r['answer']:
            grade='correct';rationale='Describes simultaneous speaking/listening and silence/PAD stream behavior.'
        else:
            grade='wrong';rationale='Inspected completed load answer is incomplete or irrelevant to required facts; see expected rubric and actual text.'
        decisions.append(dict(request_id=r['request_id'],question=q['question'],expected=q['rubric'],actual=r['answer'],
                              grade=grade,rationale=rationale,reviewer='assistant inspection; candidate review pending'))
    grades={d['request_id']:d['grade'] for d in decisions}
    path=ROOT/'results/results.csv'
    with path.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
    for row in rows:
        if row['request_id'] in grades:row['answer_grade']=grades[row['request_id']]
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (ROOT/'results/load_quality_review.json').write_text(json.dumps(decisions,indent=2),encoding='utf-8')
    print('Graded',len(decisions),'completed load/interactive answers; errors remain ungraded')


if __name__=='__main__':main()
