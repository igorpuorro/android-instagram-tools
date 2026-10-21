@echo off
rem Guided phone connection over Wi-Fi debugging: pairing (once per computer) and connecting.
rem Over USB nothing is needed: plug the phone in with USB debugging on.
cd /d "%~dp0"
chcp 65001 >nul
feed_autoplay.exe connect
echo.
pause
