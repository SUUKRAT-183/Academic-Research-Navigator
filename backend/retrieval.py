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

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class Retriever:
    def __init__(self, resources):
        self.resources = resources
        self.texts = [r["_searchable_text"] for r in resources]
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform(self.texts)

    def search(self, query: str, query_concepts, top_k: int = 10):
        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.matrix).flatten()

        results = []
        for idx, resource in enumerate(self.resources):
            base_score = float(scores[idx])

            # concept overlap boost: reward resources tagged with concepts
            # that were actually identified in the query. Small, capped
            # boost so TF-IDF signal still dominates ordering.
            overlap = set(resource["concepts"]) & set(query_concepts)
            concept_boost = 0.15 * len(overlap)

            final_score = base_score + concept_boost

            if final_score > 0:
                results.append({
                    "resource": resource,
                    "score": round(final_score, 4),
                    "matched_concepts": sorted(overlap),
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]
