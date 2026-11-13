"""Apply documented inspection decisions to a derived graded CSV, keeping raw snapshot."""
import csv
import json
import shutil
from app.settings import ROOT
from app.monitoring.logger import FIELDS

# These are per-answer inspection decisions from results/quality_review.json, not
# keyword grades or an LLM scoring call. Recheck them if answers change.
DECISIONS = {
 'A': ['wrong','wrong','wrong','wrong','refused_wrongly','wrong','wrong','wrong','correct','wrong','wrong','wrong','refused_wrongly','wrong','refused_correctly','refused_correctly','refused_correctly','refused_wrongly'],
 'B': ['wrong','wrong','wrong','wrong','refused_wrongly','wrong','wrong','wrong','wrong','wrong','wrong','wrong','refused_wrongly','wrong','refused_correctly','refused_correctly','refused_correctly','refused_wrongly'],
 'C': ['wrong','wrong','wrong','wrong','refused_wrongly','correct','wrong','correct','wrong','wrong','wrong','wrong','wrong','wrong','refused_correctly','refused_correctly','refused_correctly','wrong'],
}
RATIONALES = {
 0:'Names/scaling formula are quoted but gradient explanation is missing.',
 1:'Required six layers and dimension 512 are not given.',
 2:'Does not give both 512 and 2048.',
 3:'Quotes Moshi training values and/or omits the required 4000-step warmup.',
 4:'Answerable on Attention p8; refused.',
 5:'A includes unrelated SemantiCodec and omits codec definition; B omits codec definition; C covers codec and semantic distillation.',
 6:'Does not clearly provide both Mimi encoder sample rate 24kHz and frame rate 12.5Hz; table/generic-rate snippets are insufficient.',
 7:'A/B omit text-before-audio ordering; C gives time-aligned text and text as prefix to audio.',
 8:'A describes two streams, silence/PAD, and simultaneous listening/speaking; B/C omit the mechanism and simultaneous capability.',
 9:'Does not give both 7B and 2.1T.',
 10:'Names modules or generic chunking but omits routing boundary score and smoothing interpolation roles.',
 11:'Does not explain joint content/context-dependent segmentation and tokenization motivation completely.',
 12:'A/B refuse despite p9 evidence; C quotes a diagram fragment instead of causal mechanism.',
 13:'Returns related chunking text without answering/rejecting the unsupported equivalence with PDF RAG chunking.',
 14:'Correctly refuses a Groq account-limit question absent from all three papers.',
 15:'Correctly refuses Redis configuration absent from the library.',
 16:'Correctly refuses universal private chain-of-thought attribution.',
 17:'A/B refuse despite available cross-paper evidence; C gives only H-Net masking, omitting Transformer positional/decoder evidence.',
}


def main():
    path=ROOT/'results/results.csv'; backup=ROOT/'results/results_ungraded.csv'
    if not backup.exists(): shutil.copyfile(path,backup)
    review=json.loads((ROOT/'results/quality_review.json').read_text())
    counters={s:0 for s in 'ABC'}; grades={}
    for r in review:
        setting=r['setting'];i=counters[setting];counters[setting]+=1
        if i>=18: raise RuntimeError('Review set changed; inspect new answers instead of reusing grades')
        grade=DECISIONS[setting][i]
        r.update(grade=grade,rationale=RATIONALES[i],reviewer='assistant inspection; candidate review pending')
        grades[r['request_id']]=grade
    raw=[json.loads(l) for l in (ROOT/'results/diagnostics.jsonl').read_text().splitlines()]
    baseline=[]
    for r in raw:
        if r.get('scenario')=='Real baseline' and r.get('status')=='ok':
            grade='correct' if r['evaluation_id']=='q11' else 'wrong'
            grades[r['request_id']]=grade
            baseline.append(dict(request_id=r['request_id'],grade=grade,
                rationale='Routing/smoothing roles correctly quoted; extra caption is supporting context.' if grade=='correct'
                else '80ms frame interval plus audio watermarking sample rate do not directly answer both Mimi encoder rates.',
                reviewer='assistant inspection; candidate review pending'))
    with path.open(newline='',encoding='utf-8') as f:rows=list(csv.DictReader(f))
    for row in rows:
        if row['request_id'] in grades:row['answer_grade']=grades[row['request_id']]
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    (ROOT/'results/quality_review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
    (ROOT/'results/real_quality_review.json').write_text(json.dumps(baseline,indent=2),encoding='utf-8')
    print('Applied',len(grades),'inspectable grades; original ungraded CSV preserved')


if __name__=='__main__':main()
