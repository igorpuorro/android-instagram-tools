feed_autoplay for Windows
=========================

Plays the videos of your Instagram home timeline on your Android phone, one after another,
optionally at 2x, liking / reposting / copying links / saving them. Nothing to install.

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
first start with: play all, 2x, like all, repost followed, copy link all, save all -- open it
with Notepad to change them (a "#" in front of an option turns it off).
The first time, Windows may say "Windows protected your PC": click "More info", then
"Run anyway" (the app isn't signed with a paid certificate).

Keys while it runs (in its window):
  n next video    p pause (the phone is yours) / resume    x 2x on/off
  w play mode     l like mode    r repost mode    c copy-link mode    b save mode
  s statistics    h help         q quit

Using the phone in between: press p, use the phone, press p again. q stops it: the final
statistics are always printed and the window stays open until you press Enter. (Closing the
window with X also stops it, but without the statistics.)

Files: the runs folder next to the exe gets your copied links (shared-links.txt) and
diagnostics. It's personal -- don't share it.


Options (settings.txt, or after feed_autoplay.exe in a terminal)
-----------------------------------------------------------------
  --play followed|all            only accounts you follow (default), or every video
  --2x                           play at 2x speed
  --like none|followed|all       like videos watched to the end (default followed)
  --repost none|followed|all     repost them (default none; shown on your profile)
  --share-link none|followed|all Share > Copy link (default none)
  --save none|followed|all       save to your private Saved collection (default none)
  --max-watch S                  stop watching a video after S seconds (default 300)
All options: feed_autoplay.exe --help


Troubleshooting
---------------
- "no phone connected": USB -- cable, driver, USB debugging, the prompt on the phone;
  Wi-Fi -- run connect.bat again.
- connect.bat seems stuck at "Starting adb": a freshly started adb first looks for phones on
  the network and can take a minute or two to answer.
- Check the app's own files: feed_autoplay.exe check (in a terminal in this folder).
- Updating: download the new zip and unzip it over this folder; your settings.txt and the
  runs folder are kept (they aren't in the zip). If Windows says a file is in use, run
  disconnect.bat first (or restart the PC). Since 0.2.2 "Connect phone.bat" is called
  connect.bat, and pause.bat / stop.bat are gone (use p and q in the window): delete the
  old files.
- If scrcpy (screen mirroring) and this app keep disconnecting each other, they use two
  different adb versions: start scrcpy with this app's adb (set ADB to
  <this folder>\_internal\adbutils\binaries\adb.exe).

More: https://github.com/igorpuorro/android-instagram-tools
Third-party licenses: the LICENSES folder.
