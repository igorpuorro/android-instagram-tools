android-instagram-tools for Windows: feed_autoplay + profile_blocker
===================================================================

Two tools for Instagram on your Android phone, nothing to install:
- feed_autoplay.exe plays the videos of your home timeline one after another, optionally at
  2x, liking / commenting / reposting / copying links / saving them;
- profile_blocker.exe blocks every profile in a list (unblock.bat unblocks them again) --
  see "Blocking profiles" below.

Instagram's terms don't allow automated use. Acting at volume can get the account limited.
Use it at your own risk, with sensible settings.


1. Prepare the phone (once)
---------------------------
1. Settings > About phone > tap "Build number" 7 times (enables Developer options).
2. Developer options:
   - "USB debugging" on (for USB), and/or "Wireless debugging" on (for Wi-Fi; phone and
     computer on the same network);
   - "Stay awake" on (screen stays on while charging) -- recommended for long runs.
3. Keep the phone unlocked with Instagram available. If it locks, the tool waits until you
   unlock it (it never tries to unlock it itself).
4. On first connection over USB, accept the "Allow USB debugging?" prompt on the phone.


2. Connect the phone
--------------------
- USB: plug it in. Windows needs the phone maker's USB driver (Samsung: "Samsung Android USB
  Driver for Windows").
- Wi-Fi: double-click connect.bat and follow it (it asks for the numbers shown on the
  phone's Wireless debugging screen). Pairing is needed once; when the phone restarts or
  Wireless debugging is switched on again, its port changes: connect again.
- Done for now: double-click disconnect.bat. It ends the connections and stops adb, which
  otherwise keeps running in the background (adb.exe) after feed_autoplay ends. The pairing
  stays, so connect.bat works again without a new code. To remove this computer for good: on
  the phone, Developer options > Wireless debugging > Paired devices > tap it > Forget.


3. Run
------
Double-click feed_autoplay.exe. It uses the options in settings.txt, which it creates on its
first start with: play all, 2x, like all, repost all, copy link all, save all -- open it
with Notepad to change them (a "#" in front of an option turns it off).
The first time, Windows may say "Windows protected your PC": click "More info", then
"Run anyway" (the app isn't signed with a paid certificate).

Keys while it runs (in its window):
  n next video    p pause (the phone is yours) / resume    x 2x on/off
  w play mode     l like mode    m comment mode    r repost mode    c copy-link mode
  b save mode
  < > phone screen dimmer / brighter (your own brightness comes back at the end)
  a   your own brightness again now (adaptive if it was)
  s statistics    h / ? help     q quit

Using the phone in between: press p, use the phone, press p again. q stops it: the final
statistics are always printed and the window stays open until you press Enter. (Closing the
window with X also stops it, but without the statistics.)

Files: the runs folder next to the exe gets your copied links (shared-links.txt), the posts
you commented (commented.txt) and
diagnostics. It's personal -- don't share it.


Options (settings.txt, or after feed_autoplay.exe in a terminal)
-----------------------------------------------------------------
(default = what applies when an option is left out; the settings.txt created on the
first start sets play all, 2x, and like, repost, copy link and save all)
  --play followed|all            only accounts you follow (default), or every video
  --2x                           play at 2x speed
  --like none|followed|all       like videos watched to the end (default followed)
  --comment none|followed|all    comment on them (default none; public, under your name)
  --comment-text "TEXT"          the comment, e.g. --comment-text "🇧🇷🇧🇷"
  --comment-script FILE          or a script that prints the comment, run for each video:
                                 .bat/.cmd, .ps1, or .py (needs Python from python.org).
                                 It gets IG_AUTHOR (the account), IG_POST (the post's
                                 header), IG_FOLLOWED (1/0), and IG_TEST=1 on the trial run
                                 at start; printing nothing skips the video. A name without a folder is looked up next to the exe.
                                 Example: comment_greeting.bat (a greeting for the time of
                                 day; edit its texts with Notepad, keep it saved as UTF-8).
  --repost none|followed|all     repost them (default none; shown on your profile)
  --share-link none|followed|all Share > Copy link (default none)
  --save none|followed|all       save to your private Saved collection (default none)
  --max-watch S                  stop watching a video after S seconds (default 300)
  --brightness PERCENT           phone screen brightness at start, 1-100 (default: unchanged)
  --battery-stop PERCENT         stop when the phone's battery is this low and not charging
                                 (default 10, warnings from 20; 0 = warnings only)
All options: feed_autoplay.exe --help


Blocking profiles (profile_blocker.exe)
---------------------------------------
1. Double-click profile_blocker.exe once: it creates profiles.txt next to it and stops.
2. Open profiles.txt with Notepad and put the profiles to block in it, one per line: the
   name, @name or the profile's link (https://www.instagram.com/name/). "#" starts a comment.
3. Double-click profile_blocker.exe again: it goes to your profile > menu > Blocked
   ("Bloqueados"), and for each profile taps +, searches the name, taps Block next to exactly
   that name, confirms, and checks the profile is then on your blocked list.
   It waits 20 seconds between profiles (Instagram limits how fast accounts may act).
To undo it: double-click unblock.bat (unblocks the profiles in profiles.txt).
Keys in its window: p pause / resume, s statistics, h help, q quit.
Results: runs\blocked-profiles.txt. A later run skips the profiles already blocked, so a
stopped run just carries on. To try without blocking anything, in a terminal in this folder:
profile_blocker.exe --dry-run (goes as far as the "Block <name>?" question, then cancels).
Works with Instagram in English and Brazilian Portuguese.
All options: profile_blocker.exe --help


Phone-specific settings
-----------------------
Xiaomi, Redmi, POCO (HyperOS / MIUI) -- if the app stops right at start with
"SecurityException: Injecting input events requires ...":
1. Settings > Additional settings > Developer options.
2. Switch on "USB debugging (Security settings)". If it won't switch on: sign in to a Xiaomi
   account and turn mobile data on, then try again.
3. Switch on "Install via USB".
4. Unplug and replug the USB cable, accept the prompt on the phone, start feed_autoplay again.


Troubleshooting
---------------
- "SecurityException: Injecting input events" right at start: see Phone-specific settings.
- "no phone connected": USB -- cable, driver, USB debugging, the prompt on the phone;
  Wi-Fi -- run connect.bat again.
- connect.bat seems stuck at "Starting adb": a freshly started adb first looks for phones on
  the network and can take a minute or two to answer.
- Check the app's own files: feed_autoplay.exe check (in a terminal in this folder).
- Updating: download the new zip from
  https://github.com/igorpuorro/android-instagram-tools/releases/latest (always the newest
  version) and unzip it over this folder; your settings.txt, profiles.txt and the
  runs folder are kept (they aren't in the zip). From 0.5.0 or older: the folder in the
  zip was called feed_autoplay, now android-instagram-tools -- copy settings.txt,
  profiles.txt and the runs folder from the old folder into the new one once, then
  delete the old folder. If Windows says a file is in use, run
  disconnect.bat first (or restart the PC). Since 0.2.2 "Connect phone.bat" is called
  connect.bat, and pause.bat / stop.bat are gone (use p and q in the window): delete the
  old files.
- If scrcpy (screen mirroring) and this app keep disconnecting each other, they use two
  different adb versions: start scrcpy with this app's adb (set ADB to
  <this folder>\_internal\adbutils\binaries\adb.exe).

More: https://github.com/igorpuorro/android-instagram-tools
Third-party licenses: the LICENSES folder.
