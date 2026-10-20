#!/bin/bash
cd "$(dirname "$0")"
echo "===================================================="
echo "  🎯 JobHunter Pro - Making the job hunting simple  "
echo "===================================================="

if [ ! -d ".venv" ]; then
    echo "📦 First-time setup: Creating isolated environment & installing free libraries..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    echo "✅ Setup complete! You will never have to install anything again."
else
    source .venv/bin/activate
fi

echo "🚀 Launching Web Portal in your browser..."
streamlit run app.py
