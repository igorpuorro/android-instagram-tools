@echo off
rem Unblock the profiles in profiles.txt again (undoes profile_blocker.exe).
cd /d "%~dp0"
chcp 65001 >nul
profile_blocker.exe --unblock %*
echo.
pause
