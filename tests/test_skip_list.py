#!/usr/bin/env python3
"""The skip list (DEVELOPMENT.md 4.17) without a phone: the file, the authors of a feed post,
the cache, reloading (by itself and with key u), the skip in the feed scan. Examples use
made-up accounts.

Run: uv run tests/test_skip_list.py
"""
import argparse
import os
import sys
import tempfile
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

failures = []
lines = []
fa.log = lambda *a: lines.append(" ".join(map(str, a)))
tmp = Path(tempfile.mkdtemp())


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# --- the file ---------------------------------------------------------------------------------
f = tmp / "skip-profiles.txt"
f.write_text("# profiles to skip\nchef.marco\n@Garden_Tales   # a comment\n"
             "https://www.instagram.com/news.channel/\nnot a name!\nchef.marco\n", encoding="utf-8")
sl = fa.SkipList(f)
check("loaded", sl.refresh(), True)
check("names (lower case, no duplicates)", sl.names, frozenset({"chef.marco", "garden_tales", "news.channel"}))
check("line not understood", sl.bad, ((5, "not a name!"),))
check("describe", sl.describe(), "3 profiles (skip-profiles.txt) · 1 line(s) not understood: 5")
check("missing file", (fa.SkipList(tmp / "none.txt").refresh(), fa.SkipList(tmp / "none.txt").describe()),
      (False, "none (none.txt not found)"))

# --- the authors of a post ------------------------------------------------------------------
for desc, want in [
    ("chef.marco posted a video 2 hours ago", ["chef.marco"]),
    ("chef.marco posted a video in Lisbon, Portugal on 1 day ago", ["chef.marco"]),
    ("brand.store and chef.marco posted a video 3 hours ago", ["brand.store", "chef.marco"]),
    ("brand.store and 2 others posted a video 3 hours ago", ["brand.store"]),
    ("chef.marco postou um video em Há 7 horas", ["chef.marco"]),
    ("brand.store e chef.marco postou um video em Há 7 horas", ["brand.store", "chef.marco"]),
    ("brand.store e mais 2 postou um video em Há 7 horas", ["brand.store"]),
]:
    check(f"authors {desc!r}", sl.authors(desc), want)

# --- matching ---------------------------------------------------------------------------------
check("listed author", sl.match("chef.marco posted a video 2 hours ago"), "chef.marco")
check("case doesn't matter", sl.match("GARDEN_TALES postou um video em Há 2 horas"), "GARDEN_TALES")
check("listed co-author", sl.match("brand.store and chef.marco posted a video 3 hours ago"), "chef.marco")
check("not listed", sl.match("brand.store posted a video 3 hours ago"), None)
check("a listed name inside another doesn't count", sl.match("chef.marco.fan posted a video 1 hour ago"), None)

# --- the cache: parsed once per version of the file; edits are picked up by themselves -------
fa.load_skip_list.cache_clear()
sl = fa.SkipList(f)
sl.refresh()
for _ in range(50):
    sl.refresh()  # one os.stat each, no reading
check("50 looks, one parse", fa.load_skip_list.cache_info().misses, 1)
time.sleep(0.01)
f.write_text("chef.marco\n", encoding="utf-8")
os.utime(f, ns=(time.time_ns(), time.time_ns() + 10**9))  # a clearly newer modification time
check("edited: read again by itself", (sl.refresh(), sl.names), (True, frozenset({"chef.marco"})))
check("unchanged since: nothing to do", sl.refresh(), False)
check("forced (key u): read again", (sl.refresh(force=True), fa.load_skip_list.cache_info().misses), (True, 1))


# --- in the feed scan: skipped without opening, logged, counted -----------------------------
def node(desc, y0, y1):
    return (f'<node text="" resource-id="{fa.HEADER}" class="x" package="com.instagram.android" '
            f'content-desc="{desc}" bounds="[0,{y0}][1080,{y1}]" />')


xml = ("<hierarchy>" + node("chef.marco posted a video 2 hours ago", 300, 440)
       + node("brand.store posted a video 3 hours ago", 1500, 1640) + "</hierarchy>")
dev = types.SimpleNamespace(window_size=lambda: (1080, 2340), dump_hierarchy=lambda: xml)
p = fa.Player(dev, argparse.Namespace(play="all", skip_profiles=f), None)
lines.clear()
found = p.find_video_header()
check("the listed post is passed over", found[0] if found else None, "brand.store posted a video 3 hours ago")
check("logged", lines[-1], "⏭ auto-skipped (skip list: chef.marco): chef.marco posted a video 2 hours ago")
check("counted", p.stats["auto_skipped"], 1)
p.find_video_header()
check("not counted twice for the same post", p.stats["auto_skipped"], 1)

# key u: reload and report
p.keys = types.SimpleNamespace(get=lambda: "u")
lines.clear()
p.poll()
check("key u", lines[-1], "skip list reloaded: 1 profile (skip-profiles.txt)")

if failures:
    print(f"{len(failures)} FAILED:")
    for x in failures:
        print("  " + x)
    sys.exit(1)
print("all skip list checks passed")
