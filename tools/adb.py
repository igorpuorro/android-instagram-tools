#!/usr/bin/env python3
"""Run the adb that comes with the Python packages (adbutils) -- no separate adb install needed,
the same on Linux, macOS and Windows. All arguments are passed to adb unchanged:

  uv run tools/adb.py devices
  uv run tools/adb.py pair <ip:port> <code>     # Wireless debugging -> "Pair device with pairing code"
  uv run tools/adb.py connect <ip:port>         # the IP & port shown on the Wireless debugging screen

feed_autoplay uses this same adb (one adb server for everything).
"""
import subprocess
import sys

import adbutils


def main():
    sys.exit(subprocess.call([adbutils.adb_path(), *sys.argv[1:]]))


if __name__ == "__main__":
    main()
