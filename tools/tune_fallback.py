#!/usr/bin/env python3
"""Score frame-comparison loop-detector settings against recorded traces.

Ground truth: the time one pass takes (period T, in real seconds). From the Instagram log's
duration when the trace has a logged end (T = duration / speed); otherwise estimated from the
trace itself by self-similarity (tools/period.py), used only when the repetition is clear
(contrast <= 0.45) -- that estimate agreed with the log on 24/25 traces, the one miss had
contrast 0.96.

The detector can only match once playback returns to the point where its reference frames
were taken, i.e. at about ref_start + T. Scoring:
  - miss: no fire, or later than ref_start + T + 6 s (the video replays);
  - early (a false loop: the video gets cut short): before the true end when the log gives
    it (ends reconstructed from duration + one logged end); for traces with an estimated
    period only, the true end is unknown, so conservatively: before ref_start + T - 1 s.
    (Firing between the true end and ref_start + T is fine: the restarting video can look
    like the references.)
Offsets are reported relative to ref_start + T. Results are ranked by successes, then
fewest early fires, then lowest mean latency. The last line shows the settings currently
used by feed_autoplay.py for that speed (keep CURRENT in sync with feed_autoplay.DETECTOR).

The trace folders are local only (git-ignored): record them with tools/record_traces.py.

Usage: uv run tools/tune_fallback.py tools/traces       (2x traces)
       uv run tools/tune_fallback.py tools/traces_1x    (1x traces)
Takes a few minutes (pure CPU, no phone needed).
"""
import glob
import itertools
import sys

import numpy as np
from PIL import Image

H, W = 234, 108  # trace frame size
# (crop y0, y1, x1 as screen fractions) and
# (ref_start, ref_window, max_refs, loop_thresh, loop_rel, move_thresh, consecutive)
# per playback speed, mirroring feed_autoplay.DETECTOR
CURRENT = {
    2: ((0.12, 0.70, 0.8), (1.0, 3.0, 5, 6, 0.5, 12, 1)),
    1: ((0.20, 0.70, 0.8), (0.5, 3.0, 15, 6, 0.0, 12, 1)),
}


def prep(f, y0, y1, x1):
    """Same as Player.frame(): crop, then 48x64 grayscale."""
    im = Image.fromarray(f[int(H * y0):int(H * y1), :int(W * x1)])
    return np.asarray(im.resize((48, 64)), dtype=np.float32)


def detect(t, F, rs, win, nmax, loop, rel, move, consec):
    """Mirror of the detector in Player.watch() (plus the window/consecutive knobs)."""
    refs, moved, diffs, run = [], False, [], 0
    for ti, f in zip(t, F):
        if ti < rs:
            continue
        if ti < rs + win and len(refs) < nmax or not refs:
            refs.append(f)
            continue
        d = min(float(np.abs(f - r).mean()) for r in refs)
        diffs.append(d)
        if d > move:
            moved = True
        hit = moved and ti > rs + 3 and (d < loop or (rel and len(diffs) > 5 and d < rel * np.median(diffs)))
        run = run + 1 if hit else 0
        if run >= consec:
            return ti
    return None


def first_true_end(trace, ref_start):
    """First real end after the references were taken (log traces only), else None."""
    name, t, _, period, speed, ends = trace
    if not len(ends):
        return None
    e = ends[0][0]
    while e - period > ref_start + 0.5:
        e -= period
    while e <= ref_start + 0.5:
        e += period
    return e


def score(traces, Fs, cfg):
    """(successes, early fires, mean offset of successes, per-trace offsets)."""
    ok, early, lat, detail = 0, 0, [], []
    for trace, F in zip(traces, Fs):
        t, period = trace[1], trace[3]
        got = detect(t, F, *cfg)
        if got is None:
            detail.append("miss")
            continue
        off = got - (cfg[0] + period)
        detail.append(f"{off:+.0f}")
        end = first_true_end(trace, cfg[0])
        if (got < end - 0.5) if end is not None else (off < -1.0):
            early += 1
        elif off <= 6.0:
            ok += 1
            lat.append(off)
    return ok, early, (np.mean(lat) if lat else 99.0), detail


def load(folder):
    """[(name, t, frames, period s, speed, logged ends)] for traces with usable ground truth."""
    from period import estimate_period
    out = []
    for fn in sorted(glob.glob(folder + "/r*.npz")):
        z = np.load(fn)
        speed = int(z["speed"]) if "speed" in z else 2  # first traces predate the field
        if len(z["ends"]):
            period = z["ends"][0][1] / 1000.0 / speed
        else:
            period, _, contrast = estimate_period(z["t"], z["f"])
            if period is None or contrast > 0.45:
                continue
        if period + 4 < z["t"][-1]:  # at least one full pass after the references
            out.append((fn.split("/")[-1], z["t"], z["f"], period, speed, z["ends"]))
    return out


def main():
    if len(sys.argv) < 2 or not glob.glob(sys.argv[1] + "/r*.npz"):
        sys.exit("no traces found: the recorded data isn't in the repository (DEVELOPMENT.md 5) -- "
                 "record some with tools/record_traces.py, e.g.\n"
                 "  uv run tools/record_traces.py tools/traces 20 75")
    traces = load(sys.argv[1])
    print("traces with ground truth:", len(traces))

    crops = [(0.12, 0.70, 0.8), (0.2, 0.70, 0.8)]
    # (earlier, wider grids showed consecutive=2, a lower crop bottom and ref_start 2.5 never help)
    grid = list(itertools.product([0.5, 1.0, 1.5], [3.0, 5.0], [5, 15, 30], [6, 8, 10],
                                  [0, 0.3, 0.45], [12], [1]))
    results = []
    for crop in crops:
        Fs = [np.array([prep(x, *crop) for x in tr[2]]) for tr in traces]
        for cfg in grid:
            ok, early, lat, detail = score(traces, Fs, cfg)
            results.append((ok, -early, -lat, crop, cfg, detail))
    results.sort(key=lambda r: r[:3], reverse=True)
    print("ok / early / mean offset from ref_start+T | crop | (ref_start, ref_window, max_refs, loop_thresh, rel, move, consecutive)")
    for ok, e, ml, crop, cfg, det in results[:15]:
        print(f"{ok}/{len(traces)} early={-e} lat={-ml:.1f}s | {crop} | {cfg} | {' '.join(det)}")
    speeds = {tr[4] for tr in traces}
    for ok, e, ml, crop, cfg, det in results:
        for sp in speeds:
            if (crop, cfg) == CURRENT[sp]:
                print(f"CURRENT ({sp}x): {ok}/{len(traces)} early={-e} lat={-ml:.1f}s | {' '.join(det)}")


if __name__ == "__main__":
    main()
