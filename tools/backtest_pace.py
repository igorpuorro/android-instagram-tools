#!/usr/bin/env python3
"""Backtest the stats' pace estimate on run logs (DEVELOPMENT.md 4.8).

At a checkpoint every 10 videos, compares the estimate from the cycle times so far with the
number of videos actually played in the following hour. Hours containing a long wait (lock
screen, outage: a gap > 15 min) are skipped; such gaps are also left out of the cycle times,
as the app does.

Usage: .venv/bin/python tools/backtest_pace.py runs/*.log
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as ia  # noqa: E402  (uses the app's own constants)

GAP = 900  # s: longer cycles are waits, not videos


def starts(path):
    """Datetimes of the '▶' (video opened) lines; the date only matters across midnight."""
    out, day, prev = [], datetime(2000, 1, 1), None
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"(\d\d:\d\d:\d\d) ▶ ", line)
        if not m:
            continue
        t = datetime.combine(day.date(), datetime.strptime(m.group(1), "%H:%M:%S").time())
        if prev and t < prev:
            day += timedelta(days=1)
            t += timedelta(days=1)
        out.append(t)
        prev = t
    return out


def weighted(c):
    c = np.asarray(c, float)
    w = 0.5 ** (np.arange(len(c))[::-1] / ia.Player.PACE_HALF_LIFE)
    return 3600 / np.average(c, weights=w)


ESTIMATORS = {
    "median of last 20": lambda c: 3600 / np.median(c[-20:]),
    "mean of last 20": lambda c: 3600 / np.mean(c[-20:]),
    "mean of whole run": lambda c: 3600 / np.mean(c),
    "weighted mean (used)": weighted,
}


def main():
    err = {k: [] for k in ESTIMATORS}
    inside = total = 0
    lo_f, hi_f = ia.Player.PACE_RANGE
    for path in sys.argv[1:]:
        S = starts(path)
        C = [(b - a).total_seconds() for a, b in zip(S, S[1:])]
        for k in range(20, len(S), 10):
            c = [x for x in C[:k] if x <= GAP]
            end = S[k] + timedelta(hours=1)
            if end > S[-1] or len(c) < 20:
                continue
            nxt = [t for t in S[k:] if t < end]
            gaps = [(b - a).total_seconds() for a, b in zip(nxt, nxt[1:])]
            if gaps and max(gaps) > GAP:
                continue
            for name, f in ESTIMATORS.items():
                err[name].append(f(c) - len(nxt))
            est = weighted(c)
            total += 1
            inside += est * lo_f <= len(nxt) <= est * hi_f
    if not total:
        sys.exit("no usable checkpoints (runs need > 1 h without long waits)")
    print(f"{total} checkpoints from {len(sys.argv) - 1} logs (estimate minus videos in the next hour):")
    for name, e in err.items():
        e = np.array(e)
        print(f"  {name:22} mean abs error {np.abs(e).mean():5.1f}   bias {e.mean():+5.1f}")
    print(f"  'likely' range x{lo_f}-x{hi_f}: actual inside {inside}/{total} = {inside / total * 100:.0f}%")


if __name__ == "__main__":
    main()
