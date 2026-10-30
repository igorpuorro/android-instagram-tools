#!/usr/bin/env python3
"""The like action (DEVELOPMENT.md 4.7) on a simulated phone -- no phone needed: how a like is
confirmed (flag, count, heart icon), when a second tap happens, and refusals.

Run: uv run tests/test_like.py
"""
import argparse
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

failures = []
lines = []
fa.log = lambda *a: lines.append(" ".join(map(str, a)))
fa.time.sleep = lambda s: None


class Phone:
    """The player: a like button whose flag/label, count and heart change after taps."""
    def __init__(self, count=100, flag=False, count_step=1, icon=True, refuse=False, liked_before=False):
        self.count, self.flag, self.count_step, self.icon, self.refuse = count, flag, count_step, icon, refuse
        self.liked = liked_before
        self.clicks = 0
        self.pressed = []

    # the like button
    def click(self):
        self.clicks += 1
        if self.refuse:
            return
        self.liked = not self.liked
        self.count += self.count_step if self.liked else -self.count_step

    @property
    def info(self):
        on = self.liked and self.flag
        return {"selected": on, "contentDescription": "Like", "bounds": {}}

    # the device
    def window_size(self):
        return 1080, 2340

    def dump_hierarchy(self):
        return f'<node content-desc="The like number is {self.count}. View likes" />'

    def __call__(self, **kw):
        refusal = self.refuse and self.clicks > 0 and "textMatches" in kw
        return types.SimpleNamespace(exists=refusal)

    def press(self, key):
        self.pressed.append(key)


def player(phone):
    p = fa.Player(phone, argparse.Namespace(play="all", like="all"), None)
    p.heart_looks_liked = lambda bounds: phone.icon and phone.liked
    p.before_xml = None
    return p


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


def like(phone):
    p = player(phone)
    lines.clear()
    p.tap_like(phone, count_kind="like")
    return p


# the flag flips (older Instagram, the feed): liked after one tap
ph = Phone(flag=True)
p = like(ph)
check("flag: liked", (lines[-1], ph.clicks, ph.liked, p.stats["liked"]), ("  ♥ liked", 1, True, 1))

# the flag stays off (Instagram 451 pt-BR, 2026-10-30) but the count goes up: liked, NO second tap
ph = Phone(flag=False, icon=False)
p = like(ph)
check("count only: liked, one tap", (lines[-1], ph.clicks, ph.liked), ("  ♥ liked", 1, True))

# no exact count (abbreviated), the heart drawn liked: liked, one tap
ph = Phone(flag=False, count_step=0)
p = like(ph)
check("icon only: liked, one tap", (lines[-1], ph.clicks, ph.liked), ("  ♥ liked", 1, True))


# a lost tap: nothing changes after the first; the second tap likes
class LostFirstTap(Phone):
    def click(self):
        self.clicks += 1
        if self.clicks > 1:
            super().click()
            self.clicks -= 1  # super() counted it again


ph = LostFirstTap(flag=False, icon=False)
p = like(ph)
check("lost tap: second tap", (lines[-1], ph.clicks, ph.liked), ("  ♥ liked (second tap)", 2, True))

# nothing ever shows the like: two taps, "did not register"
ph = Phone(flag=False, count_step=0, icon=False)
p = like(ph)
check("nothing: did not register", (lines[-1], ph.clicks), ("  ♡ like did not register", 2))

# Instagram refuses: counted, likes paused, not tapped again
ph = Phone(refuse=True)
p = like(ph)
check("refused: counted", (p.stats["like_refused"], p.stats["liked"], ph.clicks), (1, 0, 1))
check("refused: logged", lines[-1].startswith("  ⚠ Instagram refused the like"), True)
check("refused: likes paused", p.should_like(True), False)
check("refused: next pause doubles", p.like_backoff, 2 * fa.REPOST_BACKOFF_MIN)

# already liked (heart red) before tapping: left alone
ph = Phone(liked_before=True)
p = player(ph)
p.is_liked = lambda like, check_icon=True: True
lines.clear()
p.tap_like(ph, count_kind="like")
check("already liked: no tap", (lines[-1], ph.clicks), ("  ♥ already liked", 0))


# it had been liked although nothing showed it: the tap removed it (count down) -> restored
class HiddenLike(Phone):
    @property
    def info(self):
        return {"selected": False, "contentDescription": "Like", "bounds": {}}


ph = HiddenLike(liked_before=True, icon=False)
p = player(ph)
p.is_liked = lambda like, check_icon=True: False
lines.clear()
p.tap_like(ph, count_kind="like")
check("hidden like removed: restored", (lines[-1], ph.clicks, ph.liked), ("  ⚠ like had been on (count 100 -> 99); restored it", 2, True))

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all like checks passed")
