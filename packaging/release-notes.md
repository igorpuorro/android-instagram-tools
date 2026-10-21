**feed_autoplay for Windows** — plays the videos of your Instagram home timeline on your
Android phone, one after another, optionally at 2x, liking / reposting / copying links /
saving them. Nothing to install: no Python, no uv, no git.

1. Download `feed_autoplay-windows-<version>.zip` below and unzip it (e.g. to your Desktop).
2. Prepare the phone: Developer options, USB or Wireless debugging — see `README.txt` in the folder.
3. Wi-Fi: double-click **`Connect phone.bat`**. USB: plug the phone in (with the phone maker's USB driver).
4. Double-click **`feed_autoplay.exe`**. Options: `settings.txt` (created on the first start).

Windows may say **"Windows protected your PC"** the first time: click **More info → Run
anyway** (the app isn't signed with a paid certificate). Check the download with the
`.sha256` file: `Get-FileHash feed_autoplay-windows-<version>.zip` in PowerShell must show the
same value.

**Updating:** unzip the new version over the old folder — `settings.txt` and `runs` are kept.

> ⚠ Instagram's terms don't allow automated use. Acting at volume can get the account
> limited (Instagram already refused reposts after ~100 in under 2 hours). Use it at your own
> risk, with sensible settings.

Third-party licenses: the `LICENSES` folder in the zip.
