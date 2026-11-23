# Demo catalogue from arXiv (while we wait for the library data)

Goal: replace the fiction-heavy Kaggle books with ~10,000 real engineering/CS research papers so the
site gives useful results for topics students actually search ("natural language processing",
"robotics", "signal processing"...).

```
Kaggle arXiv file (~3 GB)  --prepare_arxiv.py-->  arxiv_subset.csv  --import_library_data.py-->  data/catalogue.json
```
The arXiv metadata is released under CC0 (public domain), so it is fine to keep in a public repo.
Run every command from the project folder (the one containing `backend` and `scripts`).

## Step 1: Download (about 10-30 minutes depending on internet)
1. Make a free account at kaggle.com and sign in.
2. Open https://www.kaggle.com/datasets/Cornell-University/arxiv and click **Download**.
3. You get `archive.zip`. Unzip it. Inside is **`arxiv-metadata-oai-snapshot.json`** (several GB;
   keep ~5 GB of disk free while unzipping).

## Step 2: Put the file in `library_data`
Create a folder `library_data` in the project folder and move the big `.json` file into it:
```
library_data\arxiv-metadata-oai-snapshot.json
```
`library_data/` is listed in `.gitignore`, so git will never try to upload it.

## Step 3: Cut it down to 10,000 papers (takes a few minutes)
```
python -m scripts.prepare_arxiv library_data\arxiv-metadata-oai-snapshot.json
```
What it does: streams the file (never loads 3 GB into memory), keeps papers from 2018 onwards whose
MAIN category is computer science, electrical engineering & systems science (signal/image/audio
processing, control), ML-statistics or optimisation, samples **evenly across topics**, turns codes
like `cs.LG` into names like "machine learning", and drops withdrawn papers.

You should see about 10,000 papers kept and a table of papers per topic. Output file:
`library_data\arxiv_subset.csv`. Same command again = same sample (fixed seed).

Options: `--max-records 8000` (smaller), `--min-year 2015` (include older papers).
Keep it at about 10,000 or less: the free Render plan has 512 MB of memory.

## Step 4: Load it into the website
```
python -m scripts.import_library_data library_data\arxiv_subset.csv --label "arXiv sample (demo catalogue, open CC0 data)"
```
Expected report: ~10,000 records; author, year, subjects, abstract all ~100%; call number and
biblionumber 0% (normal: these are papers, not shelved books, so there are no "Open in catalogue" links).
It also backs up the old Kaggle books to `data\catalogue_kaggle_backup.json` and rebuilds
`data\vocabulary.json` (about 40 concepts such as "machine learning", "robotics").

## Step 5: Test locally
```
$env:ADMIN_PASSWORD="12345678"; python -m uvicorn backend.main:app --reload
```
Start-up takes only a few seconds (3-5 s for 10,000 abstracts). Then open http://127.0.0.1:8000
and try: `natural language processing`, `machine learning`, `robotics`, `signal processing`,
`medical imaging`, `federated learning`, `cybersecurity`.
Check `http://127.0.0.1:8000/api/health`: it should say 10,000 records and your label.

Also click every card/chip on the homepage. The ones that return nothing or nonsense need to be
re-worded (see DATA_SWAP_GUIDE.md, Step 5).

## Step 6: Commit the result
Commit `data/catalogue.json` (about 15 MB) and `data/vocabulary.json`, NOT `library_data/`:
```
git add data/catalogue.json data/vocabulary.json scripts tests ARXIV_DEMO_DATA.md
git commit -m "Use arXiv engineering sample as demo catalogue"
git push
```
GitHub rejects single files over 100 MB, so never add the raw arXiv file.

## Honesty note for the report/demo
The site shows "Data source: arXiv sample..." on the dashboard and on resource pages. Say in your
report that this is a stand-in until the TIET library data arrives, and that the same importer will
load it. The ~40 concepts here come from arXiv categories; the library's own subject headings will
give a richer concept layer.

## Troubleshooting
| Problem | Fix |
|---|---|
| `File not found` | Check the path/spelling; you must be in the project folder |
| `No matching papers found` | Wrong file. Use `arxiv-metadata-oai-snapshot.json`, not a PDF/other file |
| "only N papers matched" | Lower `--min-year` (e.g. 2012) |
| Out of disk space during unzip | Free ~5 GB; delete `archive.zip` after unzipping |
| Site slow to start | Should be a few seconds for 10,000 papers. If Render runs out of memory, reduce `--max-records` |
| Render shows "out of memory" | Re-run Step 3 with `--max-records 7000`, re-import, push |
