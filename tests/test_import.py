"""Simulates the day the library's file arrives."""
import json
import os
import subprocess
import sys
import textwrap

ROOT = os.path.join(os.path.dirname(__file__), "..")

# Koha-style headings, ';' separated subjects, one duplicate, one blank title,
# and a non-UTF-8 character (cp1252), like a real Windows/Excel export.
FAKE_EXPORT = textwrap.dedent("""\
    Biblionumber,Title,Author,Publication Year,Item Type,Subject Headings,Summary,Call Number
    101,Introduction to Machine Learning,Alpaydin E.,2020,Book,Machine learning; Artificial intelligence,A broad textbook.,006.31 ALP
    102,Digital Signal Processing,Proakis J.,2007,Book,Signal processing; Fourier analysis,,621.382 PRO
    103,Thermodynamics: An Engineering Approach,\u00c7engel Y.,2015,Book,Thermodynamics; Heat transfer,,621.402 CEN
    104,Operating System Concepts,Silberschatz A.,2018,Book,Operating systems; Computer science,,005.43 SIL
    105,Machine Learning Basics,Smith J.,2019,Book,Machine learning; Python,,006.31 SMI
    106,Deep Learning,Goodfellow I.,2016,Book,Machine learning; Neural networks,,006.31 GOO
    107,Pattern Recognition,Bishop C.,2006,Book,Machine learning; Pattern recognition,,006.4 BIS
    101,Duplicate of first row,Someone,2020,Book,Machine learning,,
    108,,No Title Author,2001,Book,Physics,,
""")


def run(*args, env=None):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT, capture_output=True, text=True, env=e)


def test_import_then_serve_library_data(tmp_path):
    src = tmp_path / "export.csv"
    src.write_bytes(FAKE_EXPORT.encode("cp1252"))
    out = tmp_path / "catalogue.json"

    # step 1: dry look
    peek = run("scripts.import_library_data", str(src), "--show-columns")
    assert peek.returncode == 0, peek.stderr
    assert "title         <- Title" in peek.stdout
    assert "subjects      <- Subject Headings" in peek.stdout
    assert "biblionumber  <- Biblionumber" in peek.stdout

    # step 2: import
    imp = run("scripts.import_library_data", str(src), "--out", str(out),
              "--label", "TEST LIBRARY DATA")
    assert imp.returncode == 0, imp.stdout + imp.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["_source_label"] == "TEST LIBRARY DATA"
    ids = [r["id"] for r in data["resources"]]
    assert ids == ["101", "102", "103", "104", "105", "106", "107"]   # dup + blank title dropped
    first = data["resources"][0]
    assert first["subjects"] == ["Machine learning", "Artificial intelligence"]
    assert first["call_number"] == "006.31 ALP" and first["biblionumber"] == "101"
    assert first["year"] == 2020
    assert data["resources"][2]["author"].startswith("\u00c7engel")      # encoding survived
    vocab = json.loads((tmp_path / "vocabulary.json").read_text(encoding="utf-8"))
    assert "machine learning" in vocab["terms"]                           # appears 4x... see min-freq below

    # step 3: the real app serves it
    code = textwrap.dedent("""
        from fastapi.testclient import TestClient
        from backend.main import app
        c = TestClient(app)
        r = c.post("/api/search", json={"query": "machine learning"}).json()
        print(r["results"][0]["title"], "|", r["identified_concepts"], "|",
              r["results"][0]["call_number"], "|", r["results"][0]["catalogue_url"])
        print(c.get("/api/health").json()["data_source"])
    """)
    env = dict(os.environ, ARN_CATALOGUE_PATH=str(out),
               ARN_VOCABULARY_PATH=str(tmp_path / "vocabulary.json"),
               ARN_SQLITE_PATH=str(tmp_path / "a.db"))
    served = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
    assert served.returncode == 0, served.stderr
    assert "TEST LIBRARY DATA" in served.stdout
    assert "machine learning" in served.stdout
    assert "biblionumber=" in served.stdout and "006.31" in served.stdout


def test_manual_map_override_and_bad_map(tmp_path):
    src = tmp_path / "odd.csv"
    src.write_text("Name of work,Writer,Topics\nBook A,Ann,x; y\n", encoding="utf-8")
    bad = run("scripts.import_library_data", str(src), "--out", str(tmp_path / "o.json"))
    assert bad.returncode != 0 and "No title column" in (bad.stdout + bad.stderr)
    ok = run("scripts.import_library_data", str(src), "--out", str(tmp_path / "o.json"),
             "--map", "title=Name of work", "--map", "author=Writer", "--no-vocab")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    rec = json.loads((tmp_path / "o.json").read_text())["resources"][0]
    assert rec["title"] == "Book A" and rec["author"] == "Ann" and rec["subjects"] == ["x", "y"]
