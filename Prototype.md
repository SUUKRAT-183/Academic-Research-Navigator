# Academic Research Navigator — Baseline Prototype

This is a **working baseline prototype**, per your own project's Phase 3
("build simple keyword search first"). No LLM, no vector DB, no graph DB —
just enough to prove the core loop end-to-end and give you something real
to demo.

## What it actually does

`query -> identify concepts -> retrieve + rank resources -> explain relevance
-> explore related concepts` — all four MVP steps, wired together.

| Requirement (from ARN_Requirements_v1.md) | File that implements it |
|---|---|
| FR-1 query input, FR-10 refinement | `frontend/index.html` + `POST /api/search` |
| FR-2 concept identification | `backend/concepts.py` |
| FR-3, FR-4 retrieval + ranking | `backend/retrieval.py` (TF-IDF + concept boost) |
| FR-5, FR-6 relationships + explore | `backend/relationships.py` + `GET /api/concept/{name}` |
| FR-7 resource detail | `GET /api/resource/{id}` |
| FR-8 relevance explanation | `backend/explain.py` |
| FR-9 link to source | `source_url_placeholder` field (real URL pattern TBD once TIET catalogue link format is known) |
| NFR-7 data provenance | every response includes `source_note` flagging synthetic data |

## How to run it

```bash
cd arn_prototype
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Then open `frontend/index.html` directly in a browser (it calls the API at
`http://127.0.0.1:8000` by default — if you used a different port, edit the
`API` constant at the top of the `<script>` in index.html).

Try the API directly too:
```bash
curl -X POST http://127.0.0.1:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "fake news detection using graph neural networks"}'
```

## Swapping in real TIET data (when it arrives)

Only **one file** needs to change: `backend/data_loader.py`.

Right now it reads `data/sample_catalogue.json`. When you get the real
export:

1. Write a small loader for whatever format TIET gives you (CSV, Excel,
   another JSON shape) that produces the same fields per resource:
   `id, title, author, year, type, subjects, keywords, abstract`.
2. If some fields are missing (e.g. no abstract), that's fine — the system
   degrades gracefully, it just has less text to match against. Update
   `CONTROLLED_VOCABULARY` in `backend/concepts.py` to reflect real subject
   headings instead of the hand-picked demo list.
3. Nothing in `retrieval.py`, `relationships.py`, `explain.py`, or `main.py`
   needs to change — they only depend on the fields above, not on where the
   data came from.

This is deliberately how the requirements doc's NFR-4 (modularity) and
NFR-5 (resilience without external sources) are supposed to work in
practice — you're seeing them hold up right now, not just written down.

## What this prototype deliberately does NOT do (by design, not oversight)

- No LLM anywhere — concept ID is controlled-vocabulary + phrase matching,
  explanations are template text filled with real matched terms.
- No vector database / embeddings — ranking is TF-IDF, a classical
  approach you can measure against later if you want to test whether
  semantic retrieval actually helps (baseline doc explicitly says this
  needs to be proven, not assumed).
- No graph database — relationships are a co-occurrence count in a plain
  Python dict, per requirements doc's note that Neo4j isn't currently justified.
- No personalization, no login, no student data of any kind.

## Honest limitations of this specific prototype (things to fix before it's a "real" system)

- `CONTROLLED_VOCABULARY` in `concepts.py` is hand-typed for ~30 CS terms
  as a demo. A real version should be generated from the actual catalogue's
  subject/keyword fields so it scales automatically.
- The 30 sample records are synthetic — good enough to prove the pipeline
  works, **not** good enough to demonstrate real coverage or run a real
  evaluation. Don't use this dataset for your evaluation experiment.
- No tests yet (unit/integration) — NFR-6 in the requirements doc calls
  for this; add pytest tests per module before this goes further.
- No filtering (FR-11), no institutional repo / external source
  integration (FR-12/13) — intentionally left out, they're PROPOSED/OPTIONAL,
  not MVP-core.
