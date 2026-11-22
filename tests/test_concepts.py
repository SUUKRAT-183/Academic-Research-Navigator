"""The fast concept matcher must give EXACTLY the same answers as the plain regex loop."""
import json
import os
import random
import re

from backend import concepts

DATA = os.path.join(os.path.dirname(__file__), "..", "data", "catalogue.json")


def reference_extract(query: str):
    """The original slow logic: run every term's regex on the text."""
    q = concepts._normalize(query)
    found = set()
    for term in concepts.CONTROLLED_VOCABULARY:
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", q):
            found.add(term)
    for alias, canonical in concepts.ALIASES.items():
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", q):
            found.add(canonical)
    return sorted(found)


def test_fast_matcher_equals_reference_on_real_catalogue_text():
    with open(DATA, encoding="utf-8") as f:
        resources = json.load(f)["resources"]
    random.Random(0).shuffle(resources)
    for r in resources[:1500]:
        text = " ".join([r.get("title", ""), r.get("abstract", ""), " ".join(r.get("subjects", []))])
        assert concepts.extract_concepts(text) == reference_extract(text), r["title"]


def test_fast_matcher_equals_reference_on_tricky_strings():
    terms = concepts.CONTROLLED_VOCABULARY[:20] + list(concepts.ALIASES)[:10]
    tricky = ["start a new project", "somebody", "lawn", "SCI-FI and Fantasy!", "  spaced   out  ", "", "&", "(",
              "1999 history", "history1999", "x" * 5000]
    tricky += [f"prefix{t}suffix {t}, and {t.upper()}; {t}." for t in terms]
    tricky += [" ".join(random.Random(i).sample(terms, 3)) for i in range(50)]
    for q in tricky:
        assert concepts.extract_concepts(q) == reference_extract(q), q
