**android-instagram-tools for Windows** — two tools for Instagram on your Android phone,
nothing to install (no Python, no uv, no git):
- **`feed_autoplay.exe`** plays the videos of your home timeline one after another, optionally
  at 2x, liking / reposting / copying links / saving them;
- **`profile_blocker.exe`** *(new in 0.4.0)* blocks every profile in a list (`profiles.txt`,
  created on its first start); **`unblock.bat`** unblocks them again. English or Brazilian
  Portuguese Instagram.

1. Download `feed_autoplay-windows-<version>.zip` below and unzip it (e.g. to your Desktop).
2. Prepare the phone: Developer options, USB or Wireless debugging — see `README.txt` in the folder.
3. Wi-Fi: double-click **`connect.bat`**. USB: plug the phone in (with the phone maker's USB driver).
   When you're done, **`disconnect.bat`** ends the connections and stops adb.
4. Double-click **`feed_autoplay.exe`**. Options: `settings.txt` (created on the first start).
   To block profiles: double-click **`profile_blocker.exe`** (first time: it creates
   `profiles.txt` — put the profiles in it with Notepad, then start it again).

Windows may say **"Windows protected your PC"** the first time: click **More info → Run
anyway** (the app isn't signed with a paid certificate). Check the download with the
`.sha256` file: `Get-FileHash feed_autoplay-windows-<version>.zip` in PowerShell must show the
same value.

**Updating:** run `disconnect.bat`, then unzip the new version over the old folder —
`settings.txt`, `profiles.txt` and `runs` are kept. (Up to 0.2.1 the folder also had `Connect phone.bat` — now
`connect.bat` — `pause.bat` and `stop.bat`: delete them; use **p** and **q** in the app's window.)

> ⚠ Instagram's terms don't allow automated use. Acting at volume can get the account
> limited (Instagram already refused reposts after ~100 in under 2 hours). Use it at your own
> risk, with sensible settings.

Third-party licenses: the `LICENSES` folder in the zip.
