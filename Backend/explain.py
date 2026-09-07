"""
Relevance explanation module (FR-8: "Why is this relevant?").

Generates a short, evidence-grounded sentence per result, based only on
observable signals: which query terms/concepts actually matched this
resource's metadata. No LLM involved - this is template text filled in
with real matched terms, which is enough to satisfy the requirement
(the baseline doc explicitly says an LLM must not be assumed here).
"""


def explain_relevance(resource: dict, matched_concepts: list) -> str:
    if matched_concepts:
        concept_list = ", ".join(matched_concepts)
        return (
            f"Relevant because this resource covers {concept_list}, "
            f"which matches your query."
        )
    # fallback: no concept overlap, but TF-IDF still scored it - explain via subjects
    subjects = resource.get("subjects", [])
    if subjects:
        return f"Relevant based on shared subject terms: {', '.join(subjects[:3])}."
    return "Relevant based on overlapping terms with your query."
