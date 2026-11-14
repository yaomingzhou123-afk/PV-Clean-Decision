import json
import math
import re
from collections import Counter
from pathlib import Path

KB_PATH = Path(__file__).parent / "knowledge.jsonl"

_cache: list | None = None
_index: "BM25 | None" = None


def load_kb() -> list:
    global _cache
    if _cache is None:
        lines = KB_PATH.read_text(encoding="utf-8").splitlines()
        _cache = [json.loads(line) for line in lines if line.strip()]
    return _cache


def tokenize(text: str) -> list:
    text = (text or "").lower()
    tokens = re.findall(r"[a-z0-9_]+", text)
    for seg in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
    return tokens


class BM25:
    def __init__(self, docs: list, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.tokens = [
            tokenize(f"{d.get('title', '')} {d.get('category', '')} {d.get('content', '')}") for d in docs
        ]
        self.doc_len = [len(t) for t in self.tokens]
        self.avg = sum(self.doc_len) / len(self.doc_len) if self.doc_len else 0.0
        self.df = Counter()
        for t in self.tokens:
            self.df.update(set(t))
        self.n = len(docs)

    def score(self, query_tokens: list, idx: int) -> float:
        score = 0.0
        tokens = self.tokens[idx]
        for term in query_tokens:
            freq = tokens.count(term)
            if freq == 0:
                continue
            df = self.df[term]
            idf = math.log(1 + (self.n - df + 0.5) / (df + 0.5))
            denom = freq + self.k1 * (1 - self.b + self.b * self.doc_len[idx] / (self.avg or 1))
            score += idf * freq * (self.k1 + 1) / (denom or 1)
        return score


def _get_index() -> BM25:
    global _index
    if _index is None:
        _index = BM25(load_kb())
    return _index


def _snippet(content: str, limit: int = 90) -> str:
    content = re.sub(r"\s+", " ", content or "").strip()
    return content if len(content) <= limit else content[:limit] + "…"


def retrieve(query: str, applies_to: str | list | None = None, top_k: int = 2) -> list:
    if not query or not query.strip():
        return []
    if isinstance(applies_to, str):
        applies_to = [applies_to]
    index = _get_index()
    q_tokens = tokenize(query)
    if not q_tokens:
        return []
    scored = []
    for i, doc in enumerate(index.docs):
        if applies_to:
            targets = doc.get("applies_to") or []
            if not any(t in targets for t in applies_to):
                continue
        s = index.score(q_tokens, i)
        if s > 0:
            scored.append((s, i))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for s, i in scored[:top_k]:
        doc = index.docs[i]
        results.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "category": doc.get("category", ""),
                "snippet": _snippet(doc.get("content", "")),
                "source": doc.get("source", ""),
                "source_url": doc.get("source_url", ""),
                "verified": bool(doc.get("verified")),
                "score": round(s, 3),
            }
        )
    return results