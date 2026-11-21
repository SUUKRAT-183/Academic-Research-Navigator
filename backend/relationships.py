"""
Topic <-> Concept <-> Resource relationships (FR-5, FR-6).

APPROACH: co-occurrence. Two concepts are "related" if they are tagged
together on the same resource(s), more often = more related. This is
plain counting over a relational structure - no graph database needed
(see baseline doc section 35: Neo4j not currently required).

Explicitly NOT a prerequisite/learning-order graph (baseline section 15) -
"related" here only ever means "co-occurs in the discovery data,"
never "must be studied before."
"""

from collections import defaultdict


class RelationshipIndex:
    def __init__(self, resources):
        self.resources = resources
        self.concept_to_resources = defaultdict(list)
        self.concept_cooccurrence = defaultdict(lambda: defaultdict(int))

        for r in resources:
            concepts = r["concepts"]
            for c in concepts:
                self.concept_to_resources[c].append(r["id"])
            for i, c1 in enumerate(concepts):
                for c2 in concepts:
                    if c1 != c2:
                        self.concept_cooccurrence[c1][c2] += 1

    def resources_for_concept(self, concept: str):
        ids = self.concept_to_resources.get(concept, [])
        by_id = {r["id"]: r for r in self.resources}
        return [by_id[i] for i in ids if i in by_id]

    def related_concepts(self, concept: str, top_k: int = 6):
        related = self.concept_cooccurrence.get(concept, {})
        ranked = sorted(related.items(), key=lambda kv: kv[1], reverse=True)
        return [c for c, _count in ranked[:top_k]]

    def related_concepts_for_many(self, concepts, top_k: int = 6):
        """Related concepts across a whole query (several identified concepts)."""
        scores = defaultdict(int)
        for c in concepts:
            for related_c, count in self.concept_cooccurrence.get(c, {}).items():
                if related_c not in concepts:
                    scores[related_c] += count
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [c for c, _count in ranked[:top_k]]
