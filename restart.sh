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
# Set your API key here or export it in your shell profile
# export OPENAI_API_KEY="your-api-key-here"
source .env 2>/dev/null || echo "No .env file found - make sure OPENAI_API_KEY is set"

python3 app.py
