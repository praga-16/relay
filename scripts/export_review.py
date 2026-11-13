"""Prepare readable grading material; do not auto-grade based on quote validity alone."""
import json
from app.settings import ROOT


def main():
    questions={q['id']:q for q in json.loads((ROOT/'data/evaluation/questions.json').read_text())}
    rows=[json.loads(line) for line in (ROOT/'results/diagnostics.jsonl').read_text().splitlines()]
    output=[]
    for r in rows:
        if r['scenario']!='Retrieval quality':continue
        q=questions[r['evaluation_id']]
        output.append(dict(request_id=r['request_id'],setting=r['retrieval_setting'],question=q['question'],
            expected=q['rubric'],expected_paper=q['paper'],expected_pages=q['expected_pages'],
            actual=r['answer'],status=r['status'],grade=None,rationale=None))
    (ROOT/'results/quality_review.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print('Review items:',len(output))


if __name__=='__main__':main()
