@echo off
cd /d "%~dp0"

if not exist venv (
    echo First-time setup: creating virtual environment...
    python -m venv venv || (echo Python not found. Install Python 3.9+ first. & pause & exit /b 1)
)

call venv\Scripts\activate
pip install -q -r requirements.txt

echo.
echo Starting Knowledge Bot... (close this window to stop)
echo Laptop: use the Local URL below.
echo Phone mirror: Network URL + /?mode=display
echo.
streamlit run app.py --server.address 0.0.0.0
pause
