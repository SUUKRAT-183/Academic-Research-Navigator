"""
Cut the huge arXiv metadata file (Kaggle: Cornell-University/arxiv, ~3 GB) down to a
balanced, engineering-focused sample and write a CSV that import_library_data.py reads.

    python -m scripts.prepare_arxiv library_data/arxiv-metadata-oai-snapshot.json

Options:
    --max-records 10000     how many papers to keep (default 10000)
    --min-year 2018         ignore papers first submitted before this year
    --seed 42               same seed = same sample every time
    --out library_data/arxiv_subset.csv

What it does:
  * streams the file one line at a time (never loads 3 GB into memory)
  * keeps papers whose MAIN category is computer science, electrical engineering &
    systems science (signal/image/audio processing, control), ML-statistics or
    optimisation & control
  * samples evenly ACROSS topics, so robotics and signal processing are not drowned
    out by machine learning
  * turns codes like "cs.LG" into readable subject names like "machine learning"
  * drops withdrawn papers and ones without a real abstract

Takes a few minutes on the full file.
"""
import argparse
import csv
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..")

# arXiv category code -> readable subject name (no commas in names: the importer
# splits subjects on ; and |). Two codes can share a name (they are the same field).
CATEGORY_NAMES = {
    "cs.AI": "artificial intelligence",
    "cs.AR": "computer architecture",
    "cs.CC": "computational complexity",
    "cs.CE": "computational engineering",
    "cs.CG": "computational geometry",
    "cs.CL": "natural language processing",
    "cs.CR": "cryptography and security",
    "cs.CV": "computer vision",
    "cs.CY": "computers and society",
    "cs.DB": "databases",
    "cs.DC": "distributed computing",
    "cs.DL": "digital libraries",
    "cs.DM": "discrete mathematics",
    "cs.DS": "algorithms and data structures",
    "cs.ET": "emerging technologies",
    "cs.GR": "computer graphics",
    "cs.GT": "game theory",
    "cs.HC": "human-computer interaction",
    "cs.IR": "information retrieval",
    "cs.IT": "information theory",
    "cs.LG": "machine learning",
    "cs.LO": "logic in computer science",
    "cs.MA": "multiagent systems",
    "cs.MM": "multimedia",
    "cs.NA": "numerical analysis",
    "cs.NE": "neural and evolutionary computing",
    "cs.NI": "computer networks",
    "cs.OS": "operating systems",
    "cs.PF": "performance evaluation",
    "cs.PL": "programming languages",
    "cs.RO": "robotics",
    "cs.SD": "sound and audio",
    "cs.SE": "software engineering",
    "cs.SI": "social networks",
    "cs.SY": "control systems",
    "eess.AS": "speech and audio processing",
    "eess.IV": "image and video processing",
    "eess.SP": "signal processing",
    "eess.SY": "control systems",
    "math.IT": "information theory",
    "math.NA": "numerical analysis",
    "math.OC": "optimization and control",
    "stat.ML": "machine learning",
}

# A paper is a candidate if its MAIN (first-listed) category is one of these.
CORE_PRIMARY = {c for c in CATEGORY_NAMES if c.split(".")[0] in ("cs", "eess")} | {"stat.ML", "math.OC"}

_CAT_RE = re.compile(r'"categories"\s*:\s*"([^"]*)"')
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
MAX_ABSTRACT_CHARS = 1500       # keeps memory predictable on a free host


def clean(text) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + " ..."


def first_year(rec) -> int | None:
    """Year of the first version (= when the paper first appeared)."""
    versions = rec.get("versions") or []
    stamp = versions[0].get("created", "") if versions else ""
    m = _YEAR_RE.search(stamp) or _YEAR_RE.search(rec.get("update_date") or "")
    return int(m.group(1)) if m else None


def authors_text(rec) -> str:
    parsed = rec.get("authors_parsed") or []
    names = []
    for p in parsed[:3]:
        last, first = (p + ["", ""])[:2]
        names.append(clean(f"{first} {last}"))
    if names:
        return ", ".join(names) + (" et al." if len(parsed) > 3 else "")
    return clean(rec.get("authors"))[:120] or "Unknown"


def subject_names(categories: str) -> list:
    out, seen = [], set()
    for code in categories.split():
        name = CATEGORY_NAMES.get(code)
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def to_row(rec, subjects):
    return {
        "id": rec["id"],
        "title": clean(rec.get("title")),
        "authors": authors_text(rec),
        "year": first_year(rec),
        "item type": "Research paper",
        "subject headings": "; ".join(subjects),
        "abstract": trim(clean(rec.get("abstract")), MAX_ABSTRACT_CHARS),
    }


def usable(rec) -> bool:
    abstract = clean(rec.get("abstract"))
    title = clean(rec.get("title"))
    if not title or len(abstract) < 100:
        return False
    low = abstract.lower()
    return not ("withdrawn" in low[:200] or "this paper has been removed" in low)


def allocate(sizes: dict, budget: int) -> dict:
    """Fair share: small topics keep everything they have, big ones split the rest evenly."""
    alloc, remaining = {}, budget
    items = sorted(sizes.items(), key=lambda kv: kv[1])
    for i, (cat, size) in enumerate(items):
        take = min(size, remaining // (len(items) - i))
        alloc[cat] = take
        remaining -= take
    return alloc


def prepare(path, out_path, max_records=10000, min_year=2018, seed=42, progress=True):
    rng = random.Random(seed)
    # Per-topic sample size kept while reading. It only has to be as big as the largest FAIR share a
    # topic could receive at the end (see allocate); a sixth of the target is plenty and still small in memory.
    cap = max(100, math.ceil(max_records / 6))
    reservoirs = defaultdict(list)       # primary category -> sampled rows
    seen_count = Counter()               # eligible papers seen per primary category
    total_lines = bad_lines = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            total_lines += 1
            if progress and total_lines % 250_000 == 0:
                print(f"  ... {total_lines:,} lines read, {sum(len(v) for v in reservoirs.values()):,} candidates kept")
            m = _CAT_RE.search(line)                    # cheap check before the slow JSON parse
            if not m:
                continue
            categories = m.group(1)
            primary = categories.split()[0] if categories.split() else ""
            if primary not in CORE_PRIMARY:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            year = first_year(rec)
            if year is None or year < min_year or not usable(rec):
                continue
            row = to_row(rec, subject_names(categories))
            if not row["subject headings"]:
                continue

            seen_count[primary] += 1                    # reservoir sampling (uniform within topic)
            bucket = reservoirs[primary]
            if len(bucket) < cap:
                bucket.append(row)
            else:
                j = rng.randrange(seen_count[primary])
                if j < cap:
                    bucket[j] = row

    if not reservoirs:
        sys.exit("No matching papers found. Is this the arXiv metadata file "
                 "(arxiv-metadata-oai-snapshot.json)? Try a lower --min-year.")

    alloc = allocate({c: len(v) for c, v in reservoirs.items()}, max_records)
    rows = []
    for cat, bucket in reservoirs.items():
        rng.shuffle(bucket)
        rows.extend(bucket[:alloc[cat]])
    rng.shuffle(rows)

    fields = ["id", "title", "authors", "year", "item type", "subject headings", "abstract"]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    return {"lines": total_lines, "bad_lines": bad_lines, "kept": len(rows),
            "per_topic": {c: alloc[c] for c in sorted(alloc, key=alloc.get, reverse=True)},
            "available": dict(seen_count), "rows": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="arxiv-metadata-oai-snapshot.json (the big JSON-lines file)")
    ap.add_argument("--out", default=os.path.join(ROOT, "library_data", "arxiv_subset.csv"))
    ap.add_argument("--max-records", type=int, default=10000)
    ap.add_argument("--min-year", type=int, default=2018)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    if not os.path.exists(a.input):
        sys.exit(f"File not found: {a.input}")
    print(f"Reading {a.input} (this takes a few minutes for the full file)...")
    r = prepare(a.input, a.out, a.max_records, a.min_year, a.seed)

    years = Counter(row["year"] for row in r["rows"])
    print(f"\nRead {r['lines']:,} lines ({r['bad_lines']} unreadable). Kept {r['kept']:,} papers -> {a.out}")
    print("\nPapers kept per main topic (top 12):")
    for cat, n in list(r["per_topic"].items())[:12]:
        print(f"  {CATEGORY_NAMES.get(cat, cat):34s} {n:5d}   (of {r['available'][cat]:,} eligible)")
    print("\nBy year:", ", ".join(f"{y}: {n}" for y, n in sorted(years.items())))
    if r["kept"] < 0.8 * a.max_records:
        print(f"\nNote: only {r['kept']:,} papers matched (you asked for {a.max_records:,}). "
              f"Lower --min-year (now {a.min_year}) to include older papers.")
    print("\nNext:")
    print(f'  python -m scripts.import_library_data "{a.out}" --label "arXiv sample (demo catalogue, open CC0 data)"')


if __name__ == "__main__":
    main()
