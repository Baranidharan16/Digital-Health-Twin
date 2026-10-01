@echo off
REM One-click start for Windows: double-click this file.
REM Creates the Python environment on first run, then starts the twin at http://localhost:8000
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating Python environment...
  %PY% -m venv .venv || goto :error
)
call ".venv\Scripts\activate.bat"

echo [2/3] Installing Python packages (first run takes a minute)...
python -m pip install -q --disable-pip-version-check -r requirements-dev.txt || goto :error

if not exist "frontend\dist\index.html" (
  echo Building the website - this needs Node.js from nodejs.org ...
  pushd frontend
  call npm install || goto :error
  call npm run build || goto :error
  popd
)

echo [3/3] Starting the Human Health Digital Twin at http://localhost:8000  (press Ctrl+C to stop)
echo       Phones on the same Wi-Fi can connect too: open My data - Connect your Android phone.
echo       If Windows Firewall asks about Python, tick "Private networks" and Allow.
start "" cmd /c "timeout /t 7 >nul & start http://localhost:8000"
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
goto :eof

:error
echo.
echo Something failed above. Read the message, fix it, and run run.bat again.
pause
