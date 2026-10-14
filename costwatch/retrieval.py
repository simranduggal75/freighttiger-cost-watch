"""Semantic retrieval over the notes (embeddings + a vector index).

Search is metadata-filtered first (a note must be scoped to the route or to all routes),
then ranked by cosine similarity. Backend: MiniLM sentence embeddings with a FAISS flat
index; falls back to TF-IDF so the project still runs where the model is not cached.
The verdict never depends on similarity scores, only on structured note facts.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from . import config
from .notes import NoteFacts

ROUTE_MATCH_BONUS = 0.15   # note names this exact route
TIME_BONUS = 0.40          # decays as 1 / (1 + gap_days / TIME_HALF_LIFE_DAYS)
TIME_HALF_LIFE_DAYS = 14


def note_document(n: NoteFacts) -> str:
    return f"{n.applies_to} ({n.note_date.isoformat()}): {n.text}"


def candidate_query(route: str, week_of: str) -> str:
    return f"Why did freight cost on {route} rise in the week of {week_of}?"


class NoteIndex:
    def __init__(self, notes: list[NoteFacts], backend: str = "auto"):
        self.notes = notes
        self.docs = [note_document(n) for n in notes]
        self.tokens_embedded = 0
        self.texts_embedded = 0
        self.backend = self._build(backend)

    # -- construction -----------------------------------------------------------------
    def _build(self, backend: str) -> str:
        if backend in ("auto", "embeddings"):
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(config.EMBEDDING_MODEL, local_files_only=True)
                self._vectors = self._embed(self.docs)
                self._index = self._make_index(self._vectors)
                return f"embeddings:{config.EMBEDDING_MODEL}"
            except Exception as exc:  # model not cached / library missing
                if backend == "embeddings":
                    raise RuntimeError(f"embedding backend unavailable: {exc}") from exc
        from sklearn.feature_extraction.text import TfidfVectorizer
        self._tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
        self._vectors = self._tfidf.fit_transform(self.docs).toarray().astype("float32")
        self._index = self._make_index(self._vectors)
        return "tfidf"

    def _embed(self, texts: list[str]) -> np.ndarray:
        self.texts_embedded += len(texts)
        tok = getattr(self._model, "tokenizer", None)
        if tok is not None:
            self.tokens_embedded += sum(len(tok.encode(t)) for t in texts)
        return np.asarray(self._model.encode(texts, normalize_embeddings=True), dtype="float32")

    @staticmethod
    def _make_index(vectors: np.ndarray):
        try:
            import faiss
            index = faiss.IndexFlatIP(vectors.shape[1])
            index.add(vectors)
            return index
        except ImportError:
            return vectors  # exact numpy search below

    # -- search -----------------------------------------------------------------------
    def _scores(self, query: str) -> np.ndarray:
        if self.backend.startswith("embeddings"):
            q = self._embed([query])
        else:
            q = self._tfidf.transform([query]).toarray().astype("float32")
            norm = np.linalg.norm(q)
            q = q / norm if norm else q
        if isinstance(self._index, np.ndarray):
            return (self._index @ q[0]).astype(float)
        scores, ids = self._index.search(q, len(self.notes))
        out = np.zeros(len(self.notes))
        out[ids[0]] = scores[0]
        return out

    def search(self, query: str, route: str, week_of: date,
               k: int = config.RETRIEVAL_TOP_K) -> list[tuple[NoteFacts, float, float]]:
        """Top-k (note, hybrid_score, cosine) among notes scoped to `route` or all routes.

        hybrid = cosine similarity + bonus for naming this exact route + bonus for being
        close in time. Ties break on note id so ordering is stable.
        """
        cosine = self._scores(query)
        rows = []
        for i, n in enumerate(self.notes):
            if n.route is not None and n.route.lower() != route.lower():
                continue  # metadata filter: out of scope
            gap = n.gap_days(week_of, config.BASELINE_WEEKS)
            hybrid = (cosine[i]
                      + (ROUTE_MATCH_BONUS if n.route is not None else 0.0)
                      + TIME_BONUS / (1 + gap / TIME_HALF_LIFE_DAYS))
            rows.append((n, round(float(hybrid), 4), round(float(cosine[i]), 4)))
        rows.sort(key=lambda t: (-t[1], t[0].note_id))
        return rows[:k]
