@echo off
chcp 65001 >nul 2>&1
title 洛克王国世界 - 知识图谱可视化

echo ============================================================
echo   洛克王国世界 知识图谱可视化服务器
echo ============================================================
echo.

:: 尝试激活 conda 环境
set "CONDA_ENV=TraeAI-4"
for /f "delims=" %%i in ('where conda 2^>nul') do set "CONDA_PATH=%%i"

if defined CONDA_PATH (
    echo [提示] 检测到 conda，正在激活环境 %CONDA_ENV%...
    for /f "delims=" %%a in ('conda info --base 2^>nul') do set "CONDA_ROOT=%%a"
    if defined CONDA_ROOT (
        call "%CONDA_ROOT%\Scripts\activate.bat" "%CONDA_ENV%" 2>nul
    )
)

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [错误] 未找到 Python
    echo 请确保已安装 Python 或 conda 环境 "%CONDA_ENV%" 存在
    echo.
    pause
    exit /b 1
)

echo [检查] 正在检查依赖...
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo [安装] 正在安装 flask...
    pip install flask
)

python -c "import flask_socketio" >nul 2>&1
if %errorlevel% neq 0 (
    echo [安装] 正在安装 flask-socketio...
    pip install flask-socketio
)

echo.
echo [启动] 正在启动服务器...
echo [提示] 浏览器访问 http://127.0.0.1:5000
echo [提示] 按 Ctrl+C 可停止服务器
echo.

:: 切换到项目根目录
cd /d "%~dp0.."

:: 启动服务器
python knowledge_graph_server.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 服务器启动失败，错误码: %errorlevel%
)

echo.
echo [提示] 服务器已停止
pause
