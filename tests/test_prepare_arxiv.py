"""Tests scripts/prepare_arxiv.py on a fake file that imitates the real arXiv dump."""
import csv
import json
import os
import random
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")

ABSTRACT = ("We study a new approach to the problem and show experimentally on several benchmark "
            "datasets that it improves accuracy while reducing computation time considerably. ")


def make_record(i, cats, year=2021, title=None, abstract=None):
    return {
        "id": f"{year % 100:02d}01.{i:05d}",
        "submitter": "Someone",
        "authors": "A. Author, B. Writer and C. Person (MIT)",
        "title": title or f"Paper number {i}\n  on {cats.split()[0]}",   # arXiv titles contain newlines
        "comments": None, "journal-ref": None, "doi": None, "report-no": None,
        "categories": cats, "license": None,
        "abstract": abstract if abstract is not None else "  " + ABSTRACT * 2 + f"Variant {i}.\n",
        "versions": [{"version": "v1", "created": f"Mon, 2 Apr {year} 19:18:42 GMT"}],
        "update_date": f"{year}-05-01",
        "authors_parsed": [["Author", "A.", ""], ["Writer", "B.", ""], ["Person", "C.", ""], ["Fourth", "D.", ""]],
    }


def build_file(path):
    rng = random.Random(1)
    recs, n = [], 0
    # lots of ML, fewer robotics / signal processing: the sampler must balance them
    for cats, count in [("cs.LG stat.ML", 400), ("cs.CV cs.LG", 300), ("cs.RO", 40), ("eess.SP cs.IT math.IT", 30)]:
        for _ in range(count):
            n += 1
            recs.append(make_record(n, cats, year=rng.choice([2018, 2020, 2022])))
    # things that must be filtered out
    recs += [
        make_record(9001, "hep-th", 2021),                                   # not engineering
        make_record(9002, "cs.LG", 2010),                                    # too old
        make_record(9003, "cs.LG", 2021, abstract="short"),                  # no real abstract
        make_record(9004, "cs.LG", 2021, abstract="This paper has been withdrawn by the author. " + ABSTRACT),
        make_record(9005, "math.CO cs.LG", 2021),                            # main category is maths
    ]
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")   # compact, like the real dump
        f.write("{this line is broken json, \"categories\":\"cs.LG\"\n")      # corrupt line must not crash
    return len(recs)


def run_prepare(src, out, *extra):
    return subprocess.run([sys.executable, "-m", "scripts.prepare_arxiv", str(src), "--out", str(out), *extra],
                          cwd=ROOT, capture_output=True, text=True)


def test_filters_balances_and_cleans(tmp_path):
    src, out = tmp_path / "arxiv.json", tmp_path / "subset.csv"
    build_file(src)
    r = run_prepare(src, out, "--max-records", "200", "--min-year", "2018")
    assert r.returncode == 0, r.stdout + r.stderr
    rows = list(csv.DictReader(open(out, encoding="utf-8")))

    assert 150 <= len(rows) <= 200
    ids = {row["id"] for row in rows}
    assert not any(i.endswith(".09001") or i.endswith(".09002") or i.endswith(".09003")
                   or i.endswith(".09004") or i.endswith(".09005") for i in ids)
    assert all(int(row["year"]) >= 2018 for row in rows)

    # balanced: robotics (40 available) and signal processing (30) are fully kept, ML does not swamp them
    subj = lambda row: row["subject headings"].split("; ")
    robotics = [x for x in rows if "robotics" in subj(x)]
    signal = [x for x in rows if "signal processing" in subj(x)]
    assert len(robotics) >= 30 and len(signal) >= 20

    sample = rows[0]
    assert "\n" not in sample["title"] and "  " not in sample["title"]       # whitespace cleaned
    assert sample["authors"].endswith("et al.")                              # 4 authors -> first 3 + et al.
    assert sample["item type"] == "Research paper"
    assert all("." not in s or " " in s for row in rows for s in subj(row))  # no raw codes like cs.LG
    # duplicates collapse: cs.IT and math.IT are one subject
    sig = signal[0]["subject headings"].split("; ")
    assert sig.count("information theory") == 1


def test_same_seed_gives_same_sample_and_fails_clearly_on_wrong_file(tmp_path):
    src = tmp_path / "arxiv.json"
    build_file(src)
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    run_prepare(src, a, "--max-records", "100")
    run_prepare(src, b, "--max-records", "100")
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")

    wrong = tmp_path / "other.json"
    wrong.write_text('{"foo": "bar"}\n', encoding="utf-8")
    bad = run_prepare(wrong, tmp_path / "c.csv")
    assert bad.returncode != 0 and "No matching papers" in (bad.stdout + bad.stderr)


def test_full_chain_prepare_then_import_then_search(tmp_path):
    """prepare_arxiv -> import_library_data -> the real app answers a query."""
    src, csv_out, cat = tmp_path / "arxiv.json", tmp_path / "subset.csv", tmp_path / "catalogue.json"
    build_file(src)
    assert run_prepare(src, csv_out, "--max-records", "200").returncode == 0
    imp = subprocess.run([sys.executable, "-m", "scripts.import_library_data", str(csv_out),
                          "--out", str(cat), "--label", "ARXIV TEST"], cwd=ROOT, capture_output=True, text=True)
    assert imp.returncode == 0, imp.stdout + imp.stderr
    data = json.loads(cat.read_text(encoding="utf-8"))
    assert data["_source_label"] == "ARXIV TEST" and len(data["resources"]) >= 150
    vocab = json.loads((tmp_path / "vocabulary.json").read_text(encoding="utf-8"))
    assert "machine learning" in vocab["terms"] and "robotics" in vocab["terms"]

    code = ("from fastapi.testclient import TestClient\nfrom backend.main import app\n"
            "r = TestClient(app).post('/api/search', json={'query': 'robotics'}).json()\n"
            "print(r['identified_concepts'], len(r['results']))")
    env = dict(os.environ, ARN_CATALOGUE_PATH=str(cat), ARN_VOCABULARY_PATH=str(tmp_path / "vocabulary.json"),
               ARN_SQLITE_PATH=str(tmp_path / "a.db"))
    served = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
    assert served.returncode == 0, served.stderr
    assert "robotics" in served.stdout
