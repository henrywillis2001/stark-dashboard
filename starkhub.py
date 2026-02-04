import os
import sqlite3
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import feedparser
import requests
from dateutil import tz

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Static, Input, Button, ListView, ListItem, Label, Tabs, TabPane

# OpenAI integration (optional - falls back to placeholder if not configured)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# -----------------------------
# Config
# -----------------------------
LOCAL_TZ = tz.gettz()  # uses local machine tz
DB_PATH = "starkhub.db"
CACHE_TTL_SEC = 60 * 10  # 10 minutes

RSS_SOURCES = [
    # Australia + USA focused sources
    ("Reuters Markets", "https://www.reuters.com/markets/rss"),
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("FT Markets", "https://www.ft.com/markets?format=rss"),
    ("RBA Media Releases", "https://www.rba.gov.au/rss/rss-cb-media-releases.xml"),
    ("US Fed Press Releases", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("AFR Markets", "https://www.afr.com/markets.rss"),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
]

# Market pulse sources:
# Australia + USA focus with global context
# MVP: use Stooq (simple CSV endpoints) for indices. You can swap later.
STOOQ_SYMBOLS = [
    # USA Major Indices
    ("S&P 500", "^spx"),
    ("NASDAQ 100", "^ndq"),
    ("Dow Jones", "^dji"),
    ("VIX", "^vix"),
    # Australia
    ("ASX 200", "^axjo"),
    ("AUD/USD", "audusd"),
    # Global Context
    ("Gold", "xauusd"),
    ("Oil (WTI)", "cl.1"),
    ("10Y Treasury", "^tnx"),
]


# -----------------------------
# Storage
# -----------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            done_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def cache_get(conn: sqlite3.Connection, key: str) -> Optional[Tuple[str, int]]:
    row = conn.execute("SELECT value, updated_at FROM cache WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return row[0], int(row[1])


def cache_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    now = int(time.time())
    conn.execute(
        "INSERT INTO cache(key, value, updated_at) VALUES(?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, now),
    )
    conn.commit()


def task_add(conn: sqlite3.Connection, title: str) -> None:
    now = int(time.time())
    conn.execute("INSERT INTO tasks(title, created_at) VALUES(?, ?)", (title.strip(), now))
    conn.commit()


def task_list(conn: sqlite3.Connection, include_done: bool = False) -> List[Tuple[int, str, int, Optional[int]]]:
    if include_done:
        rows = conn.execute("SELECT id, title, created_at, done_at FROM tasks ORDER BY done_at IS NOT NULL, created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT id, title, created_at, done_at FROM tasks WHERE done_at IS NULL ORDER BY created_at DESC").fetchall()
    return [(int(r[0]), str(r[1]), int(r[2]), (int(r[3]) if r[3] is not None else None)) for r in rows]


def task_done(conn: sqlite3.Connection, task_id: int) -> None:
    now = int(time.time())
    conn.execute("UPDATE tasks SET done_at = ? WHERE id = ?", (now, task_id))
    conn.commit()


# -----------------------------
# Data fetchers
# -----------------------------
@dataclass
class Headline:
    source: str
    title: str
    link: str
    published_ts: int


def _hash_key(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def fetch_headlines() -> List[Headline]:
    items: List[Headline] = []
    for source_name, url in RSS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:25]:
                title = (getattr(e, "title", "") or "").strip()
                link = (getattr(e, "link", "") or "").strip()
                if not title or not link:
                    continue

                # published parsing
                published_ts = int(time.time())
                if getattr(e, "published_parsed", None):
                    published_ts = int(time.mktime(e.published_parsed))
                elif getattr(e, "updated_parsed", None):
                    published_ts = int(time.mktime(e.updated_parsed))

                items.append(Headline(source=source_name, title=title, link=link, published_ts=published_ts))
        except Exception:
            continue

    # dedupe by title+link
    seen = set()
    deduped: List[Headline] = []
    for h in sorted(items, key=lambda x: x.published_ts, reverse=True):
        k = _hash_key(h.title.lower() + "|" + h.link.lower())
        if k in seen:
            continue
        seen.add(k)
        deduped.append(h)

    return deduped[:40]


def stooq_quote(symbol: str) -> Optional[Tuple[float, float]]:
    """
    Returns (last, pct_change) if possible.
    Stooq CSV endpoint: https://stooq.com/q/l/?s=^spx&i=d
    Fields: Date, Open, High, Low, Close, Volume
    """
    url = f"https://stooq.com/q/l/?s={symbol}&i=d"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        lines = r.text.strip().splitlines()
        if len(lines) < 3:
            return None
        # last two rows
        last = lines[-1].split(",")
        prev = lines[-2].split(",")
        close_last = float(last[4])
        close_prev = float(prev[4])
        pct = ((close_last - close_prev) / close_prev) * 100.0 if close_prev != 0 else 0.0
        return close_last, pct
    except Exception:
        return None


def fetch_market_pulse() -> List[Tuple[str, Optional[float], Optional[float]]]:
    out = []
    for label, sym in STOOQ_SYMBOLS:
        q = stooq_quote(sym)
        if q is None:
            out.append((label, None, None))
        else:
            out.append((label, q[0], q[1]))
    return out


# -----------------------------
# AI Brief Generation
# -----------------------------
def generate_brief(retrieval_pack: str) -> str:
    """
    Generate a structured brief from the retrieval pack using OpenAI.
    Falls back to placeholder if OpenAI is not configured.
    
    The model ONLY summarizes the retrieval_pack (RAG style) to prevent hallucination.
    Output format is strictly constrained.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not OPENAI_AVAILABLE or not api_key:
        # Fallback to placeholder
        lines = retrieval_pack.splitlines()
        headline_lines = [l for l in lines if l.startswith("- ")]
        sample = "\n".join(headline_lines[:6])
        return (
            "AM BRIEF (DRAFT - OpenAI not configured)\n"
            "• Market state: [wire in indices/rates/fx here]\n"
            "• What matters (3):\n"
            "  - [1]\n  - [2]\n  - [3]\n"
            "• Risks / watch-outs (2):\n"
            "  - [R1]\n  - [R2]\n"
            "• Top headlines (sample):\n"
            f"{sample}\n"
            "\n(Set OPENAI_API_KEY environment variable to enable AI briefs.)"
        )
    
    # Strict prompt to prevent hallucination
    prompt = f"""You are a market analyst synthesizing a daily brief. You MUST base your analysis ONLY on the data provided below. Do not add information not present in the data.

DATA PROVIDED:
{retrieval_pack}

Generate a structured brief with EXACTLY this format:

MARKET STATE:
[One sentence summarizing current market conditions from the data]

WHAT MATTERS (3 bullets):
- [First key point from the data]
- [Second key point from the data]
- [Third key point from the data]

RISKS / WATCH-OUTS (2 bullets):
- [First risk or concern from the data]
- [Second risk or concern from the data]

SETUP FOR TOMORROW:
[One sentence on what to watch based on the data]

NOTABLE HEADLINES (5 most relevant):
- [Headline 1]
- [Headline 2]
- [Headline 3]
- [Headline 4]
- [Headline 5]

IMPORTANT: Only reference information present in the data above. If data is missing or unclear, state that explicitly."""

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Fast and cost-effective, good for structured output
            messages=[
                {"role": "system", "content": "You are a precise market analyst. You only summarize provided data. Never hallucinate or add information not in the source."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Lower temperature for more consistent, factual output
            max_tokens=800,
        )
        
        brief = response.choices[0].message.content.strip()
        
        # Validate format (basic check)
        required_sections = ["MARKET STATE", "WHAT MATTERS", "RISKS", "SETUP FOR TOMORROW", "NOTABLE HEADLINES"]
        if not all(section in brief.upper() for section in required_sections):
            return f"⚠️ Brief generated but format may be incomplete:\n\n{brief}"
        
        return brief
        
    except Exception as e:
        return f"⚠️ Error generating brief: {str(e)}\n\nFalling back to retrieval pack:\n\n{retrieval_pack[:500]}..."


# -----------------------------
# UI
# -----------------------------
def fmt_ts(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(LOCAL_TZ)
    return dt.strftime("%a %H:%M")


class StarkHub(App):
    CSS = """
    Screen { background: black; color: #d0d0d0; }
    Header { background: black; }
    Footer { background: black; }
    .panel { border: tall #404040; padding: 1 2; margin: 1; }
    .title { color: #ffffff; text-style: bold; }
    .muted { color: #808080; }
    Input { border: tall #404040; }
    Button { border: tall #404040; }
    """

    BINDINGS = [
        ("h", "go_home", "Home"),
        ("t", "go_tasks", "Tasks"),
        ("n", "go_news", "News"),
        ("b", "go_brief", "Brief"),
        ("r", "refresh", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.conn = db()
        self._headlines: List[Headline] = []
        self._pulse: List[Tuple[str, Optional[float], Optional[float]]] = []
        self._last_refresh = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        tabs = Tabs()
        with tabs:
            with TabPane("HOME", id="pane-home"):
                with Horizontal():
                    yield Static("", classes="panel", id="home-ops")
                    yield Static("", classes="panel", id="home-pulse")
                    yield Static("", classes="panel", id="home-news")

            with TabPane("TASKS", id="pane-tasks"):
                with Container(classes="panel"):
                    yield Label("TASKS", classes="title")
                    yield Input(placeholder="Add task and press Enter…", id="task-input")
                    yield ListView(id="task-list")

            with TabPane("NEWS", id="pane-news"):
                with VerticalScroll(classes="panel"):
                    yield Label("NEWS", classes="title")
                    yield Static("", id="news-body")

            with TabPane("BRIEF", id="pane-brief"):
                with Container(classes="panel"):
                    yield Label("BRIEF", classes="title")
                    with Horizontal():
                        yield Button("Build Retrieval Pack", id="btn-pack")
                        yield Button("Generate Brief (AI)", id="btn-brief")
                    with VerticalScroll():
                        yield Static("", id="brief-body")
        yield tabs
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_all(force=True)
        self.query_one("#task-input", Input).focus()

    def action_go_home(self) -> None:
        self.query_one(Tabs).active = "pane-home"

    def action_go_tasks(self) -> None:
        self.query_one(Tabs).active = "pane-tasks"

    def action_go_news(self) -> None:
        self.query_one(Tabs).active = "pane-news"

    def action_go_brief(self) -> None:
        self.query_one(Tabs).active = "pane-brief"

    def action_refresh(self) -> None:
        self.refresh_all(force=True)

    def refresh_all(self, force: bool = False) -> None:
        now = int(time.time())
        if not force and (now - self._last_refresh) < 5:
            return

        # Headlines (cached)
        h_cache = cache_get(self.conn, "headlines")
        if h_cache and (now - h_cache[1]) < CACHE_TTL_SEC and not force:
            # naive parse: each line "ts|source|title|link"
            parsed = []
            for line in h_cache[0].splitlines():
                try:
                    ts, src, title, link = line.split("|", 3)
                    parsed.append(Headline(src, title, link, int(ts)))
                except Exception:
                    continue
            self._headlines = parsed
        else:
            self._headlines = fetch_headlines()
            ser = "\n".join([f"{h.published_ts}|{h.source}|{h.title}|{h.link}" for h in self._headlines])
            cache_set(self.conn, "headlines", ser)

        # Market pulse (cached)
        p_cache = cache_get(self.conn, "pulse")
        if p_cache and (now - p_cache[1]) < CACHE_TTL_SEC and not force:
            parsed = []
            for line in p_cache[0].splitlines():
                label, last, pct = line.split("|", 2)
                parsed.append((label, float(last) if last != "NA" else None, float(pct) if pct != "NA" else None))
            self._pulse = parsed
        else:
            self._pulse = fetch_market_pulse()
            ser = "\n".join([f"{l}|{v if v is not None else 'NA'}|{p if p is not None else 'NA'}" for l, v, p in self._pulse])
            cache_set(self.conn, "pulse", ser)

        self._last_refresh = now
        self.render_home()
        self.render_tasks()
        self.render_news()

    def render_home(self) -> None:
        # OPS
        tasks = task_list(self.conn, include_done=False)[:8]
        ops_lines = ["[b]OPS[/b]\n"]
        if tasks:
            ops_lines.append("[b]Today[/b]")
            for tid, title, created_at, _ in tasks[:5]:
                ops_lines.append(f"• ({tid}) {title}")
        else:
            ops_lines.append("No tasks. Add one in TASKS.")

        self.query_one("#home-ops", Static).update("\n".join(ops_lines))

        # PULSE
        pulse_lines = ["[b]PULSE[/b]\n"]
        for label, last, pct in self._pulse:
            if last is None or pct is None:
                pulse_lines.append(f"{label}: [grey]NA[/grey]")
            else:
                pulse_lines.append(f"{label}: {last:.2f}  ({pct:+.2f}%)")
        self.query_one("#home-pulse", Static).update("\n".join(pulse_lines))

        # NEWS (top headlines)
        news_lines = ["[b]NEWS[/b]\n"]
        for h in self._headlines[:10]:
            news_lines.append(f"[grey]{fmt_ts(h.published_ts)}[/grey] {h.title}")
        self.query_one("#home-news", Static).update("\n".join(news_lines))

    def render_tasks(self) -> None:
        lv = self.query_one("#task-list", ListView)
        lv.clear()
        for tid, title, created_at, done_at in task_list(self.conn, include_done=False):
            item = ListItem(Label(f"({tid}) {title}", id=f"task-{tid}"))
            lv.append(item)

    def render_news(self) -> None:
        body = []
        for h in self._headlines[:40]:
            body.append(f"[b]{fmt_ts(h.published_ts)}[/b] [grey]{h.source}[/grey]\n{h.title}\n{h.link}\n")
        self.query_one("#news-body", Static).update("\n".join(body) or "No headlines loaded.")

    def build_retrieval_pack(self) -> str:
        now = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")
        pack = []
        pack.append(f"TIME: {now}")
        pack.append("\nMARKET PULSE:")
        for label, last, pct in self._pulse:
            if last is None or pct is None:
                pack.append(f"- {label}: NA")
            else:
                pack.append(f"- {label}: {last:.2f} ({pct:+.2f}%)")

        pack.append("\nTOP HEADLINES (most recent):")
        for h in self._headlines[:20]:
            pack.append(f"- [{fmt_ts(h.published_ts)}] ({h.source}) {h.title}")

        pack.append("\nTASKS (open):")
        for tid, title, *_ in task_list(self.conn, include_done=False)[:10]:
            pack.append(f"- ({tid}) {title}")

        return "\n".join(pack)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-pack":
            pack = self.build_retrieval_pack()
            self.query_one("#brief-body", Static).update(pack)
        elif event.button.id == "btn-brief":
            pack = self.build_retrieval_pack()
            brief = generate_brief(pack)
            self.query_one("#brief-body", Static).update(brief)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "task-input":
            title = event.value.strip()
            if title:
                task_add(self.conn, title)
                event.input.value = ""
                self.render_tasks()
                self.render_home()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Mark task done when selected
        label = event.item.query_one(Label).renderable
        text = str(label)
        # text looks like "(id) title"
        try:
            tid = int(text.split(")", 1)[0].strip("("))
            task_done(self.conn, tid)
            self.render_tasks()
            self.render_home()
        except Exception:
            pass


if __name__ == "__main__":
    StarkHub().run()

