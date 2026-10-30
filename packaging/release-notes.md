**android-instagram-tools for Windows** — two tools for Instagram on your Android phone,
nothing to install (no Python, no uv, no git):
- **`feed_autoplay.exe`** plays the videos of your home timeline one after another, optionally
  at 2x, liking / commenting / reposting / copying links / saving them. *0.7.0:* the comment
  can come from a script, a different one per video — `--comment-script comment_greeting.bat`
  (in the folder: a greeting for the time of day; edit its texts with Notepad). *0.8.0:* it
  watches the phone's battery — warns, and stops cleanly at 10 % when not charging
  (`--battery-stop`). *0.9.0:* about 3.5–4 s less between videos (fewer swipes, shorter
  waits; switching the phone's battery saver off saves ~2 s more). *0.9.1:* likes are counted
  right again — a change on Instagram's side had the tool undo them ("like did not register");
  refused likes are counted and pause liking;
- **`profile_blocker.exe`** *(0.5.0: about twice as fast)* blocks every profile in a list (`profiles.txt`,
  created on its first start), through your blocked accounts list (Bloqueados → +);
  **`unblock.bat`** unblocks them again (0.5.1: also through the list). Instagram in English
  or Brazilian Portuguese.

1. Download `android-instagram-tools-windows-<version>.zip` below and unzip it (e.g. to your Desktop).
2. Prepare the phone: Developer options, USB or Wireless debugging — see `README.txt` in the folder.
3. Wi-Fi: double-click **`connect.bat`**. USB: plug the phone in (with the phone maker's USB driver).
   When you're done, **`disconnect.bat`** ends the connections and stops adb.
4. Double-click **`feed_autoplay.exe`**. Options: `settings.txt` (created on the first start).
   To block profiles: double-click **`profile_blocker.exe`** (first time: it creates
   `profiles.txt` — put the profiles in it with Notepad, then start it again).

Windows may say **"Windows protected your PC"** the first time: click **More info → Run
anyway** (the app isn't signed with a paid certificate). Check the download with the
`.sha256` file: `Get-FileHash android-instagram-tools-windows-<version>.zip` in PowerShell must show the
same value.

**Updating:** run `disconnect.bat`, then unzip the new version over the old folder —
`settings.txt`, `profiles.txt` and `runs` are kept. **From 0.5.0 or older** the folder in the zip
was called `feed_autoplay`; now it is `android-instagram-tools`: copy your `settings.txt`,
`profiles.txt` and `runs` folder from the old folder into the new one once, then delete the old
folder. (Up to 0.2.1 the folder also had `Connect phone.bat` — now
`connect.bat` — `pause.bat` and `stop.bat`: delete them; use **p** and **q** in the app's window.)

> ⚠ Instagram's terms don't allow automated use. Acting at volume can get the account
> limited (Instagram already refused reposts after ~100 in under 2 hours). Use it at your own
> risk, with sensible settings.

Third-party licenses: the `LICENSES` folder in the zip.
