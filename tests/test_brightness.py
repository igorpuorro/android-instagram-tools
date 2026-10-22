#!/usr/bin/env python3
"""Brightness keys and restore (DEVELOPMENT.md 4.13) on a simulated phone -- no phone needed.

Run: uv run tests/test_brightness.py
"""
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

failures = []
lines = []
fa.log = lambda *a: lines.append(" ".join(map(str, a)))


class Phone:
    """adb shell `settings` for screen_brightness(_mode); counts the shell calls."""
    def __init__(self, level=128, mode=1, refuse=False, ignore=False, slow_put=0.0):
        self.settings = {"screen_brightness": level, "screen_brightness_mode": mode}
        self.refuse, self.ignore, self.slow_put = refuse, ignore, slow_put
        self.calls = []

    def shell(self, cmd):
        self.calls.append(cmd)
        if self.refuse:
            raise RuntimeError("permission denied")
        out = []
        for part in cmd.split(";"):
            words = part.split()
            if words[:3] == ["settings", "get", "system"]:
                out.append(str(self.settings[words[3]]))
            elif words[:3] == ["settings", "put", "system"]:
                time.sleep(self.slow_put)
                if not self.ignore:
                    self.settings[words[3]] = int(words[4])
        return types.SimpleNamespace(output="\n".join(out))

    def state(self):
        return self.settings["screen_brightness"], self.settings["screen_brightness_mode"]


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# from the phone's own level (128/255 = 50 %, adaptive on): > goes to 60 %, adaptive off
phone = Phone()
b = fa.Brightness(lambda: phone)
b.step(up=True)
b._wait()
check("> from 50 %", (b.pct, phone.state()), (60, (153, 0)))
for _ in range(3):
    b.step(up=False)
b._wait()
check("< three times from 60 %", (b.pct, phone.state()), (30, (76, 0)))
for _ in range(6):
    b.step(up=False)
b._wait()
check("< stops at 1 %", (b.pct, phone.state()), (1, (3, 0)))
check("minimum logged", lines[-1], "☀ brightness 1% (minimum)   (< dimmer · > brighter)")
for _ in range(20):
    b.step(up=True)
b._wait()
check("> stops at 100 %", (b.pct, phone.state()), (100, (255, 0)))
check("log line", lines[-1], "☀ brightness 100% (maximum)   (< dimmer · > brighter)")

# after the first change a press is one `settings put` of the level (no reads, no mode)
before = len(phone.calls)
b.step(up=False)
b._wait()
check("one write per press", phone.calls[before:], ["settings put system screen_brightness 230"])

# restore: the phone's own level and adaptive mode back
b.restore()
check("restore", phone.state(), (128, 1))

# a slow phone: a press returns at once (the write happens in the background), and quick
# presses collapse into one write of the last level
phone = Phone(level=128, mode=1, slow_put=0.5)
b = fa.Brightness(lambda: phone)
b.step(up=False)  # first press: reads the phone's own level (fast), writes in the background
t = time.time()
for _ in range(4):
    b.step(up=False)
check("presses don't wait for the phone", time.time() - t < 0.2, True)
b._wait()
check("slow phone: last level applied", (b.pct, phone.state()), (5, (13, 0)))
puts = [c for c in phone.calls if "put system screen_brightness " in c]
check("slow phone: presses collapsed", len(puts) < 5, True)
b.restore()
check("slow phone: restored", phone.state(), (128, 1))

# pause: own brightness while held, a change while paused applies on resume
phone = Phone(level=200, mode=0)
b = fa.Brightness(lambda: phone)
b.set(20)
b.hold()
check("held: phone's own", phone.state(), (200, 0))
b.step(up=True)
b._wait()
check("change while held: not applied yet", (b.pct, phone.state()), (30, (200, 0)))
check("change while held: logged", lines[-1], "☀ brightness 30% (applied when resumed)   (< dimmer · > brighter)")
b.restore()  # e.g. quitting while paused: nothing to do, the phone has its own already
check("restore while held", phone.state(), (200, 0))
b.release()
b._wait()
check("release: app's level again", phone.state(), (76, 0))
b.restore()
check("restore after the pause", phone.state(), (200, 0))

# a pause without the app ever changing brightness: nothing touched
phone = Phone(level=90, mode=1)
b = fa.Brightness(lambda: phone)
b.hold()
b.release()
b.restore()
check("never set: untouched", (phone.state(), phone.calls), ((90, 1), []))

# key a: the phone's own brightness again; the app then leaves it alone, also after a pause
phone = Phone(level=40, mode=1)
b = fa.Brightness(lambda: phone)
b.give_back()
check("a before any change: nothing written", phone.calls, [])
check("a before any change: logged", lines[-1], "☀ brightness: already the phone's own   (< > to set it)")
b.step(up=False)
b._wait()
check("< then a: app's level first", phone.state(), (26, 0))
b.give_back()
check("a: the phone's own back", (phone.state(), b.pct), ((40, 1), None))
check("a: logged", lines[-1], "☀ brightness: the phone's own (adaptive)   (< > to set it again)")
b.hold()
b.release()
b._wait()
check("a, then pause/resume: left alone", phone.state(), (40, 1))
phone.settings["screen_brightness"] = 200  # the user (or adaptive) changed it meanwhile
b.step(up=False)
b._wait()
check("< after a: from the phone's level now (200 = 78 % -> 70 %)", (b.pct, phone.state()), (70, (178, 0)))
b.restore()
check("restore after a and <: the phone's level from before that <", phone.state(), (200, 1))
# a while paused: the phone already has its own; resuming leaves it alone
phone = Phone(level=60, mode=0)
b = fa.Brightness(lambda: phone)
b.set(30)
b.hold()
b.give_back()
b.release()
b._wait()
check("a while paused: left alone after resume", (phone.state(), b.pct), ((60, 0), None))
check("a while paused: logged as manual", lines[-1], "☀ brightness: the phone's own (manual)   (< > to set it again)")

# a phone that refuses (error) or ignores the write: one message, the run carries on
for kind in ("refuse", "ignore"):
    lines.clear()
    phone = Phone(**{kind: True})
    b = fa.Brightness(lambda: phone)
    b.step(up=True)
    b._wait()
    b.step(up=True)
    b._wait()
    b.restore()
    msgs = [x for x in lines if "can't be changed" in x]
    check(f"{kind}: one message", len(msgs), 1)
    check(f"{kind}: broken", b.broken, True)

# --brightness accepts 1..100 only
for value, ok in (("1", True), ("100", True), ("0", False), ("101", False), ("abc", False)):
    try:
        fa.percent(value)
        got = True
    except Exception:
        got = False
    check(f"--brightness {value}", got, ok)

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all brightness checks passed")
