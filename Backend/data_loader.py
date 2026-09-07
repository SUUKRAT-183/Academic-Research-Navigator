"""
Loads catalogue data and pre-computes concept tags for each resource.

Swap point for real TIET data: replace load_catalogue()'s file path/parsing
with whatever the real export format turns out to be (CSV, JSON, DB export).
Every field this module produces below (title, author, year, type, subjects,
keywords, abstract, id) should map to fields confirmed available in the real
TIET catalogue export - see "Data Requirements" section of the baseline doc.
"""

import json
import os
from .concepts import concepts_for_text

DATA_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "catalogue.json"
)


def load_catalogue():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    source_label = raw.get("_source_label", "UNKNOWN SOURCE")
    resources = []

    for r in raw["resources"]:
        searchable_text = " ".join([
            r.get("title", ""),
            r.get("abstract", ""),
            " ".join(r.get("subjects", [])),
            " ".join(r.get("keywords", [])),
        ])
        concepts = concepts_for_text(searchable_text)

        resources.append({
            **r,
            "_searchable_text": searchable_text,
            "concepts": concepts,
        })

    return resources, source_label
