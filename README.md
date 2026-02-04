# MarketPulse - Professional Market Intelligence Dashboard

A professional web-based dashboard for market intelligence, task management, and AI-powered briefs.

## Features

- **Ops**: Task management with SQLite storage (tasks persist in `starkhub.db`)
- **News**: RSS headline aggregation with deduplication (Australia + USA focused)
- **Market Pulse**: Real-time indices, rates, FX, commodities tracking (ASX, US markets, global context)
- **AI Briefs**: OpenAI-powered brief generation with strict RAG formatting (prevents hallucination)

## Installation

1. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. (Optional) Set up OpenAI API key for AI briefs:
```bash
export OPENAI_API_KEY="your-api-key-here"
```
Or create a `.env` file (not included in repo for security).

**Note**: The app works without OpenAI - it will use a placeholder brief generator. Tasks are stored in SQLite (`starkhub.db`) and persist between sessions.

## Usage

**Launch the Tony Stark-style Web Dashboard:**

1. Navigate to the Dashboard directory:
```bash
cd ~/Desktop/Dashboard
```

2. Run the launcher (it will open in your browser automatically):
```bash
./launch.sh
```

Or manually:
```bash
source .venv/bin/activate
python3 app.py
```

The dashboard will open automatically in your default web browser at `http://127.0.0.1:5000`

**Note**: 
- The web dashboard runs as a standalone application in your browser
- It features a clean, professional interface optimized for market data
- Real-time market data from multiple sources (Yahoo Finance, Stooq)
- All data is cached for fast loading
- The app auto-refreshes every 5 minutes

### Keyboard Shortcuts

- `h` - Go to Home
- `t` - Go to Tasks
- `n` - Go to News
- `b` - Go to Brief
- `r` - Refresh data
- `q` - Quit

### Tasks

- Type a task in the input field and press Enter to add
- Click or select a task to mark it as done

### Brief Generation

1. Click "Build Retrieval Pack" to see the data that will be sent to the AI
2. Click "Generate Brief" to create a brief (currently uses placeholder; ready for LLM integration)

## Configuration

Edit `starkhub.py` to customize:

- `RSS_SOURCES`: Add or remove RSS feeds
- `STOOQ_SYMBOLS`: Modify market indices to track
- `CACHE_TTL_SEC`: Adjust cache duration (default: 10 minutes)

## Database

Tasks are automatically stored in a SQLite database (`starkhub.db`) in the project directory. The database includes:
- **tasks table**: Stores all your tasks with creation and completion timestamps
- **cache table**: Caches RSS feeds and market data for fast loading

The database is created automatically on first run. Tasks persist between sessions.

## AI Brief Generation

The brief generator uses OpenAI's GPT-4o-mini model with:
- **Strict RAG**: Only summarizes the retrieval pack (no hallucination)
- **Constrained output**: Fixed format (Market State, What Matters, Risks, Setup, Headlines)
- **Low temperature** (0.3): More factual, consistent output
- **Error handling**: Falls back gracefully if API is unavailable

To use AI briefs, set the `OPENAI_API_KEY` environment variable. Without it, the app uses a placeholder.

## Data Sources

- **Market Data**: Stooq (CSV endpoints) - ASX 200, S&P 500, NASDAQ, Dow, VIX, Gold, Oil, Treasury yields, AUD/USD
- **News**: Reuters, WSJ, FT, AFR, Bloomberg, RBA, US Fed RSS feeds

All data is cached locally (10-minute TTL) for fast startup and offline access.

