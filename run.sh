#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1

if [ ! -d venv ]; then
  echo "First-time setup: creating virtual environment..."
  python3 -m venv venv || { echo "Python 3 not found. Install Python 3.9+ first."; exit 1; }
fi

source venv/bin/activate
pip install -q -r requirements.txt

echo
echo "Starting Knowledge Bot... (press Ctrl+C to stop)"
echo 'Laptop: use the Local URL below.'
echo 'Phone mirror: Network URL + /?mode=display'
echo
streamlit run app.py --server.address 0.0.0.0
