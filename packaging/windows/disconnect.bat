@echo off
rem Ends the phone connections and stops adb (it keeps running in the background after
rem feed_autoplay ends). The pairing stays: connect.bat works again without a new code.
cd /d "%~dp0"
chcp 65001 >nul
feed_autoplay.exe disconnect
echo.
pause
