"""
MarketPulse - Professional Market Intelligence Dashboard
Web-based interface for market intelligence and task management
"""
import os
import sqlite3
import time
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import feedparser
import requests
from dateutil import tz
from flask import Flask, render_template, jsonify, request

# OpenAI integration
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Import config and functions from original starkhub
LOCAL_TZ = tz.gettz()
DB_PATH = "starkhub.db"
CACHE_TTL_SEC = 60 * 10

RSS_SOURCES = [
    # Australia - Primary Focus
    ("AFR Markets", "https://www.afr.com/markets.rss"),
    ("AFR Companies", "https://www.afr.com/companies.rss"),
    ("AFR Breaking", "https://www.afr.com/breaking.rss"),
    ("RBA Media Releases", "https://www.rba.gov.au/rss/rss-cb-media-releases.xml"),
    ("ABC Business", "https://www.abc.net.au/news/feed/51892/rss.xml"),
    ("The Australian Business", "https://www.theaustralian.com.au/business/rss"),
    # USA - Primary Focus
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("WSJ World", "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("Reuters Markets", "https://www.reuters.com/markets/rss"),
    ("Reuters Business", "https://www.reuters.com/business/rss"),
    ("US Fed Press Releases", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("CNBC Markets", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch", "https://www.marketwatch.com/rss/topstories"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    # Other Foreign - Secondary
    ("FT Markets", "https://www.ft.com/markets?format=rss"),
    ("FT Companies", "https://www.ft.com/companies?format=rss"),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss"),
]

MARKET_SYMBOLS = [
    # USA Major Indices
    ("S&P 500", "GSPC", "index"),
    ("NASDAQ", "IXIC", "index"),
    ("Dow Jones", "DJI", "index"),
    ("VIX", "VIX", "index"),
    # Australia
    ("ASX 200", "AXJO", "index"),
    ("AUD/USD", "AUDUSD=X", "forex"),
    # Global Context
    ("Gold", "GC=F", "commodity"),
    ("Oil (WTI)", "CL=F", "commodity"),
    ("10Y Treasury", "TNX", "bond"),
]

app = Flask(__name__)

# Database functions
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            done_at INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )"""
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

# Data models
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
            for e in feed.entries[:40]:  # Increased from 25 to 40 per source
                title = (getattr(e, "title", "") or "").strip()
                link = (getattr(e, "link", "") or "").strip()
                if not title or not link:
                    continue
                published_ts = int(time.time())
                if getattr(e, "published_parsed", None):
                    published_ts = int(time.mktime(e.published_parsed))
                elif getattr(e, "updated_parsed", None):
                    published_ts = int(time.mktime(e.updated_parsed))
                items.append(Headline(source=source_name, title=title, link=link, published_ts=published_ts))
        except Exception:
            continue
    
    seen = set()
    deduped: List[Headline] = []
    for h in sorted(items, key=lambda x: x.published_ts, reverse=True):
        k = _hash_key(h.title.lower() + "|" + h.link.lower())
        if k in seen:
            continue
        seen.add(k)
        deduped.append(h)
    
    # Prioritize Australia/USA headlines
    aus_usa_keywords = ['australia', 'australian', 'sydney', 'melbourne', 'rba', 'asx', 'aud', 
                       'usa', 'us', 'united states', 'federal reserve', 'fed', 'wall street', 
                       'nasdaq', 's&p', 'dow', 'new york', 'washington', 'treasury', 'dollar',
                       'market', 'economy', 'inflation', 'rates', 'interest', 'gdp', 'employment']
    
    prioritized = []
    others = []
    
    for h in deduped:
        title_lower = h.title.lower()
        source_lower = h.source.lower()
        # Check if headline is relevant to Australia/USA
        is_relevant = any(keyword in title_lower or keyword in source_lower for keyword in aus_usa_keywords)
        if is_relevant:
            prioritized.append(h)
        else:
            others.append(h)
    
    # Return prioritized first, then others, limit to 60 total
    return (prioritized + others)[:60]

def get_market_quote(symbol: str, symbol_type: str = "index") -> Optional[Tuple[float, float]]:
    """
    Fetch market data using yfinance library (more reliable).
    symbol_type: "index", "forex", "commodity", "bond"
    """
    try:
        import yfinance as yf
        
        # Map symbols to yfinance format
        yf_symbol = symbol
        if symbol_type == "index":
            # Add ^ prefix for indices if not present
            if not symbol.startswith("^"):
                yf_symbol = "^" + symbol
        elif symbol_type == "forex":
            # Already in correct format (e.g., AUDUSD=X)
            yf_symbol = symbol
        elif symbol_type == "commodity":
            # Already in correct format (e.g., GC=F, CL=F)
            yf_symbol = symbol
        elif symbol_type == "bond":
            # Add ^ prefix for bonds
            if not symbol.startswith("^"):
                yf_symbol = "^" + symbol
        
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="5d", interval="1d")
        
        if len(hist) >= 2:
            close_last = float(hist['Close'].iloc[-1])
            close_prev = float(hist['Close'].iloc[-2])
            pct = ((close_last - close_prev) / close_prev) * 100.0 if close_prev != 0 else 0.0
            return close_last, pct
        elif len(hist) == 1:
            # Only one day of data, use that
            close_last = float(hist['Close'].iloc[-1])
            return close_last, 0.0
    except Exception as e:
        print(f"Error fetching {symbol} ({symbol_type}): {e}")
        # Fallback to Stooq for indices
        if symbol_type == "index":
            try:
                stooq_symbol = symbol.replace("^", "")
                url = f"https://stooq.com/q/l/?s={stooq_symbol}&f=sd2t2ohlcv&h&e=csv"
                r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                r.raise_for_status()
                lines = r.text.strip().splitlines()
                if len(lines) >= 3:
                    last = lines[-1].split(",")
                    prev = lines[-2].split(",")
                    if len(last) >= 5 and len(prev) >= 5:
                        close_last = float(last[4])
                        close_prev = float(prev[4])
                        pct = ((close_last - close_prev) / close_prev) * 100.0 if close_prev != 0 else 0.0
                        return close_last, pct
            except Exception as ex:
                print(f"Stooq fallback failed for {symbol}: {ex}")
    
    return None

def fetch_market_pulse() -> List[Tuple[str, Optional[float], Optional[float]]]:
    out = []
    for label, sym, sym_type in MARKET_SYMBOLS:
        q = get_market_quote(sym, sym_type)
        if q is None:
            out.append((label, None, None))
        else:
            out.append((label, q[0], q[1]))
    return out

def generate_fallback_decision(pulse_data: List[dict], headlines: List[dict]) -> dict:
    """Generate intelligent fallback analysis from market data when AI fails"""
    # Convert pulse_data to dict format for easier access
    pulse_dict = {p['label']: p for p in pulse_data if p.get('value') is not None and p.get('pct') is not None}
    
    # Extract key metrics
    sp500 = pulse_dict.get('S&P 500')
    nasdaq = pulse_dict.get('NASDAQ')
    vix = pulse_dict.get('VIX')
    us10y = pulse_dict.get('10Y Treasury')
    gold = pulse_dict.get('Gold')
    asx = pulse_dict.get('ASX 200')
    
    # Determine regime
    regime = "NEUTRAL | DATA-DRIVEN"
    if vix and vix['value'] > 20:
        regime = "RISK-OFF | VOLATILITY-LED"
    elif us10y and us10y['value'] > 4.0:
        regime = "RISK-OFF | RATES-LED"
    elif sp500 and sp500['pct'] < -1.0:
        regime = "RISK-OFF | EQUITY-LED"
    elif sp500 and sp500['pct'] > 1.0:
        regime = "RISK-ON | MOMENTUM-LED"
    
    if us10y:
        regime += f" | US10Y at {us10y['value']:.2f}%"
    
    # Generate what changed
    what_changed = []
    if sp500 and abs(sp500['pct']) > 0.5:
        what_changed.append(f"S&P 500 at {sp500['value']:.2f}, {sp500['pct']:+.2f}% → FORECAST: trend likely to continue near-term")
    if us10y and abs(us10y['pct']) > 0.1:
        what_changed.append(f"US10Y at {us10y['value']:.2f}%, {us10y['pct']:+.2f}% → FORECAST: rate moves likely to drive equity direction")
    if vix and vix['value'] > 18:
        what_changed.append(f"VIX at {vix['value']:.2f} → FORECAST: elevated volatility likely to persist")
    if not what_changed:
        what_changed.append("Markets consolidating → FORECAST: awaiting catalyst for direction")
    
    # Generate winners/losers based on data
    winners = []
    losers = []
    
    if us10y and us10y['value'] > 4.0:
        winners.append("Defensive sectors (healthcare, staples) - FORECAST: likely to outperform in higher rate environment")
        losers.append("Long-duration growth equities - FORECAST: likely to underperform if rates stay elevated")
    
    if vix and vix['value'] > 20:
        winners.append("Quality defensives with strong balance sheets - FORECAST: likely to outperform in volatile environment")
        losers.append("Speculative tech and high-beta names - FORECAST: likely to underperform if volatility persists")
    
    if gold and gold['pct'] > 0.5:
        winners.append("Gold and real assets - FORECAST: inflation hedge demand likely to persist")
    
    if nasdaq and nasdaq['pct'] < -1.0:
        losers.append("Tech sector - FORECAST: underperformance likely to continue if risk-off persists")
    
    if not winners:
        winners.append("Market-neutral strategies - FORECAST: await clearer direction")
    if not losers:
        losers.append("High-beta names - FORECAST: vulnerable to volatility spikes")
    
    # Opportunity zones
    opportunity_zones = [
        "Quality defensives with pricing power - FORECAST: research companies with strong margins",
        "Relative value trades - FORECAST: spread opportunities if dispersion increases",
        "Volatility strategies - FORECAST: consider if VIX remains elevated"
    ]
    
    # What breaks
    what_breaks = []
    if us10y:
        what_breaks.append(f"IF US10Y < {us10y['value'] - 0.25:.2f}% → FORECAST: regime shifts to risk-on, equity upside likely")
        what_breaks.append(f"IF US10Y > {us10y['value'] + 0.25:.2f}% → FORECAST: further equity downside likely")
    if vix:
        what_breaks.append(f"IF VIX < {max(15, vix['value'] - 5):.1f} → FORECAST: risk-on resumes, growth likely to outperform")
    
    # Time horizons
    vix_val = vix['value'] if vix else 0
    us10y_val = us10y['value'] if us10y else 0
    time_horizons = {
        "shortTerm": {
            "horizon": "1-5 days",
            "view": f"FORECAST: Current volatility ({vix_val:.1f}) likely to drive intraday moves" if vix else "FORECAST: Monitor key levels for direction",
            "action": "Monitor key levels and avoid adding beta until direction clears"
        },
        "mediumTerm": {
            "horizon": "2-8 weeks",
            "view": f"FORECAST: Rate environment ({us10y_val:.2f}%) likely to drive sector rotation" if us10y else "FORECAST: Rate environment likely to drive sector rotation",
            "action": "Favor quality and defensives until trend reverses"
        },
        "longTerm": {
            "horizon": "3-12 months",
            "view": "FORECAST: Structural backdrop will determine regime - monitor inflation and policy",
            "action": "Monitor structural shifts and position accordingly"
        }
    }
    
    # Market sentiment
    sentiment_parts = []
    if sp500:
        sentiment_parts.append(f"S&P 500 at {sp500['value']:.2f}")
    if vix:
        sentiment_parts.append(f"VIX at {vix['value']:.2f}")
    if us10y:
        sentiment_parts.append(f"US10Y at {us10y['value']:.2f}%")
    
    market_sentiment = f"FORECAST: Market sentiment driven by {' | '.join(sentiment_parts) if sentiment_parts else 'current data'}. Monitor key levels for regime shifts."
    
    # Signals
    signals = []
    if sp500:
        signals.append(f"FORECAST: S&P 500 at {sp500['value']:.2f} ({sp500['pct']:+.2f}%) - likely to drive near-term direction")
    if len(headlines) > 0:
        signals.append(f"FORECAST: {len(headlines)} news items monitored - key events likely to drive volatility")
    
    return {
        "regime": regime,
        "whatChanged": what_changed[:3],
        "winners": winners[:3],
        "losers": losers[:3],
        "opportunityZones": opportunity_zones[:5],
        "whatBreaks": what_breaks[:3],
        "timeHorizons": time_horizons,
        "structuralContext": "FORECAST: Market dynamics driven by current data. Monitor key levels for regime shifts.",
        "marketSentiment": market_sentiment,
        "signals": signals[:3] if signals else ["FORECAST: Monitoring market data for signals"]
    }

def generate_brief(retrieval_pack: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not OPENAI_AVAILABLE or not api_key:
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
    
    prompt = f"""You are a market analyst synthesizing a daily brief focused on AUSTRALIA and USA markets. You MUST base your analysis ONLY on the data provided below. Do not add information not present in the data.

PRIORITY: Focus primarily on Australia and USA news and market data. Include other foreign markets only if highly relevant.

DATA PROVIDED:
{retrieval_pack}

Generate a structured brief with EXACTLY this format:

MARKET STATE:
[One sentence summarizing current market conditions from the data, emphasizing Australia and USA]

WHAT MATTERS (3 bullets):
- [First key point from the data - prioritize Australia/USA]
- [Second key point from the data - prioritize Australia/USA]
- [Third key point from the data]

RISKS / WATCH-OUTS (2 bullets):
- [First risk or concern from the data - prioritize Australia/USA]
- [Second risk or concern from the data]

SETUP FOR TOMORROW:
[One sentence on what to watch based on the data, with focus on Australia and USA]

NOTABLE HEADLINES (5 most relevant - prioritize Australia and USA):
- [Headline 1 - Australia or USA preferred]
- [Headline 2 - Australia or USA preferred]
- [Headline 3]
- [Headline 4]
- [Headline 5]

IMPORTANT: Only reference information present in the data above. Prioritize Australia and USA headlines. If data is missing or unclear, state that explicitly."""

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a precise market analyst specializing in Australia and USA markets. You only summarize provided data. Never hallucinate or add information not in the source. Prioritize Australia and USA news in your analysis."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
        )
        brief = response.choices[0].message.content.strip()
        required_sections = ["MARKET STATE", "WHAT MATTERS", "RISKS", "SETUP FOR TOMORROW", "NOTABLE HEADLINES"]
        if not all(section in brief.upper() for section in required_sections):
            return f"⚠️ Brief generated but format may be incomplete:\n\n{brief}"
        return brief
    except Exception as e:
        return f"⚠️ Error generating brief: {str(e)}\n\nFalling back to retrieval pack:\n\n{retrieval_pack[:500]}..."

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/synthesis', methods=['GET'])
def api_synthesis():
    """Generate market synthesis - comprehensive overview"""
    conn = get_db()
    
    # Get current market data
    pulse_raw = fetch_market_pulse()
    pulse_data = [{"label": l, "value": v, "pct": p} for l, v, p in pulse_raw]
    
    # Get recent headlines
    headlines_raw = fetch_headlines()
    headlines = [asdict(h) for h in headlines_raw[:20]]
    
    # Get cached decision for context
    cached = cache_get(conn, "stark_decision")
    decision_context = ""
    if cached:
        try:
            decision_data = json.loads(cached[0])
            decision_context = f"""
Current Regime: {decision_data.get('regime', {}).get('label', 'Unknown')}
Current Stance: {decision_data.get('stance', {}).get('label', 'Unknown')}
Verdict: {decision_data.get('verdict', 'N/A')}
"""
        except:
            pass
    
    # Build context
    context = "CURRENT MARKET DATA:\n"
    valid_pulse = [p for p in pulse_data if p['value'] is not None and p['pct'] is not None]
    for p in valid_pulse[:10]:
        context += f"- {p['label']}: {p['value']:.2f} ({p['pct']:+.2f}%)\n"
    
    context += "\nTOP NEWS:\n"
    for h in headlines[:15]:
        context += f"- [{h['source']}] {h['title']}\n"
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OpenAI API key not configured"}
    
    if not OPENAI_AVAILABLE:
        conn.close()
        return jsonify({"synthesis": "OpenAI not available. Install openai package."})
    
    try:
        client = OpenAI(api_key=api_key, timeout=30.0)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a senior market strategist synthesizing market intelligence. Focus on BROAD TRENDS, WHERE MARKETS ARE HEADING, and WHAT COULD HAPPEN NEXT. Think strategically about trends, not minute-by-minute adjustments. Prioritize Australia and USA markets. Provide a comprehensive, forward-looking synthesis that includes SPECIFIC FACTS, STATS, and NUMBERS from the data, while being CONCLUSIVE and ACTIONABLE."},
                {"role": "user", "content": f"""Synthesize this market intelligence into a comprehensive, detailed overview. Include SPECIFIC FACTS, STATS, and NUMBERS from the data. Be CONCLUSIVE and ACTIONABLE. Focus on BROAD TRENDS and FORWARD-LOOKING ANALYSIS:

{decision_context}

Market Data:
{context}

Provide a detailed synthesis with SPECIFIC NUMBERS, FACTS, and FORECASTS:
1. THE BIG PICTURE: 2-3 sentences on the overall market trend and direction with SPECIFIC STATS AND FORECASTS (e.g., "S&P 500 is at X, up Y%, while ASX 200 is at Z, down W% - FORECAST: likely to [FUTURE OUTCOME] over next X timeframe"). Emphasize Australia and USA markets.

2. KEY TRENDS: 3-4 major trends developing with SPECIFIC NUMBERS AND FORECASTS (e.g., "US10Y yields at X%, up Ybp - FORECAST: likely to [FUTURE EFFECT] if [CONDITION] persists over next X weeks"). Include where they will likely lead.

3. WHAT MATTERS: Top 3-4 things driving markets with SPECIFIC DATA POINTS AND FUTURE IMPLICATIONS (e.g., "VIX at X, NASDAQ at Y, Gold at Z - FORECAST: if [CONDITION], expect [FUTURE OUTCOME]"). Include their future effects.

4. WHAT TO WATCH: 3-4 critical developments with SPECIFIC LEVELS/THRESHOLDS AND FORECASTS (e.g., "If US10Y breaks above X%, FORECAST: then [FUTURE OUTCOME] likely within X timeframe"). Include what will likely change direction or accelerate trends.

5. BOTTOM LINE: One clear, CONCLUSIVE takeaway with SPECIFIC NUMBERS AND FORECAST on what this means for positioning over next X timeframe.

Be detailed, include facts, stats, and FORECASTS with TIMEFRAMES. Think about the bigger picture, future trends, and likely outcomes. Markets price the future, not the present."""}
            ],
            temperature=0.4,
            max_tokens=600,
        )
        
        synthesis = response.choices[0].message.content.strip()
        conn.close()
        return jsonify({"synthesis": synthesis})
    except Exception as e:
        conn.close()
        return jsonify({"synthesis": f"Error generating synthesis: {str(e)}"})

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "endpoints": ["/api/stark/decision", "/api/pulse", "/api/headlines", "/api/synthesis"]})

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """Chat endpoint for questioning assumptions"""
    data = request.json
    question = data.get('question', '').strip()
    
    if not question:
        return jsonify({"error": "No question provided"})
    
    conn = get_db()
    
    # Get current market context
    pulse_raw = fetch_market_pulse()
    pulse_data = [{"label": l, "value": v, "pct": p} for l, v, p in pulse_raw]
    headlines_raw = fetch_headlines()
    headlines = [asdict(h) for h in headlines_raw[:15]]
    
    # Get cached decision for context
    cached = cache_get(conn, "stark_decision")
    decision_context = ""
    if cached:
        try:
            decision_data = json.loads(cached[0])
            decision_context = f"""
Current Regime: {decision_data.get('regime', {}).get('label', 'Unknown')}
Current Stance: {decision_data.get('stance', {}).get('label', 'Unknown')}
Verdict: {decision_data.get('verdict', 'N/A')}
"""
        except:
            pass
    
    # Build comprehensive context with ALL market data - include current date
    current_date = datetime.now().strftime("%Y-%m-%d")
    context = f"CURRENT MARKET DATA (as of {current_date} - ALL AVAILABLE):\n"
    context += f"CRITICAL: This is LIVE, CURRENT data. Do NOT use old data from your training (like Q2 2023, 2024, etc.).\n"
    context += f"If specific data isn't in this feed, say 'Data not available in current market feed' - DO NOT use old data.\n\n"
    
    valid_pulse = [p for p in pulse_data if p['value'] is not None and p['pct'] is not None]
    for p in valid_pulse:
        context += f"- {p['label']}: {p['value']:.2f} ({p['pct']:+.2f}%)\n"
    
    # Include data points that might be None for completeness
    all_pulse = [p for p in pulse_data]
    context += "\nALL MARKET INDICATORS (including unavailable):\n"
    for p in all_pulse:
        if p['value'] is not None and p['pct'] is not None:
            context += f"- {p['label']}: {p['value']:.2f} ({p['pct']:+.2f}%)\n"
        else:
            context += f"- {p['label']}: N/A\n"
    
    context += f"\nTOP NEWS (Australia/USA prioritized - as of {current_date}):\n"
    for h in headlines[:20]:  # Increased to 20 to capture more company mentions
        context += f"- [{h['source']}] {h['title']}\n"
    
    # Extract energy-related headlines for better context
    energy_headlines = [h for h in headlines if any(kw in h['title'].lower() for kw in ['energy', 'oil', 'gas', 'petroleum', 'renewable', 'solar', 'wind', 'coal', 'exxon', 'chevron', 'shell', 'bp', 'woodside', 'santos', 'origin'])]
    if energy_headlines:
        context += f"\nENERGY-RELATED NEWS (extracted from headlines):\n"
        for h in energy_headlines[:10]:
            context += f"- [{h['source']}] {h['title']}\n"
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OpenAI API key not configured"}
    
    if not OPENAI_AVAILABLE:
        conn.close()
        return jsonify({"error": "OpenAI not available", "response": "OpenAI library not installed"})
    
    try:
        client = OpenAI(api_key=api_key, timeout=20.0)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Stark-level market analyst. You CAN name well-known companies in sectors (Newmont, Barrick for gold; Exxon, Chevron, Woodside for energy; etc.) - this is public knowledge. You CANNOT cite specific company financial metrics from old data. When asked about companies: 1) NAME specific companies worth researching in the sector, 2) Connect recommendations to CURRENT market data (indices, rates, commodities), 3) Provide FORECASTS with timeframes. Focus on Australia and USA markets. Be specific, actionable, and forward-looking. Always tie company/sector recommendations to current market conditions."},
                {"role": "user", "content": f"""User question: {question}

Current market context:
{decision_context}

COMPLETE MARKET DATA (you MUST cite specific numbers from this data):
{context}

CRITICAL INSTRUCTIONS:
1. Markets price the FUTURE, not the present. Make FORECASTS and ESTIMATES about what will happen
2. When asked about companies or sectors:
   - YOU CAN name well-known companies in a sector using your general knowledge (e.g., "Major gold miners include Newmont (NEM), Barrick Gold (GOLD), Agnico Eagle (AEM)")
   - YOU CAN recommend sectors and types of companies (e.g., "Gold miners with strong balance sheets" or "Large-cap energy producers")
   - YOU CANNOT cite specific financial metrics from your training (no P/E ratios, debt-to-equity, revenue figures from old data)
   - Connect company/sector recommendations to CURRENT market data (e.g., "Gold at $X suggests gold miners likely to benefit...")
3. For market data (indices, rates, commodities): ONLY use the CURRENT data provided above
4. For company NAMES and sector knowledge: You CAN use your general knowledge to name major companies
5. For company FINANCIAL METRICS: Do NOT cite specific numbers from your training - instead say "research their balance sheets" or similar
6. ALWAYS cite specific numbers from the CURRENT market data above when discussing market conditions
7. When making any claim, include the actual data point AND a forecast (e.g., "Gold at $5,150 - FORECAST: if it breaks above $5,200, gold miners likely to outperform over next 2-4 weeks")
8. Reference specific market levels, percentages, and changes WITH FUTURE IMPLICATIONS
9. Include TIMEFRAMES in your forecasts (e.g., "likely to happen over next X days/weeks/months")
10. Be forward-looking and strategic - focus on what WILL happen, not just what IS happening

EXAMPLES OF GOOD RESPONSES:
- "Gold miners worth researching: Newmont (NEM), Barrick Gold (GOLD), Agnico Eagle (AEM), Northern Star (ASX: NST). With Gold at $X (+Y%), FORECAST: if gold breaks above $5,200 over next 1-2 weeks, these miners likely to outperform."
- "Energy producers to consider: Woodside (ASX: WDS), Santos (ASX: STO), Exxon (XOM), Chevron (CVX). With Oil at $X and rates at Y%, FORECAST: energy sector likely to..."

Answer with company names, sector recommendations, and FORECASTS tied to CURRENT market data. Be specific and actionable."""}
            ],
            temperature=0.4,
            max_tokens=500,  # Increased to allow for detailed responses with stats
        )
        
        answer = response.choices[0].message.content.strip()
        conn.close()
        return jsonify({"response": answer})
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e), "response": f"Error: {str(e)}"})

@app.route('/api/headlines')
def api_headlines():
    conn = get_db()
    now = int(time.time())
    h_cache = cache_get(conn, "headlines")
    
    if h_cache and (now - h_cache[1]) < CACHE_TTL_SEC:
        parsed = []
        for line in h_cache[0].splitlines():
            try:
                ts, src, title, link = line.split("|", 3)
                parsed.append({"source": src, "title": title, "link": link, "published_ts": int(ts)})
            except Exception:
                continue
        headlines = parsed
    else:
        headlines_raw = fetch_headlines()
        headlines = [asdict(h) for h in headlines_raw]
        ser = "\n".join([f"{h.published_ts}|{h.source}|{h.title}|{h.link}" for h in headlines_raw])
        cache_set(conn, "headlines", ser)
    
    conn.close()
    return jsonify(headlines)

@app.route('/api/pulse')
def api_pulse():
    conn = get_db()
    now = int(time.time())
    p_cache = cache_get(conn, "pulse")
    
    if p_cache and (now - p_cache[1]) < CACHE_TTL_SEC:
        parsed = []
        for line in p_cache[0].splitlines():
            try:
                label, last, pct = line.split("|", 2)
                parsed.append({
                    "label": label,
                    "value": float(last) if last != "NA" else None,
                    "pct": float(pct) if pct != "NA" else None
                })
            except Exception:
                continue
        pulse = parsed
    else:
        pulse_raw = fetch_market_pulse()
        pulse = [{"label": l, "value": v, "pct": p} for l, v, p in pulse_raw]
        ser = "\n".join([f"{l}|{v if v is not None else 'NA'}|{p if p is not None else 'NA'}" for l, v, p in pulse_raw])
        cache_set(conn, "pulse", ser)
    
    conn.close()
    return jsonify(pulse)

@app.route('/api/tasks', methods=['GET'])
def api_tasks_get():
    conn = get_db()
    rows = conn.execute("SELECT id, title, created_at, done_at FROM tasks WHERE done_at IS NULL ORDER BY created_at DESC").fetchall()
    tasks = [{"id": r[0], "title": r[1], "created_at": r[2], "done_at": r[3]} for r in rows]
    conn.close()
    return jsonify(tasks)

@app.route('/api/tasks', methods=['POST'])
def api_tasks_post():
    data = request.json
    conn = get_db()
    now = int(time.time())
    conn.execute("INSERT INTO tasks(title, created_at) VALUES(?, ?)", (data['title'].strip(), now))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/tasks/<int:task_id>/done', methods=['POST'])
def api_tasks_done(task_id):
    conn = get_db()
    now = int(time.time())
    conn.execute("UPDATE tasks SET done_at = ? WHERE id = ?", (now, task_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/brief/pack', methods=['GET'])
def api_brief_pack():
    conn = get_db()
    
    # Get pulse
    pulse_raw = fetch_market_pulse()
    pulse = [{"label": l, "value": v, "pct": p} for l, v, p in pulse_raw]
    
    # Get headlines
    headlines_raw = fetch_headlines()
    headlines = [asdict(h) for h in headlines_raw[:20]]
    
    # Get tasks
    rows = conn.execute("SELECT id, title FROM tasks WHERE done_at IS NULL ORDER BY created_at DESC LIMIT 10").fetchall()
    tasks = [{"id": r[0], "title": r[1]} for r in rows]
    
    now = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M %Z")
    pack = {
        "time": now,
        "pulse": pulse,
        "headlines": headlines,
        "tasks": tasks
    }
    
    conn.close()
    return jsonify(pack)

@app.route('/api/brief/generate', methods=['POST'])
def api_brief_generate():
    data = request.json
    pack_text = data.get('pack', '')
    brief = generate_brief(pack_text)
    return jsonify({"brief": brief})

@app.route('/api/stark/decision', methods=['GET'])
def api_stark_decision():
    """Generate Stark Decision Engine output: regime, stance, conditions, signals, verdict"""
    print("🔵 /api/stark/decision endpoint called")
    conn = get_db()
    
    # Get current market data
    print("📊 Fetching market pulse...")
    pulse_raw = fetch_market_pulse()
    pulse_data = [{"label": l, "value": v, "pct": p} for l, v, p in pulse_raw]
    
    # Check cache first (cache for 5 minutes)
    now = int(time.time())
    cached = cache_get(conn, "stark_decision")
    if cached and (now - cached[1]) < 300:  # 5 minute cache
        print("✅ Returning cached Stark decision")
        conn.close()
        return jsonify(json.loads(cached[0]))
    
    print("🔄 Cache miss, generating new decision...")
    
    # Get recent headlines (prioritize Australia/USA)
    print("📰 Fetching headlines...")
    headlines_raw = fetch_headlines()
    headlines = [asdict(h) for h in headlines_raw[:15]]  # Reduced to 15 for speed
    print(f"✅ Got {len(headlines)} headlines")
    
    # Build context - minimal for speed
    context = "CURRENT MARKET DATA:\n"
    valid_pulse = [p for p in pulse_data if p['value'] is not None and p['pct'] is not None]
    for p in valid_pulse[:8]:  # Only top 8 market indicators
        context += f"- {p['label']}: {p['value']:.2f} ({p['pct']:+.2f}%)\n"
    
    context += "\nTOP NEWS (Australia/USA):\n"
    for h in headlines[:10]:  # Only top 10 headlines
        context += f"- [{h['source']}] {h['title']}\n"
    
    print(f"📝 Context built ({len(context)} chars)")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not OPENAI_AVAILABLE:
        print("⚠️ OpenAI not available, using fallback analysis")
        fallback_result = generate_fallback_decision(pulse_data, headlines)
        cache_set(conn, "stark_decision", json.dumps(fallback_result))
        conn.close()
        return jsonify(fallback_result)
    
    try:
        print("🔄 Starting OpenAI API call (will cache for 5 min)...")
        client = OpenAI(api_key=api_key, timeout=30.0)  # 30 second timeout
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a hedge-fund-grade decision engine. You compress market intelligence into portfolio-directive judgments. You are FORWARD-LOOKING - markets price the future, not the present. Think in TIME HORIZONS, WINNERS vs LOSERS, and OPPORTUNITY ZONES. Make FORECASTS and ESTIMATES about future effects. Be brutally concise - no redundancy, no generic phrases. Every word must translate to positioning, horizons, or capital allocation. Focus on Australia and USA markets. Always respond with valid JSON only."},
                {"role": "user", "content": f"""Generate a hedge-fund-grade decision output that is FORWARD-LOOKING. Markets price the future, not the present. Make FORECASTS and ESTIMATES about what will happen, not just what is happening. Be COMPRESSED - cut word count by 50%. No redundancy. Every claim must cite SPECIFIC NUMBERS. Return ONLY valid JSON with this exact structure:

{{
  "regime": "RISK-OFF | RATES-LED | [ONE LINE WITH SPECIFIC CONTEXT]",
  "whatChanged": [
    "US10Y at X%, up Ybp → FORECAST: will likely drive risk-off for next X days (SPECIFIC)",
    "Tech underperformance widened → FORECAST: likely to continue if rates stay above X% (SPECIFIC)",
    "Gold at $X, Y% change → FORECAST: inflation hedge demand likely to persist if [CONDITION] (SPECIFIC)"
  ],
  "winners": [
    "Defensive equities (healthcare, staples) - FORECAST: will outperform if rates stay elevated for next X weeks (SPECIFIC)",
    "Real assets (gold at $X, energy) - FORECAST: likely to benefit from [FUTURE CONDITION] (SPECIFIC)",
    "Value over growth - FORECAST: rotation likely to accelerate if US10Y breaks above X% (SPECIFIC)"
  ],
  "losers": [
    "Long-duration growth equities - FORECAST: likely to underperform if rates trend higher over next X months (SPECIFIC)",
    "Highly leveraged companies - FORECAST: financing costs will pressure margins if rates stay above X% (SPECIFIC)",
    "Speculative tech - FORECAST: multiple compression likely if risk-off persists (SPECIFIC)"
  ],
  "opportunityZones": [
    "Gold miners with strong balance sheets - FORECAST: likely to outperform if gold breaks above $X (research prompt)",
    "Energy producers with free cash flow leverage - FORECAST: likely to benefit if oil stays above $X (research prompt)",
    "Quality defensives with pricing power - FORECAST: likely to maintain margins if inflation persists (research prompt)",
    "Relative value: defensives vs tech - FORECAST: spread likely to widen if rates continue higher (research prompt)",
    "Volatility strategies if VIX > X - FORECAST: likely opportunity if risk-off accelerates (research prompt)"
  ],
  "whatBreaks": [
    "IF US10Y < X% → FORECAST: regime shifts to risk-on, equity upside likely (SPECIFIC)",
    "IF VIX > X → FORECAST: risk-on resumes, growth likely to outperform (SPECIFIC)",
    "IF [SPECIFIC CATALYST] → FORECAST: [FUTURE OUTCOME with TIMEFRAME] (SPECIFIC)"
  ],
  "timeHorizons": {{
    "shortTerm": {{
      "horizon": "1-5 days",
      "view": "FORECAST: Rates volatility will likely dominate intraday equity moves - SPECIFIC LEVELS and TIMEFRAME",
      "action": "Avoid adding equity beta until rates stabilize"
    }},
    "mediumTerm": {{
      "horizon": "2-8 weeks",
      "view": "FORECAST: Rising yields will likely pressure growth multiples if US10Y stays above X% - SPECIFIC TIMEFRAME",
      "action": "Favor low-beta / defensives until rate trend reverses"
    }},
    "longTerm": {{
      "horizon": "3-12 months",
      "view": "FORECAST: If inflation persists → higher-for-longer regime likely, real assets favored - SPECIFIC CONDITIONS",
      "action": "Monitor structural backdrop for regime shift signals"
    }}
  }},
  "structuralContext": "FORECAST: Market transitioning from liquidity-driven to rate-driven regime. Dispersion likely to increase → stock selection will matter more. Macro volatility likely to exceed micro fundamentals for next X months.",
  "marketSentiment": "FORECAST: Risk-off bias likely to persist (S&P 500 at X, VIX at Y, US10Y at Z%). If rates break above X%, expect [FUTURE OUTCOME]. If rates fall below Y%, expect [FUTURE OUTCOME].",
  "signals": [
    "FORECAST: Broad market signal with SPECIFIC NUMBERS - likely to lead to [FUTURE OUTCOME] over next X timeframe",
    "FORECAST: What news/events will likely matter for direction - [SPECIFIC EVENT] likely to cause [FUTURE EFFECT]",
    "FORECAST: Forward-looking indicators - if [CONDITION] breaks, expect [FUTURE OUTCOME] within X timeframe"
  ]
}}

Market data:
{context}

CRITICAL: Be COMPRESSED. No redundancy. Every claim must cite SPECIFIC NUMBERS from the data. This is portfolio-directive, not commentary."""}
            ],
            temperature=0.3,
            max_tokens=1000,  # Increased for new fields
            response_format={"type": "json_object"}
        )
        
        print("✅ OpenAI API call completed")
        result = json.loads(response.choices[0].message.content.strip())
        # Cache the result for 5 minutes
        cache_set(conn, "stark_decision", json.dumps(result))
        conn.close()
        return jsonify(result)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Error in Stark decision engine: {error_details}")
        print("🔄 Generating fallback analysis from market data...")
        
        # Generate intelligent fallback from market data
        fallback_result = generate_fallback_decision(pulse_data, headlines)
        
        # Cache the fallback for 2 minutes (shorter than AI cache)
        cache_set(conn, "stark_decision", json.dumps(fallback_result))
        conn.close()
        return jsonify(fallback_result)

@app.route('/api/analysis', methods=['GET'])
def api_analysis():
    """Generate AI-powered market analysis (legacy endpoint)"""
    conn = get_db()
    
    # Get current market data
    pulse_raw = fetch_market_pulse()
    pulse_data = [{"label": l, "value": v, "pct": p} for l, v, p in pulse_raw]
    
    # Get recent headlines
    headlines_raw = fetch_headlines()
    headlines = [asdict(h) for h in headlines_raw[:40]]
    
    # Build analysis context
    analysis_context = "CURRENT MARKET DATA:\n"
    valid_pulse = [p for p in pulse_data if p['value'] is not None and p['pct'] is not None]
    for p in valid_pulse:
        analysis_context += f"- {p['label']}: {p['value']:.2f} ({p['pct']:+.2f}%)\n"
    
    analysis_context += "\nRECENT MARKET NEWS (Top 30):\n"
    for h in headlines[:30]:
        analysis_context += f"- [{h['source']}] {h['title']}\n"
    
    # Generate analysis
    api_key = os.getenv("OPENAI_API_KEY")
    if not OPENAI_AVAILABLE or not api_key:
        return jsonify({
            "analysis": "OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
            "sentiment": "neutral"
        })
    
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert market analyst specializing in Australia and USA markets. Focus on BROAD TRENDS, WHERE MARKETS ARE HEADING, and WHAT COULD HAPPEN NEXT. Think strategically about trends, not minute-by-minute adjustments. Prioritize Australia and USA market news and data."},
                {"role": "user", "content": f"""Analyze the current market situation based on this data, with PRIMARY FOCUS on Australia and USA. Think about BROAD TRENDS and FORWARD-LOOKING ANALYSIS:

{analysis_context}

Provide a comprehensive analysis focused on TRENDS, DIRECTION, and FORECASTS with:
1. MARKET OVERVIEW: 2-3 sentences on the BROAD TREND and FORECAST of where markets are heading with TIMEFRAMES (emphasize Australia and USA). Include what will likely happen, not just what is happening.

2. KEY TRENDS: Top 3-4 significant TRENDS developing with FORECASTS on where they will likely lead over SPECIFIC TIMEFRAMES (prioritize Australia/USA trends). Include future implications.

3. SENTIMENT & DIRECTION: Overall market direction and sentiment with FORECASTS on what this means going forward, focusing on Australia and USA. Include likely outcomes over next X days/weeks/months.

4. WHAT TO WATCH: 3-4 critical trends, catalysts, or developments with FORECASTS on what will likely change direction or accelerate trends (prioritize Australia/USA). Include specific conditions and expected outcomes.

Think about the bigger picture, future trends, and likely outcomes with TIMEFRAMES - not just today's moves. Markets price the future, not the present. Format clearly with section headers."""}
            ],
            temperature=0.4,
            max_tokens=800,
        )
        
        analysis_text = response.choices[0].message.content.strip()
        
        # Extract sentiment
        sentiment = "neutral"
        analysis_lower = analysis_text.lower()
        if any(word in analysis_lower for word in ["bullish", "positive", "gaining", "rally", "upward", "optimistic"]):
            sentiment = "bullish"
        elif any(word in analysis_lower for word in ["bearish", "negative", "declining", "drop", "downward", "fall", "pessimistic"]):
            sentiment = "bearish"
        
        conn.close()
        return jsonify({
            "analysis": analysis_text,
            "sentiment": sentiment,
            "timestamp": int(time.time())
        })
    except Exception as e:
        conn.close()
        return jsonify({
            "analysis": f"Error generating analysis: {str(e)}",
            "sentiment": "neutral"
        })

@app.route('/api/news/synthesis', methods=['GET'])
def api_news_synthesis():
    """Generate synthesized news summary with sentiment"""
    conn = get_db()
    headlines_raw = fetch_headlines()
    headlines = [asdict(h) for h in headlines_raw[:25]]
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not OPENAI_AVAILABLE or not api_key:
        return jsonify({
            "synthesis": "OpenAI API key not configured.",
            "topics": [],
            "sentiment": "neutral"
        })
    
    news_text = "\n".join([f"- [{h['source']}] {h['title']}" for h in headlines])
    
    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a financial news analyst specializing in Australia and USA markets. Synthesize news into key themes and topics, prioritizing Australia and USA coverage."},
                {"role": "user", "content": f"""Synthesize these market news headlines into key themes, with PRIMARY FOCUS on Australia and USA:

{news_text}

Provide:
1. KEY THEMES: 3-4 main themes/topics dominating the news (prioritize Australia/USA themes)
2. SENTIMENT: Overall news sentiment (positive/negative/neutral) for Australia and USA markets
3. TOP STORIES: 3 most important stories with brief context (prioritize Australia/USA stories)

Format clearly with sections. Emphasize Australia and USA market developments."""}
            ],
            temperature=0.3,
            max_tokens=500,
        )
        
        synthesis = response.choices[0].message.content.strip()
        
        # Extract sentiment
        sentiment = "neutral"
        synthesis_lower = synthesis.lower()
        if any(word in synthesis_lower for word in ["positive", "optimistic", "gains", "growth"]):
            sentiment = "positive"
        elif any(word in synthesis_lower for word in ["negative", "concern", "decline", "risk", "worries"]):
            sentiment = "negative"
        
        conn.close()
        return jsonify({
            "synthesis": synthesis,
            "sentiment": sentiment,
            "headlines_count": len(headlines)
        })
    except Exception as e:
        conn.close()
        return jsonify({
            "synthesis": f"Error generating synthesis: {str(e)}",
            "sentiment": "neutral"
        })

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Set OpenAI API key if not already set
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("✅ OpenAI API key loaded from environment")
    else:
        print("⚠️ No OpenAI API key found - set OPENAI_API_KEY environment variable")
    
    import webbrowser
    import threading
    
    def open_browser():
        time.sleep(1.5)
        webbrowser.open('http://127.0.0.1:5001')
    
    threading.Thread(target=open_browser).start()
    print("🚀 Starting Flask server on port 5001...")
    print("📊 Available endpoints:")
    print("   - /api/stark/decision (Stark Decision Engine)")
    print("   - /api/pulse (Market Pulse)")
    print("   - /api/headlines (Headlines)")
    app.run(debug=False, port=5001, use_reloader=False, host='127.0.0.1')

