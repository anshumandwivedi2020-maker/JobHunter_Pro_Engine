@echo off
cd /d "%~dp0"
echo ====================================================
echo   JobHunter Pro - Making the job hunting simple
echo ====================================================

if not exist ".venv" (
    echo First-time setup: Creating environment and installing free libraries...
    python -m venv .venv
    call .venv\Scripts\activate
    python -m pip install --upgrade pip --quiet
    pip install -r requirements.txt --quiet
    echo Setup complete!
) else (
    call .venv\Scripts\activate
)

echo Launching Web Portal in your browser...
streamlit run app.py
pause
