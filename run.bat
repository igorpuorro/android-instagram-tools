@echo off
rem feed_autoplay launcher for Windows -- double-click it, or run it from a terminal with options:
rem   run.bat --play all --2x --like all
rem The first run sets up Python and the packages by itself (uv); later runs start at once.
rem Stop: press q in this window, or run stop.bat (e.g. for a minimized window).
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv is not installed. Install it once, then run this again:
    echo     winget install --id astral-sh.uv
    echo or see https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

rem Windows Terminal / modern consoles show the log's symbols; this makes older ones use UTF-8
chcp 65001 >nul

uv run feed_autoplay.py %*

echo.
echo feed_autoplay has stopped.
pause
