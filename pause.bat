@echo off
rem Pauses a running feed_autoplay so you can use the phone (it stops touching it), or resumes
rem it when it is paused: creates / deletes the pause file the app checks about once a second.
cd /d "%~dp0"
if not exist runs mkdir runs
if exist runs\PAUSE (
  del runs\PAUSE
  echo Resume requested -- feed_autoplay carries on.
) else (
  type nul > runs\PAUSE
  echo Pause requested -- the phone is yours. Run pause.bat again to resume.
)
