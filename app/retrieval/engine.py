"""Page-bounded chunks, full-text embeddings (no silent truncation), FAISS tool."""
import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass, asdict
import numpy as np
from app.settings import ROOT, load_config

SETTINGS = {"A": (200, 3, False), "B": (500, 5, False), "C": (500, 5, True)}


@dataclass
class RetrievalInput:
    question: str
    setting: str = "A"
    expand: bool = False


@dataclass
class RetrievalOutput:
    tool: str
    arguments: dict
    passages: list


def chunks(paragraphs, size, tokenizer):
    grouped = {}
    for p in paragraphs:
        key = (p["arxiv_version"], p["page"], p["section"])
        grouped.setdefault(key, []).append(p)
    output, seen = [], set()
    for group in grouped.values():
        # Preserve layout blocks whenever they fit. Tables and equations are often
        # emitted as one block, so ordinary chunks end at paragraph/block boundaries.
        units = []
        for paragraph in group:
            text = paragraph["text"]
            encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                                truncation=False, verbose=False)
            ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
            # Keep an intact extraction block when it fits.  Only a block that is
            # itself too large is split, so ordinary chunk boundaries follow the
            # source PDF's paragraph/layout boundaries.
            if len(ids) <= size:
                if ids:
                    units.append((text, len(ids)))
                continue
            for start in range(0, len(ids), size):
                end = min(start + size, len(ids))
                units.append((text[offsets[start][0]:offsets[end - 1][1]], end - start))

        batch, batch_tokens, sequence = [], 0, 0

        def emit():
            nonlocal batch, batch_tokens, sequence
            if not batch:
                return
            body = "\n\n".join(batch)
            digest = hashlib.sha256(body.encode()).hexdigest()
            identity = (group[0]["arxiv_version"], digest)
            if identity not in seen:
                seen.add(identity)
                row = {k: group[0][k] for k in ("paper_title", "arxiv_version", "page", "section")}
                row.update(chunk_id=f"{row['arxiv_version']}:p{row['page']}:b{sequence}:{digest[:8]}",
                           text=body, chunk_tokens=batch_tokens)
                output.append(row)
            sequence += 1
            batch, batch_tokens = [], 0

        for unit, unit_tokens in units:
            if batch and batch_tokens + unit_tokens > size:
                emit()
            batch.append(unit)
            batch_tokens += unit_tokens
        emit()
    return output


class Encoder:
    def __init__(self, config=None):
        import torch
        torch.set_num_threads(2)
        from sentence_transformers import SentenceTransformer
        cfg = config or load_config()
        self.model = SentenceTransformer(cfg["embedding_model"], revision=cfg["embedding_revision"], device="cpu")
        self.tokenizer = self.model.tokenizer

    def encode(self, texts):
        # MiniLM has a shorter context than setting B/C. Pool every subwindow instead
        # of truncating 500-token chunks to the first 256 tokens.
        windows, owners, weights = [], [], []
        size = self.model.max_seq_length - 2
        for i, text in enumerate(texts):
            ids = self.tokenizer.encode(text, add_special_tokens=False, verbose=False)
            for start in range(0, max(1, len(ids)), size):
                part = ids[start:start + size]
                windows.append(self.tokenizer.decode(part)); owners.append(i); weights.append(max(1, len(part)))
        encoded = self.model.encode(windows, batch_size=1, convert_to_numpy=True,
                                    normalize_embeddings=True, show_progress_bar=False)
        pooled = np.zeros((len(texts), encoded.shape[1]), dtype=np.float32)
        for i, vector, weight in zip(owners, encoded, weights):
            pooled[i] += vector * weight
        pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
        return pooled.astype("float32")


def build_indexes():
    import faiss
    encoder = Encoder()
    paragraphs = json.loads((ROOT / "data/extracted/paragraphs.json").read_text(encoding="utf-8"))
    folder = ROOT / "data/indexes"; folder.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    for size in (200, 500):
        rows = chunks(paragraphs, size, encoder.tokenizer)
        embeddings = encoder.encode([p["text"] for p in rows])
        index = faiss.IndexFlatIP(embeddings.shape[1]); index.add(embeddings)
        faiss.write_index(index, str(folder / f"{size}.faiss"))
        (folder / f"{size}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        print(f"Indexed {len(rows)} chunks at {size} tokens", flush=True)
    (folder / "metadata.json").write_text(json.dumps({"embedding_model": cfg["embedding_model"],
        "revision": cfg["embedding_revision"], "pooling": "token-weighted normalized subwindows",
        "extraction_sha256": hashlib.sha256((ROOT / 'data/extracted/paragraphs.json').read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256((ROOT / "paper_manifest.json").read_bytes()).hexdigest()}, indent=2))


class RetrievalTool:
    name = "retrieve_papers"
    def __init__(self, encoder=None):
        self.encoder = encoder or Encoder()
        self.cache = {}
        self.lock = threading.Lock()
        self.lexical = {}

    def __call__(self, arguments: RetrievalInput) -> RetrievalOutput:
        with self.lock:
            return self._retrieve(arguments)

    def _retrieve(self, arguments):
        import faiss
        size, top_k, rerank = SETTINGS[arguments.setting]
        if size not in self.cache:
            folder = ROOT / "data/indexes"
            meta = json.loads((folder / "metadata.json").read_text())
            expected = {
                "manifest_sha256": hashlib.sha256((ROOT / "paper_manifest.json").read_bytes()).hexdigest(),
                "extraction_sha256": hashlib.sha256((ROOT / "data/extracted/paragraphs.json").read_bytes()).hexdigest(),
                "embedding_model": load_config()["embedding_model"],
                "revision": load_config()["embedding_revision"],
            }
            if any(meta.get(k) != v for k, v in expected.items()):
                raise RuntimeError("Index metadata is stale or incompatible; rebuild indexes")
            try:
                index = faiss.read_index(str(folder / f"{size}.faiss"))
                rows = json.loads((folder / f"{size}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError, RuntimeError) as exc:
                raise RuntimeError("Index files are unreadable; rebuild indexes") from exc
            if index.ntotal != len(rows) or index.d != self.encoder.encode(["index dimension check"]).shape[1]:
                raise RuntimeError("Index/vector metadata mismatch; rebuild indexes")
            self.cache[size] = (index, rows)
        index, rows = self.cache[size]
        count = top_k * (2 if arguments.expand else 1)
        candidate_count = min(index.ntotal, count * (8 if rerank else 1))
        scores, indices = index.search(self.encoder.encode([arguments.question]), candidate_count)
        passages = [dict(rows[int(i)], similarity_score=float(s), vector_score=float(s))
                    for s, i in zip(scores[0], indices[0]) if i >= 0]
        if rerank:
            # Hybrid reranking combines semantic FAISS retrieval with local BM25.
            # It is deterministic and adds no provider call or model dependency.
            if size not in self.lexical:
                document_frequency = {}
                lengths = []
                for row in rows:
                    terms = re.findall(r"\w+", row["text"].lower())
                    lengths.append(len(terms))
                    for term in set(terms):
                        document_frequency[term] = document_frequency.get(term, 0) + 1
                self.lexical[size] = (document_frequency, sum(lengths) / max(1, len(lengths)))
            document_frequency, average_length = self.lexical[size]
            query_terms = set(re.findall(r"\w+", arguments.question.lower()))
            maximum = 0.0
            for passage in passages:
                terms = re.findall(r"\w+", passage["text"].lower())
                frequencies = {}
                for term in terms:
                    frequencies[term] = frequencies.get(term, 0) + 1
                score = 0.0
                for term in query_terms:
                    frequency = frequencies.get(term, 0)
                    if frequency:
                        df = document_frequency.get(term, 0)
                        idf = math.log(1 + (len(rows) - df + 0.5) / (df + 0.5))
                        score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(terms) / max(1, average_length)))
                passage["lexical_score"] = score
                maximum = max(maximum, score)
            for passage in passages:
                passage["hybrid_score"] = 0.70 * passage["vector_score"] + 0.30 * passage["lexical_score"] / max(maximum, 1e-12)
                passage["rerank_score"] = passage["hybrid_score"]
            passages.sort(key=lambda passage: passage["hybrid_score"], reverse=True)
        return RetrievalOutput(self.name, asdict(arguments), passages[:count])
