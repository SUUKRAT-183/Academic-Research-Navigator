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
import json
import os
import re
import shutil
import sys
from datetime import date

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
    "biblionumber": ["biblionumber", "biblionum", "bibid", "recordid", "biblio.biblionumber"],
    "isbn":         ["isbn", "isbn13", "isbn10", "biblioitems.isbn"],
    "id":           ["id", "identifier", "recordnumber", "accessionnumber", "accessionno", "accno", "barcode"],
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
        delim = "\t" if ext == ".tsv" else (csv.Sniffer().sniff(text[:5000], delimiters=",;\t|").delimiter
                                            if text[:5000].strip() else ",")
        reader = csv.DictReader(text.splitlines(), delimiter=delim)
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


def convert(rows, mapping, subject_sep=";|", default_type="Book"):
    def cell(row, field):
        col = mapping.get(field)
        v = row.get(col, "") if col else ""
        return "" if v is None else str(v).strip()

    resources, seen_ids, stats = [], set(), {"no_title": 0, "duplicates": 0}
    for i, row in enumerate(rows, start=1):
        title = cell(row, "title")
        if not title:
            stats["no_title"] += 1
            continue
        rid = cell(row, "id") or cell(row, "biblionumber") or cell(row, "isbn") or f"L{i:06d}"
        if rid in seen_ids:
            stats["duplicates"] += 1
            continue
        seen_ids.add(rid)

        subjects = split_list(cell(row, "subjects"), subject_sep)
        keywords = split_list(cell(row, "keywords"), subject_sep) or list(subjects)
        rec = {
            "id": rid,
            "title": title,
            "author": cell(row, "author") or "Unknown",
            "year": get_year(cell(row, "year")),
            "type": cell(row, "type") or default_type,
            "subjects": subjects,
            "keywords": keywords,
            "abstract": cell(row, "abstract"),
        }
        for optional in ("call_number", "biblionumber", "isbn"):
            if cell(row, optional):
                rec[optional] = cell(row, optional)
        resources.append(rec)
    return resources, stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="CSV / TSV / XLSX file from the library")
    ap.add_argument("--sheet", help="sheet name (xlsx only)")
    ap.add_argument("--map", action="append", default=[], metavar="FIELD=COLUMN",
                    help="override a guess, e.g. --map subjects=\"Subject Headings\"")
    ap.add_argument("--subject-sep", default=";|", help="characters that separate several subjects in one cell "
                    "(default ';' and '|'; use \",\" if the library separates with commas)")
    ap.add_argument("--default-type", default="Book")
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

    resources, stats = convert(rows, mapping, a.subject_sep, a.default_type)
    n = len(resources)
    if not n:
        sys.exit("No usable records.")

    def pct(pred):
        return round(100 * sum(1 for r in resources if pred(r)) / n)

    print(f"\nImported {n} records (skipped {stats['no_title']} without title, {stats['duplicates']} duplicate ids)")
    print("Completeness:")
    print(f"  author        {pct(lambda r: r['author'] != 'Unknown')}%")
    print(f"  year          {pct(lambda r: r['year'])}%")
    print(f"  subjects      {pct(lambda r: r['subjects'])}%")
    print(f"  abstract      {pct(lambda r: r['abstract'])}%")
    print(f"  call number   {pct(lambda r: r.get('call_number'))}%")
    print(f"  biblionumber  {pct(lambda r: r.get('biblionumber'))}%")
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
            print(f"\nBacked up the previous catalogue to {os.path.relpath(backup)}")
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"_source_label": label, "resources": resources}, f, ensure_ascii=False)
    print(f"Wrote {a.out}  (source label: {label!r})")

    if not a.no_vocab:
        from .build_vocabulary import build_vocabulary
        vocab_path = os.path.join(os.path.dirname(a.out), "vocabulary.json")
        _, distinct, terms = build_vocabulary(a.out, vocab_path)
        print(f"Rebuilt concept vocabulary: {len(terms)} concepts from {distinct} distinct subjects -> {vocab_path}")
    print("\nNext: restart the server, open the site, and try a few searches.")


if __name__ == "__main__":
    main()
