#!/usr/bin/env python3
"""Time between videos (DEVELOPMENT.md 4.16) on a simulated phone -- no phone needed: finding the
post just watched, the aimed swipe past it, when the full feed check runs, the shared "before"
read of the counts. Examples use made-up accounts.

Run: uv run tests/test_navigation.py
"""
import argparse
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

failures = []
fa.log = lambda *a: None
W, H = 1080, 2340
RID = fa.RID


def node(rid, y0, y1, desc=""):
    return (f'<node text="" resource-id="{RID}{rid}" class="x" package="com.instagram.android" '
            f'content-desc="{desc}" bounds="[0,{y0}][{W},{y1}]" />')


class Device:
    def __init__(self, xml=""):
        self.xml, self.swipes, self.dumps = xml, [], 0

    def window_size(self):
        return W, H

    def dump_hierarchy(self):
        self.dumps += 1
        return self.xml

    def swipe(self, x0, y0, x1, y1, duration):
        self.swipes.append((y0, y1, duration))


def player(xml=""):
    p = fa.Player(Device(xml), argparse.Namespace(play="all", like="none", repost="none", share_link="none",
                                                  save="none", speed2x=False, max_scrolls=40), None)
    return p


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


fa.time.sleep = lambda s: None

# --- the post just watched, found although its time label moved on --------------------------
watched = "chef.marco posted a video 50 minutes ago"
now = "chef.marco posted a video 51 minutes ago"
xml = node("row_feed_profile_header", 300, 440, now) + node("media_group", 300, 2060)  # starts at the header's top
p = player(xml)
check("found by author + time, media from the header's top", p.watched_media_box(watched), (0, 300, W, 2060))
xml2 = node("row_feed_profile_header", 300, 440, now) + node("media_group", 440, 1800)  # starts below the header
check("media starting right below the header", player(xml2).watched_media_box(watched), (0, 440, W, 1800))
other = node("row_feed_profile_header", 300, 440, "garden_tales posted a video 51 minutes ago") + node("media_group", 300, 2060)
check("another account: not found", player(other).watched_media_box(watched), None)
older = node("row_feed_profile_header", 300, 440, "chef.marco posted a video 3 hours ago") + node("media_group", 300, 2060)
check("same account, another post: not found", player(older).watched_media_box(watched), None)

# --- the aimed swipe past it ---------------------------------------------------------------
p = player(xml)  # tall video: reaches 2060 > 0.85·h
p.scroll_past(watched)
check("tall video: swipe from 0.85·h to 0.10·h", p.d.swipes, [(int(H * 0.85), int(H * 0.10), 0.5)])
short = node("row_feed_profile_header", 300, 440, now) + node("media_group", 300, 1200)
p = player(short)
p.scroll_past(watched)
check("short video: from just below it", p.d.swipes, [(1200 + int(H * 0.05), int(H * 0.10), 0.5)])
p = player(other)
p.scroll_past(watched)
check("not found: the fixed scroll as before", p.d.swipes, [(int(H * 0.75), int(H * 0.75 - H * 0.35), 0.4)])
for name, y1 in (("tall", 2060), ("short", 1200)):
    start = min(y1 + int(H * 0.05), int(H * 0.85))
    below = y1  # anything below the video lies at or below its bottom
    check(f"{name}: nothing below the video ends above 0.05·h", below - (start - int(H * 0.10)) >= int(H * 0.05) - 1, True)

# --- when the full feed check runs -----------------------------------------------------------
clock = types.SimpleNamespace(now=10000.0)
fa.time.time = lambda: clock.now
p = player()
calls = []
p.ensure_feed = lambda: (calls.append("full"), setattr(p, "feed_checked", clock.now))
p.in_feed = lambda: True
p.back_to_feed()
check("first time: full check", calls, ["full"])
clock.now += 60
p.back_to_feed()
check("60 s later, feed there: quick", calls, ["full"])
clock.now += 61
p.back_to_feed()
check("over 120 s: full check", calls, ["full", "full"])
clock.now += 10
p.in_feed = lambda: (setattr(clock, "now", clock.now + 0.5), False)[1]  # no feed (locked, another app)
p.back_to_feed()
check("no feed within 2 s: full check at once", calls, ["full", "full", "full"])

# --- the counts before a video's actions: one screen read shared ----------------------------
counts = ('<node content-desc="The like number is 1,204. View likes" />'
          '<node content-desc="Reposted 49 times" /><node content-desc="Save number is 39" />')
p = player(counts)
p.before_xml = None
got = (p.exact_count("like", before=True), p.exact_count("repost", before=True), p.exact_count("save", before=True))
check("before counts", got, (1204, 49, 39))
check("one read for all three", p.d.dumps, 1)
p.d.xml = counts.replace("39", "40")
check("after a tap: read fresh", (p.exact_count("save"), p.d.dumps), (40, 2))

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all navigation checks passed")
