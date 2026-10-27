@echo off
REM Double-click to start the Lecture Notes app.
cd /d "%~dp0"

REM Start Ollama in the background if it isn't running yet
curl -s http://127.0.0.1:11434/api/version >nul 2>&1
if errorlevel 1 (
    start "" /min "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
    timeout /t 4 >nul
)

"venv\Scripts\python.exe" -m streamlit run NoteTakingApp.py
pause
