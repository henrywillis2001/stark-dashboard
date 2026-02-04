#!/bin/bash
# Kill any existing server and restart

echo "🛑 Killing existing processes on port 5000..."
lsof -ti:5000 | xargs kill -9 2>/dev/null || echo "No process found"

echo "🛑 Killing Python app.py processes..."
ps aux | grep "python.*app.py" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || echo "No Python processes found"

sleep 2

echo "🚀 Starting server..."
cd "$(dirname "$0")"
source .venv/bin/activate

# Set OpenAI API key
export OPENAI_API_KEY="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"

python3 app.py
