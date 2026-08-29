#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 fehlt. Auf dem Mac: xcode-select --install"
  echo "Danach: brew install python"
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo
echo "App startet im Browser unter http://localhost:8501"
echo "Zum Beenden: Ctrl+C im Terminal."
echo
exec streamlit run app.py --server.headless true
