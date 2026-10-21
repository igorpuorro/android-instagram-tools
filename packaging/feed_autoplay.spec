# PyInstaller spec: feed_autoplay as a one-folder app (DEVELOPMENT.md 1, "Windows app").
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

a = Analysis(
    [str(ROOT / "feed_autoplay.py")],
    pathex=[str(ROOT)],
    datas=datas,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)

version_file = None
if sys.platform == "win32":  # file properties of the exe (also a small plus for antivirus heuristics)
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct,
                                                     StringTable, VarFileInfo, VarStruct, VSVersionInfo)
    nums = tuple(int(x) for x in VERSION.split(".")) + (0,)
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[StringFileInfo([StringTable("040904B0", [
                  StringStruct("ProductName", "android-instagram-tools"),
                  StringStruct("FileDescription", "feed_autoplay"),
                  StringStruct("FileVersion", VERSION),
                  StringStruct("ProductVersion", VERSION),
                  StringStruct("InternalName", "feed_autoplay"),
                  StringStruct("OriginalFilename", "feed_autoplay.exe")])]),
              VarFileInfo([VarStruct("Translation", [1033, 1200])])])
    version_file = Path(workpath) / "version_info.txt"
    version_file.write_text(str(info), encoding="utf-8")

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # one folder: the exe plus _internal/, nothing unpacked at start
    name="feed_autoplay",
    console=True,
    upx=False,  # compressed exes are flagged by antivirus more often
    version=str(version_file) if version_file else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="feed_autoplay", upx=False)
