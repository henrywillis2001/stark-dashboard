#!/bin/bash
# Launch StarkHub Dashboard

cd "$(dirname "$0")"
source .venv/bin/activate

# Set OpenAI API key - try multiple sources
if [ -f .env ]; then
    source .env
    echo "✅ Loaded API key from .env file"
elif [ -n "$OPENAI_API_KEY" ]; then
    echo "✅ Using API key from environment"
else
    echo "⚠️  WARNING: No API key found. Dashboard will use fallback analysis."
    echo "   Set OPENAI_API_KEY in .env file or export it in your shell."
fi

python3 app.py


