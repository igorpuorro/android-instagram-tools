#!/bin/sh
# Container entrypoint (feed_autoplay, profile_blocker) -- see CONTAINER.md.
#
#   pair <ip:port> <code>   one-time pairing with the phone (Wireless debugging ->
#                           "Pair device with pairing code"); the key is kept in /root/.android
#   adb <args...>           run the bundled adb (e.g. "adb devices")
#   tool <script> <args>    run a tools/ script (e.g. "tool period.py runs/maxwatch-....npz")
#   block <list> <options>  connect to $PHONE, then run profile_blocker.py (e.g. "block runs/profiles.txt")
#   <app options...>        connect to $PHONE, then run feed_autoplay.py with these options
set -e

case "$1" in
  pair)
    shift
    if [ $# -lt 1 ]; then
      echo "usage: pair <ip:port> [code]   (ip:port and code from 'Pair device with pairing code')" >&2
      exit 2
    fi
    exec adb pair "$@"
    ;;
  adb)
    shift
    exec adb "$@"
    ;;
  tool)
    shift
    script="$1"; shift
    exec python -u "/app/tools/$script" "$@"
    ;;
esac

app=feed_autoplay.py
if [ "$1" = block ]; then
  shift
  app=profile_blocker.py
fi

case " $* " in
  *" -h "*|*" --help "*) exec python -u "/app/$app" "$@" ;;   # help needs no phone
esac

if [ -n "$PHONE" ]; then
  # The phone's IP:port is shown under Developer options -> Wireless debugging. The port
  # changes whenever wireless debugging is switched on again or the phone restarts.
  ok=""
  for i in 1 2 3 4 5; do
    adb connect "$PHONE" >/dev/null 2>&1 || true
    if adb devices | grep -q "^$PHONE[[:space:]]*device"; then ok=1; break; fi
    sleep 2
  done
  if [ -z "$ok" ]; then
    echo "could not connect to the phone at $PHONE" >&2
    echo "- check the IP address & port shown under Developer options -> Wireless debugging" >&2
    echo "  (the port changes when wireless debugging is re-enabled or the phone restarts)" >&2
    echo "- first time on this PC? pair once: ... run --rm app pair <ip:port> <code>" >&2
    adb devices >&2 || true
    exit 1
  fi
else
  echo "PHONE is not set (e.g. PHONE=192.168.1.23:41235 in .env); using whatever adb already sees" >&2
fi

exec python -u "/app/$app" "$@"
