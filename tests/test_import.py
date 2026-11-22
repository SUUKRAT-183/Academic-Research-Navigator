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


# ---------------------------------------------------------------------------
# The real TIET export layout (columns copied from the professor's sheet)
# ---------------------------------------------------------------------------
TIET_HEADER = ["Accession No", "Call Number", "Title", "Author", "Co-Author(s)", "Language", "Publisher", "Place",
               "Year", "Edition", "Pages", "ISBN/ISSN", "Subjects", "Material Type", "Biblio ID", "Catalogue Link"]
OPAC = "https://library.thapar.edu/cgi-bin/koha/opac-detail.pl?biblionumber={}"


def tiet_rows(url=OPAC):
    def row(bib, title, author, co, year, subj, mtype="Text Book", call="005.74 PO"):
        # Excel hands whole numbers over as floats (794.0)
        return [None, call, title, author, co, "ENGLISH", "Wiley India", "New Delhi", year, "2nd ed.", "xxviii,571p.",
                9788126518449.0, subj, mtype, float(bib), url.format(int(bib))]
    return [
        row(794, "Data Warehousing Fundamentals", "Ponniah, Paulraj", "Chan, E.C.", 2010, "Data Warehousing; Database management"),
        row(794, "Data Warehousing Fundamentals", "Ponniah, Paulraj", "Chan, E.C.", 2010, "Data Warehousing; Database management"),  # 2nd copy
        row(1220, "Fundamentals of Computer Algorithms", "Horowitz, Ellis", None, 2008, "Algorithms; Computer programming"),
        row(4570, "Objects, Abstraction and Data Structures Using Java", "Koffman, Elliot", "Wolfgang, Paul", 2005,
            "JAVA (Computer program language); Data structures (Computer science)", "General Book"),
        row(9324, "Core Java Volume 1", "Horstmann, Cay", None, 2012, "JAVA (Computer program language) -- Handbooks", "General Book"),
        row(9325, "Learning Java", "Niemeyer, Patrick", None, 2016, "JAVA (Computer program language)", "General Book"),
        row(9326, "Data Structures in Java", "Weiss, Mark", None, 2014, "Data structures (Computer science); JAVA (Computer program language)"),
        row(11889, "AutoCAD Basics", "Jones, Fred", "Martin, Lee", 1990, "Auto Cad; Engineering drawing", "General Book"),
        row(11890, "Engineering Drawing", "Bhatt, N.D.", None, 2001, "Engineering drawing", "Text Book"),
        [None, "x", None, "No Title Author", None, "ENGLISH", "", "", 2001, "", "", None, "Physics", "Text Book", 99999.0, OPAC.format(99999)],
    ]


def test_real_tiet_excel_layout_end_to_end(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title = "Catalogue"
    ws.append(TIET_HEADER)
    for r in tiet_rows():
        ws.append(r)
    src = tmp_path / "tiet.xlsx"; wb.save(src)
    out = tmp_path / "catalogue.json"

    peek = run("scripts.import_library_data", str(src), "--show-columns")
    assert peek.returncode == 0, peek.stderr
    for expected in ["title         <- Title", "author        <- Author", "coauthors     <- Co-Author(s)",
                     "year          <- Year", "type          <- Material Type", "subjects      <- Subjects",
                     "call_number   <- Call Number", "biblionumber  <- Biblio ID", "isbn          <- ISBN/ISSN",
                     "catalogue_url <- Catalogue Link", "id            <- (not found)"]:
        assert expected in peek.stdout, expected + "\n" + peek.stdout

    imp = run("scripts.import_library_data", str(src), "--out", str(out), "--label", "TIET TEST")
    assert imp.returncode == 0, imp.stdout + imp.stderr
    assert "repeated record ids" in imp.stdout and "stored once" in imp.stdout
    data = json.loads(out.read_text(encoding="utf-8"))
    recs = {r["id"]: r for r in data["resources"]}
    assert sorted(recs) == ["11889", "11890", "1220", "4570", "794", "9324", "9325", "9326"]   # copy + no-title row dropped, ids are "794" not "794.0"
    assert recs["794"]["author"] == "Ponniah, Paulraj; Chan, E.C."                          # co-author merged
    assert recs["1220"]["author"] == "Horowitz, Ellis"
    assert recs["794"]["type"] == "Text Book" and recs["4570"]["type"] == "General Book"
    assert recs["794"]["year"] == 2010 and recs["794"]["biblionumber"] == "794"
    assert recs["794"]["subjects"] == ["Data Warehousing", "Database management"]
    assert recs["794"]["call_number"] == "005.74 PO"
    assert recs["794"]["publisher"] == "Wiley India" and recs["794"]["edition"] == "2nd ed."
    assert not any(k in recs["794"] for k in ("place", "language", "pages", "isbn"))      # opt-in only
    assert data["_opac_url_template"] == OPAC.format("{biblionumber}")                      # link pattern stored ONCE
    assert not any("catalogue_url" in r for r in data["resources"])

    vocab = json.loads((tmp_path / "vocabulary.json").read_text(encoding="utf-8"))["terms"]
    assert "java" in vocab and "data structures" in vocab                                  # qualifiers/subdivisions stripped
    assert not any("(" in t or "--" in t for t in vocab)

    code = textwrap.dedent("""
        from fastapi.testclient import TestClient
        from backend.main import app
        r = TestClient(app).post("/api/search", json={"query": "java programming"}).json()
        x = r["results"][0]
        print(r["identified_concepts"], "|", x["catalogue_url"], "|", x["call_number"], "|", x["publisher"], "|", x["edition"], "|", x["author"])
    """)
    env = dict(os.environ, ARN_CATALOGUE_PATH=str(out), ARN_VOCABULARY_PATH=str(tmp_path / "vocabulary.json"),
               ARN_SQLITE_PATH=str(tmp_path / "a.db"))
    env.pop("ARN_OPAC_URL_TEMPLATE", None)
    served = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, env=env)
    assert served.returncode == 0, served.stderr
    assert "'java'" in served.stdout
    assert "https://library.thapar.edu/cgi-bin/koha/opac-detail.pl?biblionumber=" in served.stdout
    assert "Wiley India" in served.stdout and "2nd ed." in served.stdout                  # reach the API for the result card


def test_catalogue_links_without_a_common_pattern_are_kept_per_record(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(TIET_HEADER)
    ws.append([None, "1", "Book One", "A", None, "EN", "", "", 2000, "", "", None, "Topic X", "Text Book", 1.0, "https://a.example/rec/1"])
    ws.append([None, "2", "Book Two", "B", None, "EN", "", "", 2001, "", "", None, "Topic X", "Text Book", 2.0, "https://b.example/other?id=2"])
    src, out = tmp_path / "x.xlsx", tmp_path / "c.json"; wb.save(src)
    r = run("scripts.import_library_data", str(src), "--out", str(out), "--no-vocab")
    assert r.returncode == 0, r.stdout + r.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "_opac_url_template" not in data
    assert [x["catalogue_url"] for x in data["resources"]] == ["https://a.example/rec/1", "https://b.example/other?id=2"]


def test_csv_with_line_breaks_bom_semicolons_and_windows_encoding(tmp_path):
    """Real exports: UTF-8 BOM or cp1252, ';' or ',' delimiters, and line breaks INSIDE quoted cells."""
    body = ('Biblio ID;Title;Author;Subjects;Year\r\n'
            '1;"Data\r\nStructures";"\u00c7engel, Y.";"Algorithms\r\nJava (Computer program language)";2010\r\n'
            '2;"Plain Book";"Smith, J.";"Algorithms; Databases";2011\r\n'
            '3;"Third Book";"Roy, K.";"Databases";2012\r\n')
    src, out = tmp_path / "x.csv", tmp_path / "c.json"
    src.write_bytes(body.encode("cp1252"))
    r = run("scripts.import_library_data", str(src), "--out", str(out), "--no-vocab")
    assert r.returncode == 0, r.stdout + r.stderr
    recs = {x["id"]: x for x in json.loads(out.read_text(encoding="utf-8"))["resources"]}
    assert recs["1"]["title"] == "Data Structures"                       # NOT "DataStructures"
    assert recs["1"]["author"].startswith("\u00c7engel")                 # cp1252 decoded
    assert recs["1"]["subjects"] == ["Algorithms", "Java (Computer program language)"]   # line break separates subjects
    assert recs["2"]["subjects"] == ["Algorithms", "Databases"]

    src2 = tmp_path / "y.csv"
    src2.write_bytes(b"\xef\xbb\xbf" + body.replace(";", ",").replace('"Algorithms\r\nJava', '"Algorithms\r\nJava').encode("utf-8"))
    r2 = run("scripts.import_library_data", str(src2), "--out", str(tmp_path / "d.json"), "--no-vocab")
    assert r2.returncode == 0, r2.stdout + r2.stderr


def test_undetectable_delimiter_falls_back_to_comma(tmp_path):
    src = tmp_path / "z.csv"
    src.write_text("Title\nOnly One Column Book\nAnother\n", encoding="utf-8")        # nothing for the sniffer to detect
    r = run("scripts.import_library_data", str(src), "--out", str(tmp_path / "o.json"), "--no-vocab")
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))["resources"]) == 2


def test_extra_fields_are_stored_only_when_asked(tmp_path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.append(TIET_HEADER)
    for r in tiet_rows()[:3]:
        ws.append(r)
    src, out = tmp_path / "x.xlsx", tmp_path / "c.json"; wb.save(src)
    r = run("scripts.import_library_data", str(src), "--out", str(out), "--no-vocab", "--extra-fields", "place,language,pages,isbn")
    assert r.returncode == 0, r.stdout + r.stderr
    rec = json.loads(out.read_text(encoding="utf-8"))["resources"][0]
    assert rec["place"] == "New Delhi" and rec["language"] == "ENGLISH" and rec["pages"] == "xxviii,571p."
    assert rec["isbn"] == "9788126518449"                                              # float 9788126518449.0 -> clean digits
    bad = run("scripts.import_library_data", str(src), "--out", str(out), "--no-vocab", "--extra-fields", "colour")
    assert bad.returncode != 0 and "unknown" in (bad.stdout + bad.stderr)
