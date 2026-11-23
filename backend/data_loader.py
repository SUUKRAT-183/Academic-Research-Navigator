"""
Loads catalogue data and pre-computes concept tags for each resource.

Swap point for real TIET data: replace load_catalogue()'s file path/parsing
with whatever the real export format turns out to be (CSV, JSON, DB export).
Every field this module produces below (title, author, year, type, subjects,
keywords, abstract, id) should map to fields confirmed available in the real
TIET catalogue export - see "Data Requirements" section of the baseline doc.
"""

import ctypes
import gc
import json
import os
import sys
from .concepts import concepts_for_text

# The catalogue file the site serves. To use a different file without touching
# code, set the ARN_CATALOGUE_PATH environment variable.
DATA_PATH = os.environ.get("ARN_CATALOGUE_PATH") or os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "catalogue.json"
)


# Extra facts from the catalogue file's header (filled in by load_catalogue):
#   "opac_url_template": one link pattern for every record, e.g. ".../opac-detail.pl?biblionumber={biblionumber}"
CATALOGUE_META = {}


def searchable_text(r) -> str:
    """The text a resource is indexed and concept-tagged by. Built on demand (never stored per
    record), because keeping a copy of every record's text costs a lot of memory on big catalogues."""
    return " ".join([
        r.get("title", ""),
        r.get("abstract", ""),
        " ".join(r.get("subjects", [])),
        " ".join(r.get("keywords", [])),
    ])


def _release_memory():
    """Hand freed memory back to the operating system (Linux only; does nothing elsewhere).
    Matters on small hosts: loading a big catalogue leaves a lot of freed-but-held memory."""
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def load_catalogue():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    source_label = raw.get("_source_label", "UNKNOWN SOURCE")
    CATALOGUE_META.clear()
    if raw.get("_opac_url_template"):
        CATALOGUE_META["opac_url_template"] = raw["_opac_url_template"]
    resources = raw["resources"]          # MEMORY: reuse these dicts instead of copying each one

    intern = sys.intern                   # one shared copy of every repeated string
    for r in resources:
        subjects = [intern(str(s)) for s in r.get("subjects", [])]
        r["subjects"] = subjects
        keywords = r.get("keywords", [])
        # importer writes keywords = subjects when there are none: share the list, don't duplicate it
        r["keywords"] = subjects if list(keywords) == subjects else [intern(str(k)) for k in keywords]
        for key in ("type", "publisher", "place", "edition", "language"):   # few distinct values: share one copy
            if isinstance(r.get(key), str):
                r[key] = intern(r[key])
        if r.get("biblionumber") is not None and r.get("biblionumber") == r.get("id"):
            r["biblionumber"] = r["id"]

        r["concepts"] = concepts_for_text(searchable_text(r))

    del raw
    return resources, source_label
