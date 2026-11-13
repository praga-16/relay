"""Original questions with explicit, inspectable expectations; no automatic LLM judge."""
import json
from app.settings import ROOT

QUESTIONS = [
 ('q01', 'Why is dot-product attention scaled for large key dimensions?', True, '1706.03762v7', [4], 'Large dot products push softmax into regions with extremely small gradients; scaling counteracts this.'),
 ('q02', 'What are the encoder layer count and model dimension in the base Transformer?', True, '1706.03762v7', [3], 'N=6; model dimension 512. Both facts required.'),
 ('q03', 'What are the input/output and inner-layer dimensions of the position-wise feed-forward network?', True, '1706.03762v7', [5], '512 input/output; 2048 inner layer.'),
 ('q04', 'How does the Transformer learning rate change during and after warmup, and how long is warmup?', True, '1706.03762v7', [7], 'Linear increase for 4000 steps then inverse-square-root decay.'),
 ('q05', 'What label smoothing value is used, and what is its effect on perplexity versus BLEU?', True, '1706.03762v7', [8], '0.1; hurts perplexity while improving accuracy and BLEU.'),
 ('q06', 'What is Mimi, and how does it combine semantic information with acoustic tokens?', True, '2410.00037v1', [3,9,10,11], 'Neural audio codec; distills semantic information into acoustic tokens, particularly first RVQ level.'),
 ('q07', 'What audio sample rate and latent frame rate does the Mimi encoder use?', True, '2410.00037v1', [10], '24 kHz audio to 12.5 frames per second.'),
 ('q08', 'In Moshi, what is Inner Monologue and when are text tokens predicted relative to audio?', True, '2410.00037v1', [3,17,18], 'Time-aligned text tokens predicted before audio; not a claim about hidden reasoning.'),
 ('q09', 'How does Moshi handle speaking and listening at the same time?', True, '2410.00037v1', [7,15,16,17], 'Multi-stream architecture models user and system audio; does not require explicit turn taking.'),
 ('q10', 'What are the size and text pretraining token count of Helium?', True, '2410.00037v1', [3], '7B parameters; 2.1T public English tokens.'),
 ('q11', 'What are the roles of routing and smoothing in H-Net dynamic chunking?', True, '2507.07955v2', [2,3,5,6,7,8], 'Router predicts boundaries from adjacent representations; smoothing interpolates to make boundaries learnable.'),
 ('q12', 'Why does H-Net replace fixed-vocabulary tokenization?', True, '2507.07955v2', [1,2], 'Learns content- and context-dependent segmentation jointly end to end; explain fixed-tokenization limitations.'),
 ('q13', 'How does H-Net maintain causality in boundary prediction and smoothing?', True, '2507.07955v2', [9], 'Current/previous representations and recursive past compressed states; no future leakage.'),
 ('q14', 'Is H-Net dynamic chunking the same as splitting PDFs into fixed 500-token retrieval passages?', False, None, [], 'Refuse attribution: paper describes learned model segmentation; no implementation of this PDF RAG chunker.'),
 ('q15', 'What Groq free-tier requests-per-minute limit does the Moshi paper report?', False, None, [], 'No Groq account limits in library; refuse.'),
 ('q16', 'Which exact Redis configuration does Attention Is All You Need recommend for a RAG cache?', False, None, [], 'No Redis deployment configuration in library; refuse.'),
 ('q17', 'Does Moshi Inner Monologue reveal private chain-of-thought of every hosted LLM?', False, None, [], 'No such universal claim; refuse. Terminology trap.'),
 ('q18', 'Compare how the Transformer and H-Net handle positional information and causal sequence processing.', True, 'multiple', [5,6,9], 'Requires evidence from BOTH papers: positional encoding and decoder masking; H-Net causal routing/smoothing. Partial excerpt is wrong.'),
 ('q19', 'What functions are used for Transformer positional encodings, and why are they added to token embeddings?', True, '1706.03762v7', [6], 'Sine and cosine functions of different frequencies; they give the model position/order information because attention alone has no recurrence or convolution.'),
 ('q20', 'What do the downsampler and upsampler do in H-Net?', True, '2507.07955v2', [3,5], 'The downsampler aggregates a chunk into a coarser representation; the upsampler broadcasts/interpolates coarser information back to finer representations.'),
]


def main():
    out = ROOT / 'data/evaluation'; out.mkdir(parents=True, exist_ok=True)
    rows = [dict(id=i, question=q, answerable=a, paper=p, expected_pages=pages, rubric=r)
            for i,q,a,p,pages,r in QUESTIONS]
    (out/'questions.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print('Created', len(rows), 'original questions')


if __name__ == '__main__': main()
