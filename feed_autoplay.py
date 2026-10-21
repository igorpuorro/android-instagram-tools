#!/usr/bin/env python3
"""Walk the Instagram home timeline and play every video/reel, one after another.

Flow: find a video post in the feed -> tap it (opens full-screen player with sound)
-> optionally lock 2x speed (--2x: hold screen edge + slide down) -> watch until it ends
(Instagram's player log, with frame comparison as fallback) -> Back -> scroll on -> repeat.

--play followed|all picks whether suggested (not followed) videos are skipped or played;
--like none|followed|all picks which fully watched videos get liked;
--repost none|followed|all which get reposted (default none: reposts show on your profile);
--share-link none|followed|all which get Share -> Copy link (links saved to runs/shared-links.txt);
--save none|followed|all which get saved to your private Saved collection (default none).

Keys while running (h shows them):
  n = next video  p = pause (hand the phone over) / resume  x = 2x on/off  w = play mode
  l = like mode  r = repost mode  c = copy-link mode  b = save mode  s = statistics  q = quit
Without keys (background runs): create the file runs/STOP to stop cleanly (stop.bat on Windows);
while the file runs/PAUSE exists the run is paused (pause.bat on Windows toggles it).

Run with uv (sets up Python and the packages by itself): uv run feed_autoplay.py --help
"""
import argparse
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

WINDOWS = os.name == "nt"
if WINDOWS:
    import msvcrt
else:
    import select
    import termios
    import tty

import adbutils
import numpy as np
import uiautomator2 as u2
from uiautomator2.exceptions import UiObjectNotFoundError

PKG = "com.instagram.android"
RID = PKG + ":id/"

# Instagram versions the selectors, texts and icon masks were found and tested on
# (DEVELOPMENT.md 2): 450 for the first exploration only, 451 for everything since.
TESTED_INSTAGRAM = ("450.0.0.50.77", "451.0.0.53.80")

HEADER = RID + "row_feed_profile_header"

# Instagram UI texts the tool relies on, per app language (DEVELOPMENT.md 4.12). English is the
# original (UK English; US English differs in a few texts) and is listed first, unchanged; Brazilian Portuguese (pt-BR) was recorded on
# Instagram 451 with the phone's system language left in English. Every check accepts any of
# the listed texts, so adding a language never changes how another one is matched.
UI_TEXT = {
    "home_tab": ("Home", "Página inicial"),                          # content-desc of the Home tab
    "video_post": ("posted a video", "postou um video", "postou um vídeo"),  # feed post header
    "sponsored": ("Sponsored", "Patrocinado"),                       # header of an ad
    "suggested": ("Suggested for you", "Sugestões para você"),       # secondary_label in a header
    "speed_locked": ("normal speed", "velocidade normal"),           # hint while holding, 2x locked
    "speed_unlocked": ("lock 2X speed", "lock 2x speed",             # hint while holding, not locked
                       "ativar a velocidade 2x"),                    # (English UK "2X", US "2x")
    "followed_by": ("Followed by ", "Seguido por ", "Seguida por "), # player: suggested account
    "like_unliked": ("Like", "Curtir"),                              # like button label, not liked
    "copy_link": ("Copy link", "Copiar link"),                       # share sheet button
    "copied": ("Copied", "Copiado"),                                 # after Copy link
    "reposted": ("Reposted", "Repostado"),                           # snackbar after Repost
}
# Exact counts in the player, per language: (regex capturing the number, thousands separator).
# English is the original pattern; abbreviated values ("18.5K", "1,2 mil") are not exact.
COUNTS = {
    "like": ((r'content-desc="(?:The like|Like) number is ([\d,]+(?:\.\d+)?[KM]?)', ","),  # UK / US
             (r'content-desc="O número de curtidas é (\d+(?:\.\d{3})*(?:,\d+)?(?: ?mil| ?mi)?)', ".")),
    "repost": ((r'content-desc="Reposted ([\d,]+(?:\.\d+)?[KM]?) times?"', ","),
               (r'content-desc="Repostado (\d+(?:\.\d{3})*(?:,\d+)?(?: ?mil| ?mi)?) vez(?:es)?"', ".")),
    "save": ((r'content-desc="Save number is ([\d,]+(?:\.\d+)?[KM]?)', ","),
             (r'content-desc="O número de salvamentos é (\d+(?:\.\d{3})*(?:,\d+)?(?: ?mil| ?mi)?)', ".")),
}
# refusal messages in the snackbar (repost, save)
REFUSED = r"(?i).*(unable|couldn.t|can.t|try again|não foi possível|tente novamente).*"
HOME_TAB = "^(" + "|".join(re.escape(t) for t in UI_TEXT["home_tab"]) + ")$"


def has_any(text, key):
    """True if any of the languages' texts for `key` occurs in `text`."""
    return any(t in text for t in UI_TEXT[key])
# Shapes of the full-screen player's white icons (116x116, recorded on this phone, see
# DEVELOPMENT.md 4.7): the like heart's outline, and the parts of the repost icon that change
# when it's on (arrowhead tips vanish, a checkmark appears).
ICON_MASKS = dict(np.load(Path(__file__).resolve().parent / "assets" / "icon_masks.npz"))
CLIPS_VIEWER = RID + "clips_viewer_container"
FEED_LIST = "android:id/list"


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, end="\r\n", flush=True)


class Keys:
    """Non-blocking single-key reader for the terminal (termios on Linux/macOS, msvcrt on
    Windows). Inert when stdin isn't a terminal (background runs, pipes, tests)."""

    def __enter__(self):
        self.tty = sys.stdin.isatty()
        if self.tty and not WINDOWS:
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def __exit__(self, *exc):
        if self.tty and not WINDOWS:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)

    def get(self):
        if not self.tty:
            return None
        if WINDOWS:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):  # arrow/function keys come as two codes: ignore
                    msvcrt.getwch()
                    return None
                return ch.lower()
            return None
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1).lower()
        return None


# Creating this file stops a run cleanly (final statistics), on any system and without a
# terminal: background runs, Windows (no SIGTERM there; stop.bat creates it).
STOP_FILE = Path("runs") / "STOP"
# While this file exists the run is paused (same as key p): pause.bat toggles it on Windows.
PAUSE_FILE = Path("runs") / "PAUSE"
# resuming in place needs the paused frame unchanged (mean grey-level difference, 0-255)
PAUSE_SAME_FRAME = 4.0


class Quit(Exception):
    pass


class Resumed(Exception):
    """Raised by Player.key() after a pause that can't continue where it left off (the phone
    was used meanwhile, or nothing was playing): the current step is dropped and the run
    starts again from the Home feed."""


# Frame-comparison loop detector settings per playback speed, tuned offline on recorded
# videos with ground truth (tools/tune_fallback.py; DEVELOPMENT.md 4.5):
#   2x: 13/13 detected, none early  |  1x: 19/20, none early (the one miss: no setting found it)
# top: upper edge of the compared area (fraction of screen height) in the full-screen player;
# refs: up to max_refs frames taken between ref_start and ref_start + ref_window seconds;
# "back at the start": diff < loop_thresh, or diff < loop_rel x median diff (0 = off).
# No single setting works at both speeds: the relative rule is needed at 2x but cuts
# videos short (fires early) at 1x.
DETECTOR = {
    2: dict(top=0.12, ref_start=1.0, ref_window=3.0, max_refs=5, loop_thresh=6, loop_rel=0.5),
    1: dict(top=0.20, ref_start=0.5, ref_window=3.0, max_refs=15, loop_thresh=6, loop_rel=0.0),
}

# pause after Instagram refuses a repost ("Unable to repost"): 30 min, doubling per refusal
REPOST_BACKOFF_MIN, REPOST_BACKOFF_MAX = 30, 240

PLAY_MODES = ["followed", "all"]
# every mode list follows the same order: none -> followed -> all ("do nothing" to "do it for
# everything"); play has no "none"
LIKE_MODES = ["none", "followed", "all"]
REPOST_MODES = ["none", "followed", "all"]
SAVE_MODES = ["none", "followed", "all"]
SHARE_MODES = ["none", "followed", "all"]
SHARED_LINKS = Path("runs") / "shared-links.txt"  # every copied link is appended here
# mode keys: key -> (args attribute, label, cycle, note)
SPEED_MODES = ["off", "on"]  # key x: 2x speed (--2x sets the start value)
MODE_KEYS = {
    "w": ("play", "play", PLAY_MODES, "followed = skip accounts you don't follow"),
    "l": ("like", "like", LIKE_MODES, ""),
    "r": ("repost", "repost", REPOST_MODES, "shows on your profile"),
    "c": ("share_link", "copy link", SHARE_MODES, "→ runs/shared-links.txt"),
    "b": ("save", "save", SAVE_MODES, "private to you"),
}


def cycle_text(modes, current):
    """'followed → [all] → none': the cycle a key steps through, current mode in brackets."""
    return " → ".join(f"[{m}]" if m == current else m for m in modes)


class EndWatcher:
    """Follows Instagram's player log to learn when the playing video reaches its end.

    On (almost) every pass through the end of a video, Instagram logs
        W ServicePlayerState: position=45763 bigger than duration=45718
    Lines are timestamped on arrival (PC clock), so callers just ask for events after a time.
    """

    LINE = re.compile(r"position=(\d+) bigger than duration=(\d+)")

    def __init__(self, serial):
        self.serial = serial
        self.events = []  # (arrival time, duration ms)
        self.proc = None
        self.start()

    def start(self):
        # the adb bundled with adbutils: works even without a system-wide adb install
        cmd = [adbutils.adb_path(), "-s", self.serial, "logcat", "-T", "1", "-s", "ServicePlayerState:W"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def ensure_running(self):
        """Restart logcat if it died (e.g. the adb connection dropped). Returns False if it had."""
        if self.proc.poll() is None:
            return True
        self.start()
        return False

    def _read(self, proc):
        for line in proc.stdout:
            m = self.LINE.search(line)
            if m:
                self.events.append((time.time(), int(m.group(2))))
                del self.events[:-200]  # only recent events matter; keep memory flat on long runs

    def ends_since(self, t0, debounce=2.0):
        """Video-end events after t0, merging bursts that belong to the same pass."""
        out = []
        for t, dur in self.events:
            if t > t0 and (not out or t - out[-1][0] > debounce):
                out.append((t, dur))
        return out

    def stop(self):
        self.proc.terminate()


class Player:
    def __init__(self, d, args, keys, ends=None):
        self.d = d
        self.args = args
        self.keys = keys
        self.ends = ends  # EndWatcher, or None to rely on frame comparison only
        self.w, self.h = d.window_size()
        self.seen = []  # recently watched post keys, to avoid replaying after Back
        self.ended_by = None  # how the last watch() ended, for the stats
        self.repost_paused_until = 0.0  # set when Instagram refuses a repost
        self.repost_backoff = REPOST_BACKOFF_MIN
        self.stats = dict(played=0, liked=0, reposted=0, repost_refused=0, saved=0, links=0, skipped=0, suggested_skipped=0,
                          end_log=0, end_frames=0, end_static=0, end_max=0, errors=0)
        self.started = time.time()
        self.waited = dict(locked=0.0, reconnect=0.0, paused=0.0)  # idle, excluded from "active" rate
        self.pauses = []  # (start, end) of each pause: end-of-video log lines in them are ignored
        self.context = None  # "player" / "feed-video" while watch() runs: what a pause leaves
        self.need_feed = True  # (re)start from the Home feed on the next loop turn
        self.cycles = []        # recent active cycle times (s): start of one played video to the next
        self.last_start = None  # (time, idle seconds so far) at the last played video's start
        self.next_report = 20  # print stats every 20 played videos

    @staticmethod
    def hm(seconds):
        h, m = divmod(int(seconds // 60), 60)
        return f"{h}h {m:02d}m" if h else f"{m}m"

    # Pace estimate, chosen by backtesting on 4 recorded runs (56 checkpoints: estimate vs.
    # videos actually played in the next hour; DEVELOPMENT.md 4.8):
    #   median of recent cycles: error ~20 videos/h, always too high (long videos are rare
    #   but take much of the hour -- the hourly count follows the MEAN cycle);
    #   mean (recent / whole run) or time-weighted mean: ~10; weighted mean adapts to
    #   real pace changes, so it is used.
    PACE_HALF_LIFE = 30     # videos: weight of a cycle halves every 30 videos back
    PACE_RANGE = (0.75, 1.25)  # "likely": actual next hour inside it in ~80 % of checkpoints
    PACE_MIN, PACE_ROUGH = 5, 20  # no estimate below 5 cycles; marked rough below 20
    PACE_KEEP = 300         # older cycles weigh < 0.1 %

    def mark_played(self):
        """Count a played video and record the cycle since the previous one, minus the time
        spent waiting (lock screen, reconnect back-off, pauses) in between."""
        self.stats["played"] += 1
        now, idle = time.time(), sum(self.waited.values())
        if self.last_start is not None:
            t0, idle0 = self.last_start
            self.cycles = (self.cycles + [max(now - t0 - (idle - idle0), 1.0)])[-self.PACE_KEEP:]
        self.last_start = (now, idle)

    def pace(self):
        """(videos/h expected at the current pace, low, high), or None if too few cycles:
        3600 / time-weighted mean cycle time (recent videos count more), range from the
        backtest calibration."""
        if len(self.cycles) < self.PACE_MIN:
            return None
        c = np.asarray(self.cycles, float)
        w = 0.5 ** (np.arange(len(c))[::-1] / self.PACE_HALF_LIFE)
        now = 3600 / float(np.average(c, weights=w))
        return now, now * self.PACE_RANGE[0], now * self.PACE_RANGE[1]

    def report(self):
        """Statistics block: one line per topic. Pace = estimate from the recent cycle times
        (what to expect if things go on like this); the whole-run rates follow for
        comparison, per active hour too when time was spent waiting (unlock, reconnect, pause)."""
        s = self.stats
        elapsed = max(time.time() - self.started, 1)
        idle = sum(self.waited.values())
        active = max(elapsed - idle, 1)
        whole = f"whole run {s['played'] / (elapsed / 3600):.1f}/h"
        if idle >= 60:
            whole += f" ({s['played'] / (active / 3600):.1f}/h active)"
        p = self.pace()
        if p:
            now, lo, hi = p
            pace = f"~{now:.0f} videos/h at the current pace (likely {lo:.0f}–{hi:.0f})"
            if len(self.cycles) < self.PACE_ROUGH:
                pace += f" (rough: {len(self.cycles) + 1} videos so far)"
        else:
            pace = f"estimate after {self.PACE_MIN + 1} videos"
        head = f"── stats after {self.hm(elapsed)}" + (f" (active {self.hm(active)})" if idle >= 60 else "") + " "
        log(head + "─" * max(4, 64 - len(head)))
        log(f"   videos   played {s['played']} · skipped {s['skipped']} · "
            f"suggested not played {s['suggested_skipped']}")
        log(f"   pace     {pace}")
        log(f"            {whole}")
        log(f"   actions  liked {s['liked']} · reposted {s['reposted']} (refused {s['repost_refused']}) · "
            f"links copied {s['links']} · saved {s['saved']}")
        log(f"   ends     log {s['end_log']} · frames {s['end_frames']} · static {s['end_static']} · "
            f"max-time {s['end_max']}")
        log(f"   waits    errors recovered {s['errors']} · locked {self.hm(self.waited['locked'])} · "
            f"reconnecting {self.hm(self.waited['reconnect'])} · paused {self.hm(self.waited['paused'])}")

    def locked(self):
        """Is the lock screen showing? ("screen on" alone can't tell: it is also on while
        the lock screen shows.)"""
        return "isKeyguardShowing=true" in self.d.shell("dumpsys window").output

    def wake(self):
        """Turn the screen on; if the phone is locked, wait until someone unlocks it.

        Never gestures on the lock screen: this phone has a pattern lock, and a swipe
        across the dot grid can count as a wrong attempt (repeated ones lock the phone out).
        """
        if not self.d.info.get("screenOn"):
            self.d.screen_on()
            time.sleep(1)
        if not self.locked():
            return
        log("phone is locked: waiting for it to be unlocked (q quits)")
        lock_start = time.time()
        waited = 0
        while self.locked():
            for _ in range(15):
                self.key()  # q still quits
                time.sleep(1)
            waited += 15
            if waited % 600 == 0:
                log(f"  still locked after {waited // 60} min")
        self.waited["locked"] += time.time() - lock_start
        log("phone unlocked: carrying on")

    # ---- helpers -------------------------------------------------------
    def key(self):
        """Handle a pending key press and the stop / pause files. Global keys (quit, pause,
        modes, stats, help) are dealt with here; n is returned for the caller to act on,
        everything else is None. A pause blocks here until resumed (see pause())."""
        k = self.poll()
        if k == "p" or PAUSE_FILE.exists():
            self.pause(by_file=k != "p")
            return None
        return k if k == "n" else None

    def poll(self):
        """The keys and the stop file that work everywhere, paused or not; returns the key
        (or None) for the caller."""
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
        if k in MODE_KEYS:
            attr, label, modes, _ = MODE_KEYS[k]
            new = modes[(modes.index(getattr(self.args, attr)) + 1) % len(modes)]
            setattr(self.args, attr, new)
            log(f"{label} mode: {new}   ({cycle_text(modes, new)})")
        elif k == "x":
            # applied when the next video opens: the playing one keeps its speed (and the end
            # detector's settings for it)
            self.args.speed2x = not self.args.speed2x
            new = "on" if self.args.speed2x else "off"
            log(f"2x: {new} from the next video   ({cycle_text(SPEED_MODES, new)})")
        elif k == "s":
            self.report()
        elif k in ("h", "?"):
            self.help()
        return k

    def pause(self, by_file):
        """Hand the phone over: pause the video if the full-screen player is playing it, then
        leave the phone alone -- no taps, swipes or screen reads -- until resumed with p (or,
        when paused by the file, until runs/PAUSE is deleted). Instagram's end-of-video log
        lines from that time are ignored (they would come from whatever you watch).

        On resume nothing is tapped blindly: the video is resumed in place only if the same
        video is still open and paused at the same frame (nobody touched it); otherwise the
        current video is dropped (no like/repost/link/save) and Resumed is raised, which takes
        the run back to the Home feed."""
        t0 = time.time()
        ref = None
        if self.context == "player":
            try:
                self.d.click(self.w // 2, self.h // 2)  # tap toggles play/pause
                time.sleep(1.0)  # let the tap's overlay fade
                ref = (self.player_author(), self.frame(self.player_box()))
            except Exception:  # can't tell later whether it's unchanged: start over on resume
                ref = None
        how = f"delete {PAUSE_FILE} to resume" if by_file else "p to resume"
        log(f"⏸ paused: the phone is yours ({how})")
        try:
            while True:
                k = self.poll()  # q, stop file, modes, stats and help still work
                if k == "p" or (by_file and not PAUSE_FILE.exists()):
                    break
                time.sleep(0.2)
        finally:  # also when quitting while paused: the final statistics count the pause
            t1 = time.time()
            self.pauses.append((t0, t1))
            self.waited["paused"] += t1 - t0
        try:
            PAUSE_FILE.unlink()  # resumed with p while the file exists: don't pause again
        except OSError:
            pass
        if ref and self.same_paused_video(*ref):
            self.d.click(self.w // 2, self.h // 2)
            log(f"▶ resumed after {self.hm(t1 - t0)}")
            return
        if self.context:
            self.stats["skipped"] += 1
            log(f"▶ resumed after {self.hm(t1 - t0)}: the phone was used, so this video is left "
                f"(no actions); back to the Home feed")
        else:
            log(f"▶ resumed after {self.hm(t1 - t0)}: back to the Home feed")
        raise Resumed

    def same_paused_video(self, author, ref_frame):
        """After a pause: Instagram in front, unlocked, the same author in the full-screen
        player and the same (paused) frame -- i.e. nobody touched the video."""
        try:
            if not self.d.info.get("screenOn") or self.locked():
                return False
            if self.d.app_current().get("package") != PKG or not self.in_viewer():
                return False
            if self.player_author() != author:
                return False
            return float(np.abs(self.frame(self.player_box()) - ref_frame).mean()) < PAUSE_SAME_FRAME
        except Exception:
            return False

    def player_author(self):
        """Author line of the full-screen player (None if not found)."""
        m = re.search(r'text="([^"]*)" resource-id="' + re.escape(RID + "clips_author_username"),
                      self.d.dump_hierarchy())
        return m.group(1) if m else None

    def help(self):
        """Key help in the same block style as the statistics, current modes inline."""
        a = self.args

        def mode(key):
            attr, label, modes, note = MODE_KEYS[key]
            line = f"{key}  {label + ' mode':<16} {cycle_text(modes, getattr(a, attr))}"
            return f"{line:<45} {note}".rstrip()

        log("── keys " + "─" * 56)
        log(f"   playback   n  next video (a skipped video gets no like/repost/link/save)")
        log(f"              p  pause: the phone is yours until p again (also runs/PAUSE)")
        speed = "x  2x speed".ljust(20) + cycle_text(SPEED_MODES, "on" if a.speed2x else "off")
        log(f"              {speed:<45} from the next video")
        log(f"              {mode('w')}")
        log(f"   actions    {mode('l')}")
        log(f"   (screen    {mode('r')}")
        log(f"    order)    {mode('c')}")
        log(f"              {mode('b')}")
        log(f"   info       s  statistics so far")
        log(f"              h  this help (also ?)")
        log(f"              q  quit")

    def player_box(self, top=0.12):
        """Video area of the full-screen player, minus side buttons and caption."""
        return 0, int(self.h * top), int(self.w * 0.8), int(self.h * 0.70)

    def detector(self, speed):
        """Loop-detector settings for this playback speed, with command-line overrides."""
        cfg = dict(DETECTOR[speed])
        for k in ("ref_start", "loop_thresh", "loop_rel"):
            if getattr(self.args, k, None) is not None:
                cfg[k] = getattr(self.args, k)
        return cfg

    def frame(self, box):
        """Small grayscale crop of the given screen box."""
        im = self.d.screenshot().convert("L").crop(box)
        return np.asarray(im.resize((48, 64)), dtype=np.float32)

    def in_viewer(self):
        return self.d(resourceId=CLIPS_VIEWER).exists

    def in_feed(self):
        return self.d(resourceId=FEED_LIST).exists and self.d(packageName=PKG, descriptionMatches=HOME_TAB, selected=True).exists

    def scroll(self, frac=0.55, settle=1.0):
        y0 = int(self.h * 0.75)
        self.d.swipe(self.w // 2, y0, self.w // 2, int(y0 - self.h * frac), 0.4)
        time.sleep(settle)

    def ensure_feed(self):
        """Get back to the Home timeline from wherever we are (popups, other tabs...)."""
        self.wake()
        for _ in range(4):
            if self.d.app_current().get("package") != PKG:
                self.d.app_start(PKG)
                time.sleep(4)
            if self.in_feed():
                return
            if self.in_viewer():
                self.d.press("back")
            else:
                home = self.d(packageName=PKG, descriptionMatches=HOME_TAB)
                if home.exists:
                    home.click()
                else:
                    self.d.press("back")
            time.sleep(1.5)
        log("could not reach the Home feed; retrying with app restart")
        self.d.app_start(PKG, stop=True)
        time.sleep(5)

    # ---- feed ----------------------------------------------------------
    HEADER_NODE = re.compile(r'<node [^>]*resource-id="' + re.escape(HEADER) + r'"[^>]*>')
    # signs that a post comes from an account you don't follow: a "Follow" button or a
    # "Suggested for you" label inside the post header
    _SUGGESTED = "(?:" + "|".join(re.escape(t) for t in UI_TEXT["suggested"]) + ")"
    NOT_FOLLOWED_NODE = re.compile(
        r'<node [^>]*(?:resource-id="' + re.escape(RID + "inline_follow_button") + r'"'
        r'|content-desc="' + _SUGGESTED + r'" [^>]*resource-id="' + re.escape(RID + "secondary_label") + r'"'
        r'|resource-id="' + re.escape(RID + "secondary_label") + r'" [^>]*content-desc="' + _SUGGESTED + r'")[^>]*>')

    @staticmethod
    def _y_range(node):
        return tuple(map(int, re.search(r'bounds="\[\d+,(\d+)\]\[\d+,(\d+)\]"', node).groups()))

    AGO = re.compile(r"^(.*?) (?:on )?(\d+) (second|minute|hour|day|week)s? ago$")
    # pt-BR: "x postou um video em Há 7 horas" (also "há", lower case)
    AGO_PT = re.compile(r"^(.*?) em [Hh]á (\d+) (segundo|minuto|hora|dia|semana)s?$")
    PT_UNIT = dict(segundo="second", minuto="minute", hora="hour", dia="day", semana="week")
    UNIT_MIN = dict(second=1 / 60, minute=1, hour=60, day=1440, week=10080)

    def post_id(self, desc):
        """(author/location part, estimated posting time in minutes or None, tolerance).
        The header's relative time label moves on while a post is watched ("23 minutes ago"
        -> "25 minutes ago"), so the text alone doesn't identify a post."""
        m = self.AGO.match(desc)
        unit = m.group(3) if m else None
        if not m:
            m = self.AGO_PT.match(desc)
            unit = self.PT_UNIT[m.group(3)] if m else None
        if not m:  # absolute dates ("7 October"): the text is stable
            return desc, None, 0
        n = int(m.group(2))
        posted = time.time() / 60 - n * self.UNIT_MIN[unit]
        return m.group(1), posted, max(3, self.UNIT_MIN[unit] * 1.1)  # label rounding

    def is_seen(self, desc):
        prefix, posted, tol = self.post_id(desc)
        for p, q, t in self.seen:
            if p == prefix and (posted is None and q is None or
                                posted is not None and q is not None and abs(posted - q) <= max(tol, t)):
                return True
        return False

    def remember(self, desc):
        # Only a short memory: the feed is walked forward, so all it must prevent is
        # re-picking the posts just handled (still on screen after Back). A long memory
        # would also skip later posts that look identical ("x posted a video 2 hours ago"
        # twice from the same account).
        self.seen = (self.seen + [self.post_id(desc)])[-6:]

    def find_video_header(self):
        """(desc, top, bottom, followed) of the topmost on-screen, not-yet-handled video
        post, or None.

        Uses a single hierarchy dump: querying each header separately costs a round trip
        apiece, and every second spent here is a second the video autoplays in the feed
        (the full-screen player then resumes from there instead of the beginning).
        With --play followed, videos from accounts you don't follow are skipped here.
        """
        xml = self.d.dump_hierarchy()
        not_followed = [self._y_range(n) for n in self.NOT_FOLLOWED_NODE.findall(xml)]
        best = None
        for node in self.HEADER_NODE.findall(xml):
            desc = re.search(r'content-desc="([^"]*)"', node).group(1)
            if not has_any(desc, "video_post") or has_any(desc, "sponsored") or self.is_seen(desc):
                continue
            top, bottom = self._y_range(node)
            followed = not any(top <= y0 < bottom for y0, _ in not_followed)
            if not followed and self.args.play == "followed":
                log(f"skipping suggested (not followed): {desc}")
                self.stats["suggested_skipped"] += 1
                self.remember(desc)
                continue
            if best is None or top < best[1]:
                best = (desc, top, bottom, followed)
        return best

    def media_box(self, desc):
        """Screen box (x0, y0, x1, y1) of the video of the feed post with this header."""
        xml = self.d.dump_hierarchy()
        hdr = re.search(r'<node [^>]*resource-id="' + re.escape(HEADER) + r'"[^>]*content-desc="'
                        + re.escape(desc) + r'"[^>]*>', xml)
        if not hdr:
            return None
        top = self._y_range(hdr.group(0))[1]
        for node in re.findall(r'<node [^>]*resource-id="' + re.escape(RID + "media_group") + r'"[^>]*>', xml):
            y0, y1 = self._y_range(node)
            if abs(y0 - top) < 10:
                return 0, y0, self.w, y1
        return 0, top, self.w, min(top + int(self.w * 1.25), int(self.h * 0.88))

    def open_next_video(self):
        """Find the next video and start it. Returns None if none was found, else
        (where, desc, followed): where is "player" (full-screen player opened) or "feed"
        (a regular feed video: a tap only turns its sound on, it keeps playing in place)."""
        tab_bar = int(self.h * 0.88)
        for _ in range(self.args.max_scrolls):
            self.key()
            found = self.find_video_header()
            if found:
                desc, top, bottom, followed = found
                if top > self.h * 0.35:
                    # pull the post up first: a tap low on the screen lands on the strip at
                    # the bottom of the video ("Turn sound on"), which doesn't open the player
                    self.d.swipe(self.w // 2, top, self.w // 2, int(self.h * 0.12), 0.5)
                    time.sleep(0.6)
                    found = self.find_video_header()
                    if not found or found[0] != desc:
                        continue
                    bottom = found[2]
                self.remember(desc)
                # tap right away: the sooner, the less the video has autoplayed in the feed
                self.d.click(self.w // 2, min(bottom + int(self.h * 0.15), tab_bar - 20))
                if self.d(resourceId=CLIPS_VIEWER).wait(timeout=5):
                    log(f"▶ {desc}")
                    return "player", desc, followed
                box = self.media_box(desc)
                if box:  # one more try, dead center of the video
                    self.d.click(self.w // 2, min((box[1] + box[3]) // 2, tab_bar - 20))
                    if self.d(resourceId=CLIPS_VIEWER).wait(timeout=5):
                        log(f"▶ {desc}")
                        return "player", desc, followed
                if self.d(resourceId=HEADER, description=desc).exists:
                    log(f"▶ {desc}  (plays in the feed: no full-screen player, no 2x)")
                    return "feed", desc, followed
                log(f"tap did not open the video: {desc}")
                self.ensure_feed()
            else:
                self.scroll()
        log("no video found after many scrolls; refreshing feed")
        self.d(packageName=PKG, descriptionMatches=HOME_TAB).click()  # scroll to top
        time.sleep(1)
        self.d(packageName=PKG, descriptionMatches=HOME_TAB).click()  # pull fresh
        time.sleep(4)
        self.seen.clear()
        return None

    # ---- watching ------------------------------------------------------
    def speed_2x(self):
        """Lock 2x playback: press & hold near the screen edge, then slide down and release.
        Returns True when the video plays at 2x.

        While held, Instagram shows a hint telling the current state:
          "Slide down to lock 2X speed"  -> not locked yet: slide down to lock (US English: "2x")
          "Slide down for normal speed"  -> already locked: just release (sliding would undo it)
        """
        # left edge, upper third: clear of the like/comment column and of the caption
        x, y = 60, int(self.h * 0.3)
        for attempt in range(2):
            self.d.touch.down(x, y)
            y_up = y  # where the finger is when released
            try:
                time.sleep(1.2)
                xml = self.d.dump_hierarchy()
                if has_any(xml, "speed_locked"):
                    log("  ⏩ 2x already locked")
                    return True
                if has_any(xml, "speed_unlocked"):
                    for i in range(1, 11):
                        y_up = y + i * 40
                        self.d.touch.move(x, y_up)
                        time.sleep(0.05)
                    log("  ⏩ 2x locked")
                    return True
            finally:
                self.d.touch.up(x, y_up)  # always lift the finger, even on errors / quit
            time.sleep(1)  # e.g. first-time "Press edge to fast-forward" tip: try once more
        log("  could not switch to 2x (hint not shown); playing at normal speed")
        return False

    def watch(self, still_open, box=None, can_pause=True, followed=True, speed=1):
        """See _watch(); records what a pause during it would leave (self.context)."""
        self.context = "player" if can_pause else "feed-video"
        try:
            return self._watch(still_open, box, followed, speed)
        finally:
            self.context = None

    def paused_since(self, start):
        """Seconds spent paused since `start`."""
        return sum(t1 - max(t0, start) for t0, t1 in self.pauses if t1 > start)

    def in_pause(self, t, slack=2.0):
        """Was time t during a pause (or just after it: log lines arrive a little late)?"""
        return any(t0 <= t <= t1 + slack for t0, t1 in self.pauses)

    def _watch(self, still_open, box=None, followed=True, speed=1):
        """Play the video until it has played args.loops times or hit max time (-> True),
        or until it is skipped / it goes away (-> False).

        still_open: callable telling whether the video is still on screen;
        can_pause (watch()): whether the video is in the full-screen player, where a pause taps
        it to pause it (a tap on an in-feed video would only toggle its sound);
        box: screen area the frame comparison looks at (None: the full-screen player's,
        per the speed profile);
        speed: actual playback speed (1 or 2), selects the detector settings (DETECTOR);
        followed: whether the author is followed -- switching the play mode to "followed"
        (key w) while a suggested video plays skips it right away.

        End of video is known from two independent signals, whichever comes first:
          1. Instagram's player log ("position bigger than duration") -- exact, but now and
             then a pass goes unlogged;
          2. frame comparison: the picture returns to what it showed near the start.
             The picture only gets back to the reference frames once the next pass reaches
             the point where they were taken, so this fires a few seconds after the end
             (~5 s in tests: the player opens a little into the video).
        """
        a = self.args
        cfg = self.detector(speed)
        if box is None:
            box = self.player_box(cfg["top"])
        start = time.time()
        refs, moved, loops, diffs = [], False, 0, []
        history = []  # (t, frame) kept for the max-watch diagnostic
        while True:
            if self.ends:
                if not self.ends.ensure_running():  # cheap: a poll() of the logcat process
                    log("  player-log watcher had stopped (adb connection drop?); restarted")
                ends = [e for e in self.ends.ends_since(start) if not self.in_pause(e[0])]
                if len(ends) >= a.loops:
                    t = ends[-1][0] - start - self.paused_since(start)
                    log(f"  end of video reached at {t:.0f}s (duration {ends[-1][1] / 1000:.0f}s)")
                    self.stats["end_log"] += 1
                    return True
            k = self.key()
            if k == "n":
                log("⏭ skipped")
                self.stats["skipped"] += 1
                return False
            if a.play == "followed" and not followed:
                log("⏭ skipped: play mode is now 'followed' and you don't follow this account")
                self.stats["skipped"] += 1
                return False
            if not still_open():
                log("  video closed unexpectedly")
                return False

            f = self.frame(box)
            t = time.time() - start - self.paused_since(start)  # after the screenshot, as in the recorded traces
            history.append((t, f.astype(np.uint8)))
            if t < cfg["ref_start"]:
                continue
            # frames near the start = the "loop point"
            if t < cfg["ref_start"] + cfg["ref_window"] and len(refs) < cfg["max_refs"] or not refs:
                refs.append(f)
                continue
            diff = min(float(np.abs(f - r).mean()) for r in refs)
            diffs.append(diff)
            # "back at the start": close to a reference frame, either in absolute terms or
            # relative to how different this video's frames usually are (talking heads and
            # other low-motion videos never get below a fixed threshold)
            back = diff < cfg["loop_thresh"] or (
                cfg["loop_rel"] and len(diffs) > 5 and diff < cfg["loop_rel"] * float(np.median(diffs)))
            # NB: not an elif -- a relative match can lie above move_thresh (high-motion
            # videos); the tuner (tools/tune_fallback.detect) evaluates it the same way
            if diff > a.move_thresh:
                moved = True
            if moved and back and t > cfg["ref_start"] + a.min_watch:
                loops += 1
                moved = False
                log(f"  loop {loops} detected by frame comparison at {t:.0f}s")
                if loops >= a.loops:
                    self.stats["end_frames"] += 1
                    return True
            if not moved and loops == 0 and t > a.static_watch:
                log("  no motion detected (static video); moving on")
                self.stats["end_static"] += 1
                return True
            if t > a.max_watch:
                log(f"  max watch time ({a.max_watch}s) reached")
                self.stats["end_max"] += 1
                self.save_max_watch_frames(history)
                return True

    def save_max_watch_frames(self, history):
        """A video that hits --max-watch is either really long or a loop both end signals
        missed; the log can't tell which. Save what was seen so tools/period.py can."""
        try:
            Path("runs").mkdir(exist_ok=True)
            fn = Path("runs") / f"maxwatch-{time.strftime('%Y%m%d-%H%M%S')}.npz"
            np.savez_compressed(fn, t=np.array([t for t, _ in history]),
                                f=np.array([f for _, f in history]))
            how = (f"docker compose run --rm app tool period.py {fn}" if os.environ.get("FEED_AUTOPLAY_CONTAINER")
                   else f"uv run tools/period.py {fn}")
            log(f"  frames saved for diagnosis: {how}")
        except Exception as e:  # diagnostics must never break a run
            log(f"  could not save frames ({type(e).__name__}: {e})")

    def player_author_followed(self):
        """In the full-screen player: is the video's author an account you follow?

        Not followed shows as a "Follow" button by the author's name, or as a social-context
        line ("Followed by X and 13 others") that Instagram shows instead of it on suggestions.
        Collaboration posts ("x and 2 others") are the exception: there the Follow button is
        for a co-author, while the feed showing the post means you follow one of them.
        """
        xml = self.d.dump_hierarchy()
        author = re.search(r'text="([^"]*)" resource-id="' + re.escape(RID + "clips_author_username"), xml)
        # collab: "x and 2 others" / "x and y" (pt-BR expected: "x e mais 2" / "x e y"; usernames
        # contain no spaces, so " e " only occurs between co-authors)
        if author and re.search(r" (?:and|e) (\d+ others|mais \d+|\S+)", author.group(1)):
            return True
        return RID + "inline_follow_button" not in xml and not any(
            f'text="{t}' in xml for t in UI_TEXT["followed_by"])

    def exact_count(self, kind):
        """An exact number shown in the player (e.g. "The like number is 304" / "O número de
        curtidas é 304"), or None when missing or abbreviated ("18.5K", "1,2 mil": a change
        of one isn't visible). kind: "like", "repost" or "save" (COUNTS)."""
        xml = self.d.dump_hierarchy()
        for pattern, sep in COUNTS[kind]:
            m = re.search(pattern, xml)
            if m:
                if not re.fullmatch(r"\d+(?:" + re.escape(sep) + r"\d{3})*", m.group(1)):
                    return None
                return int(m.group(1).replace(sep, ""))
        return None

    def icon_white(self, bounds):
        """116x116 map of the pure-white pixels of a button's icon (the full-screen player's
        like/repost icons are drawn in white; a strict threshold keeps light-grey video
        backgrounds out)."""
        b = bounds
        im = self.d.screenshot().convert("RGB").crop((b["left"], b["top"], b["right"], b["bottom"]))
        c = np.asarray(im.resize((116, 116))).astype(int)
        return (c.min(-1) > 235) & (c.max(-1) - c.min(-1) < 25)

    def heart_looks_liked(self, bounds):
        """An unliked heart is a white outline on any background; a liked one is filled red,
        so those outline pixels are red. Only the outline's own pixels are checked (the
        heart_outline mask), so the video behind the icon doesn't matter. Measured: outline
        >= 98 % white on 16 unliked hearts (incl. red and grey backgrounds), 0 % when liked."""
        return float(self.icon_white(bounds)[ICON_MASKS["heart_outline"]].mean()) < 0.5

    def is_liked(self, like, check_icon=True):
        """Liked if ANY sign says so: `selected` (in the player the label stays "Like" when
        liked; in the feed it becomes "Liked"), a label other than "Like", or -- in the
        full-screen player -- a heart without its white outline."""
        info = like.info
        if info.get("selected") or info.get("contentDescription") not in UI_TEXT["like_unliked"]:
            return True
        if not check_icon or not self.heart_looks_liked(info["bounds"]):
            return False
        time.sleep(1)  # only the icon says "liked": look once more before believing it
        return self.heart_looks_liked(info["bounds"])

    def tap_like(self, like, count_kind=None):
        """Tap a like button unless already liked; report the outcome. A like button is a
        toggle: tapping a liked post would remove the like, so check first. With
        count_pattern, the like count is compared before/after as a safety net."""
        if self.is_liked(like, check_icon=count_kind is not None):
            log("  ♥ already liked")
            return
        before = self.exact_count(count_kind) if count_kind else None
        like.click()
        if self.wait_liked(like):
            log("  ♥ liked")
            self.stats["liked"] += 1
            return
        after = self.exact_count(count_kind) if count_kind else None
        if before is not None and after is not None and after < before:
            # the checks said "not liked" but the count went down: it was liked and this
            # tap removed it -- put it back
            like.click()
            log(f"  ⚠ like had been on (count {before} -> {after}); restored it")
            return
        # Still not liked after 3 s: either the tap was lost, or (with an abbreviated count
        # the safety net can't read) the post had been liked and the tap removed it. One more
        # tap ends liked in both cases.
        like.click()
        if self.wait_liked(like):
            log("  ♥ liked (second tap)")
            self.stats["liked"] += 1
        else:
            log("  ♡ like did not register")

    def wait_liked(self, like, timeout=3.0):
        """Poll the like button's flag/label until it shows liked (the UI can lag the tap)."""
        end = time.time() + timeout
        while True:
            time.sleep(0.5)
            info = like.info
            if info.get("selected") or info.get("contentDescription") not in UI_TEXT["like_unliked"]:
                return True
            if time.time() > end:
                return False

    def like_in_player(self):
        like = self.d(resourceId=RID + "like_button")
        if like.exists:
            self.tap_like(like, count_kind="like")
        else:
            log("  ♡ like button not found")

    def like_in_feed(self, desc):
        """Like button of the feed post with this header: the first one below its video."""
        box = self.media_box(desc)
        if box:
            for like in self.d(resourceId=RID + "row_feed_button_like"):
                try:
                    if like.info["bounds"]["top"] >= box[3] - 10:
                        return self.tap_like(like)
                except UiObjectNotFoundError:
                    pass
        log("  ♡ like button not found")

    def run(self):
        failures = 0  # consecutive unexpected errors
        while True:
            try:
                if self.need_feed:  # at start and after a pause; inside the try: a hiccup here
                    self.d.screen_on()  # is recovered like any other
                    self.ensure_feed()
                    self.need_feed = False
                if self.ends and not self.ends.ensure_running():
                    log("player-log watcher had stopped (adb connection drop?); restarted")
                opened = self.open_next_video()
                if not opened:
                    continue
                where, desc, followed = opened
                if where == "player":
                    # the feed doesn't always mark suggested posts; the player does
                    followed = followed and self.player_author_followed()
                    if followed or self.args.play == "all":
                        self.mark_played()
                        self.play_in_player(followed, desc)
                    else:
                        log("  skipping: you don't follow this account")
                        self.stats["suggested_skipped"] += 1
                    self.d.press("back")
                    time.sleep(1.0)
                    self.ensure_feed()
                else:
                    self.mark_played()
                    self.play_in_feed(desc, followed)
                self.scroll(0.35, settle=0.6)  # move past the post we just watched
                failures = 0
                if self.stats["played"] >= self.next_report:
                    self.report()
                    self.next_report += 20
            except UiObjectNotFoundError as e:
                # the UI changed under us (scroll, popup, feed refresh): recover and keep going
                log(f"UI element vanished ({str(e)[-120:]}); recovering")
                time.sleep(1)
                self.recover()
            except (Quit, KeyboardInterrupt):
                raise
            except Resumed:  # after a pause the phone may be anywhere: start from the feed
                self.need_feed = True
            except Exception as e:
                # anything else (adb/Wi-Fi drop, uiautomator2 agent restart, ...): unattended
                # runs must not die -- back off, reconnect, carry on
                failures += 1
                self.stats["errors"] += 1
                wait = min(10 * failures, 120)
                log(f"error: {type(e).__name__}: {str(e)[:150]} -- retrying in {wait}s (#{failures})")
                time.sleep(wait)
                self.waited["reconnect"] += wait
                self.recover(reconnect=True)

    def recover(self, reconnect=False):
        """Best effort back to a usable state; errors here are left to the next loop turn."""
        try:
            if reconnect:
                self.d = u2.connect(self.d.serial)
                if self.ends:
                    self.ends.ensure_running()
            self.ensure_feed()
        except Quit:
            raise
        except Resumed:  # paused while waiting for an unlock: the next loop turn starts over
            self.need_feed = True
        except Exception as e:
            log(f"recovery failed ({type(e).__name__}: {str(e)[:100]}); will retry")

    def should_like(self, followed):
        """--like none | followed | all; only asked for videos watched to the end."""
        if self.args.like == "all" or (self.args.like == "followed" and followed):
            return True
        if self.args.like == "followed":
            log("  ♡ not liked: you don't follow this account")
        return False

    def should_repost(self, followed):
        """--repost none | followed | all; only asked for videos watched to the end.
        Paused for a while after Instagram refuses a repost (see repost_in_player)."""
        if self.args.repost == "all" or (self.args.repost == "followed" and followed):
            if time.time() < self.repost_paused_until:
                log(f"  not reposted: paused after Instagram refused one "
                    f"(until {time.strftime('%H:%M', time.localtime(self.repost_paused_until))})")
                return False
            return True
        if self.args.repost == "followed":
            log("  not reposted: you don't follow this account")
        return False

    def repost_state(self, bounds):
        """"reposted", "not reposted" or "unclear". The Repost button is identical in the UI
        tree in both states; only the icon differs: when reposted, the arrowhead tips vanish
        and a checkmark appears in the middle. Both regions are checked (repost_tips /
        repost_check masks), so a bright background can't fake either state on its own.
        Measured: plain icon tips >= 89 % white & check <= 21 %; reposted tips 0 %, check 100 %."""
        w = self.icon_white(bounds)
        tips = float(w[ICON_MASKS["repost_tips"]].mean())
        check = float(w[ICON_MASKS["repost_check"]].mean())
        if check >= 0.7 and tips <= 0.3:
            return "reposted"
        if tips >= 0.7 and check <= 0.4:
            return "not reposted"
        return "unclear"

    def repost_in_player(self):
        btn = self.d(packageName=PKG, description="Repost", clickable=True)  # not "Reposted N times"
        if not btn.exists:
            log("  repost button not found")
            return
        state = self.repost_state(btn.info["bounds"])
        for _ in range(2):  # the background is a playing video: an unclear read may clear up
            if state != "unclear":
                break
            time.sleep(1)
            state = self.repost_state(btn.info["bounds"])
        if state == "reposted":
            log("  🔁 already reposted")
            return
        if state == "unclear":
            # tapping a reposted video would undo the repost: when the icon can't be read,
            # leave it alone
            log("  repost skipped: icon state unclear (busy background)")
            return
        count = "repost"
        before = self.exact_count(count)
        btn.click()
        if self.d(resourceId=RID + "snackbar_message",
                  textMatches="^(" + "|".join(UI_TEXT["reposted"]) + ")$").wait(timeout=3):
            # "Reposted" is optimistic: when Instagram refuses (rate limit), the same bar turns
            # into "Unable to repost" ~5 s later and the icon/count revert. Confirm first.
            if self.repost_confirmed(btn, count, before):
                log("  🔁 reposted")
                self.stats["reposted"] += 1
                self.repost_backoff = REPOST_BACKOFF_MIN
            else:
                self.repost_refused()
            return
        time.sleep(1)
        after = self.exact_count(count)
        if before is not None and after is not None and after < before:
            # no "Reposted" message and the count went down: it had been reposted and this
            # tap removed it -- put it back
            btn.click()
            log(f"  ⚠ repost had been on (count {before} -> {after}); restored it")
        else:
            log("  repost not confirmed (no \"Reposted\" message)")

    def should_save(self, followed):
        """--save none | followed | all; only asked for videos watched to the end."""
        if self.args.save == "all" or (self.args.save == "followed" and followed):
            return True
        if self.args.save == "followed":
            log("  not saved: you don't follow this account")
        return False

    SAVE_SHEET = re.compile(r"Start a collection|Tap this row to unsave|"
                            + re.escape(RID + "empty_state_body"))

    def save_in_player(self):
        """Save the open video (to your private Saved collection).

        Findings (player, Instagram 450): `save_button`, label "Save" in both states -- only
        `selected` flips; the count ("Save number is 39") goes +1. Saving opens a
        "Saved / Start a collection" bottom sheet, closed here with Back. Tapping a saved
        post is inconsistent: once it reopened that sheet (with a "Tap this row to unsave"
        row), once it unsaved directly -- so treat it as a toggle: check `selected` before
        tapping, and if the exact count went down after the tap, tap again to restore."""
        btn = self.d(resourceId=RID + "save_button")
        if not btn.exists:
            log("  save button not found")
            return
        if btn.info.get("selected"):
            log("  🔖 already saved")
            return
        count = "save"
        before = self.exact_count(count)
        btn.click()
        saved = False
        end = time.time() + 3
        while time.time() < end:
            time.sleep(0.5)
            if self.d(resourceId=RID + "snackbar_message", textMatches=REFUSED).exists:
                log("  ⚠ Instagram refused the save")
                break
            if btn.info.get("selected"):
                saved = True
                break
        after = self.exact_count(count)
        if before is not None and after is not None and after < before:
            # the flag said "not saved" but the count went down: it was saved and this tap
            # removed it -- put it back
            btn.click()
            time.sleep(1.5)
            if self.SAVE_SHEET.search(self.d.dump_hierarchy()):
                self.d.press("back")
                time.sleep(0.8)
            log(f"  ⚠ save had been on (count {before} -> {after}); restored it")
            return
        if self.SAVE_SHEET.search(self.d.dump_hierarchy()):
            self.d.press("back")  # close the collections sheet, stay in the player
            time.sleep(0.8)
        if not saved:
            log("  save not confirmed")
        elif before is not None and after is not None and after <= before:
            log("  🔖 already saved (count unchanged)")  # the flag had missed it
        else:
            log("  🔖 saved")
            self.stats["saved"] += 1

    def should_share(self, followed):
        """--share-link none | followed | all; only asked for videos watched to the end."""
        if self.args.share_link == "all" or (self.args.share_link == "followed" and followed):
            return True
        if self.args.share_link == "followed":
            log("  no link copied: you don't follow this account")
        return False

    def share_sheet_open(self):
        xml = self.d.dump_hierarchy()
        return any(f'content-desc="{t}"' in xml for t in UI_TEXT["copy_link"])

    def close_share_sheet(self):
        """Back closes the sheet -- but only press it while the sheet is showing: otherwise
        Back would leave the player."""
        for _ in range(2):
            if not self.share_sheet_open():
                return
            self.d.press("back")
            time.sleep(1)

    def copy_link_in_player(self, desc):
        """Share -> "Copy link": Instagram puts the post's link on the phone's clipboard
        ("Copied"). The link is read back and appended to runs/shared-links.txt, since the
        next copy overwrites the phone's clipboard.

        Findings (player, Instagram 450): Share = `direct_share_button` (desc "Share"). The
        sheet holds a grid of chat recipients (tapping one selects it to SEND the post!),
        "Add to story", "WhatsApp", "Share", "Copy link", "WhatsApp status" -- only the
        button with content-desc exactly "Copy link" is ever tapped. The sheet stays open
        after copying. The copied link carries ?exln=... (unique to the account: "Links you
        share are unique to you"); the file gets the clean link without it."""
        share = self.d(resourceId=RID + "direct_share_button")
        if not share.exists:
            log("  share button not found")
            return
        share.click()
        copy = self.d(packageName=PKG, descriptionMatches="^(" + "|".join(UI_TEXT["copy_link"]) + ")$",
                      clickable=True)
        if not copy.wait(timeout=4):
            log("  no link copied: \"Copy link\" not found in the share sheet")
            self.close_share_sheet()
            return
        try:
            before = self.d.clipboard
        except Exception:
            before = None
        copy.click()
        copied = self.d(packageName=PKG, textMatches="^(" + "|".join(UI_TEXT["copied"]) + ")$").wait(timeout=3)
        link = None
        for _ in range(4):  # the clipboard can update a moment after "Copied"
            try:
                clip = self.d.clipboard
            except Exception:
                clip = None
            if clip and clip.startswith("https://www.instagram.com/") and (clip != before or copied):
                link = clip
                break
            time.sleep(0.5)
        self.close_share_sheet()
        if not link and not copied:
            log("  link not copied (no \"Copied\" message)")
            return
        self.stats["links"] += 1
        if not link:
            log("  🔗 link copied (couldn't read it back from the phone's clipboard)")
            return
        clean = link.split("?")[0]
        log(f"  🔗 link copied: {clean}")
        try:
            SHARED_LINKS.parent.mkdir(exist_ok=True)
            with SHARED_LINKS.open("a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{desc}\t{clean}\n")
        except Exception as e:  # a full disk etc. must not stop the run
            log(f"  could not write {SHARED_LINKS} ({type(e).__name__}: {e})")

    def repost_confirmed(self, btn, count, before, window=8.0):
        """After the optimistic "Reposted": False if Instagram says it's unable to repost
        within `window` s, or the icon ends up plain; True when the icon shows reposted."""
        end = time.time() + window
        while time.time() < end:
            if self.d(resourceId=RID + "snackbar_message", textMatches=REFUSED).exists:
                return False
            time.sleep(0.5)
        state = self.repost_state(btn.info["bounds"])
        if state == "reposted":
            return True
        after = self.exact_count(count)
        if state == "unclear" and before is not None and after is not None:
            return after > before
        return state == "unclear"  # icon unreadable and no exact count: trust the message

    def repost_refused(self):
        """Instagram refused a repost -- most likely a rate limit. Retrying straight away can
        lengthen a block, so pause reposting, doubling the pause on repeated refusals."""
        self.stats["repost_refused"] += 1
        minutes = self.repost_backoff
        self.repost_paused_until = time.time() + minutes * 60
        self.repost_backoff = min(self.repost_backoff * 2, REPOST_BACKOFF_MAX)
        log(f"  ⚠ Instagram refused the repost (\"Unable to repost\", probably a rate limit): "
            f"pausing reposts for {minutes} min")

    def play_in_player(self, followed, desc=""):
        """2x, watch to the end, then like, repost, copy the link and save (per options)."""
        speed = 2 if self.args.speed2x and self.speed_2x() else 1
        if not self.watch(self.in_viewer, followed=followed, speed=speed):
            return
        if self.should_like(followed):
            self.like_in_player()
        if self.should_repost(followed):
            self.repost_in_player()
        # same order as the buttons on screen (top to bottom): like, repost, share, save.
        # Each step closes its own sheet (share sheet, collections sheet) before the next.
        if self.should_share(followed):
            self.copy_link_in_player(desc)
        if self.should_save(followed):
            self.save_in_player()

    def play_in_feed(self, desc, followed):
        """Regular feed video (no full-screen player): watch it where it is, then like."""
        box = self.media_box(desc)
        if not box:
            log("  video went off screen")
            return
        misses = 0

        def still_open():
            # a single lookup can miss while the feed redraws: only give up after a few in a row
            nonlocal misses
            misses = 0 if self.d(resourceId=HEADER, description=desc).exists else misses + 1
            return misses < 4

        if not self.watch(still_open, box, can_pause=False, followed=followed, speed=1):
            return
        if self.should_like(followed):
            self.like_in_feed(desc)
        if self.args.repost != "none":
            log("  not reposted: the Repost button only exists in the full-screen player")
        if self.args.share_link != "none":
            log("  no link copied: only implemented in the full-screen player")
        if self.args.save != "none":
            log("  not saved: saving is only implemented in the full-screen player")


def startup_report(d, args, keys_on):
    """Startup block (same style as the stats and help): phone, Instagram version, settings."""
    def prop(name):
        try:
            return d.shell(f"getprop {name}").output.strip()
        except Exception:
            return ""
    phone = " ".join(x for x in (prop("ro.product.manufacturer").title(), prop("ro.product.model")) if x) or "phone"
    android = prop("ro.build.version.release")
    hw = prop("ro.serialno") or d.serial
    link = "Wi-Fi" if (":" in d.serial or "tls-connect" in d.serial) else "USB"
    try:
        m = re.search(r"versionName=(\S+)", d.shell(f"dumpsys package {PKG}").output)
        insta = m.group(1) if m else "?"
    except Exception:
        insta = "?"
    log("── feed_autoplay " + "─" * 47)
    log(f"   phone      {phone}" + (f" · Android {android}" if android else "") + f" · serial {hw} · {link}")
    if insta in TESTED_INSTAGRAM:
        log(f"   instagram  {insta}")
    else:
        log(f"   instagram  {insta}  ⚠ untested version (tested: {TESTED_INSTAGRAM[-1]}) -- labels or")
        log(f"              icons may have changed; if likes/reposts/2x misbehave, see DEVELOPMENT.md")
    extra = f" · {args.loops} passes" if args.loops > 1 else ""
    log(f"   playback   play {args.play} · 2x {'on' if args.speed2x else 'off'} · "
        f"max {args.max_watch:g} s per video{extra}")
    log(f"   actions    like {args.like} · repost {args.repost} · copy link {args.share_link} · "
        f"save {args.save}")
    log(f"   end        " + ("Instagram's log + frame comparison" if args.use_log else "frame comparison only (--no-log)"))
    stop = "stop.bat or create runs\\STOP" if WINDOWS else "Ctrl-C, kill <pid> or create runs/STOP"
    pause = "pause.bat" if WINDOWS else "create / delete runs/PAUSE"
    log(f"   keys       " + ("press h for help" if keys_on else f"off (no terminal) -- stop: {stop} · pause: {pause}"))


def pick_serial():
    """The adb serial to use when -s isn't given.

    With wireless debugging the same phone is often listed twice (ip:port and the
    adb-<serial>-xxxx._adb-tls-connect._tcp auto-connect name): that is fine, any entry
    works. Only several *different* phones need -s.
    """
    entries = [d for d in adbutils.adb.device_list() if d.get_state() == "device"]
    if not entries:
        sys.exit("no device connected (check `adb devices`; for Wi-Fi: adb connect <ip>:<port>)")
    phones = {}
    for d in entries:
        phones.setdefault(d.getprop("ro.serialno") or d.serial, []).append(d.serial)
    if len(phones) > 1:
        listing = "\n".join(f"  {hw}: {', '.join(serials)}" for hw, serials in phones.items())
        sys.exit(f"more than one phone connected, pick one with -s <serial>:\n{listing}")
    return entries[0].serial


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    g = p.add_argument_group("playback")
    g.add_argument("--play", choices=PLAY_MODES, default="followed",
                   help="followed (default) = only play videos from accounts you follow, skipping "
                        "suggested ones; all = play every video in the timeline")
    g.add_argument("--2x", dest="speed2x", action="store_true",
                   help="lock 2x playback speed for each video (default: normal speed; key x toggles it)")
    g.add_argument("--loops", type=int, default=1, help="how many times to watch each video (default 1)")
    g.add_argument("--max-watch", type=float, default=300, help="max seconds per video (default 300)")

    g = p.add_argument_group("actions on videos watched to the end (done in screen order)")
    g.add_argument("--like", choices=LIKE_MODES, default="followed",
                   help="which fully watched videos to like: none = never; followed (default) = only "
                        "from accounts you follow; all = every one")
    g.add_argument("--repost", choices=REPOST_MODES, default="none",
                   help="which fully watched videos to repost (shown on your profile): none "
                        "(default) = never; followed = only from accounts you follow; all = every one")
    g.add_argument("--share-link", choices=SHARE_MODES, default="none",
                   help="which fully watched videos to Share -> Copy link for (links are also "
                        "appended to runs/shared-links.txt): none (default) = never; followed = only "
                        "from accounts you follow; all = every one")
    g.add_argument("--save", choices=SAVE_MODES, default="none",
                   help="which fully watched videos to save to your (private) Saved collection: "
                        "none (default) = never; followed = only from accounts you follow; all = every one")

    g = p.add_argument_group("device")
    g.add_argument("-s", "--serial", help="adb device serial (default: the only connected device)")

    g = p.add_argument_group("advanced tuning (end-of-video detection, feed scrolling; DEVELOPMENT.md 4.5)")
    g.add_argument("--no-log", dest="use_log", action="store_false",
                   help="don't use Instagram's player log for end-of-video; frame comparison only")
    g.add_argument("--ref-start", type=float,
                   help="seconds after start to grab the reference frames for loop detection "
                        "(default: per-speed profile, see DETECTOR)")
    g.add_argument("--loop-thresh", type=float,
                   help="frame diff below this = back at start (default: 6)")
    g.add_argument("--loop-rel", type=float,
                   help="...or below this fraction of the video's median frame diff, 0 = off "
                        "(default: 0.5 at 2x, off at 1x)")
    g.add_argument("--move-thresh", type=float, default=12, help="frame diff above this = video is moving")
    g.add_argument("--min-watch", type=float, default=3, help="ignore loop matches before this many seconds")
    g.add_argument("--static-watch", type=float, default=45,
                   help="seconds to show a video with no detectable motion before moving on")
    g.add_argument("--max-scrolls", type=int, default=40, help="scrolls without a video before refreshing")
    args = p.parse_args()

    # the log uses symbols/emoji: make sure they can be written even to a redirected file or an
    # old Windows console (code page), instead of crashing
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    for f in (STOP_FILE, PAUSE_FILE):  # left over from an earlier run: must not stop/pause this one
        try:
            f.unlink()
        except OSError:
            pass

    d = u2.connect(args.serial or pick_serial())
    startup_report(d, args, keys_on=sys.stdin.isatty())
    # `kill <pid>` and `docker/podman stop` send SIGTERM, which would end Python without the
    # final statistics: treat it like Ctrl-C (SIGINT)
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    if WINDOWS:  # Ctrl+Break in the console window
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    ends = EndWatcher(d.serial) if args.use_log else None
    with Keys() as keys:
        player = Player(d, args, keys, ends)
        try:
            player.run()
        except (Quit, KeyboardInterrupt):
            player.report()
            log("bye")
        finally:
            if ends:
                ends.stop()


if __name__ == "__main__":
    main()
