"""
Convert the library's metadata export (CSV or Excel) into data/catalogue.json,
the one file the website reads.

STEP 1 - look at what columns the library sent and what the script guesses:
    python -m scripts.import_library_data library_export.csv --show-columns

STEP 2 - import (fix any wrong guesses with --map FIELD=COLUMN):
    python -m scripts.import_library_data library_export.csv \
        --label "TIET Central Library catalogue (export of 2026-12-01)"

    python -m scripts.import_library_data export.xlsx --sheet Sheet1 \
        --map subjects="Subject Headings" --map abstract=Summary --subject-sep ";"

Fields the website understands:
    id (required, made up if missing), title (required), author, year, type,
    subjects, keywords, abstract, call_number, biblionumber, isbn
Everything except title can be missing; the site just has less to show/match.
"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
from datetime import date

from .segment_subjects import SubjectSegmenter, looks_space_joined

ROOT = os.path.join(os.path.dirname(__file__), "..")

# column-name guesses, checked in order, case/space/underscore-insensitive.
# Includes typical Koha, Excel and MARC-ish headings.
GUESSES = {
    "title":        ["title", "titlestatement", "booktitle", "245", "245a", "biblio.title"],
    "author":       ["author", "authors", "creator", "mainauthor", "100a", "biblio.author"],
    "year":         ["year", "publicationyear", "publishedyear", "pubyear", "copyrightdate", "date",
                     "publicationdate", "biblioitems.publicationyear", "biblio.copyrightdate"],
    "type":         ["type", "itemtype", "materialtype", "format", "doctype", "biblioitems.itemtype"],
    "subjects":     ["subjects", "subject", "subjectheadings", "topics", "categories", "category",
                     "650", "650a", "genre", "classification"],
    "keywords":     ["keywords", "keyword", "tags", "uncontrolledterms"],
    "abstract":     ["abstract", "summary", "description", "notes", "abstractsummary", "520", "520a",
                     "biblio.abstract"],
    "call_number":  ["callnumber", "callno", "itemcallnumber", "shelfmark", "ddc", "classno",
                     "items.itemcallnumber", "952o"],
    "biblionumber": ["biblionumber", "biblionum", "biblioid", "biblioidnumber", "bibliono", "bibid",
                     "recordid", "biblio.biblionumber"],
    "isbn":         ["isbn", "isbn13", "isbn10", "isbnissn", "issn", "biblioitems.isbn"],
    # NOTE: accession numbers / barcodes identify one physical COPY, not the book, so they are NOT
    # guessed as the id (several copies would then appear as duplicate results). Use --map id=... to force.
    "id":           ["id", "identifier", "recordnumber"],
    "publisher":    ["publisher", "publishername", "imprint"],
    "place":        ["place", "placeofpublication", "publicationplace", "city"],
    "edition":      ["edition", "editionstatement"],
    "language":     ["language", "lang"],
    "pages":        ["pages", "extent", "physicaldescription", "pagination"],
    "coauthors":    ["coauthor", "coauthors", "coauthor(s)", "otherauthors", "additionalauthors", "secondaryauthors"],
    "catalogue_url": ["cataloguelink", "catalogurl", "cataloglink", "catalogueurl", "opaclink", "opacurl",
                      "recordlink", "link", "url"],
}
LIST_FIELDS = ("subjects", "keywords")


def norm(name: str) -> str:
    return re.sub(r"[\s_\-./]+", "", str(name).strip().lower())


def read_rows(path, sheet=None):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(it)]
        rows = [dict(zip(header, ["" if v is None else v for v in r])) for r in it]
        return header, rows
    if ext in (".csv", ".tsv", ".txt"):
        raw = open(path, "rb").read()
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        del raw
        delim = "\t" if ext == ".tsv" else ","
        if ext != ".tsv" and text[:5000].strip():
            try:
                delim = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|").delimiter
            except csv.Error:
                delim = ","                      # could not tell: assume a normal comma-separated file
        csv.field_size_limit(50_000_000)
        # newline="" lets the csv module see line breaks INSIDE quoted cells (a plain splitlines()
        # would silently glue those lines together: "Data\nStructures" -> "DataStructures")
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
        return reader.fieldnames or [], list(reader)
    sys.exit(f"Unsupported file type '{ext}'. Export from the library as CSV or XLSX.")


def guess_mapping(columns):
    by_norm = {norm(c): c for c in columns}
    mapping = {}
    for field, names in GUESSES.items():
        for n in names:
            if n in by_norm:
                mapping[field] = by_norm[n]
                break
    return mapping


def split_list(value, seps):
    if value is None:
        return []
    parts = re.split("[" + re.escape(seps) + "\n]", str(value))
    out, seen = [], set()
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" .")
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return out


def get_year(value):
    m = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", str(value or ""))
    return int(m.group(1)) if m else None


def derive_opac_url_template(resources):
    """If every record's catalogue link is the same URL with only the biblionumber changing, return
    that pattern ("...biblionumber={biblionumber}") so it can be stored ONCE instead of 160,000 times."""
    pairs = [(r["catalogue_url"], r["biblionumber"]) for r in resources
             if r.get("catalogue_url") and r.get("biblionumber")]
    if not pairs:
        return None
    url, bn = pairs[0]
    if url.count(bn) != 1 or "{" in url or "}" in url:
        return None
    template = url.replace(bn, "{biblionumber}")
    return template if all(template.format(biblionumber=b) == u for u, b in pairs) else None


CORE_FIELDS = ("call_number", "biblionumber", "catalogue_url", "publisher", "edition")
EXTRA_FIELDS = ("place", "language", "pages", "isbn")      # opt-in: each costs memory and catalogue-file size


def convert(rows, mapping, subject_sep=";|", default_type="Book", extra_fields=(), segmenter=None):
    def cell(row, field):
        col = mapping.get(field)
        v = row.get(col, "") if col else ""
        if v is None:
            return ""
        if isinstance(v, float) and v.is_integer():     # Excel stores 794 as 794.0
            v = int(v)
        v = str(v).strip()
        if field in ("subjects", "keywords"):
            return v                                     # a line break may separate two subjects: keep it
        return re.sub(r"\s+", " ", v)                    # elsewhere a line break is just stray whitespace

    resources, seen_ids, stats = [], set(), {"no_title": 0, "duplicates": 0}
    for i, row in enumerate(rows, start=1):
        title = cell(row, "title")
        if not title:
            stats["no_title"] += 1
            continue
        # The library's own record number wins: it is one per BOOK (an accession number is one per copy).
        rid = cell(row, "biblionumber") or cell(row, "id") or cell(row, "isbn") or f"L{i:06d}"
        if rid in seen_ids:
            stats["duplicates"] += 1
            continue
        seen_ids.add(rid)

        author = cell(row, "author")
        co = cell(row, "coauthors")
        if co:
            author = f"{author}; {co}" if author else co

        subjects = split_list(cell(row, "subjects"), subject_sep)
        if segmenter:                                     # cut space-joined headings into separate subjects
            cut, seen_subjects = [], set()
            for piece in subjects:
                for part in segmenter.split(piece):
                    if part.lower() not in seen_subjects:
                        seen_subjects.add(part.lower())
                        cut.append(part)
            subjects = cut
        keywords = split_list(cell(row, "keywords"), subject_sep) or list(subjects)
        rec = {
            "id": rid,
            "title": title,
            "author": author or "Unknown",
            "year": get_year(cell(row, "year")),
            "type": cell(row, "type") or default_type,
            "subjects": subjects,
            "keywords": keywords,
            "abstract": cell(row, "abstract"),
        }
        for optional in CORE_FIELDS + tuple(extra_fields):
            if cell(row, optional):
                rec[optional] = cell(row, optional)
        resources.append(rec)
    return resources, stats


def _shown(path):
    """A short path to print. os.path.relpath() raises ValueError on Windows when the file is on a
    different drive than the current folder (C: temp folder, E: project), so fall back to the full path."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return os.path.abspath(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="CSV / TSV / XLSX file from the library")
    ap.add_argument("--sheet", help="sheet name (xlsx only)")
    ap.add_argument("--map", action="append", default=[], metavar="FIELD=COLUMN",
                    help="override a guess, e.g. --map subjects=\"Subject Headings\"")
    ap.add_argument("--subject-sep", default=";|", help="characters that separate several subjects in one cell "
                    "(default ';' and '|'; use \",\" if the library separates with commas)")
    ap.add_argument("--default-type", default="Book")
    ap.add_argument("--segment-subjects", action="store_true",
                    help="use when several subject headings sit in one cell joined by plain spaces with no separator "
                    "(e.g. 'Concrete Technology Concrete Construction'). Learns the library's headings from the data "
                    "and splits the cells. A re-export with ';' between subjects is better if you can get one.")
    ap.add_argument("--extra-fields", default="", metavar="LIST",
                    help="also store these columns: any of " + ", ".join(EXTRA_FIELDS) + " (comma separated). "
                    "Off by default: each one adds ~6-10 MB of memory per 137,000 records and makes the "
                    "catalogue file bigger. Publisher and edition are always stored.")
    ap.add_argument("--label", help="shown on the site/dashboard as the data source")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "catalogue.json"))
    ap.add_argument("--show-columns", action="store_true", help="only print columns and guesses, write nothing")
    ap.add_argument("--no-vocab", action="store_true", help="do not rebuild data/vocabulary.json afterwards")
    a = ap.parse_args()

    columns, rows = read_rows(a.input, a.sheet)
    mapping = guess_mapping(columns)
    for item in a.map:
        field, _, col = item.partition("=")
        if field not in GUESSES or col not in columns:
            sys.exit(f"--map {item!r}: field must be one of {list(GUESSES)} and the column must exist.\n"
                     f"Columns in your file: {columns}")
        mapping[field] = col

    print(f"\n{len(rows)} rows, {len(columns)} columns found:\n  " + "\n  ".join(columns))
    print("\nMapping (website field <- your column):")
    for field in GUESSES:
        print(f"  {field:13s} <- {mapping.get(field, '(not found)')}")
    if a.show_columns:
        print("\nFix wrong/missing ones with --map FIELD=COLUMN, then run again without --show-columns.")
        return
    if "title" not in mapping:
        sys.exit("\nNo title column found. Use --map title=<column name>.")

    segmenter = None
    if "subjects" in mapping:
        pieces = [p for row in rows for p in split_list(row.get(mapping["subjects"]) or "", a.subject_sep)]
        if a.segment_subjects:
            segmenter = SubjectSegmenter.learn(pieces)
            share, multi = segmenter.quality(pieces)
            print(f"\nSubject splitter: learned {len(segmenter.headings)} headings from the data; "
                  f"{share:.0%} of {multi} multi-word subject cells split cleanly into known headings.")
            if share < 0.6:
                print("!! Under 60% split cleanly. Many concepts will be wrong or missing. Ask the library for an "
                      "export with ';' between the subjects of each record.")
        elif looks_space_joined(pieces):
            print("\n!! Many Subjects cells look like several headings joined by spaces. Add --segment-subjects to "
                  "split them (or ask the library for an export with ';' between subjects).")

    extra = tuple(x.strip() for x in a.extra_fields.split(",") if x.strip())
    unknown = [x for x in extra if x not in EXTRA_FIELDS]
    if unknown:
        sys.exit(f"--extra-fields: unknown {unknown}. Choose from {list(EXTRA_FIELDS)}.")
    resources, stats = convert(rows, mapping, a.subject_sep, a.default_type, extra, segmenter)
    n = len(resources)
    if not n:
        sys.exit("No usable records.")

    def pct(pred):
        return round(100 * sum(1 for r in resources if pred(r)) / n)

    opac_template = derive_opac_url_template(resources)
    if opac_template:
        for r in resources:
            r.pop("catalogue_url", None)           # stored once in the file header instead
    print(f"\nImported {n} records (skipped {stats['no_title']} without title, "
          f"{stats['duplicates']} repeated record ids: usually extra copies of the same book)")
    print("Completeness:")
    print(f"  author        {pct(lambda r: r['author'] != 'Unknown')}%")
    print(f"  year          {pct(lambda r: r['year'])}%")
    print(f"  subjects      {pct(lambda r: r['subjects'])}%")
    print(f"  abstract      {pct(lambda r: r['abstract'])}%")
    print(f"  call number   {pct(lambda r: r.get('call_number'))}%")
    print(f"  biblionumber  {pct(lambda r: r.get('biblionumber'))}%")
    print(f"  publisher     {pct(lambda r: r.get('publisher'))}%   edition {pct(lambda r: r.get('edition'))}%")
    skipped = [f for f in EXTRA_FIELDS if f in mapping and f not in extra]
    if skipped:
        print(f"  not stored (saves memory): {', '.join(skipped)}   (add them with --extra-fields {','.join(skipped)})")
    if opac_template:
        print(f"  catalogue links follow one pattern, stored once: {opac_template}")
    elif "catalogue_url" in mapping:
        print(f"  catalogue link {pct(lambda r: r.get('catalogue_url'))}%  (no common pattern, stored per record)")
    if pct(lambda r: r["subjects"]) < 50:
        print("\n!! Under half the records have subjects. Concepts, related-concepts and ranking depend on "
              "them. Check the subjects mapping / --subject-sep, or ask the library for a fuller export.")
    if pct(lambda r: r["abstract"]) < 20:
        print("\nNote: few abstracts - search will rely mostly on titles and subjects. That is OK, just "
              "expect weaker ranking.")

    label = a.label or f"Central Library catalogue (imported {date.today().isoformat()})"
    if os.path.exists(a.out):
        backup = os.path.join(os.path.dirname(a.out), "catalogue_kaggle_backup.json")
        if not os.path.exists(backup):
            shutil.copy(a.out, backup)
            print(f"\nBacked up the previous catalogue to {_shown(backup)}")
    with open(a.out, "w", encoding="utf-8") as f:
        header = {"_source_label": label}
        if opac_template:
            header["_opac_url_template"] = opac_template
        json.dump({**header, "resources": resources}, f, ensure_ascii=False)
    print(f"Wrote {a.out}  (source label: {label!r})")

    if not a.no_vocab:
        from .build_vocabulary import build_vocabulary
        vocab_path = os.path.join(os.path.dirname(a.out), "vocabulary.json")
        _, distinct, terms = build_vocabulary(a.out, vocab_path)
        print(f"Rebuilt concept vocabulary: {len(terms)} concepts from {distinct} distinct subjects -> {vocab_path}")
    print("\nNext: restart the server, open the site, and try a few searches.")


if __name__ == "__main__":
    main()
