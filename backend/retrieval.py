"""
Retrieval + ranking module (FR-3, FR-4).

APPROACH: classical TF-IDF + cosine similarity over each resource's
searchable text, with a small boost for resources whose tagged concepts
overlap the query's identified concepts.

This is deliberately NOT semantic/embedding-based search. Per the baseline
doc (section 13), hybrid/semantic retrieval must be experimentally
justified before being adopted - it is not assumed here. TF-IDF is the
simplest thing that gives real ranking (not just a boolean keyword filter),
and it's a well-understood, easily explainable baseline to compare any
future semantic approach against (this comparison IS the evaluation
experiment described in the requirements doc, section on Evaluation).
"""

from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .data_loader import searchable_text

CONCEPT_BOOST = 0.15
_ROUND_MARGIN = 1e-4          # scores are rounded to 4 decimals; see search()


class Retriever:
    def __init__(self, resources):
        self.resources = resources
        # MEMORY: texts are streamed into the vectorizer one at a time, never held as a big list.
        # (A resource that already carries "_searchable_text" is indexed by that, as before.)
        texts = (r["_searchable_text"] if "_searchable_text" in r else searchable_text(r) for r in resources)
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform(texts)
        for r in resources:
            r.pop("_searchable_text", None)

        # concept -> positions of the resources tagged with it. Lets search() add the concept
        # boost with one array operation instead of looking at every resource per query.
        index = defaultdict(list)
        for pos, r in enumerate(resources):
            for c in set(r["concepts"]):
                index[c].append(pos)
        self._concept_positions = {c: np.asarray(v, dtype=np.int32) for c, v in index.items()}

    def search(self, query: str, query_concepts, top_k: int = 10):
        """Same ranking as the original loop-over-everything version (tests prove it),
        but only the handful of top candidates are ever turned into Python objects, so
        a search costs about the same on 10,000 records as on 160,000."""
        # TfidfVectorizer already L2-normalises every row (and the query vector), so the cosine
        # similarity is just a dot product. sklearn's cosine_similarity would re-normalise a full
        # COPY of the whole index on every query, which costs a lot of memory on big catalogues.
        query_vec = self.vectorizer.transform([query])
        scores = (self.matrix @ query_vec.T).toarray().ravel()

        # concept overlap boost: reward resources tagged with concepts that were actually
        # identified in the query. Small, capped boost so TF-IDF still dominates ordering.
        wanted = set(query_concepts)
        overlap_counts = np.zeros(len(scores), dtype=np.float64)
        for c in wanted:
            positions = self._concept_positions.get(c)
            if positions is not None:
                overlap_counts[positions] += 1
        final = scores + CONCEPT_BOOST * overlap_counts

        candidates = np.flatnonzero(final > 0)           # ascending positions
        if candidates.size == 0:
            return []

        # The original sorted by the score ROUNDED to 4 decimals (ties keep catalogue order).
        # Keep every candidate that could still tie with or beat the k-th best after rounding,
        # then sort just those exactly like the original did.
        raw = final[candidates]
        if candidates.size > top_k:
            kth = np.partition(raw, candidates.size - top_k)[candidates.size - top_k]
            candidates = candidates[raw >= kth - _ROUND_MARGIN]

        results = []
        for idx in candidates:
            resource = self.resources[int(idx)]
            results.append({
                "resource": resource,
                "score": round(float(final[idx]), 4),
                "matched_concepts": sorted(set(resource["concepts"]) & wanted),
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]
