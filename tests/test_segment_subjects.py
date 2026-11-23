"""Splitting subject cells whose headings were joined with plain spaces (as in the TIET export)."""
import csv
import json
import os
import random
import subprocess
import sys

from scripts.build_vocabulary import clean_term
from scripts.segment_subjects import SubjectSegmenter, looks_space_joined

ROOT = os.path.join(os.path.dirname(__file__), "..")


def library_like_cells():
    cells = []
    def add(heading, n):
        cells.extend([heading] * n)
    for h, n in [("Computer programming", 30), ("Electronic digital computer-programming", 12), ("Integrated Circuits", 25),
                 ("Metal Oxide Semiconductors Complementary", 9), ("Physics", 80), ("Physics, vibration and waves", 14),
                 ("Concrete Technology", 20), ("Concrete Construction", 10), ("Concrete", 40), ("Civil Engineering", 50),
                 ("Concrete Structure", 8), ("Load of Structure", 6), ("Reinforced Concrete", 15), ("Strength of Concrete", 7),
                 ("Electronic Data Processing-Distributed Processing", 11), ("Computer science", 200)]:
        add(h, n)
    add("Computer programming Electronic digital computer-programming", 15)        # a cataloguer's habit, repeated a lot
    add("Integrated Circuits Metal Oxide Semiconductors Complementary", 4)
    add("Physics Physics, vibration and waves", 6)
    add("Concrete Technology Concrete Construction Concrete", 3)
    add("Civil Engineering Concrete Structure Load of Structure Reinforced Concrete Strength of Concrete", 2)
    return cells


def test_cells_from_the_real_export_are_split_into_their_headings():
    seg = SubjectSegmenter.learn(library_like_cells())
    assert seg.split("Computer programming Electronic digital computer-programming") == \
        ["Computer programming", "Electronic digital computer-programming"]
    assert seg.split("Integrated Circuits Metal Oxide Semiconductors Complementary") == \
        ["Integrated Circuits", "Metal Oxide Semiconductors Complementary"]
    assert seg.split("Physics Physics, vibration and waves") == ["Physics", "Physics, vibration and waves"]
    assert seg.split("Concrete Technology Concrete Construction Concrete") == \
        ["Concrete Technology", "Concrete Construction", "Concrete"]
    assert seg.split("Civil Engineering Concrete Structure Load of Structure Reinforced Concrete Strength of Concrete") == \
        ["Civil Engineering", "Concrete Structure", "Load of Structure", "Reinforced Concrete", "Strength of Concrete"]


def test_single_headings_with_subdivisions_are_left_whole():
    seg = SubjectSegmenter.learn(library_like_cells())
    for cell in ["Electronic Data Processing-Distributed Processing", "Computer science",
                 "JAVA (Computer program language) - data structures",
                 "Physics and Technology - Congresses, conferences, etc."]:           # starts with the known heading "Physics"
        assert seg.split(cell) == [cell], cell


def test_a_real_compound_is_not_broken_just_because_its_words_are_headings():
    cells = ["Data structures"] * 120 + ["Data"] * 3 + ["Structures"] * 3 + ["Algorithms"] * 40
    seg = SubjectSegmenter.learn(cells)
    assert ("data", "structures") in seg.headings
    assert seg.split("Algorithms Data structures") == ["Algorithms", "Data structures"]


def test_unknown_words_are_kept_not_dropped():
    seg = SubjectSegmenter.learn(["Physics"] * 5)
    assert seg.split("Physics Zymurgy Brewing") == ["Physics", "Zymurgy Brewing"]
    assert seg.split("") == [] and seg.split("Solo") == ["Solo"]


def test_accuracy_on_synthetic_data_with_known_answers():
    rng = random.Random(1)
    words = [w.title() for w in ("".join(rng.choices("abcdefghijklmnopqrstuvwxyz", k=rng.randint(4, 9))) for _ in range(300))]
    heads = set(words[:120])
    while len(heads) < 700:
        heads.add(" ".join(rng.choices(words, k=rng.choice([2, 2, 3, 3, 4, 5]))))
    heads = sorted(heads)
    weights = [1 / (i + 1) ** 0.9 for i in range(len(heads))]
    rng.shuffle(heads)
    records = []
    for _ in range(40000):
        k = 1 if rng.random() < 0.30 else rng.choice([2, 2, 3, 3, 4])
        chosen = []
        while len(chosen) < k:
            h = rng.choices(heads, weights)[0]
            if h not in chosen:
                chosen.append(h)
        records.append(chosen)
    cells = [" ".join(r) for r in records]
    seg = SubjectSegmenter.learn(cells)
    exact = sum(seg.split(c) == r for c, r in zip(cells, records)) / len(cells)
    assert exact > 0.90, exact
    share, _ = seg.quality(cells)
    assert share > 0.90


def test_space_joined_detection():
    assert looks_space_joined(["Concrete Technology Concrete Construction Concrete"] * 10 + ["Physics"] * 5)
    assert not looks_space_joined(["Algorithms", "Databases", "Machine learning", "Physics"] * 10)


def test_spaced_hyphen_subdivisions_are_dropped_for_concepts():
    assert clean_term("JAVA (Computer program language) - data structures") == "java"
    assert clean_term("Physics and Technology - Congresses, conferences, etc.") == "physics and technology"
    assert clean_term("Electronic digital computer-programming") == "electronic digital computer-programming"


def test_importer_end_to_end_with_space_joined_subjects(tmp_path):
    rows = []
    for i in range(1, 61):
        rows.append((i, f"Book {i}", ["Physics"]))
    for i in range(61, 101):
        rows.append((i, f"Book {i}", ["Concrete Technology"]))
    for i in range(101, 131):
        rows.append((i, f"Book {i}", ["Concrete"]))
    for i in range(131, 191):
        rows.append((i, f"Book {i}", ["Physics", "Concrete Technology", "Concrete"]))
    src, out = tmp_path / "x.csv", tmp_path / "c.json"
    with open(src, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Biblio ID", "Title", "Subjects"])
        for i, t, subs in rows:
            w.writerow([i, t, " ".join(subs)])                      # joined by spaces, like the real export

    def run(*extra):
        return subprocess.run([sys.executable, "-m", "scripts.import_library_data", str(src), "--out", str(out), *extra],
                              cwd=ROOT, capture_output=True, text=True)

    hint = run("--no-vocab")
    assert hint.returncode == 0
    assert "Add --segment-subjects" in hint.stdout                     # forgetting the flag is pointed out
    assert json.loads(out.read_text())["resources"][-1]["subjects"] == ["Physics Concrete Technology Concrete"]
    first = run("--no-vocab", "--segment-subjects")
    assert first.returncode == 0, first.stdout + first.stderr
    assert "Subject splitter" in first.stdout and "split cleanly" in first.stdout
    recs = {r["id"]: r for r in json.loads(out.read_text(encoding="utf-8"))["resources"]}
    assert recs["131"]["subjects"] == ["Physics", "Concrete Technology", "Concrete"]
    assert recs["1"]["subjects"] == ["Physics"]

    full = run("--segment-subjects")                                  # also builds the concept vocabulary
    assert full.returncode == 0, full.stdout + full.stderr
    terms = json.loads((tmp_path / "vocabulary.json").read_text(encoding="utf-8"))["terms"]
    assert {"physics", "concrete technology", "concrete"} <= set(terms)


def test_path_display_survives_a_different_drive_on_windows(monkeypatch, tmp_path):
    """On Windows os.path.relpath raises ValueError for a file on another drive (seen: C: temp vs E: project)."""
    from scripts import import_library_data as imp

    def other_drive(path, start=None):
        raise ValueError("path is on mount 'C:', start on mount 'E:'")
    monkeypatch.setattr(imp.os.path, "relpath", other_drive)
    target = tmp_path / "catalogue_kaggle_backup.json"
    assert imp._shown(str(target)) == os.path.abspath(str(target))


def test_importing_over_an_existing_file_makes_a_backup_and_reports_it(tmp_path):
    src, out = tmp_path / "x.csv", tmp_path / "c.json"
    src.write_text("Biblio ID,Title\n1,One\n2,Two\n", encoding="utf-8")
    out.write_text('{"resources": []}', encoding="utf-8")                   # something already there
    r = subprocess.run([sys.executable, "-m", "scripts.import_library_data", str(src), "--out", str(out), "--no-vocab"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Backed up the previous catalogue" in r.stdout
    assert (tmp_path / "catalogue_kaggle_backup.json").exists()
    assert len(json.loads(out.read_text(encoding="utf-8"))["resources"]) == 2
