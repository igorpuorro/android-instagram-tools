#!/usr/bin/env python3
"""Comment feature pieces that need no phone (DEVELOPMENT.md 4.7e): the record of commented
posts across runs, settings.txt with a quoted comment text, the m key without a text.
Examples use made-up accounts.

Run: uv run tests/test_comment.py
"""
import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import feed_autoplay as fa  # noqa: E402

failures = []
lines = []
fa.log = lambda *a: lines.append(" ".join(map(str, a)))
tmp = Path(tempfile.mkdtemp())


class Device:
    def window_size(self):
        return 1080, 2340


def player(**kw):
    args = dict(play="all", like="none", repost="none", share_link="none", save="none",
                comment="followed", comment_text="🇧🇷🇧🇷", speed2x=False)
    args.update(kw)
    return fa.Player(Device(), argparse.Namespace(**args), None)


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


# --- the record of commented posts (runs/commented.txt) ------------------------------------
fa.COMMENTED = tmp / "commented.txt"
p = player()
check("nothing recorded yet", p.already_commented("chef.marco posted a video 2 hours ago"), False)
p.record_comment("chef.marco posted a video 2 hours ago")
p.record_comment("news.channel posted a video 7 October")
p.record_comment("garden_tales postou um video em Há 5 horas")
check("same post, same run", p.already_commented("chef.marco posted a video 2 hours ago"), True)

later = player()  # a new run reads the file
check("next run: same post", later.already_commented("chef.marco posted a video 2 hours ago"), True)
real_time = time.time
fa.time.time = lambda: real_time() + 3 * 3600  # three hours later the label says 5 hours ago
later = player()
check("3 h later, label moved on", later.already_commented("chef.marco posted a video 5 hours ago"), True)
check("3 h later, another post", later.already_commented("chef.marco posted a video 2 hours ago"), False)
fa.time.time = real_time
check("absolute date", later.already_commented("news.channel posted a video 7 October"), True)
check("pt-BR header", later.already_commented("garden_tales postou um video em Há 5 horas"), True)
check("other account", later.already_commented("brand.store posted a video 2 hours ago"), False)
check("file lines", len(fa.COMMENTED.read_text(encoding="utf-8").splitlines()), 3)

# --- settings.txt: a quoted text with spaces and emoji, # comments ----------------------------
fa.SETTINGS_FILE = tmp / "settings.txt"
fa.SETTINGS_FILE.write_text('--play all\n--comment followed   # public\n'
                            '--comment-text "Nice video 🇧🇷🇧🇷"\n# --save all\n', encoding="utf-8")
check("settings with a quoted text", fa.settings_args(),
      ["--play", "all", "--comment", "followed", "--comment-text", "Nice video 🇧🇷🇧🇷"])

# --- key m without a comment text: the mode doesn't change -------------------------------
p = player(comment="none", comment_text="")
p.keys = type("K", (), {"get": lambda self: "m"})()
p.poll()
check("m without text: mode unchanged", p.args.comment, "none")
check("m without text: explained", lines[-1], "comment mode needs a text: start with --comment-text TEXT")
p = player(comment="none")
p.keys = type("K", (), {"get": lambda self: "m"})()
p.poll()
check("m with text: next mode", p.args.comment, "followed")

# --- should_comment: modes and the pause after a refusal ----------------------------------
p = player(comment="followed")
check("followed, followed account", p.should_comment(True), True)
check("followed, other account", p.should_comment(False), False)
p.comment_refused()
check("after a refusal: paused", p.should_comment(True), False)
check("refusal counted", p.stats["comment_refused"], 1)
check("next pause doubles", p.comment_backoff, 2 * fa.REPOST_BACKOFF_MIN)

if failures:
    print(f"{len(failures)} FAILED:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all comment checks passed")
