#!/usr/bin/env python3
"""Pause and statistics timing (DEVELOPMENT.md 4.10, 4.11) on a simulated clock -- no phone needed.

Run: uv run tests/test_pause_stats.py
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

failures = []
lines = []
fa.log = lambda *a: lines.append(" ".join(map(str, a)))


class Clock:
    """Stands in for the time module: sleep() only moves the clock."""
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s

    def strftime(self, *a):
        return "00:00"

    def localtime(self, *a):
        return None


class Keys:
    """Presses scheduled keys once the clock reaches their time: {seconds after start: key}."""
    def __init__(self, clock, schedule):
        self.clock, self.t0, self.schedule = clock, clock.now, dict(schedule)

    def get(self):
        for at in sorted(self.schedule):
            if self.clock.now - self.t0 >= at:
                return self.schedule.pop(at)
        return None


class Device:
    def window_size(self):
        return 1080, 2340


def player(clock, schedule):
    args = argparse.Namespace(play="all", like="none", repost="none", share_link="none", save="none",
                              speed2x=False)
    p = fa.Player(Device(), args, Keys(clock, schedule))
    p.started = clock.now
    return p


def check(name, got, want, tol=1.5):
    if abs(got - want) > tol:
        failures.append(f"{name}: got {got:.1f}, want {want:.1f}")


fa.time = clock = Clock()

# 1. a pause between two played videos is left out of the cycle (the pace)
p = player(clock, {130: "p"})
p.mark_played()
clock.sleep(30)
try:
    p.pause(by_file=False)  # p again at +130 s: paused 100 s; nothing playing -> Resumed
except fa.Resumed:
    pass
clock.sleep(30)
p.mark_played()
check("cycle without the pause", p.cycles[-1], 60)
check("paused total", p.waited["paused"], 100)
check("watch time excludes the pause", clock.now - p.paused_since(p.started) - p.started, 60)

# 2. stats shown while paused count the pause in progress
lines.clear()
p = player(clock, {0: "p", 90: "s", 200: "p"})  # 3600 s run time before the pause
p.started -= 3600
try:
    p.key()
except fa.Resumed:
    pass
block = "\n".join(lines)
m = re.search(r"paused (\d+)m", block)
check("paused shown during a pause (min)", int(m.group(1)) if m else -1, 1, tol=0)
m = re.search(r"\(active (?:(\d+)h )?(\d+)m\)", block)
active = (int(m.group(1) or 0) * 60 + int(m.group(2))) if m else -1
check("active time shown during a pause (min)", active, 60, tol=0)

# 3. a pause during the unlock wait counts as paused, not as locked
p = player(clock, {30: "p", 100: "p"})
unlock_at = clock.now + 300
p.locked = lambda: clock.now < unlock_at
p.d.info = {"screenOn": True}
try:
    p.wake()
except fa.Resumed:
    pass
check("locked time before the pause", p.waited["locked"], 30, tol=2)
check("paused time", p.waited["paused"], 70, tol=2)

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all pause/statistics checks passed")
