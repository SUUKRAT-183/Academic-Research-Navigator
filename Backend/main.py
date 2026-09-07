"""
Academic Research Navigator - baseline prototype API.

Maps to requirements doc (ARN_Requirements_v1.md):
  POST /api/search        -> FR-1, FR-2, FR-3, FR-4, FR-8, FR-9 (query -> ranked, explained results + concepts)
  GET  /api/concept/{c}    -> FR-5, FR-6 (explore a related concept)
  GET  /api/resource/{id}  -> FR-7 (resource detail view)

Run with:  uvicorn backend.main:app --reload --app-dir /home/claude/arn_prototype
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import html
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data_loader import load_catalogue
from .retrieval import Retriever
from .relationships import RelationshipIndex
from .concepts import extract_concepts
from .explain import explain_relevance

app = FastAPI(title="Academic Research Navigator - Prototype API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- load data + build indexes once at startup ----
RESOURCES, SOURCE_LABEL = load_catalogue()
RETRIEVER = Retriever(RESOURCES)
REL_INDEX = RelationshipIndex(RESOURCES)
RESOURCES_BY_ID = {r["id"]: r for r in RESOURCES}


class SearchRequest(BaseModel):
    query: str


def _serialize_result(item):
    resource = item["resource"]
    return {
        "id": resource["id"],
        "title": resource["title"],
        "author": resource["author"],
        "year": resource["year"],
        "type": resource["type"],
        "subjects": resource["subjects"],
        "abstract": resource.get("abstract", ""),
        # Real call numbers require the confirmed library metadata export;
        # None here renders as "pending library data" in the frontend.
        "call_number": resource.get("call_number"),
        # Once real biblionumbers are available from the library export,
        # this becomes a working link to the actual Koha OPAC record.
        "catalogue_url": f"https://library.thapar.edu/cgi-bin/koha/opac-detail.pl?biblionumber={resource.get('biblionumber', '')}"
            if resource.get("biblionumber") else None,
        "resource_url": f"http://127.0.0.1:8000/api/resource/{resource['id']}/view",
        "score": item["score"],
        "matched_concepts": item["matched_concepts"],
        "explanation": explain_relevance(resource, item["matched_concepts"]),
        "source_note": SOURCE_LABEL,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "resource_count": len(RESOURCES), "data_source": SOURCE_LABEL}


@app.post("/api/search")
def search(req: SearchRequest):
    """FR-1 (query input) + FR-2 (concept ID) + FR-3/FR-4 (retrieval + ranking)
    + FR-8 (explanation), all in one response so the frontend can render
    the full discovery view in a single call."""
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    concepts = extract_concepts(req.query)
    raw_results = RETRIEVER.search(req.query, concepts, top_k=10)
    related_concepts = REL_INDEX.related_concepts_for_many(concepts, top_k=8)

    return {
        "query": req.query,
        "identified_concepts": concepts,
        "related_concepts": related_concepts,
        "results": [_serialize_result(r) for r in raw_results],
        "result_count": len(raw_results),
    }


@app.get("/api/concept/{concept_name}")
def explore_concept(concept_name: str):
    """FR-6: click a related concept -> new discovery view scoped to it."""
    concept_name = concept_name.lower().strip()
    resources = REL_INDEX.resources_for_concept(concept_name)

    if not resources:
        raise HTTPException(status_code=404, detail=f"No resources found for concept '{concept_name}'.")

    related_concepts = REL_INDEX.related_concepts(concept_name, top_k=8)

    results = []
    for r in resources:
        results.append({
            "id": r["id"], "title": r["title"], "author": r["author"],
            "year": r["year"], "type": r["type"], "subjects": r["subjects"],
            "explanation": f"Tagged with the concept '{concept_name}'.",
        })

    return {
        "concept": concept_name,
        "related_concepts": related_concepts,
        "results": results,
        "result_count": len(results),
    }


@app.get("/api/resource/{resource_id}")
def resource_detail(resource_id: str):
    """FR-7: resource detail view. FR-9: source_url stands in for the
    real catalogue link-out once TIET's catalogue URL pattern is known."""
    resource = RESOURCES_BY_ID.get(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found.")

    return {
        **{k: v for k, v in resource.items() if not k.startswith("_")},
        "source_url_placeholder": f"https://library.thapar.edu/catalogue/{resource_id}",
        "source_note": SOURCE_LABEL,
    }

@app.get("/api/resource/{resource_id}/view", response_class=HTMLResponse)
def resource_view(resource_id: str):
    resource = RESOURCES_BY_ID.get(resource_id)

    if not resource:
        raise HTTPException(
            status_code=404,
            detail="Resource not found."
        )

    title = html.escape(str(resource.get("title", "")))
    author = html.escape(str(resource.get("author", "")))
    year = html.escape(str(resource.get("year", "")))
    resource_type = html.escape(str(resource.get("type", "")))
    abstract = html.escape(str(resource.get("abstract", "")))

    subjects = resource.get("subjects", [])

    subject_html = "".join(
        f"<span class='tag'>{html.escape(str(subject))}</span>"
        for subject in subjects
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>

        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #f5f5f5;
                margin: 0;
                padding: 40px;
                color: #222;
            }}

            .container {{
                max-width: 900px;
                margin: auto;
                background: white;
                padding: 40px;
                border-radius: 14px;
                box-shadow: 0 8px 30px rgba(0,0,0,0.08);
            }}

            .badge {{
                display: inline-block;
                padding: 6px 10px;
                border-radius: 20px;
                background: #eee;
                margin-right: 8px;
                font-size: 13px;
            }}

            .tag {{
                display: inline-block;
                padding: 6px 10px;
                margin: 5px 5px 0 0;
                border-radius: 16px;
                background: #eef2ff;
                font-size: 13px;
            }}

            h1 {{
                margin-bottom: 10px;
            }}

            .meta {{
                color: #666;
                margin-bottom: 25px;
            }}

            .section {{
                margin-top: 30px;
            }}

            .prototype {{
                margin-top: 35px;
                padding: 15px;
                background: #fff3cd;
                border-radius: 8px;
                font-size: 14px;
            }}
        </style>
    </head>

    <body>
        <div class="container">

            <span class="badge">Academic Research Navigator</span>
            <span class="badge">{resource_type}</span>

            <h1>{title}</h1>

            <div class="meta">
                {author} · {year}
            </div>

            <div class="section">
                <h2>Abstract / Description</h2>
                <p>
                    {abstract if abstract else "No abstract available."}
                </p>
            </div>

            <div class="section">
                <h2>Subjects</h2>
                <div>
                    {subject_html if subject_html else "No subjects available."}
                </div>
            </div>

            <div class="prototype">
                <strong>Prototype Notice:</strong><br>
                This is a demonstration resource page generated from
                synthetic prototype data. It is not a real TIET catalogue
                record or real library document.
            </div>

        </div>
    </body>
    </html>
    """

@app.get("/api/concepts")
def list_all_concepts():
    """Utility endpoint - not a formal requirement, useful for debugging/demo."""
    return {"concepts": sorted(REL_INDEX.concept_to_resources.keys())}
