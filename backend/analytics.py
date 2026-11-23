"""
Anonymous usage analytics for ARN (the "footfall" requirement).

WHAT IS RECORDED (and nothing else):
  - a random anonymous visitor id (made by the browser, stored in localStorage)
  - a random session id (per browser tab session)
  - event type: visit / search / explore_concept / click_result /
    click_catalogue / click_link / feedback_up / feedback_down
  - the search query text, number of results, and the clicked resource id
  - device class (mobile / desktop) and a UTC timestamp

WHAT IS NOT RECORDED: names, emails, login info, IP addresses, user agents.

STORAGE: any database SQLAlchemy supports.
  - Local development: a SQLite file (data/analytics.db) is used automatically.
  - Production: set DATABASE_URL to a Postgres URL (e.g. a free Neon/Supabase
    database). This matters because free hosts wipe local files on redeploy.

Analytics must never break the search itself, so every write is wrapped in
try/except and failures are only printed to the server log.
"""

import csv
import html
import io
import os
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column, DateTime, Integer, MetaData, String, Table, Text, create_engine,
    insert, select,
)

# ---------------------------------------------------------------- settings

ALLOWED_CLIENT_EVENTS = {
    "visit", "click_result", "click_catalogue", "click_link",
    "feedback_up", "feedback_down",
}

CLICK_EVENTS = {"click_result", "click_catalogue", "click_link"}

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|headless|monitor|uptime|python-requests|curl", re.I)
_MOBILE_RE = re.compile(r"Mobi|Android|iPhone|iPad", re.I)

# Dashboard day-buckets are shown in this timezone. 330 = India (UTC+5:30).
TZ_OFFSET = timedelta(minutes=int(os.environ.get("ARN_TZ_OFFSET_MINUTES", "330")))

# ---------------------------------------------------------------- database


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        path = os.environ.get(
            "ARN_SQLITE_PATH",
            os.path.join(os.path.dirname(__file__), "..", "data", "analytics.db"),
        )
        return f"sqlite:///{os.path.abspath(path)}"
    # Neon/Heroku/Render give "postgres://" or "postgresql://"; SQLAlchemy
    # needs to be told to use the psycopg (v3) driver.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


_metadata = MetaData()
events = Table(
    "events", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", DateTime, nullable=False, index=True),      # naive UTC
    Column("event", String(32), nullable=False, index=True),
    Column("visitor_id", String(64), nullable=False, index=True),
    Column("session_id", String(64)),
    Column("query", Text),
    Column("result_count", Integer),
    Column("target", String(200)),                            # resource id / concept
    Column("device", String(10)),
)

_engine = None
_ready = False
_lock = threading.Lock()


def _get_engine():
    global _engine, _ready
    with _lock:
        if _engine is None:
            _engine = create_engine(_database_url(), pool_pre_ping=True)
        if not _ready:
            _metadata.create_all(_engine)
            _ready = True
    return _engine


def storage_backend() -> str:
    """"postgresql" when DATABASE_URL points at Postgres (e.g. Neon), otherwise "sqlite" (a local file)."""
    return "postgresql" if _database_url().startswith("postgresql") else "sqlite"


def init_db():
    """Call once at startup. Never raises - the site must work without analytics."""
    try:
        _get_engine()
        print("[analytics] database ready")
    except Exception as exc:  # noqa: BLE001
        print(f"[analytics] WARNING: database unavailable at startup: {exc}")


# ---------------------------------------------------------------- helpers


def is_bot(user_agent: str | None) -> bool:
    return bool(user_agent and _BOT_RE.search(user_agent))


def device_class(user_agent: str | None) -> str:
    return "mobile" if user_agent and _MOBILE_RE.search(user_agent) else "desktop"


def valid_id(value: str | None) -> bool:
    return bool(value and _ID_RE.match(value))


def log_event(event, visitor_id, session_id=None, query=None,
              result_count=None, target=None, user_agent=None):
    """Store one event. Silently skips bots and requests without a valid anonymous id."""
    if not valid_id(visitor_id) or is_bot(user_agent):
        return
    try:
        row = {
            "ts": datetime.now(timezone.utc).replace(tzinfo=None),
            "event": event,
            "visitor_id": visitor_id,
            "session_id": session_id if valid_id(session_id) else None,
            "query": (query or "").strip()[:300] or None,
            "result_count": result_count,
            "target": (target or "").strip()[:200] or None,
            "device": device_class(user_agent),
        }
        with _get_engine().begin() as conn:
            conn.execute(insert(events).values(**row))
    except Exception as exc:  # noqa: BLE001
        print(f"[analytics] could not log event: {exc}")


# ---------------------------------------------------------------- rate limit


class RateLimiter:
    """Tiny in-memory sliding-window limiter, keyed by client IP.
    Basic protection against someone spamming the search or inflating counts."""

    def __init__(self, max_calls: int, window_seconds: int = 60):
        self.max_calls = max_calls
        self.window = window_seconds
        self.hits = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self.hits[key] if now - t < self.window]
            if len(recent) >= self.max_calls:
                self.hits[key] = recent
                return False
            recent.append(now)
            self.hits[key] = recent
            if len(self.hits) > 20000:  # keep memory bounded
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] > self.window]:
                    del self.hits[k]
            return True


# ---------------------------------------------------------------- stats


def _load_rows(limit: int = 300_000):
    with _get_engine().connect() as conn:
        rows = conn.execute(
            select(events.c.ts, events.c.event, events.c.visitor_id,
                   events.c.session_id, events.c.query, events.c.result_count,
                   events.c.target, events.c.device)
            .order_by(events.c.ts.desc()).limit(limit)
        ).fetchall()
    return rows


def compute_stats(title_lookup=None, days: int = 14) -> dict:
    """Aggregate everything the dashboard shows. Done in Python (not SQL) so it
    behaves identically on SQLite and Postgres; fine for student-project volumes."""
    rows = _load_rows()
    local = lambda ts: ts + TZ_OFFSET  # noqa: E731
    now_local = local(datetime.now(timezone.utc).replace(tzinfo=None))
    today = now_local.date()

    visitors_all, visitor_days = set(), defaultdict(set)
    sessions = set()
    searches = zero_results = 0
    query_counter, zero_counter = Counter(), Counter()
    clicked = Counter()
    up = down = 0
    devices = defaultdict(set)
    per_day_visitors = defaultdict(set)
    per_day_searches = Counter()
    search_sessions, click_sessions = set(), set()
    recent = []

    for ts, event, vid, sid, query, rcount, target, device in rows:
        d = local(ts).date()
        visitors_all.add(vid)
        visitor_days[vid].add(d)
        per_day_visitors[d].add(vid)
        devices[device or "desktop"].add(vid)
        if sid:
            sessions.add(sid)
        if event == "search":
            searches += 1
            per_day_searches[d] += 1
            if sid:
                search_sessions.add(sid)
            q = (query or "").lower().strip()
            query_counter[q] += 1
            if not rcount:
                zero_results += 1
                zero_counter[q] += 1
            if len(recent) < 20:
                recent.append((local(ts).strftime("%d %b %H:%M"), query or "", rcount))
        elif event in CLICK_EVENTS:
            if sid:
                click_sessions.add(sid)
            if event == "click_result" and target:
                clicked[target] += 1
        elif event == "feedback_up":
            up += 1
        elif event == "feedback_down":
            down += 1

    def uniq_since(n_days):
        cutoff = today - timedelta(days=n_days - 1)
        return len({v for d, vs in per_day_visitors.items() if d >= cutoff for v in vs})

    daily = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        daily.append({"date": d.isoformat(), "visitors": len(per_day_visitors.get(d, ())),
                      "searches": per_day_searches.get(d, 0)})

    sessions_searched = len(search_sessions)
    sessions_clicked = len(search_sessions & click_sessions)
    title_lookup = title_lookup or (lambda _id: None)

    return {
        "unique_visitors_total": len(visitors_all),
        "unique_visitors_today": len(per_day_visitors.get(today, ())),
        "unique_visitors_7d": uniq_since(7),
        "unique_visitors_30d": uniq_since(30),
        "returning_visitors": sum(1 for ds in visitor_days.values() if len(ds) >= 2),
        "sessions": len(sessions),
        "searches": searches,
        "searches_per_visitor": round(searches / len(visitors_all), 2) if visitors_all else 0,
        "zero_result_searches": zero_results,
        "zero_result_pct": round(100 * zero_results / searches, 1) if searches else 0,
        "search_sessions_with_click_pct":
            round(100 * sessions_clicked / sessions_searched, 1) if sessions_searched else 0,
        "feedback_up": up, "feedback_down": down,
        "helpful_pct": round(100 * up / (up + down), 1) if (up + down) else None,
        "devices": {k: len(v) for k, v in devices.items()},
        "daily": daily,
        "top_queries": query_counter.most_common(15),
        "zero_result_queries": zero_counter.most_common(15),
        "top_clicked": [(rid, title_lookup(rid) or rid, n) for rid, n in clicked.most_common(10)],
        "recent_searches": recent,
        "total_events": len(rows),
    }


def export_csv() -> str:
    """Raw event log as CSV (for your report). Guards against spreadsheet formula injection."""
    def safe(v):
        s = "" if v is None else str(v)
        return "'" + s if s[:1] in ("=", "+", "-", "@") else s

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["time_ist", "event", "visitor_id", "session_id", "query",
                "result_count", "target", "device"])
    for ts, event, vid, sid, query, rc, target, device in reversed(_load_rows()):
        w.writerow([(ts + TZ_OFFSET).strftime("%Y-%m-%d %H:%M:%S"), event, vid,
                    sid or "", safe(query), rc if rc is not None else "", safe(target), device])
    return out.getvalue()


# ---------------------------------------------------------------- dashboard


def render_dashboard(s: dict, source_label: str, resource_count: int) -> str:
    esc = html.escape
    if storage_backend() == "postgresql":
        storage_note = "Stats stored in: <b>PostgreSQL</b> (safe across restarts and redeploys)"
    else:
        storage_note = ("Stats stored in: <b style='color:#c0392b'>a local SQLite file</b>. "
                        "Fine on your laptop, but on a free host this file is erased on every restart. "
                        "Set DATABASE_URL to a Postgres database.")

    def card(label, value, sub=""):
        return (f"<div class='card'><div class='v'>{esc(str(value))}</div>"
                f"<div class='l'>{esc(label)}</div>"
                f"<div class='s'>{esc(sub)}</div></div>")

    cards = "".join([
        card("Unique visitors (all time)", s["unique_visitors_total"],
             f"today {s['unique_visitors_today']} · 7 days {s['unique_visitors_7d']} · 30 days {s['unique_visitors_30d']}"),
        card("Returning visitors", s["returning_visitors"], "came back on 2+ different days"),
        card("Sessions", s["sessions"]),
        card("Searches", s["searches"], f"{s['searches_per_visitor']} per visitor"),
        card("Searches with 0 results", f"{s['zero_result_pct']}%", f"{s['zero_result_searches']} searches"),
        card("Search sessions with a click", f"{s['search_sessions_with_click_pct']}%"),
        card("Found helpful",
             "n/a" if s["helpful_pct"] is None else f"{s['helpful_pct']}%",
             f"👍 {s['feedback_up']} · 👎 {s['feedback_down']}"),
        card("Devices", " / ".join(f"{k} {v}" for k, v in s["devices"].items()) or "n/a"),
    ])

    peak = max([d["visitors"] for d in s["daily"]] + [1])
    bars = "".join(
        f"<div class='bar'><div class='fill' style='height:{int(100 * d['visitors'] / peak)}%'></div>"
        f"<div class='n'>{d['visitors']}</div><div class='d'>{esc(d['date'][5:])}</div></div>"
        for d in s["daily"])

    def table(head, rows):
        if not rows:
            return "<p class='muted'>No data yet.</p>"
        th = "".join(f"<th>{esc(h)}</th>" for h in head)
        body = "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in r) + "</tr>" for r in rows)
        return f"<table><tr>{th}</tr>{body}</table>"

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>ARN usage dashboard</title>
<style>
body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:24px;color:#222}}
.wrap{{max-width:1100px;margin:auto}} h1{{margin:0 0 4px}} h2{{margin-top:34px}}
.muted{{color:#777;font-size:14px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px;margin-top:20px}}
.card{{background:#fff;border-radius:12px;padding:16px;box-shadow:0 2px 10px rgba(0,0,0,.06)}}
.v{{font-size:28px;font-weight:700}} .l{{font-size:14px;margin-top:2px}} .s{{font-size:12px;color:#777;margin-top:4px}}
.chart{{display:flex;align-items:flex-end;gap:6px;height:170px;background:#fff;border-radius:12px;padding:16px 16px 8px;overflow-x:auto}}
.bar{{flex:1;min-width:34px;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center}}
.fill{{width:70%;background:#4f6df5;border-radius:4px 4px 0 0;min-height:2px}}
.n{{font-size:12px;font-weight:700}} .d{{font-size:11px;color:#777}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;font-size:14px}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #eee}} th{{background:#fafafa}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:20px}}
a.btn{{display:inline-block;margin-top:10px;padding:8px 14px;background:#4f6df5;color:#fff;border-radius:8px;text-decoration:none;font-size:14px}}
</style></head><body><div class="wrap">
<h1>ARN usage dashboard</h1>
<div class="muted">Data source: {esc(source_label)} · {resource_count} resources · {s['total_events']} recorded events · times in IST</div>
<div class="muted" style="margin-top:4px">{storage_note}</div>
<div class="cards">{cards}</div>
<h2>Unique visitors per day (last {len(s['daily'])} days)</h2><div class="chart">{bars}</div>
<div class="grid">
<div><h2>Top searches</h2>{table(["Query","Count"], s["top_queries"])}</div>
<div><h2>Searches with no results</h2>{table(["Query","Count"], s["zero_result_queries"])}</div>
<div><h2>Most opened resources</h2>{table(["ID","Title","Opens"], s["top_clicked"])}</div>
<div><h2>Latest searches</h2>{table(["Time","Query","Results"], s["recent_searches"])}</div>
</div>
<p><a class="btn" href="/admin/export.csv">Download raw events (CSV)</a></p>
</div></body></html>"""
