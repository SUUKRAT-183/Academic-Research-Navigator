"""
Academic Research Navigator - API + website.

Maps to requirements doc (ARN_Requirements_v1.md):
  POST /api/search        -> FR-1, FR-2, FR-3, FR-4, FR-8, FR-9 (query -> ranked, explained results + concepts)
  GET  /api/concept/{c}    -> FR-5, FR-6 (explore a related concept)
  GET  /api/resource/{id}  -> FR-7 (resource detail view)

Also serves the website itself at "/" so the whole thing deploys as ONE service,
records anonymous usage events (see analytics.py) and exposes a password-protected
dashboard at /admin.

Run locally with:  uvicorn backend.main:app --reload
then open http://127.0.0.1:8000
"""

import html
import os
import secrets
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from . import analytics
from .concepts import extract_concepts
from .data_loader import load_catalogue
from .explain import explain_relevance
from .relationships import RelationshipIndex
from .retrieval import Retriever

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# Link to the real library record. Needs a "biblionumber" per resource in the data.
# Change it with the ARN_OPAC_URL_TEMPLATE env var if the library's URL differs.
OPAC_URL_TEMPLATE = os.environ.get(
    "ARN_OPAC_URL_TEMPLATE",
    "https://library.thapar.edu/cgi-bin/koha/opac-detail.pl?biblionumber={biblionumber}",
)

app = FastAPI(title="Academic Research Navigator")

# The website is served from the same origin as the API, so CORS is only needed
# if you host the frontend somewhere else. In production you can restrict it:
#   ARN_ALLOWED_ORIGINS="https://arn.example.edu"
_origins = [o.strip() for o in os.environ.get("ARN_ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- load data + build indexes once at startup ----
RESOURCES, SOURCE_LABEL = load_catalogue()
RETRIEVER = Retriever(RESOURCES)
REL_INDEX = RelationshipIndex(RESOURCES)
RESOURCES_BY_ID = {r["id"]: r for r in RESOURCES}

analytics.init_db()

# ---- basic abuse protection (per client IP, in memory) ----
_search_limiter = analytics.RateLimiter(max_calls=40, window_seconds=60)
_track_limiter = analytics.RateLimiter(max_calls=120, window_seconds=60)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit_search(request: Request):
    if not _search_limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many searches. Please wait a minute.")


def limit_track(request: Request):
    if not _track_limiter.allow(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests.")


# ---- admin auth (HTTP Basic; password comes from the ADMIN_PASSWORD env var) ----
_basic = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(_basic)):
    expected = os.environ.get("ADMIN_PASSWORD")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin is disabled. Set the ADMIN_PASSWORD environment variable.")
    if not secrets.compare_digest(credentials.password.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Wrong password.",
                            headers={"WWW-Authenticate": "Basic"})


def _ids(request: Request):
    """Anonymous ids sent by the browser as headers."""
    return (request.headers.get("x-visitor-id"), request.headers.get("x-session-id"),
            request.headers.get("user-agent"))


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


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
        "catalogue_url": OPAC_URL_TEMPLATE.format(biblionumber=resource["biblionumber"])
            if resource.get("biblionumber") else None,
        "resource_url": f"/api/resource/{resource['id']}/view",
        "score": item["score"],
        "matched_concepts": item["matched_concepts"],
        "explanation": explain_relevance(resource, item["matched_concepts"]),
        "source_note": SOURCE_LABEL,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "resource_count": len(RESOURCES), "data_source": SOURCE_LABEL}


@app.post("/api/search", dependencies=[Depends(limit_search)])
def search(req: SearchRequest, request: Request, background: BackgroundTasks):
    """FR-1 (query input) + FR-2 (concept ID) + FR-3/FR-4 (retrieval + ranking)
    + FR-8 (explanation), all in one response so the frontend can render
    the full discovery view in a single call."""
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    concepts = extract_concepts(req.query)
    raw_results = RETRIEVER.search(req.query, concepts, top_k=10)
    related_concepts = REL_INDEX.related_concepts_for_many(concepts, top_k=8)

    vid, sid, ua = _ids(request)
    background.add_task(analytics.log_event, "search", vid, sid, query=req.query,
                        result_count=len(raw_results), user_agent=ua)

    return {
        "query": req.query,
        "identified_concepts": concepts,
        "related_concepts": related_concepts,
        "results": [_serialize_result(r) for r in raw_results],
        "result_count": len(raw_results),
    }


@app.get("/api/concept/{concept_name}")
def explore_concept(concept_name: str, request: Request, background: BackgroundTasks):
    """FR-6: click a related concept -> new discovery view scoped to it."""
    concept_name = concept_name.lower().strip()
    resources = REL_INDEX.resources_for_concept(concept_name)

    if not resources:
        raise HTTPException(status_code=404, detail=f"No resources found for concept '{concept_name}'.")

    related_concepts = REL_INDEX.related_concepts(concept_name, top_k=8)

    vid, sid, ua = _ids(request)
    background.add_task(analytics.log_event, "explore_concept", vid, sid,
                        target=concept_name, result_count=len(resources), user_agent=ua)

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
                <strong>Data source:</strong> {html.escape(SOURCE_LABEL)}
            </div>

        </div>
    </body>
    </html>
    """

@app.get("/api/concepts")
def list_all_concepts():
    """Utility endpoint - not a formal requirement, useful for debugging/demo."""
    return {"concepts": sorted(REL_INDEX.concept_to_resources.keys())}


# =====================================================================
# Usage tracking + admin dashboard
# =====================================================================

class TrackEvent(BaseModel):
    event: str
    visitor_id: str
    session_id: str | None = None
    query: str | None = None
    target: str | None = None


@app.post("/api/track", status_code=204, dependencies=[Depends(limit_track)])
def track(ev: TrackEvent, request: Request, background: BackgroundTasks):
    """Browser-side events (page visit, clicks, thumbs up/down). Search and
    concept events are logged server-side inside their own endpoints."""
    if ev.event not in analytics.ALLOWED_CLIENT_EVENTS:
        raise HTTPException(status_code=400, detail="Unknown event.")
    background.add_task(analytics.log_event, ev.event, ev.visitor_id, ev.session_id,
                        query=ev.query, target=ev.target,
                        user_agent=request.headers.get("user-agent"))
    return Response(status_code=204)


def _title_of(resource_id: str):
    r = RESOURCES_BY_ID.get(resource_id)
    return r["title"] if r else None


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False,
         dependencies=[Depends(require_admin)])
def admin_dashboard():
    stats = analytics.compute_stats(title_lookup=_title_of)
    return analytics.render_dashboard(stats, SOURCE_LABEL, len(RESOURCES))


@app.get("/api/admin/stats", include_in_schema=False, dependencies=[Depends(require_admin)])
def admin_stats_json():
    return analytics.compute_stats(title_lookup=_title_of)


@app.get("/admin/export.csv", include_in_schema=False, dependencies=[Depends(require_admin)])
def admin_export():
    return Response(analytics.export_csv(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=arn_events.csv"})
