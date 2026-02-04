#!/bin/bash
# Launch StarkHub Dashboard

cd "$(dirname "$0")"
source .venv/bin/activate

# Set OpenAI API key
# Set your API key here or export it in your shell profile
# export OPENAI_API_KEY="your-api-key-here"
source .env 2>/dev/null || echo "No .env file found - make sure OPENAI_API_KEY is set"

python3 app.py


