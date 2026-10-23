# PyInstaller spec: feed_autoplay and profile_blocker as one one-folder app (DEVELOPMENT.md 1,
# "Windows app"): two exes next to each other, sharing one _internal folder.
# Built by packaging/build.py -- on Windows for the release, on Linux to test the same bundle.
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "([^"]+)"', (ROOT / "feed_autoplay.py").read_text(encoding="utf-8")).group(1)

# data the app finds at run time (FROZEN paths in feed_autoplay.py); listed one by one, so
# nothing else from the project folder (runs/, .env, tuning data) can get in
datas = [(str(ROOT / "assets" / "icon_masks.npz"), "assets")]
# uiautomator2 installs its helper app on the phone from these
datas += collect_data_files("uiautomator2", includes=["assets/u2.jar", "assets/app-uiautomator.apk",
                                                       "assets/version.json"])
# adb (adb.exe + its DLLs in the Windows package)
datas += collect_data_files("adbutils", includes=["binaries/*"])
# default settings.txt, copied next to the exe on first start (not in the zip itself, so
# unzipping an update over the folder keeps the user's settings)
datas += [(str(ROOT / "packaging" / "windows" / "settings.txt"), ".")]
# profile_blocker's example profiles.txt, created next to the exe on first start (same reason)
datas += [(str(ROOT / "packaging" / "windows" / "profiles.txt"), ".")]


def version_info(name):
    """File properties of the exe (also a small plus for antivirus heuristics); Windows only."""
    if sys.platform != "win32":
        return None
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                     StringTable, VarFileInfo, VarStruct, VSVersionInfo)
    nums = tuple(int(x) for x in VERSION.split(".")) + (0,)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
                  StringStruct("ProductName", "android-instagram-tools"),
                  StringStruct("FileDescription", name),
                  StringStruct("FileVersion", VERSION),
                  StringStruct("ProductVersion", VERSION),
                  StringStruct("InternalName", name),
                  StringStruct("OriginalFilename", f"{name}.exe")])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])
    path = Path(workpath) / f"version_info_{name}.txt"
    path.write_text(str(info), encoding="utf-8")
    return str(path)


parts = []
for name in ("feed_autoplay", "profile_blocker"):  # profile_blocker imports feed_autoplay
    a = Analysis([str(ROOT / f"{name}.py")], pathex=[str(ROOT)], datas=datas, excludes=["tkinter"])
    exe = EXE(
        PYZ(a.pure),
        a.scripts,
        [],
        exclude_binaries=True,  # one folder: the exe plus _internal/, nothing unpacked at start
        name=name,
        console=True,
        upx=False,  # compressed exes are flagged by antivirus more often
        version=version_info(name),
    )
    parts += [exe, a.binaries, a.datas]
# one folder for both: the shared files (Python, packages, adb) are in _internal once
# the zip's one top-level folder, named after the project (feed_autoplay up to 0.5.0)
coll = COLLECT(*parts, name="android-instagram-tools", upx=False)
