#!/usr/bin/env python3
"""Block every Instagram profile in a list, one after another -- or, with --unblock, unblock them.

Flow per profile: open it (instagram.com/<name> link, handed to the app) -> check it is the
right profile and not blocked yet -> ⋯ menu -> Block -> confirm "Block <name>?" (plain Block,
never "Block and Report") -> check the profile now shows Unblock.
--unblock: the profile's Unblock button -> confirm "Unblock <name>?" -> check it shows Follow.
Each result goes to runs/blocked-profiles.txt; profiles an earlier run already blocked (or, with
--unblock, unblocked) are skipped (--recheck looks at them again).

The list: one profile per line -- name, @name or a profile link (https://www.instagram.com/name/);
empty lines and text after # are ignored.

Try it first with --dry-run: everything up to the confirmation, which is then cancelled.

Keys while running (h shows them):
  p = pause (hand the phone over) / resume  s = statistics  q = quit
Without keys (background runs): create the file runs/STOP to stop cleanly; while the file
runs/PAUSE exists the run is paused.

Run with uv: uv run profile_blocker.py profiles.txt
Windows app: profile_blocker.exe, started without options it uses profiles.txt next to it;
unblock.bat unblocks them.
"""
import argparse
import random
import re
import signal
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# shared with feed_autoplay until the shared package exists (DEVELOPMENT.md 3)
import feed_autoplay as fa
from feed_autoplay import (APP_DIR, BUNDLE_DIR, FROZEN, PAUSE_FILE, PKG, REFUSED, RUNS, STOP_FILE,
                           WINDOWS, Keys, Quit, log,
                           log_block_end, pick_serial, u2)

__version__ = fa.__version__

# Instagram UI texts this tool relies on, per app language (as UI_TEXT in feed_autoplay,
# DEVELOPMENT.md 4.12): English first, then pt-BR -- both recorded on Instagram 452 (4.14), except
# "More options", "Mais opções" and "Esta página não está disponível" (fallbacks, not seen).
# Every check accepts any of them.
UI_TEXT = {
    "options": ("Options", "More options", "Opções", "Mais opções"),  # content-desc of the ⋯ button
    "block": ("Block", "Bloquear"),                  # menu item and the confirmation's button
    "unblock": ("Unblock", "Desbloquear"),           # profile button of a blocked account
    "not_found": ("Sorry, this page isn't available", "User not found",
                  "Esta página não está disponível", "Usuário não encontrado"),
}
PROFILES_FILE = APP_DIR / "profiles.txt"  # the Windows app's list, when started without one
DONE_LOG = RUNS / "blocked-profiles.txt"  # one line per profile handled: time, name, outcome
# latest outcomes that make a later run skip the profile (unless --recheck), per mode
DONE = {"block": ("blocked", "already blocked"), "unblock": ("unblocked", "not blocked")}
USERNAME = re.compile(r"[A-Za-z0-9._]{1,30}")
# pause after Instagram refuses a block (rate limit): 30 min, doubling per refusal
REFUSED_BACKOFF_MIN, REFUSED_BACKOFF_MAX = 30, 240


def exact(key):
    """Regex matching any language's text for `key` exactly."""
    return "^(" + "|".join(re.escape(t) for t in UI_TEXT[key]) + ")$"


def parse_profiles(lines):
    """(usernames in list order without duplicates, [(line number, line) not understood])."""
    names, bad, seen = [], [], set()
    for n, line in enumerate(lines, 1):
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        m = re.match(r"(?:https?://)?(?:www\.|m\.)?instagram\.com/([^/?#\s]+)", s)
        s = m.group(1) if m else s.lstrip("@")
        if not USERNAME.fullmatch(s):
            bad.append((n, line.rstrip()))
            continue
        if s.lower() not in seen:
            seen.add(s.lower())
            names.append(s)
    return names, bad


def done_before(mode, path=None):
    """Lower-case usernames whose latest outcome in the results file is done for `mode`
    ("block" / "unblock"): a profile blocked, then unblocked, is blocked again by the next run."""
    path = path or DONE_LOG
    latest = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                latest[parts[1].lower()] = parts[2]
    except OSError:
        pass
    return {name for name, outcome in latest.items() if outcome in DONE[mode]}


def nodes(xml):
    """The screen's elements: dicts with text, desc, rid, clickable, bounds (x0, y0, x1, y1)."""
    out = []
    for e in ET.fromstring(xml).iter("node"):
        b = re.findall(r"\d+", e.get("bounds", ""))
        out.append(dict(text=e.get("text", ""), desc=e.get("content-desc", ""),
                        rid=e.get("resource-id", ""), pkg=e.get("package", ""),
                        clickable=e.get("clickable") == "true",
                        bounds=tuple(map(int, b)) if len(b) == 4 else (0, 0, 0, 0)))
    return out


def profile_state(xml, name):
    """What the screen shows for profile `name`: "not found", "blocked" (Unblock button),
    "profile" (that profile, not blocked) or "other" (loading, or some other screen)."""
    ns = [n for n in nodes(xml) if n["pkg"] == PKG]
    texts = [n["text"] for n in ns] + [n["desc"] for n in ns]
    if any(t.startswith(nf) for t in texts for nf in UI_TEXT["not_found"]):
        return "not found"
    # the username must be on screen as a text of its own (the action bar title): never act on
    # whatever profile happens to be open
    if not any(t.lower() == name.lower() for t in texts):
        return "other"
    if any(re.fullmatch(exact("unblock"), n["text"]) for n in ns):
        return "blocked"
    return "profile"


class Blocker:
    def __init__(self, d, args, keys):
        self.d = d
        self.args = args
        self.keys = keys
        self.stats = {"blocked": 0, "already blocked": 0, "would block": 0, "unblocked": 0,
                      "not blocked": 0, "would unblock": 0, "not found": 0, "refused": 0,
                      "failed": 0, "skipped": 0}
        self.started = time.time()
        self.paused = 0.0
        self.backoff = REFUSED_BACKOFF_MIN

    # ---- keys, pause, lock screen (as in feed_autoplay's Player) ----------------------------
    def poll(self):
        if STOP_FILE.exists():
            try:
                STOP_FILE.unlink()
            except OSError:
                pass
            log(f"stop requested ({STOP_FILE} found)")
            raise Quit
        k = self.keys.get()
        if k == "q":
            raise Quit
        if k == "s":
            self.report()
        elif k in ("h", "?"):
            self.help()
        return k

    def key(self):
        """Keys and stop / pause files; a pause blocks here and raises Restart when resumed
        (the phone was the user's: the current profile starts over)."""
        k = self.poll()
        if k == "p" or PAUSE_FILE.exists():
            by_file = k != "p"
            t0 = time.time()
            log(f"⏸ paused: the phone is yours ({f'delete {PAUSE_FILE}' if by_file else 'p'} to resume)")
            try:
                while True:
                    k = self.poll()
                    if k == "p" or (by_file and not PAUSE_FILE.exists()):
                        break
                    time.sleep(0.2)
            finally:
                self.paused += time.time() - t0
            try:
                PAUSE_FILE.unlink()
            except OSError:
                pass
            log(f"▶ resumed after {fa.Player.hm(time.time() - t0)}: this profile starts over")
            raise Restart

    def sleep(self, seconds):
        """Wait, keys still working."""
        end = time.time() + seconds
        while time.time() < end:
            self.key()
            time.sleep(min(0.2, max(0.0, end - time.time())))

    def locked(self):
        return "isKeyguardShowing=true" in self.d.shell("dumpsys window").output

    def wake(self):
        """Screen on; if locked, wait for someone to unlock it -- never gesture on the lock
        screen (a pattern lock can count a swipe as a wrong attempt, DEVELOPMENT.md 4.8)."""
        if not self.d.info.get("screenOn"):
            self.d.screen_on()
            time.sleep(1)
        if self.locked():
            log("phone is locked: waiting for it to be unlocked (q quits)")
            while self.locked():
                self.sleep(15)
            log("phone unlocked: carrying on")

    # ---- screen ------------------------------------------------------------------------------
    def tap(self, **selector):
        """Click the lowest on-screen element matching the selector (scoped to Instagram:
        system UI reuses labels). False if there is none."""
        found = self.d(packageName=PKG, **selector)
        if not found.exists:
            return False
        best = None
        for el in found:
            try:
                b = el.info["bounds"]
            except fa.UiObjectNotFoundError:
                continue
            if best is None or b["top"] > best[0]["top"]:
                best = (b, el)
        if not best:
            return False
        best[1].click()
        return True

    def wait_for(self, check, timeout):
        """Poll the screen until check(xml) gives something truthy; that, or None."""
        end = time.time() + timeout
        while True:
            self.key()
            xml = self.d.dump_hierarchy()
            r = check(xml)
            if r or time.time() > end:
                return r or None
            time.sleep(0.5)

    def open_profile(self, name, want=None):
        """Open the profile in the app; its state (profile_state) once it has loaded. With
        `want`, wait up to 10 s for that state: right after a block / unblock the profile can
        still show the old state for a moment."""
        if self.d.app_current().get("package") != PKG:
            self.d.app_start(PKG)
            time.sleep(3)
        # name is a checked username ([A-Za-z0-9._]): safe in the shell command
        self.d.shell(f"am start -a android.intent.action.VIEW -p {PKG} "
                     f"-d https://www.instagram.com/{name}/")
        time.sleep(1.5)  # the screen before (maybe this same profile) is still there for a moment
        last = ["other"]

        def loaded(xml):
            last[0] = profile_state(xml, name)
            return last[0] == want if want else last[0] != "other"
        self.wait_for(loaded, timeout=10)
        return last[0]

    def refused(self, xml):
        return any(re.match(REFUSED, n["text"]) for n in nodes(xml) if n["pkg"] == PKG)

    # the ⋯ menu's items, the bottom sheets (block confirmation, "You blocked") and the unblock
    # dialog; the profile stays
    # in the UI tree behind them, so it can't tell whether one is open
    SHEET = re.compile(r'resource-id="' + re.escape(fa.RID) + r'(?:context_menu_item|layout_container_bottom_sheet|background_dimmer|igds_alert_dialog_\w+)"')

    def close_sheets(self, name):
        """Back while a menu or sheet is showing (at most twice: never leave the profile)."""
        for _ in range(2):
            if not self.SHEET.search(self.d.dump_hierarchy()):
                return
            self.d.press("back")
            time.sleep(1)

    # ---- one profile ---------------------------------------------------------------------------
    def confirmation(self, name, button):
        """check for wait_for: the "Block <name>?" / "Unblock <name>?" confirmation is showing --
        it names the profile (proof it's the right account) and has the button `button`."""
        def check(xml):
            ns = nodes(xml)
            named = any(name.lower() in (n["text"] + n["desc"]).lower() and n["text"].lower() != name.lower()
                        for n in ns)
            return named and any(re.fullmatch(exact(button), n["text"]) for n in ns)
        return check

    def unblock(self, name):
        """Unblock one profile; returns the outcome (a key of self.stats)."""
        self.wake()
        state = self.open_profile(name)
        if state == "not found":
            return "not found"
        if state == "profile":
            return "not blocked"
        if state != "blocked":
            log("  profile did not open (or its name isn't on screen)")
            return "failed"
        self.tap(textMatches=exact("unblock"))  # the profile's button
        if not self.wait_for(self.confirmation(name, "unblock"), 5):
            log(f"  no \"Unblock {name}?\" confirmation")
            self.close_sheets(name)
            return "failed"
        if self.args.dry_run:
            log("  dry run: confirmation found, cancelled")
            self.close_sheets(name)
            return "would unblock"
        self.tap(textMatches=exact("unblock"))  # the dialog's button, below the profile's
        return {True: "unblocked", False: "failed", None: "refused"}[self.confirmed(name, "profile")]

    def block(self, name):
        """Block one profile; returns the outcome (a key of self.stats)."""
        self.wake()
        state = self.open_profile(name)
        if state == "not found":
            return "not found"
        if state == "blocked":
            return "already blocked"
        if state != "profile":
            log("  profile did not open (or its name isn't on screen)")
            return "failed"
        # the menu's own "Block" (exact text: not "Unblock", "Restrict", "Report")
        for attempt in range(2):  # a tap while the profile is still drawing can get lost
            if not self.tap(descriptionMatches=exact("options")):
                log("  ⋯ menu button not found")
                return "failed"
            if self.wait_for(lambda x: any(re.fullmatch(exact("block"), n["text"]) for n in nodes(x)), 4):
                break
            self.close_sheets(name)
        else:
            log("  no Block item in the ⋯ menu")
            return "failed"
        self.tap(textMatches=exact("block"))
        if not self.wait_for(self.confirmation(name, "block"), 5):
            log(f"  no \"Block {name}?\" confirmation")
            self.close_sheets(name)
            return "failed"
        if self.args.dry_run:
            log("  dry run: confirmation found, cancelled")
            self.close_sheets(name)
            return "would block"
        # the confirmation's button, at the bottom; "Block and Report" never matches exactly
        self.tap(textMatches=exact("block"))
        return {True: "blocked", False: "failed", None: "refused"}[self.confirmed(name, "blocked")]

    def confirmed(self, name, want):
        """After the confirmation's button: True once the profile shows `want` ("blocked" /
        "profile"), False if it doesn't, None if Instagram refused. The open profile changes in
        place, which is the proof; a freshly reopened one can show Instagram's cached state from
        before for a while (DEVELOPMENT.md 4.14), so reopening is only the fallback."""
        seen = self.wait_for(lambda x: "refused" if self.refused(x) else
                             profile_state(x, name) == want and "seen", timeout=10)
        self.close_sheets(name)
        if seen == "refused":
            return None
        return bool(seen) or self.open_profile(name, want=want) == want

    def record(self, name, outcome):
        try:
            DONE_LOG.parent.mkdir(exist_ok=True)
            with DONE_LOG.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{name}\t{outcome}\n")
        except OSError as e:
            log(f"  could not write {DONE_LOG} ({type(e).__name__}: {e})")

    SYMBOL = {"blocked": "⛔ blocked", "already blocked": "already blocked", "would block": "would block",
              "unblocked": "✓ unblocked", "not blocked": "not blocked (nothing to undo)",
              "would unblock": "would unblock", "not found": "profile not found",
              "refused": "⚠ Instagram refused it", "failed": "✗ failed"}

    def run(self, names):
        for i, name in enumerate(names, 1):
            log(f"[{i}/{len(names)}] {name}")
            for attempt in range(1, 4):
                try:
                    outcome = (self.unblock if self.args.unblock else self.block)(name)
                    break
                except Restart:
                    continue
                except (Quit, KeyboardInterrupt):
                    raise
                except Exception as e:  # adb/Wi-Fi drop, agent restart, UI changed mid-step
                    log(f"  error: {type(e).__name__}: {str(e)[:150]} -- retrying in {10 * attempt}s")
                    self.sleep(10 * attempt)
                    try:
                        self.d = u2.connect(self.d.serial)
                    except Exception:
                        pass
            else:
                outcome = "failed"
            self.stats[outcome] += 1
            log("  " + self.SYMBOL[outcome])
            if not outcome.startswith("would"):
                self.record(name, outcome)
            if outcome == "refused":
                log(f"  pausing for {self.backoff} min (probably a rate limit); this profile is "
                    f"retried after")
                self.sleep(self.backoff * 60)
                self.backoff = min(self.backoff * 2, REFUSED_BACKOFF_MAX)
                names.insert(i, name)  # once more, right after the pause
                continue
            if i < len(names):
                self.sleep(self.args.delay * random.uniform(0.7, 1.3))

    # ---- blocks ---------------------------------------------------------------------------------
    def report(self):
        s = self.stats
        dry = self.args.dry_run
        head = f"── stats after {fa.Player.hm(time.time() - self.started)} "
        log(head + "─" * max(4, 64 - len(head)))
        if self.args.unblock:
            log(f"   profiles  unblocked {s['unblocked']} · not blocked {s['not blocked']} · "
                f"skipped (done before) {s['skipped']}" + (f" · would unblock {s['would unblock']}" if dry else ""))
        else:
            log(f"   profiles  blocked {s['blocked']} · already blocked {s['already blocked']} · "
                f"skipped (done before) {s['skipped']}" + (f" · would block {s['would block']}" if dry else ""))
        log(f"   problems  not found {s['not found']} · refused {s['refused']} · failed {s['failed']}")
        log_block_end()

    def help(self):
        log("── keys " + "─" * 56)
        log("   p  pause: the phone is yours until p again (also runs/PAUSE)")
        log("   s  statistics so far")
        log("   h  this help (also ?)")
        log("   q  quit")
        log_block_end()


class Restart(Exception):
    """Raised after a pause: the current profile starts over."""


def entry():
    """Start; the Windows app's own window waits for Enter at the end (as feed_autoplay.entry())."""
    # the log uses symbols (⛔ ✓): writable even to a redirected file or an old Windows console
    # (code page), instead of crashing
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code
        if isinstance(code, str):
            print(code, file=sys.stderr)
            code = 1
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    if fa.owns_console():
        print("\nprofile_blocker has stopped -- press Enter to close this window.")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    sys.exit(code)


def default_list():
    """The Windows app started without a list: profiles.txt next to the exe -- created on the
    first start as an example to edit (not in the zip, so an update never overwrites it)."""
    if not PROFILES_FILE.exists():
        try:
            PROFILES_FILE.write_bytes((BUNDLE_DIR / "profiles.txt").read_bytes())
        except OSError as e:
            sys.exit(f"can't create {PROFILES_FILE}: {e}")
        sys.exit(f"created {PROFILES_FILE.name} -- open it with Notepad, put the profiles to block "
                 f"in it (one per line), then start profile_blocker again")
    return PROFILES_FILE


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("profiles", type=Path, nargs="?" if FROZEN else None,
                   help="text file with the profiles to block, one per line"
                        + (f" (default: {PROFILES_FILE.name} next to the app)" if FROZEN else ""))
    p.add_argument("--unblock", action="store_true",
                   help="unblock the listed profiles instead (undoes an earlier run)")
    p.add_argument("--dry-run", action="store_true",
                   help="go as far as the \"Block <name>?\" / \"Unblock <name>?\" confirmation, then "
                        "cancel: nothing changes")
    p.add_argument("--delay", type=float, default=20,
                   help="seconds between profiles, ±30%% at random (default 20; Instagram limits "
                        "how fast accounts may act)")
    p.add_argument("--recheck", action="store_true",
                   help=f"also open profiles {DONE_LOG} already lists as blocked (with --unblock: unblocked)")
    p.add_argument("-s", "--serial", help="adb device serial (default: the only connected device)")
    args = p.parse_args()
    if args.profiles is None:
        args.profiles = default_list()

    try:
        names, bad = parse_profiles(args.profiles.read_text(encoding="utf-8-sig").splitlines())
    except OSError as e:
        sys.exit(f"can't read the profile list: {e}")
    for n, line in bad:
        print(f"{args.profiles}:{n}: not a username, left out: {line}", file=sys.stderr)
    skipped = 0
    if not args.recheck:
        done = done_before("unblock" if args.unblock else "block")
        skipped = sum(n.lower() in done for n in names)
        names = [n for n in names if n.lower() not in done]
    if not names:
        what = "unblocked" if args.unblock else "blocked"
        sys.exit(f"nothing to do: no profiles in {args.profiles}"
                 + (f" that {DONE_LOG} doesn't list as {what} (--recheck to look again)" if skipped else ""))

    for f in (STOP_FILE, PAUSE_FILE):  # left over from an earlier run
        try:
            f.unlink()
        except OSError:
            pass
    d = u2.connect(args.serial or pick_serial())
    head = f"── profile_blocker {__version__} "
    log(head + "─" * (64 - len(head)))
    log(f"   phone      {d.serial}")
    verb = "unblock" if args.unblock else "block"
    log(f"   profiles   {len(names)} to {verb} from {args.profiles}"
        + (f" · {skipped} {verb}ed in earlier runs, skipped" if skipped else ""))
    log(f"   mode       {verb} · " + ("DRY RUN: nothing changes" if args.dry_run else f"{args.delay:g} s between profiles"))
    log(f"   results    {DONE_LOG}")
    log(f"   keys       " + ("press h for help" if sys.stdin.isatty() else
                            f"off (no terminal) -- stop: create {STOP_FILE} · pause: create / delete {PAUSE_FILE}"))
    log_block_end()
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if WINDOWS:
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    with Keys() as keys:
        blocker = Blocker(d, args, keys)
        blocker.stats["skipped"] = skipped
        try:
            blocker.run(names)
            blocker.report()
            log("all profiles done")
        except (Quit, KeyboardInterrupt):
            blocker.report()
            log("bye")


if __name__ == "__main__":
    entry()
