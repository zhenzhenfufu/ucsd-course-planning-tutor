"""Retrieval over the course catalog.

The first version of this app pasted the entire catalog (~32 KB of JSON) into
every request. That works at 68 courses and stops working well before the full
UCSD catalog, and it spends the model's attention on 60-odd courses that have
nothing to do with the question.

This module indexes each course once and retrieves only what a question needs.

Two backends:

  * `embedding` - Gemini embeddings + cosine similarity. Used when an API key
    is present. Vectors are cached on disk keyed by (model, content hash), so
    the index is built once rather than per session.
  * `tfidf` - pure-Python TF-IDF, no network. Used as a fallback so the app,
    the tests, and the evaluation harness all run without a key.

Both expose the same `search(query, k)`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from prereq_graph import CourseGraph, build

# Loaded from this file's directory rather than the process cwd, so the module
# behaves the same when imported from eval/ or from Streamlit.
load_dotenv(Path(__file__).with_name(".env"))

CACHE_PATH = Path(__file__).with_name(".embedding_cache.json")
EMBED_MODEL = "gemini-embedding-001"
# 3072 dims per vector is more than 68 short documents need; 768 keeps the
# on-disk cache small with no measurable loss in ranking here.
EMBED_DIMS = 768

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "is",
    "are", "this", "that", "it", "as", "by", "at", "from", "be", "will", "can",
    "course", "courses", "students", "student", "introduction", "topics",
}


@dataclass
class Hit:
    course_id: str
    score: float
    text: str


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 1]


def build_documents(cg: CourseGraph) -> dict[str, str]:
    """One retrieval document per course.

    The prerequisite expression and the list of courses a course unlocks are
    folded into the text, so "what do I need before DSC 100" and "what does
    DSC 80 open up" both retrieve the right rows instead of relying on the
    model to already know the structure.
    """
    docs: dict[str, str] = {}
    for cid, course in cg.courses.items():
        req = cg.requirements.get(cid)
        if req and req.groups:
            prereq_text = "; ".join(" or ".join(g) for g in req.groups)
        else:
            prereq_text = "none"
        unlocked = sorted(cg.graph.successors(cid)) if cid in cg.graph else []
        subs = sorted(cg.substitutes.get(cid, set()))
        docs[cid] = (
            f"{cid} — {course['name']} ({course.get('units', '?')} units, "
            f"{course.get('department', '')}). "
            f"Prerequisites: {prereq_text}. "
            f"Leads to: {', '.join(unlocked) if unlocked else 'nothing further'}. "
            + (f"May be replaced by: {', '.join(subs)}. " if subs else "")
            + (course.get("description") or "")
        )
    return docs


# --------------------------------------------------------------------------
# TF-IDF backend
# --------------------------------------------------------------------------
class TfidfIndex:
    name = "tfidf"

    def __init__(self, docs: dict[str, str]):
        self.docs = docs
        self.ids = list(docs)
        tokenised = {cid: _tokens(text) for cid, text in docs.items()}
        n = len(docs)
        df = Counter()
        for toks in tokenised.values():
            df.update(set(toks))
        self.idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
        self.vectors = {cid: self._vec(toks) for cid, toks in tokenised.items()}

    def _vec(self, toks: list[str]) -> dict[str, float]:
        if not toks:
            return {}
        tf = Counter(toks)
        vec = {t: (c / len(toks)) * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def search(self, query: str, k: int = 8) -> list[Hit]:
        q = self._vec(_tokens(query))
        scored = []
        for cid, vec in self.vectors.items():
            small, large = (q, vec) if len(q) < len(vec) else (vec, q)
            score = sum(w * large.get(t, 0.0) for t, w in small.items())
            if score > 0:
                scored.append((score, cid))
        scored.sort(reverse=True)
        return [Hit(cid, round(s, 4), self.docs[cid]) for s, cid in scored[:k]]


# --------------------------------------------------------------------------
# Embedding backend
# --------------------------------------------------------------------------
class EmbeddingIndex:
    name = "embedding"

    def __init__(self, docs: dict[str, str], api_key: str, model: str = EMBED_MODEL):
        from google import genai

        self.docs = docs
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.vectors = self._load_or_embed(docs)

    def _fingerprint(self, docs: dict[str, str]) -> str:
        blob = json.dumps(docs, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256((self.model + blob).encode()).hexdigest()[:16]

    def _load_or_embed(self, docs: dict[str, str]) -> dict[str, list[float]]:
        fp = self._fingerprint(docs)
        if CACHE_PATH.exists():
            try:
                cached = json.loads(CACHE_PATH.read_text())
                if cached.get("fingerprint") == fp:
                    return cached["vectors"]
            except (json.JSONDecodeError, KeyError):
                pass  # rebuild on a corrupt cache
        vectors = {cid: self._embed(text) for cid, text in docs.items()}
        CACHE_PATH.write_text(json.dumps(
            {"fingerprint": fp, "model": self.model, "vectors": vectors}))
        return vectors

    def _embed(self, text: str) -> list[float]:
        resp = self.client.models.embed_content(
            model=self.model, contents=text,
            config={"output_dimensionality": EMBED_DIMS})
        return list(resp.embeddings[0].values)

    def search(self, query: str, k: int = 8) -> list[Hit]:
        q = self._embed(query)
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        scored = []
        for cid, vec in self.vectors.items():
            vn = math.sqrt(sum(x * x for x in vec)) or 1.0
            score = sum(a * b for a, b in zip(q, vec)) / (qn * vn)
            scored.append((score, cid))
        scored.sort(reverse=True)
        return [Hit(cid, round(s, 4), self.docs[cid]) for s, cid in scored[:k]]


def get_index(cg: CourseGraph | None = None, prefer_embeddings: bool = True):
    """Return the best index available in this environment."""
    cg = cg or build()
    docs = build_documents(cg)
    key = os.getenv("GEMINI_API_KEY")
    if prefer_embeddings and key:
        try:
            return EmbeddingIndex(docs, key)
        except Exception as exc:  # missing SDK, quota, offline
            print(f"[retrieval] embedding backend unavailable ({exc}); using TF-IDF")
    return TfidfIndex(docs)


def expand_along_graph(ids: list[str], cg: CourseGraph, hops: int = 1) -> list[str]:
    """Pull in the prerequisites of everything retrieved.

    Similarity alone is not enough for this catalog. Asking "what do I need
    before DSC 100" retrieves DSC 100 and other courses that *read* like it,
    but DSC 40B — an actual prerequisite — is not textually similar to the
    question, so it can be ranked below unrelated courses and never reach the
    model. Walking the DAG for `hops` levels guarantees that whenever a course
    is in context, the courses it depends on are too.
    """
    out = list(ids)
    seen = set(ids)
    frontier = list(ids)
    for _ in range(hops):
        nxt = []
        for cid in frontier:
            if cid not in cg.graph:
                continue
            for parent in cg.graph.predecessors(cid):
                if parent not in seen:
                    seen.add(parent)
                    out.append(parent)
                    nxt.append(parent)
        frontier = nxt
    return out


def context_for(query: str, index, k: int = 8, extra: list[str] = (),
                cg: CourseGraph | None = None, hops: int = 1) -> str:
    """Retrieved rows, graph-expanded, plus courses the caller knows matter."""
    ids = [h.course_id for h in index.search(query, k=k)]
    for cid in extra:
        if cid not in ids and cid in index.docs:
            ids.append(cid)
    if cg is not None and hops:
        ids = [c for c in expand_along_graph(ids, cg, hops) if c in index.docs]
    return "\n".join(f"- {index.docs[cid]}" for cid in ids)


if __name__ == "__main__":
    cg = build()
    docs = build_documents(cg)
    index = get_index(cg)
    full = json.dumps(cg.courses, ensure_ascii=False)

    print(f"backend      : {index.name}")
    print(f"documents    : {len(docs)}")
    print(f"full catalog : {len(full) / 1024:.1f} KB  (what the old prompt sent every turn)")

    for q in ["What do I need before taking DSC 100?",
              "I want to do machine learning, which classes?",
              "easiest way to satisfy the probability requirement"]:
        plain = [h.course_id for h in index.search(q, k=6)]
        expanded = [c for c in expand_along_graph(plain, cg, 1) if c in docs]
        ctx = context_for(q, index, k=6, cg=cg)
        print(f"\nQ: {q}")
        print(f"   similarity  : {', '.join(plain)}")
        print(f"   +graph hops : {', '.join(c for c in expanded if c not in plain) or '(none added)'}")
        print(f"   context     : {len(ctx)/1024:.1f} KB = "
              f"{100*len(ctx)/len(full):.0f}% of the full catalog")
