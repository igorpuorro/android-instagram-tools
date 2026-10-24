#!/usr/bin/env python3
"""Comment feature pieces that need no phone (DEVELOPMENT.md 4.7e): the record of commented
posts across runs, settings.txt with a quoted comment text, the m key without a text,
--comment-script (how it's run, what it gets, its failures).
Examples use made-up accounts.

Run: uv run tests/test_comment.py
"""
import argparse
import os
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
                comment="followed", comment_text="🇧🇷🇧🇷", comment_script="", speed2x=False)
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
check("m without text: explained", lines[-1], "comment mode needs a text: start with --comment-text TEXT or --comment-script FILE")
p = player(comment="none")
p.keys = type("K", (), {"get": lambda self: "m"})()
p.poll()
check("m with text: next mode", p.args.comment, "followed")

# --- --comment-script: the command per extension, the video in the environment, failures ----
script = tmp / "greet.py"
script.write_text("import os\nprint(f'Oi @{os.environ[\"IG_AUTHOR\"]} 🇧🇷 {os.environ[\"IG_FOLLOWED\"]}"
                  "{os.environ[\"IG_TEST\"]} {os.environ[\"IG_POST\"]}')\n", encoding="utf-8")
cmd = fa.script_command(script)
check(".py runs with this Python", cmd, [sys.executable, str(script)])
check("text from the script", fa.run_comment_script(cmd, "chef.marco", "chef.marco posted a video", True),
      ("Oi @chef.marco 🇧🇷 10 chef.marco posted a video", None))
check("not followed", fa.run_comment_script(cmd, "chef.marco", "p")[0], "Oi @chef.marco 🇧🇷 00 p")
check("trial run", fa.run_comment_script(cmd, "a", "p", test=True)[0], "Oi @a 🇧🇷 01 p")
quiet = tmp / "quiet.py"
quiet.write_text("print('  ')\n", encoding="utf-8")
check("prints nothing", fa.run_comment_script(fa.script_command(quiet)), (None, "the script printed nothing"))
broken = tmp / "broken.py"
broken.write_text("raise SystemExit('no greetings left')\n", encoding="utf-8")
check("fails", fa.run_comment_script(fa.script_command(broken)),
      (None, "the script failed (exit 1: no greetings left)"))
long = tmp / "long.py"
long.write_text("print('x' * 2201)\n", encoding="utf-8")
check("too long", fa.run_comment_script(fa.script_command(long))[1],
      "the script printed 2201 characters (Instagram takes up to 2200)")
slow = tmp / "slow.py"
slow.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
fa.COMMENT_SCRIPT_TIMEOUT = 1
check("too slow", fa.run_comment_script(fa.script_command(slow)), (None, "the script took more than 1 s"))
fa.COMMENT_SCRIPT_TIMEOUT = 15
if os.name != "nt":
    sh = tmp / "greet.sh"
    sh.write_text('echo "Boa noite $IG_AUTHOR 🌙"\n', encoding="utf-8")
    check(".sh runs with sh", fa.script_command(sh), ["sh", str(sh)])
    check("text from sh", fa.run_comment_script(fa.script_command(sh), "chef.marco")[0], "Boa noite chef.marco 🌙")
check("no extension: run directly", fa.script_command(tmp / "greet"), [str(tmp / "greet")])

# the start: the file is found and tried once, a broken one stops the start
parser = argparse.ArgumentParser()
parser.error = lambda msg: (_ for _ in ()).throw(ValueError(msg))


def start(name):
    try:
        return fa.comment_script_check(parser, name)
    except ValueError as e:
        return str(e)


check("start: sample", start(str(script)), ([sys.executable, str(script.resolve())],
                                            "Oi @example.account 🇧🇷 11 example.account posted a video 2 hours ago"))
check("start: quiet is fine", start(str(quiet))[1], "(nothing for the example)")
check("start: missing", start(str(tmp / "none.py")), f"--comment-script: {tmp / 'none.py'} not found")
check("start: broken", start(str(broken)), "--comment-script: the script failed (exit 1: no greetings left)")
fa.APP_DIR = tmp  # a name next to the app (the Windows app started by a double-click)
check("start: next to the app", start("greet.py")[0], [sys.executable, str(script.resolve())])

# key m with a script and no text: the mode changes
p = player(comment="none", comment_text="", comment_script=[sys.executable, str(script)])
p.keys = type("K", (), {"get": lambda self: "m"})()
p.poll()
check("m with a script: next mode", p.args.comment, "followed")

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
