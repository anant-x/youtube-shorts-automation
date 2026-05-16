#!/bin/bash
# Create shorts.mp4 and upload to YouTube
set -euo pipefail
cd "$(dirname "$0")"

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy

PY311="/opt/homebrew/opt/python@3.11/bin/python3.11"
if [[ ! -x "$PY311" ]]; then
  echo "Install Python 3.11: brew install python@3.11"
  exit 1
fi

# Recreate venv if it points at the wrong Python (e.g. 3.15)
if [[ -x .venv/bin/python ]]; then
  ver="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$ver" != "3.11" ]]; then
    echo "Recreating .venv (was Python $ver, need 3.11)..."
    rm -rf .venv
  fi
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating Python 3.11 venv..."
  "$PY311" -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

if ! .venv/bin/python -c "import moviepy" 2>/dev/null; then
  echo "Installing moviepy..."
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f .env ]]; then
  echo "Missing .env (GROQ_API_KEY, PEXELS_API_KEY)"
  exit 1
fi

set -a
source .env
set +a

echo "=== Step 1: Create shorts.mp4 ==="
if [[ -f voice.mp3 ]] && ls clips/clip_*.mp4 &>/dev/null && [[ ! -f shorts.mp4 ]]; then
  echo "Resuming: assembling from existing voice + clips..."
  .venv/bin/python main.py --assemble-only
else
  .venv/bin/python main.py
fi

if [[ ! -f shorts.mp4 ]]; then
  echo "ERROR: shorts.mp4 was not created. Run: .venv/bin/python main.py"
  exit 1
fi

echo ""
echo "=== Step 2: Upload to YouTube ==="
node app.js

echo ""
echo "=== Done ==="
