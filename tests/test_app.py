"""Run with:  pytest -q"""
import os
import tempfile

# must be set BEFORE the app is imported
_tmp = tempfile.mkdtemp()
os.environ["ARN_SQLITE_PATH"] = os.path.join(_tmp, "test.db")
os.environ["ADMIN_PASSWORD"] = "secret123"
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from backend import analytics  # noqa: E402
from backend.main import RESOURCES, app  # noqa: E402

client = TestClient(app)
# a query that is guaranteed to match something in WHATEVER catalogue is loaded
KNOWN_QUERY = RESOURCES[0]["title"]
VID_A = "aaaaaaaaaaaaaaaa1111"
VID_B = "bbbbbbbbbbbbbbbb2222"
SID_A = "sessionaaaaaaaa1111"
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"}


def hdr(vid=VID_A, sid=SID_A, ua=BROWSER["User-Agent"]):
    return {"X-Visitor-Id": vid, "X-Session-Id": sid, "User-Agent": ua}


def test_homepage_is_served_and_has_no_localhost():
    r = client.get("/")
    assert r.status_code == 200
    assert "Academic Research Navigator" in r.text
    assert "127.0.0.1" not in r.text


def test_search_returns_relative_resource_url():
    r = client.post("/api/search", json={"query": KNOWN_QUERY}, headers=hdr())
    assert r.status_code == 200
    results = r.json()["results"]
    assert results
    assert results[0]["resource_url"].startswith("/api/resource/")


def test_search_and_track_are_counted_per_unique_visitor():
    client.post("/api/search", json={"query": "mathematics"}, headers=hdr(VID_A))
    client.post("/api/search", json={"query": "mathematics"}, headers=hdr(VID_B, "sessionbbbbbbbb2222"))
    client.post("/api/track", json={"event": "visit", "visitor_id": VID_A, "session_id": SID_A},
                headers=BROWSER)
    stats = analytics.compute_stats()
    assert stats["unique_visitors_total"] >= 2
    assert stats["searches"] >= 2


def test_requests_without_anonymous_id_or_from_bots_are_not_logged():
    before = analytics.compute_stats()["total_events"]
    client.post("/api/search", json={"query": "history"})  # no ids at all
    client.post("/api/search", json={"query": "history"}, headers=hdr(ua="Googlebot/2.1"))
    client.post("/api/search", json={"query": "history"}, headers=hdr("short"))  # invalid id
    assert analytics.compute_stats()["total_events"] == before


def test_track_rejects_unknown_events():
    r = client.post("/api/track", json={"event": "hack", "visitor_id": VID_A}, headers=BROWSER)
    assert r.status_code == 400


def test_feedback_and_clicks_show_up_in_stats():
    client.post("/api/track", json={"event": "click_result", "visitor_id": VID_A,
                                    "session_id": SID_A, "target": "9780439554930"}, headers=BROWSER)
    client.post("/api/track", json={"event": "feedback_up", "visitor_id": VID_A,
                                    "session_id": SID_A}, headers=BROWSER)
    s = analytics.compute_stats()
    assert s["feedback_up"] >= 1
    assert s["search_sessions_with_click_pct"] > 0


def test_empty_query_still_rejected():
    assert client.post("/api/search", json={"query": "  "}, headers=hdr()).status_code == 400


def test_admin_requires_correct_password():
    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401
    ok = client.get("/admin", auth=("admin", "secret123"))
    assert ok.status_code == 200 and "usage dashboard" in ok.text
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/admin/export.csv").status_code == 401


def test_admin_disabled_when_no_password_configured(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD")
    assert client.get("/admin", auth=("admin", "x")).status_code == 503


def test_csv_export_neutralises_spreadsheet_formulas():
    client.post("/api/search", json={"query": "=cmd|' /C calc'!A0"}, headers=hdr())
    csv_text = client.get("/admin/export.csv", auth=("admin", "secret123")).text
    assert "'=cmd" in csv_text


def test_dashboard_escapes_html_in_queries():
    client.post("/api/search", json={"query": "<script>alert(1)</script>"}, headers=hdr())
    page = client.get("/admin", auth=("admin", "secret123")).text
    assert "<script>alert(1)</script>" not in page


def test_rate_limiter_blocks_after_limit():
    rl = analytics.RateLimiter(max_calls=3, window_seconds=60)
    assert [rl.allow("ip") for _ in range(5)] == [True, True, True, False, False]
    assert rl.allow("other-ip")


def test_resource_page_shows_data_source():
    rid = next(iter(client.post("/api/search", json={"query": KNOWN_QUERY}, headers=hdr()).json()["results"]))["id"]
    r = client.get(f"/api/resource/{rid}/view")
    assert r.status_code == 200 and "Data source" in r.text


def test_health_reports_memory_and_stats_storage():
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["stats_storage"] == "sqlite"       # tests run on the local file
    assert "memory_mb" in h and "memory_peak_mb" in h                   # None on Windows/Mac, numbers on Linux
    if os.path.exists("/proc/self/status"):
        assert h["memory_mb"] > 0 and h["memory_peak_mb"] >= h["memory_mb"]


def test_dashboard_says_where_stats_are_stored():
    page = client.get("/admin", auth=("admin", "secret123")).text
    assert "Stats stored in" in page and "SQLite" in page


def test_postgres_url_is_detected_without_connecting(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@ep-x.neon.tech/db?sslmode=require")
    assert analytics.storage_backend() == "postgresql"
    assert analytics._database_url().startswith("postgresql+psycopg://")


def test_health_and_home_accept_head_requests_for_uptime_monitors():
    assert client.head("/api/health").status_code == 200
    assert client.head("/").status_code == 200
    assert client.get("/api/health").status_code == 200
