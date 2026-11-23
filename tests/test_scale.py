"""The large-catalogue optimisations must not change any answer."""
import json
import os
import random
import tempfile

from backend import data_loader
from backend.concepts import concepts_for_text, extract_concepts
from backend.retrieval import Retriever


def reference_search(retriever, query, query_concepts, top_k=10):
    """The ORIGINAL algorithm: look at every resource in Python."""
    from sklearn.metrics.pairwise import cosine_similarity
    scores = cosine_similarity(retriever.vectorizer.transform([query]), retriever.matrix).flatten()
    results = []
    for idx, resource in enumerate(retriever.resources):
        base = float(scores[idx])
        overlap = set(resource["concepts"]) & set(query_concepts)
        final = base + 0.15 * len(overlap)
        if final > 0:
            results.append({"resource": resource, "score": round(final, 4), "matched_concepts": sorted(overlap)})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def same(a, b):
    assert [(x["resource"]["id"], x["score"], x["matched_concepts"]) for x in a] == \
           [(x["resource"]["id"], x["score"], x["matched_concepts"]) for x in b]


def test_search_gives_identical_results_to_the_original_algorithm_on_real_data():
    resources, _ = data_loader.load_catalogue()
    retriever = Retriever(resources)
    rng = random.Random(4)
    words = [w for r in resources[:3000] for w in r["title"].split() if len(w) > 3]
    queries = ["detective mystery", "fantasy", "history of science", "business and economics", "sci-fi",
               "a", "the of and", "zzzzqqq"]
    queries += [" ".join(rng.sample(words, rng.randint(1, 4))) for _ in range(150)]
    for q in queries:
        concepts = extract_concepts(q)
        for k in (1, 10, 25):
            same(retriever.search(q, concepts, k), reference_search(retriever, q, concepts, k))


def test_ties_are_broken_in_catalogue_order_exactly_like_before():
    # many identical records -> identical scores -> the order must follow catalogue position
    resources = []
    for i in range(60):
        text = "quantum computing basics" if i % 3 else "quantum computing basics advanced"
        resources.append({"id": f"r{i}", "title": text, "subjects": ["physics"], "keywords": ["physics"],
                          "abstract": "", "_searchable_text": text + " physics physics",
                          "concepts": ["physics"] if i % 4 == 0 else []})
    retriever = Retriever(resources)
    for q, qc in [("quantum computing", []), ("quantum computing", ["physics"]), ("basics", ["physics", "x"])]:
        for k in (3, 10, 30, 100):
            same(retriever.search(q, qc, k), reference_search(retriever, q, qc, k))


def test_loader_output_matches_the_original_loader():
    path = data_loader.DATA_PATH
    raw = json.load(open(path, encoding="utf-8"))["resources"]
    resources, _ = data_loader.load_catalogue()
    assert len(resources) == len(raw)
    for old, new in zip(raw, resources):
        text = " ".join([old.get("title", ""), old.get("abstract", ""), " ".join(old.get("subjects", [])),
                         " ".join(old.get("keywords", []))])
        assert data_loader.searchable_text(new) == text
        assert "_searchable_text" not in new                  # never stored per record any more
        assert new["concepts"] == concepts_for_text(text)
        for key, value in old.items():
            assert new[key] == value, (key, old["id"])


def test_raw_text_is_dropped_after_indexing():
    resources, _ = data_loader.load_catalogue()
    Retriever(resources)
    assert not any("_searchable_text" in r for r in resources)


def test_explore_concept_is_capped_but_reports_the_true_total(monkeypatch):
    os.environ.setdefault("ARN_SQLITE_PATH", os.path.join(tempfile.mkdtemp(), "scale.db"))
    from fastapi.testclient import TestClient
    import backend.main as m
    monkeypatch.setattr(m, "EXPLORE_LIMIT", 5)
    c = TestClient(m.app)
    concept = max(m.REL_INDEX.concept_to_resources, key=lambda k: len(m.REL_INDEX.concept_to_resources[k]))
    total = len(m.REL_INDEX.concept_to_resources[concept])
    assert total > 5
    body = c.get(f"/api/concept/{concept}").json()
    assert body["results_shown"] == 5 and len(body["results"]) == 5 and body["result_count"] == total
    first = [r["id"] for r in body["results"]]
    assert first == m.REL_INDEX.concept_to_resources[concept][:5]       # same order as before, just a prefix
