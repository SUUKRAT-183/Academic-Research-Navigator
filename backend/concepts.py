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

import json
import os
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


# ---------------------------------------------------------------------------
# Vocabulary generated from YOUR catalogue (see scripts/build_vocabulary.py).
# If data/vocabulary.json exists it replaces the hand-picked lists above, so
# the concept layer always matches the data that is actually loaded.
# ---------------------------------------------------------------------------
VOCABULARY_PATH = os.environ.get("ARN_VOCABULARY_PATH") or os.path.join(
    os.path.dirname(__file__), "..", "data", "vocabulary.json"
)


def _auto_aliases(terms):
    """Users type "and", catalogues use "&": add the "and" form of every "X & Y" term."""
    return {t.replace(" & ", " and "): t for t in terms if " & " in t}


def _load_vocabulary_file():
    global CONTROLLED_VOCABULARY, ALIASES
    if not os.path.exists(VOCABULARY_PATH):
        return
    with open(VOCABULARY_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    terms = [t.strip().lower() for t in data.get("terms", []) if t and t.strip()]
    # NOTE: if the file exists we ALWAYS use it, even if it is empty. Silently falling
    # back to the old hand-typed (Kaggle) list would tag library books with wrong concepts.
    CONTROLLED_VOCABULARY = sorted(set(terms))
    aliases = _auto_aliases(CONTROLLED_VOCABULARY)
    # optional hand-written extras: {"aliases": {"ml": "machine learning"}}
    for alias, canonical in (data.get("aliases") or {}).items():
        if canonical.lower() in CONTROLLED_VOCABULARY:
            aliases[alias.lower()] = canonical.lower()
    ALIASES = aliases


_load_vocabulary_file()


def _whole_word(phrase: str):
    """Match the phrase only as whole word(s), so "art" does not fire inside
    "start" and "law" does not fire inside "lawn"."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])")


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _first_token(phrase: str):
    """First alphanumeric run of a phrase, e.g. "machine learning" -> "machine"."""
    m = _TOKEN_RE.match(phrase)
    return m.group(0) if m else None


# SPEED: running every term's regex over every abstract is slow (it was ~97% of start-up time).
# A whole-word match of a phrase can only exist if the phrase's FIRST word is a whole word of the
# text, and that is a cheap set lookup. So the regex only runs for the few terms that pass it.
# (Results are identical; tests/test_concepts.py checks this against the plain regex loop.)
_VOCAB_PATTERNS = [(t, _whole_word(t), _first_token(t)) for t in
                   sorted(CONTROLLED_VOCABULARY, key=len, reverse=True)]
_ALIAS_PATTERNS = [(c, _whole_word(a), _first_token(a)) for a, c in ALIASES.items()]


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
    tokens = set(_TOKEN_RE.findall(q))
    found = set()

    # direct vocabulary phrase matches, as whole words/phrases
    for term, pattern, first in _VOCAB_PATTERNS:
        if (first is None or first in tokens) and pattern.search(q):
            found.add(term)

    # alias matches (e.g. "sci-fi" -> "science fiction")
    for canonical, pattern, first in _ALIAS_PATTERNS:
        if (first is None or first in tokens) and pattern.search(q):
            found.add(canonical)

    return sorted(found)


def concepts_for_text(text: str) -> List[str]:
    """
    Same matching logic, applied to a resource's own metadata text
    (title + abstract + subjects + keywords) instead of a query.
    Used to tag each catalogue resource with the concepts it covers.
    """
    return extract_concepts(text)
