#!/usr/bin/env python3
"""Block every Instagram profile in a list, one after another -- or, with --unblock, unblock them.

Flow: your profile (bottom right tab) -> menu (top right) -> Blocked accounts, once; then per
profile: + (top right) -> search the username -> Block on the row of exactly that username ->
confirm "Block <name>?" -> back on the blocked accounts list, check the profile is in it with
Unblock. An account already blocked doesn't show up in the search: then the list is looked
through to tell "already blocked" from "not found".
--unblock: the same list -> the profile's row -> Unblock -> confirm "Unblock ... (<name>)?" ->
check the row is gone.
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
# "More options" and "Mais opções" (fallbacks, not seen).
# Every check accepts any of them.
UI_TEXT = {
    "options": ("Options", "More options", "Opções", "Mais opções"),  # content-desc of your profile's menu
    "block": ("Block", "Bloquear"),                  # row button, confirmation ("Block <name>?")
    "unblock": ("Unblock", "Desbloquear"),           # row button of a blocked account, its dialog
    # the blocked accounts list: settings row, screen title, + button (content-desc)
    "blocked_row": ("Blocked", "Bloqueados"),
    "blocked_title": ("Blocked accounts", "Contas bloqueadas"),
    "settings_title": ("Settings and activity", "Configurações e atividade"),
    "add": ("Add", "Adicionar"),
    "blocking": ("Blocking", "Bloqueando"),          # progress dialog after confirming ("Bloqueando...")
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


# the blocked accounts list and its search (+): rows of username + button, the same in both
ROW, ROW_NAME, ROW_BUTTON = (fa.RID + x for x in ("blocked_list_container", "blocked_list_username",
                                                   "unblock_button"))
SEARCH = fa.RID + "search_bar_real_field"


def list_rows(xml):
    """[(username, button text, button bounds)] of the rows on screen: the blocked accounts
    (button Unblock) or the search results (button Block). Each row holds its own button, so a
    button is only ever tapped for the username next to it."""
    rows = []
    for c in ET.fromstring(xml).iter("node"):
        if c.get("resource-id") != ROW:
            continue
        name = button = None
        for e in c.iter("node"):
            if e.get("resource-id") == ROW_NAME:
                name = e.get("text", "")
            elif e.get("resource-id") == ROW_BUTTON:
                b = tuple(map(int, re.findall(r"\d+", e.get("bounds", ""))))
                button = (e.get("text", ""), b)
        if name is not None and button and len(button[1]) == 4:
            rows.append((name, *button))
    return rows


def on_blocked_list(xml):
    """The blocked accounts screen (title and its + button), not the search on top of it."""
    ns = [n for n in nodes(xml) if n["pkg"] == PKG]
    return (any(n["rid"] == fa.RID + "action_bar_title" and re.fullmatch(exact("blocked_title"), n["text"])
                for n in ns)
            and any(re.fullmatch(exact("add"), n["desc"]) for n in ns)
            and not any(n["rid"] == SEARCH for n in ns))


def blocking(xml):
    """Instagram's "Blocking..." progress dialog is showing (it can stay for over 15 s)."""
    return any(n["rid"] == fa.RID + "message" and n["text"].startswith(UI_TEXT["blocking"])
               for n in nodes(xml))


def unblock_question(xml, name):
    """The unblock dialog asks about exactly `name`: "Unblock The New York Times (nytimes)?"."""
    return any(n["rid"] == fa.RID + "igds_alert_dialog_headline" and n["text"].startswith(UI_TEXT["unblock"])
               and (f"({name.lower()})?" in n["text"].lower() or n["text"].lower().endswith(f" {name.lower()}?"))
               for n in nodes(xml))


def block_question(xml, name):
    """The confirmation sheet asks to block exactly `name` ("Block <name>?")."""
    want = {f"{w} {name}?".lower() for w in UI_TEXT["block"]}
    return any(n["rid"] == fa.RID + "igds_headline_headline" and n["text"].lower() in want
               for n in nodes(xml))


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

    def refused(self, xml):
        return any(re.match(REFUSED, n["text"]) for n in nodes(xml) if n["pkg"] == PKG)

    # the confirmation sheet and the unblock dialog: the screen behind stays in the UI tree, so
    # only their IDs tell whether one is open
    SHEET = re.compile(r'resource-id="' + re.escape(fa.RID) + r'(?:context_menu_item|layout_container_bottom_sheet|background_dimmer|igds_alert_dialog_\w+)"')

    def swipe_until(self, found, max_swipes=15):
        """Swipe the list up until found(xml) is true or the screen stops changing; True if found.
        Plain swipes: uiautomator2's scroll.to addresses the list as "the n-th scrollable", and
        that count changes while Instagram's settings list scrolls (UiObjectNotFoundError)."""
        w, h = self.d.window_size()
        last = None
        for _ in range(max_swipes + 1):
            self.key()
            xml = self.d.dump_hierarchy()
            if found(xml):
                return True
            if xml == last:                  # the end of the list
                return False
            last = xml
            self.d.swipe(w // 2, int(h * 0.75), w // 2, int(h * 0.35), 0.3)
            time.sleep(0.8)
        return False

    def goto_blocked_list(self):
        """To the blocked accounts list -- your profile tab -> menu (top right) -> Blocked
        accounts -- from whatever screen is showing; True when there."""
        if self.d.app_current().get("package") != PKG:
            self.d.app_start(PKG)
            time.sleep(3)
        for _ in range(8):
            xml = self.d.dump_hierarchy()
            ns = [n for n in nodes(xml) if n["pkg"] == PKG]
            if on_blocked_list(xml):
                return True
            if blocking(xml):  # never Back out of a block in progress: it would stop it
                self.wait_for(lambda x: not blocking(x), 60)
                continue
            if SEARCH in xml or self.SHEET.search(xml):
                self.d.press("back")                  # out of the search / a sheet
            elif any(re.fullmatch(exact("blocked_row"), n["text"]) for n in ns):
                self.tap(textMatches=exact("blocked_row"))
                self.wait_for(on_blocked_list, 8)
                continue
            elif any(re.fullmatch(exact("settings_title"), n["text"]) for n in ns):
                # Settings and activity: Blocked is far down
                if not self.swipe_until(lambda x: any(re.fullmatch(exact("blocked_row"), n["text"])
                                                      for n in nodes(x))):
                    self.d.press("back")
            elif any(n["rid"] == fa.RID + "profile_tab" for n in ns):
                self.d(resourceId=fa.RID + "profile_tab").click()
                time.sleep(1.5)
                # your own profile: its menu (top right) opens Settings and activity
                if self.tap(descriptionMatches=exact("options")):
                    self.wait_for(lambda x: re.search(exact("settings_title")[1:-1], x), 6)
                continue
            else:
                self.d.press("back")                  # a deeper screen: no tab bar
            time.sleep(1)
        return False

    def search(self, name):
        """+ on the blocked accounts list, type the username: the result rows once they have
        settled (they replace the suggestions as the search runs), or None without a search."""
        if not self.tap(descriptionMatches=exact("add")):
            return None
        field = self.d(resourceId=SEARCH)
        if not field.wait(timeout=5):
            return None
        field.set_text(name)
        time.sleep(1)
        last, end = None, time.time() + 8
        while time.time() < end:
            self.key()
            xml = self.d.dump_hierarchy()
            typed = any(n["rid"] == SEARCH and n["text"] == name for n in nodes(xml))
            rows = list_rows(xml)
            if typed and rows == last:
                return rows
            last = rows if typed else None
            time.sleep(0.7)
        return last or []

    def in_blocked_list(self, name):
        """Is `name` on the blocked accounts list? Scrolled through; then the list is opened
        again from Settings, so it starts at the top (where a new block shows up)."""
        found = self.swipe_until(lambda x: any(r[0].lower() == name.lower() for r in list_rows(x)),
                                 max_swipes=60)
        self.reopen_list()
        return found

    def unblock(self, name):
        """Unblock one profile through the blocked accounts list (its row's Unblock button);
        returns the outcome (a key of self.stats). Instagram can show a profile you blocked as
        "User not found", so its own page is no way to it (DEVELOPMENT.md 4.14)."""
        self.wake()
        if not self.goto_blocked_list():
            log("  couldn't open the blocked accounts list")
            return "failed"
        listed = lambda x: [r for r in list_rows(x) if r[0].lower() == name.lower()]
        if not self.swipe_until(lambda x: listed(x), max_swipes=60):
            self.reopen_list()
            return "not blocked"
        row = listed(self.d.dump_hierarchy())
        if not row or not re.fullmatch(exact("unblock"), row[0][1]):
            self.reopen_list()
            return "failed"
        x0, y0, x1, y1 = row[0][2]
        self.d.click((x0 + x1) // 2, (y0 + y1) // 2)
        if not self.wait_for(lambda x: unblock_question(x, name), 5):
            log(f"  no \"Unblock {name}?\" question")
            self.reopen_list()
            return "failed"
        if self.args.dry_run:
            log("  dry run: confirmation found, cancelled")
            self.reopen_list()
            return "would unblock"
        self.d(resourceId=fa.RID + "igds_alert_dialog_primary_button").click()

        # the row goes away (or its button turns to Block)
        def done(xml):
            if self.refused(xml):
                return "refused"
            if not on_blocked_list(xml):
                return None
            row = listed(xml)
            return "unblocked" if not row or re.fullmatch(exact("block"), row[0][1]) else None
        outcome = self.wait_for(done, 10) or "failed"
        self.reopen_list()
        return outcome

    def reopen_list(self):
        """Out of a dialog or the search, and the blocked accounts list opened again from
        Settings: it then starts at the top, where the next block shows up."""
        self.close_dialogs()
        if on_blocked_list(self.d.dump_hierarchy()):
            self.d.press("back")
            time.sleep(1)
        self.goto_blocked_list()

    def close_dialogs(self):
        """Back while a sheet or dialog is showing (at most twice)."""
        for _ in range(2):
            if not self.SHEET.search(self.d.dump_hierarchy()):
                return
            self.d.press("back")
            time.sleep(1)

    def block(self, name):
        """Block one profile through the blocked accounts list; returns the outcome (a key of
        self.stats)."""
        self.wake()
        if not self.goto_blocked_list():
            log("  couldn't open the blocked accounts list")
            return "failed"
        rows = self.search(name)
        if rows is None:
            log("  no search on the blocked accounts list (+ not found)")
            return "failed"
        match = [r for r in rows if r[0].lower() == name.lower()]  # the username, never the full name
        if not match or re.fullmatch(exact("unblock"), match[0][1]):
            self.goto_blocked_list()  # Back out of the search
            # blocked accounts don't show up in the search: look on the list
            return "already blocked" if match or self.in_blocked_list(name) else "not found"
        if not re.fullmatch(exact("block"), match[0][1]):
            log(f"  unexpected button \"{match[0][1]}\" next to {name}")
            self.goto_blocked_list()
            return "failed"
        # a tap right after typing can get lost (seen once, keyboard still up): tap again, but
        # only while no sheet is open and on the row where it is now
        for _ in range(2):
            xml = self.d.dump_hierarchy()
            row = [r for r in list_rows(xml) if r[0].lower() == name.lower()]
            if self.SHEET.search(xml) or not row:
                break
            x0, y0, x1, y1 = row[0][2]
            self.d.click((x0 + x1) // 2, (y0 + y1) // 2)
            if self.wait_for(lambda x: block_question(x, name), 4):
                break
        if not block_question(self.d.dump_hierarchy(), name):
            log(f"  no \"Block {name}?\" confirmation")
            self.goto_blocked_list()
            return "failed"
        if self.args.dry_run:
            log("  dry run: confirmation found, cancelled")
            self.goto_blocked_list()
            return "would block"
        # the sheet's own button: the rows behind it say "Block" too
        self.d(resourceId=fa.RID + "bb_primary_action_container").click()

        # back on the blocked accounts list, with the profile in it (button Unblock)
        def done(xml):
            if self.refused(xml):
                return "refused"
            return on_blocked_list(xml) and any(
                r[0].lower() == name.lower() and re.fullmatch(exact("unblock"), r[1])
                for r in list_rows(xml)) and "blocked"
        outcome = self.wait_for(done, 10)
        # "Blocking..." can take long (seen: over 15 s): wait for it rather than give up
        end = time.time() + 60
        while not outcome and time.time() < end and blocking(self.d.dump_hierarchy()):
            outcome = self.wait_for(done, 5)
        if outcome:
            return outcome
        self.goto_blocked_list()
        return "blocked" if self.in_blocked_list(name) else "failed"

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
                   help=f"also handle profiles {DONE_LOG} already lists as blocked (with --unblock: unblocked)")
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
    log("   keys       " + ("press h for help" if sys.stdin.isatty() else
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
