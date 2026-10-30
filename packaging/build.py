#!/usr/bin/env python3
"""Build the Windows app (feed_autoplay + profile_blocker) as a one-folder zip (DEVELOPMENT.md 1).

  uv run --group build packaging/build.py

On Windows this makes the release zip (GitHub Actions runs it on every v* tag); on Linux it
builds the same bundle for Linux, to test the bundling without a Windows PC. Steps: PyInstaller
(packaging/feed_autoplay.spec), add the files users need next to the exe, collect the
third-party license notices, self-check the app, check the contents, zip + SHA-256.
Output: build/android-instagram-tools-<windows|linux>-<version>.zip, everything in one folder
android-instagram-tools/ (feed_autoplay/ up to 0.5.0)
"""
import hashlib
import importlib.metadata as md
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
WINDOWS = os.name == "nt"
PLATFORM = "windows" if WINDOWS else "linux"
# files next to the exes (Windows only: connect.bat, disconnect.bat, unblock.bat,
# comment_greeting.bat, README.txt);
# settings.txt and profiles.txt are bundled instead: the apps create them on first start, so
# updates keep the user's own
CREATED = ("settings.txt", "profiles.txt")
EXTRAS = sorted(f for f in (ROOT / "packaging" / "windows").iterdir() if f.name not in CREATED)
# must never be in the bundle (private data, see .gitignore)
FORBIDDEN = re.compile(r"(^|/)(runs|\.env|traces|traces_1x|icon_samples|\.git)(/|$)")


def version():
    """The version, checked: pyproject.toml == feed_autoplay.__version__ (== the tag on CI)."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    app = re.search(r'__version__ = "([^"]+)"', (ROOT / "feed_autoplay.py").read_text(encoding="utf-8")).group(1)
    if project != app:
        sys.exit(f"version mismatch: pyproject.toml {project}, feed_autoplay.py {app}")
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and tag != f"v{app}":
        sys.exit(f"tag {tag} doesn't match the version v{app}")
    return app


def runtime_dists():
    """The distributions the app ships: the project's dependencies and theirs (not the build tools)."""
    roots = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    seen, todo = {}, [Requirement(r) for r in roots]
    while todo:
        req = todo.pop()
        if req.marker and not req.marker.evaluate({"extra": ""}):
            continue
        name = req.name.lower().replace("_", "-")
        if name in seen:
            continue
        dist = md.distribution(req.name)
        seen[name] = dist
        todo += [Requirement(r) for r in dist.requires or []]
    return sorted(seen.values(), key=lambda d: d.metadata["Name"].lower())


def collect_licenses(dest):
    """Third-party license notices: every shipped package, Python, PyInstaller's bootloader, adb."""
    dest.mkdir()
    index = ["Third-party software in this folder and the licenses it is distributed under.", ""]
    for dist in runtime_dists() + [md.distribution("pyinstaller")]:
        name = dist.metadata["Name"]
        files = [f for f in dist.files or [] if ".dist-info" in str(f)
                 and re.search(r"LICEN[CS]E|COPYING|NOTICE", f.name, re.I)]
        if not files:
            sys.exit(f"no license file found for {name}")
        for f in files:
            shutil.copy(f.locate(), dest / f"{name}-{dist.version}-{f.name}")
        lic = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "see files"
        what = " (bootloader in feed_autoplay.exe)" if name.lower() == "pyinstaller" else ""
        index.append(f"{name} {dist.version}{what}: {lic.splitlines()[0][:80]}")
    py = Path(sys.base_prefix)
    py_license = next((p for p in (py / "LICENSE.txt",
                                   py / "lib" / f"python{sys.version_info[0]}.{sys.version_info[1]}" / "LICENSE.txt")
                       if p.exists()), None)
    if not py_license:
        sys.exit("Python's LICENSE.txt not found")
    shutil.copy(py_license, dest / f"Python-{sys.version.split()[0]}-LICENSE.txt")
    index.append(f"Python {sys.version.split()[0]}: PSF License Agreement")
    apache = next(f for f in md.distribution("packaging").files if f.name == "LICENSE.APACHE")
    shutil.copy(apache.locate(), dest / "adb-Apache-2.0.txt")
    index.append("adb (Android SDK Platform-Tools, shipped by adbutils): Apache License 2.0 -- "
                 "source: https://android.googlesource.com/platform/packages/modules/adb/")
    (dest / "README.txt").write_text("\n".join(index) + "\n", encoding="utf-8")


def main():
    ver = version()
    app = BUILD / "dist" / "android-instagram-tools"
    shutil.rmtree(BUILD / "dist", ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"),
                    str(ROOT / "packaging" / "feed_autoplay.spec")], check=True)
    if WINDOWS:
        for f in EXTRAS:
            shutil.copy(f, app / f.name)
    collect_licenses(app / "LICENSES")

    ext = ".exe" if WINDOWS else ""
    for name, cmd in (("feed_autoplay", ["check"]), ("feed_autoplay", ["--help"]),
                      ("feed_autoplay", ["adb", "version"]), ("profile_blocker", ["--help"])):
        exe = app / (name + ext)
        print(f"$ {exe.name} {' '.join(cmd)}", flush=True)
        subprocess.run([str(exe), *cmd], check=True, stdin=subprocess.DEVNULL, cwd=BUILD)

    shutil.rmtree(app / "runs", ignore_errors=True)  # in case the checks created them
    for name in CREATED:
        (app / name).unlink(missing_ok=True)
    names = [p.relative_to(app).as_posix() for p in app.rglob("*")]
    bad = [n for n in names if FORBIDDEN.search(n)]
    if bad:
        sys.exit(f"private or unexpected files in the bundle: {bad[:10]}")

    zip_base = BUILD / f"android-instagram-tools-{PLATFORM}-{ver}"
    zip_path = Path(shutil.make_archive(str(zip_base), "zip", root_dir=app.parent, base_dir=app.name))
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    # "\n" line end on every system: `sha256sum -c` (Linux/macOS) fails on Windows' "\r\n"
    zip_path.with_suffix(".zip.sha256").write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8",
                                                    newline="\n")
    size = zip_path.stat().st_size / 1e6
    print(f"\n{zip_path.relative_to(ROOT)}  {size:.0f} MB  {len(names)} files  sha256 {digest[:16]}…")


if __name__ == "__main__":
    main()
