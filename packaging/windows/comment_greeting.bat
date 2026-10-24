@echo off
rem Example --comment-script for feed_autoplay.exe: a greeting for the time of day, picked at
rem random. feed_autoplay runs it before each comment and posts what it prints (one line).
rem To use it, in settings.txt:
rem   --comment followed
rem   --comment-script comment_greeting.bat
rem The video comes in: IG_AUTHOR (the account), IG_POST (the post's header), IG_FOLLOWED
rem (1 = you follow the account) and IG_TEST (1 on the trial run at start, nothing is posted).
rem Print nothing to leave a video without a comment. Edit the texts below with Notepad and
rem keep the file in UTF-8 (Notepad: Save as, Encoding UTF-8) so emoji come out right.
setlocal
chcp 65001 >nul

set "h=%time:~0,2%"
set "h=%h: =0%"
set /a hour=1%h% - 100
set /a pick=(%random% + 1%time:~-2%) %% 3

if %hour% lss 5 goto night
if %hour% lss 12 goto morning
if %hour% lss 18 goto afternoon
:night
set "g0=Boa noite! 🌙"
set "g1=Boa noite, adorei! 🇧🇷"
set "g2=Ótimo vídeo, boa noite! ✨"
goto chosen
:morning
set "g0=Bom dia! ☀️"
set "g1=Bom dia, ótimo vídeo! 🇧🇷"
set "g2=Que manhã boa com esse vídeo! ☕"
goto chosen
:afternoon
set "g0=Boa tarde! 👏"
set "g1=Boa tarde, muito bom! 🇧🇷"
set "g2=Excelente, boa tarde! 🙌"
:chosen
call set "text=%%g%pick%%%"

rem name the accounts you follow (a co-authored post has spaces in IG_AUTHOR); delete these
rem four lines to never mention anyone
if not defined IG_AUTHOR goto say
if not "%IG_FOLLOWED%"=="1" goto say
if "%IG_AUTHOR: =%"=="%IG_AUTHOR%" set "text=@%IG_AUTHOR% %text%"
:say
echo(%text%
