"""
Concept identification module.

APPROACH (see baseline doc section 12: "Meaning of Understand"):
We use a CONTROLLED VOCABULARY + keyword/phrase matching approach.
This is intentionally the simplest thing that can satisfy the requirement:
  - no LLM
  - no embeddings
  - fully deterministic and explainable (every match is traceable to a phrase)

This module is a single, swappable component. If later experiments show
this is not "reliable enough" (see Open Questions in requirements doc),
only this file needs to change - retrieval.py and relationships.py don't
know or care HOW concepts were identified, only what the result looks like.
"""

import re
from typing import List

# Controlled vocabulary, derived from the actual catalogue (data/catalogue.json)
# rather than hand-typed: every distinct `subjects` value across the 6,398
# books was counted, junk/placeholder tags (e.g. "Unknown") were dropped, and
# anything appearing fewer than 5 times was discarded as too sparse to ever
# usefully match a query. That left these 74 genre/subject terms. Re-run the
# same frequency count against data/catalogue.json if the dataset changes.
CONTROLLED_VOCABULARY = [
    "adventure stories", "american", "american fiction", "americans",
    "animals", "architecture", "art", "authors",
    "biography & autobiography", "body", "british", "business & economics",
    "children's stories", "city and town life", "comics & graphic novels",
    "computers", "cooking", "crafts & hobbies", "design",
    "detective and mystery stories", "discworld (imaginary place)", "drama",
    "education", "england", "english", "english fiction", "families",
    "family & relationships", "fantasy", "fantasy fiction", "fiction",
    "foreign language study", "games", "games & activities", "gardening",
    "great britain", "health & fitness", "history", "horror tales", "humor",
    "humorous stories", "juvenile fiction", "juvenile nonfiction",
    "language arts & disciplines", "law", "life on other planets",
    "literary collections", "literary criticism", "london (england)",
    "mathematics", "medical", "mind & spirit", "music", "nature",
    "performing arts", "pets", "philosophy", "photography", "poetry",
    "political science", "psychology", "reference", "religion", "science",
    "science fiction", "self-help", "short stories", "social science",
    "sports & recreation", "technology & engineering", "travel",
    "true crime", "united states", "young adult fiction",
]

# Common surface variants -> canonical vocabulary term, so a query doesn't
# need to hit the exact catalogue wording to match. Two kinds:
#  1. "X and Y" for every "X & Y" term (users type "and", data uses "&")
#  2. everyday synonyms/abbreviations for specific genres (sci-fi, YA, etc.)
ALIASES = {
    "autobiography": "biography & autobiography",
    "biography": "biography & autobiography",
    "biography and autobiography": "biography & autobiography",
    "business": "business & economics",
    "business and economics": "business & economics",
    "children's fiction": "juvenile fiction",
    "childrens fiction": "juvenile fiction",
    "comics": "comics & graphic novels",
    "comics and graphic novels": "comics & graphic novels",
    "crafts": "crafts & hobbies",
    "crafts and hobbies": "crafts & hobbies",
    "detective stories": "detective and mystery stories",
    "economics": "business & economics",
    "engineering": "technology & engineering",
    "family and relationships": "family & relationships",
    "games and activities": "games & activities",
    "graphic novel": "comics & graphic novels",
    "graphic novels": "comics & graphic novels",
    "health and fitness": "health & fitness",
    "hobbies": "crafts & hobbies",
    "kids fiction": "juvenile fiction",
    "language arts": "language arts & disciplines",
    "language arts and disciplines": "language arts & disciplines",
    "memoir": "biography & autobiography",
    "mind and spirit": "mind & spirit",
    "mystery": "detective and mystery stories",
    "mystery stories": "detective and mystery stories",
    "nonfiction for kids": "juvenile nonfiction",
    "recreation": "sports & recreation",
    "sci fi": "science fiction",
    "sci-fi": "science fiction",
    "scifi": "science fiction",
    "self help": "self-help",
    "sports": "sports & recreation",
    "sports and recreation": "sports & recreation",
    "tech": "technology & engineering",
    "technology and engineering": "technology & engineering",
    "whodunit": "detective and mystery stories",
    "ya": "young adult fiction",
    "ya fiction": "young adult fiction",
    "young adult": "young adult fiction",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def extract_concepts(query: str) -> List[str]:
    """
    Identify main concepts in a natural-language query.

    Returns a list of canonical concept names found in CONTROLLED_VOCABULARY,
    matched against the query text (including alias resolution).

    This is FR-2 from the requirements doc.
    """
    q = _normalize(query)
    found = set()

    # direct vocabulary phrase matches (longest phrases first, so
    # "graph neural networks" wins over just "graph" or "networks")
    for term in sorted(CONTROLLED_VOCABULARY, key=len, reverse=True):
        if term in q:
            found.add(term)

    # alias matches
    for alias, canonical in ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", q):
            found.add(canonical)

    return sorted(found)


def concepts_for_text(text: str) -> List[str]:
    """
    Same matching logic, applied to a resource's own metadata text
    (title + abstract + subjects + keywords) instead of a query.
    Used to tag each catalogue resource with the concepts it covers.
    """
    return extract_concepts(text)
