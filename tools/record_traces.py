#!/usr/bin/env python3
"""Record test data for tuning the frame-comparison loop detector.

For each video (full-screen player only): open it, lock 2x if --speed 2, then for SECS
seconds save small full-screen grayscale screenshots (108x234) with timestamps, plus the
arrival times of Instagram's end-of-video log lines (the ground truth).

Output: OUT/r<n>.npz with arrays
  t      (N,)        seconds since recording started (after the 2x lock at --speed 2)
  f      (N,234,108) uint8 frames
  ends   (K,2)       [seconds since start, duration ms] of each logged end
  speed  ()          playback speed (1 or 2); older 2x traces lack it

The output folders hold screenshots of your feed and are git-ignored (DEVELOPMENT.md 5).

Usage (from the project folder, phone connected, Instagram logged in):
  uv run tools/record_traces.py tools/traces 10 75 --first 13          # 2x
  uv run tools/record_traces.py tools/traces_1x 10 150 --speed 1       # 1x
At 1x record long enough for ~2 passes of a typical video (150 s).
Nothing gets liked; suggested videos are recorded too (--play all behaviour).
"""
import argparse
import sys
import time
from argparse import Namespace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as ia  # noqa: E402
import uiautomator2 as u2  # noqa: E402


class NoKeys:
    def get(self):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("count", type=int)
    ap.add_argument("secs", type=float)
    ap.add_argument("--first", type=int, default=0, help="index of the first trace file")
    ap.add_argument("--speed", type=int, choices=[1, 2], default=2)
    a = ap.parse_args()

    a.out.mkdir(parents=True, exist_ok=True)
    d = u2.connect(ia.pick_serial())
    p = ia.Player(d, Namespace(max_scrolls=40, play="all"), NoKeys())
    truth = ia.EndWatcher(d.serial)
    d.screen_on()
    p.ensure_feed()
    n, end = a.first, a.first + a.count
    while n < end:
        opened = p.open_next_video()
        if not opened:
            continue
        if opened[0] != "player":  # in-feed videos have no 2x and a different crop
            p.scroll(0.35, settle=0.6)
            continue
        if a.speed == 2:
            p.speed_2x()
        t0, ts, frames = time.time(), [], []
        while time.time() - t0 < a.secs:
            im = d.screenshot().convert("L")
            ts.append(time.time() - t0)
            frames.append(np.asarray(im.resize((108, 234)), dtype=np.uint8))
        ends = [(e - t0, dur) for e, dur in truth.ends_since(t0 - 0.5)]
        np.savez_compressed(a.out / f"r{n}.npz", t=np.array(ts), f=np.array(frames),
                            ends=np.array(ends, dtype=float).reshape(-1, 2), speed=a.speed)
        print(n, len(ts), "frames; log ends (s, ms):", [(round(x, 1), y) for x, y in ends], flush=True)
        n += 1
        d.press("back")
        time.sleep(1.0)
        p.ensure_feed()
        p.scroll(0.35, settle=0.6)
    truth.stop()


if __name__ == "__main__":
    main()
