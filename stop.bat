@echo off
rem Stops a running feed_autoplay cleanly (it prints its final statistics first): creates the
rem stop file the app checks about once a second. Works for minimized/background windows too.
cd /d "%~dp0"
if not exist runs mkdir runs
type nul > runs\STOP
echo Stop requested -- feed_autoplay will finish in a moment.
