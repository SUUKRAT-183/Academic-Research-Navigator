# Replacing the sample data with the library's data

The website reads **one file**: `data/catalogue.json`. Everything else (search, concepts, related topics,
explanations, dashboard) is computed from it when the server starts. So swapping data =
**convert the library's file into `catalogue.json`, restart.** A script does the conversion.

```
library file (CSV/XLSX)  --import_library_data.py-->  data/catalogue.json  +  data/vocabulary.json  --> website
```

## Step 0: Before the file arrives
- Ask the library for these columns (more is better, only **title** is mandatory):
  `biblionumber, title, author, publication year, item type, subject headings, abstract/summary, call number`
  Ask for **CSV or Excel**, UTF-8 if possible.
- Ask for **permission** to host their data online (and keep your GitHub repo private).
- Ask whether the catalogue is Koha and what the public record link looks like. The site builds
  "Open in catalogue" links from `biblionumber`. Default pattern:
  `https://library.thapar.edu/cgi-bin/koha/opac-detail.pl?biblionumber=<number>`.
  If the real pattern differs, set the env var `ARN_OPAC_URL_TEMPLATE`, e.g.
  `https://opac.example.edu/record?id={biblionumber}`.
- Ask if their system supports **OAI-PMH** or **SRU**. If it does, you may be able to pull metadata yourselves.

## Step 1: Put the file in a folder (not inside `data/`)
```
arn_prototype/library_data/export.csv
```
Do **not** commit it to a public repo.

## Step 2: Look before you import
```bash
python -m scripts.import_library_data library_data/export.csv --show-columns
```
It lists the columns and shows what it guessed:
```
  title         <- Title
  author        <- Author
  subjects      <- Subject Headings
  abstract      <- (not found)
```
Anything wrong or `(not found)` although the column exists? Fix with `--map FIELD=COLUMN`:
```bash
--map subjects="Topical Term" --map abstract=Summary --map biblionumber="Bib No"
```
Valid fields: `id, title, author, year, type, subjects, keywords, abstract, call_number, biblionumber, isbn`.

If many subjects are in one cell and the library separates them with commas, add `--subject-sep ","`
(default separators are `;` and `|`).

## Step 3: Import
```bash
python -m scripts.import_library_data library_data/export.csv \
    --label "TIET Central Library catalogue (export of 2026-12-01)"
```
What it does for you:
- reads CSV (any common encoding) or XLSX; skips rows without a title; drops duplicate ids
- splits subject cells into lists, extracts a 4-digit year
- **backs up** the Kaggle data once to `data/catalogue_kaggle_backup.json`
- writes `data/catalogue.json` and **rebuilds `data/vocabulary.json`** (the concept list) from the
  library's own subject headings

Read the **Completeness** report it prints:

| What it shows | What to do |
|---|---|
| subjects under 50% | Concepts and related topics will be weak. Check the mapping or ask the library for subject headings. |
| few abstracts | Normal for libraries. Search relies on titles + subjects. Ranking is weaker but works. |
| biblionumber 0% | "Open in catalogue" buttons won't appear. Map the column or ask for it. |

## Step 4: Check locally
```bash
uvicorn backend.main:app --reload
```
Open http://127.0.0.1:8000. Try 10 searches your classmates would really type. Check:
- `/api/health` shows the new record count and your label
- concept chips look sensible (they come from real subject headings now)
- Open a result: call number and catalogue link are present

Then run `pytest -q`. The tests don't depend on a specific dataset, so they should still pass.

## Step 5: Update the homepage examples (5 minutes, matters for real users)
These are typed into `frontend/index.html`, not generated from data:
- the **"research direction" cards** (search for `const discoveryAreas`, about line 3206): AI, CS, ECE, Data
- the example **chips** under the search box (`setQuery('fake news + GNNs')` etc., about line 2734)
- the four **"DISCOVER"** cards (Recently added, Trending, ...) just search for those literal words.
  They are not real features yet. Replace them with real subjects from your data, or
  ask me to drive "Trending" from your actual top searches in `/admin`.

Pick example searches that return good results in the library's data. A first-time visitor who
clicks an example and gets nothing will leave.

## Step 6: Publish the new data
```bash
git add data/catalogue.json data/vocabulary.json
git commit -m "Use library catalogue data"
git push
```
Render redeploys automatically. Check `https://<your-link>/api/health`.
Your **visitor statistics are kept**: they live in Neon, not in the catalogue.

## Going back to the demo data
```bash
copy data\catalogue_kaggle_backup.json data\catalogue.json     (Mac/Linux: cp)
del data\vocabulary.json                                       (rm)
```
Deleting `vocabulary.json` matters: without it the app uses the built-in Kaggle genre list again.

## Updating later (library sends a newer export)
Just repeat Steps 2-4 and 6. Re-running the import regenerates both files.

## Trying a different interim dataset
Until the library data arrives, the importer works on **any** CSV/XLSX with a title column,
e.g. an arXiv or engineering-books dataset from Kaggle. A technical dataset makes the site
useful to students now, which is what gets real footfall. Use `--label "arXiv sample (demo)"` so the site is honest about the source.

## Troubleshooting
| Problem | Fix |
|---|---|
| `No title column found` | `--map title="<your column name>"` |
| Strange characters (é, ç broken) | Re-export as UTF-8 CSV, or open in Excel and save as XLSX |
| Every book has 1 giant subject | Wrong `--subject-sep`; look at a raw cell and match its separator |
| Very few concept chips | Subjects are sparse; try `python -m scripts.build_vocabulary --min-freq 2` |
| Server slow to start with a big file | Startup tags every record; ~6 s per 6,000 records. Normal. |

## Big catalogues (50,000 - 200,000+ records)
The site holds the whole catalogue in memory, so the host's RAM decides how big it can be.
Measured on realistic synthetic files (peak memory after a batch of searches):

| Catalogue | Peak memory | Free Render (512 MB) |
|---|---|---|
| 10,000 records with abstracts | ~270 MB | comfortable |
| 100,000 records, titles + subjects | ~345 MB | fits |
| 160,000 records, titles + author + year only | ~340 MB | fits |
| 160,000 records, titles + subjects + call numbers | ~450 MB | too tight, use a bigger host or a subset |

Startup is a few seconds and a search takes ~10-30 ms at any of these sizes.
Check the real number on your real file: open `/api/health` and read `memory_peak_mb`.

Things that are different for big files:
- **Concepts need subject headings.** A file with only title/author/year gives 0 concepts: the concept chips and
  "related concepts" stay empty and search is plain TF-IDF over titles. Ask the library for subject headings.
- **"Explore a concept" shows at most 100 resources** (the response also reports the true total).
  Change the cap with the `ARN_EXPLORE_LIMIT` environment variable.
- **Git file size:** GitHub warns at 50 MB and refuses files over 100 MB. `data/catalogue.json` is roughly
  300 bytes per record, so ~330,000 records is the ceiling for a plain JSON file.
- **Never commit library data to a public repository.** Make the repo private first (Settings -> Danger Zone).

## The TIET export (the spreadsheet the professor sent)
Columns: Accession No, Call Number, Title, Author, Co-Author(s), Language, Publisher, Place, Year, Edition,
Pages, ISBN/ISSN, Subjects, Material Type, Biblio ID, Catalogue Link. The importer handles this layout as is:

| Column | Used for |
|---|---|
| Title, Author + Co-Author(s) | shown on every result (co-authors are joined to the author) |
| Subjects | concepts, related topics, ranking |
| Material Type | type filter ("Text Book", "General Book") |
| Year, Call Number | shown on the result card |
| Biblio ID | the record's unique id (one per BOOK) |
| Catalogue Link | the real "Open in catalogue" link. If every link has the same pattern it is stored once |
| Publisher, Edition | shown in the detail panel; edition also next to the year ("Weiss, Mark · 2014 · 2nd ed.") |
| Place, Language, Pages, ISBN/ISSN | **opt-in**: `--extra-fields place,language,pages,isbn`. Each costs ~6-10 MB of memory per 137,000 records and makes catalogue.json ~6 MB bigger, for little value to someone choosing a book |
| Accession No | ignored on purpose (one per physical copy, not per book) |

What the website shows for a library record:
- the card: title, "author · year · edition", subjects, **VIEW IN LIBRARY →** (the Thapar catalogue page, where live
  availability is) and *View details* (the in-site panel). The old "OPEN RESOURCE" button only appears for records
  that have no library link, so students are never offered two competing links.
- the detail panel: type, year, author, record number, call number, publisher, edition, subjects, and a note to check
  live availability in the library catalogue. Fields with no value are hidden instead of saying "Not provided".
- There is no abstract in this export, so no abstract section is shown. Search uses title, subjects and author.

- **Copies:** if the sheet has one row per copy, rows with the same Biblio ID are merged into one record.
  The import report says how many repeated ids it skipped.
- **Subject headings** such as `JAVA (Computer program language) -- Handbooks` are reduced to `java` for the concept
  list, so a student typing "java" gets the concept. The full heading stays on the record.
- **Several subjects in one cell** are split on `;` and `|`. If the library uses another separator, add
  `--subject-sep ","` (or whatever it is). Check by looking at a Subjects cell that has several subjects.
- **Use the CSV, not the .xlsx, when you have both.** A 160,000-row CSV (~41 MB) imports in about 7 seconds; the
  Excel version (~15 MB, compressed) takes about 40 seconds and more RAM. Either needs ~1 GB of free RAM while importing.
  The CSV reader copes with UTF-8 (with or without BOM), Windows cp1252, `,` or `;` delimiters and line breaks inside cells.
- Run `--show-columns` first, as always. Every line should show a column except abstract, keywords and id.
