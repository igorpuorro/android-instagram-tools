"""Estimate a looping video's period from a recorded trace (self-similarity), as ground truth
for traces whose Instagram log has no end line. See DEVELOPMENT.md section 5.

Command line: analyse the frames feed_autoplay.py saves when a video hits --max-watch
  .venv/bin/python tools/period.py runs/maxwatch-*.npz
"""
import sys

import numpy as np

from tune_fallback import prep


def estimate_period(t, frames, crop=(0.2, 0.70, 0.8), min_period=5.0, step=0.1):
    """(period s, score, contrast) -- score: median frame diff at that lag; contrast: score /
    median score over all lags (low = a clear repetition). Smallest lag within 15 % of the best
    score wins, so a multiple of the period isn't picked."""
    # crop=None: frames are already cropped/resized (as saved by feed_autoplay.py)
    F = np.asarray(frames, dtype=np.float32) if crop is None else np.array([prep(x, *crop) for x in frames])
    span = t[-1]
    lags, scores = [], []
    for lag in np.arange(min_period, span - 20, step):
        j = np.searchsorted(t, t + lag)
        ok = j < len(t)
        i, j = np.nonzero(ok)[0], j[ok]
        close = np.abs(t[j] - t[i] - lag) < 0.2
        if close.sum() < 20:
            continue
        d = np.abs(F[i[close]] - F[j[close]]).mean(axis=(1, 2))
        lags.append(lag)
        scores.append(float(np.median(d)))
    if not scores:
        return None, None, None
    lags, scores = np.array(lags), np.array(scores)
    k = int(scores.argmin())
    # a video also repeats at 2x, 3x ... its period: take the shortest divisor that still
    # repeats nearly as well (best within +-1 s of lag/n)
    for n in range(6, 1, -1):
        near = np.abs(lags - lags[k] / n) <= 1.0
        if near.any():
            j = np.nonzero(near)[0][scores[near].argmin()]
            if scores[j] <= scores[k] * 1.5 + 1.0:
                k = int(j)
                break
    return float(lags[k]), float(scores[k]), float(scores[k] / np.median(scores))


if __name__ == "__main__":
    for fn in sys.argv[1:]:
        z = np.load(fn)
        T, score, contrast = estimate_period(z["t"], z["f"], crop=None)
        if T is not None and contrast <= 0.45:
            print(f"{fn}: LOOPED every {T:.1f} s (contrast {contrast:.2f}) -> the end detection missed it")
        else:
            c = "n/a" if contrast is None else f"{contrast:.2f}"
            print(f"{fn}: no clear repetition (contrast {c}) -> most likely a video longer than the cap")
