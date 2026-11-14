@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/3] 创建虚拟环境...
  python -m venv .venv
  if errorlevel 1 (
    echo 创建失败：请确认已安装 Python 3.10+ 并加入 PATH
    pause
    exit /b 1
  )
)

echo [2/3] 安装依赖...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo 依赖安装失败，可尝试国内镜像：
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  pause
  exit /b 1
)

echo [3/3] 启动服务...
cd backend
"..\.venv\Scripts\python.exe" main.py
pause