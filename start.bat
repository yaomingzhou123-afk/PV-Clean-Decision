@echo off
setlocal
cd /d "%~dp0"

echo [1/4] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install Python 3.10+ and check "Add to PATH".
  pause
  exit /b 1
)

echo [2/4] Installing dependencies...
python -m pip install "fastapi>=0.115" "uvicorn>=0.34" "httpx>=0.28" -i https://mirrors.aliyun.com/pypi/simple --user
if errorlevel 1 (
  echo Dependency install failed. Check network and retry.
  pause
  exit /b 1
)

echo [3/4] Checking .env...
if not exist ".env" (
  if exist ".env.example" copy ".env.example" ".env" >nul
  echo .env created. Fill LLM_API_KEY and save, then run start.bat again.
  notepad .env
  pause
  exit /b 1
)
powershell -NoProfile -Command "if (-not (Select-String -Path '.env' -Pattern '^LLM_API_KEY=.+')) { exit 1 }"
if errorlevel 1 (
  echo LLM_API_KEY is empty in .env. Fill it and save, then run start.bat again.
  notepad .env
  pause
  exit /b 1
)

echo [4/4] Starting server at http://127.0.0.1:8001
start "" http://127.0.0.1:8001
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd backend
python main.py
pause