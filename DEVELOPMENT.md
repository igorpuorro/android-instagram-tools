# android-instagram-tools — development notes

This document records how the project's tools work, why each decision was made, and what was
tried and failed along the way. There is one tool so far, **feed_autoplay** (`feed_autoplay.py`).
(For what the tools do and how to install and run them, start with `README.md`; containers:
`CONTAINER.md`.) Read it before changing behaviour: most of the "obvious" alternatives were
already tried on the real phone and are listed here with the reason they were dropped.

- **Project-wide:** 2 (test environment), 3 (naming, project layout, architecture), the
  container setup (in 1), 7 (pitfalls) — they apply to any future tool too.
- **feed_autoplay:** 1, 4 (feature details), 5 (tests and runs), 6 (limitations). Much of 4.8–4.11
  (recovery, connection, keys, statistics) is meant to become shared code (3).

Contents

1. [feed_autoplay: what it does / how to run](#1-feed_autoplay-what-it-does--how-to-run)
2. [Test environment](#2-test-environment)
3. [Naming, project layout and architecture](#3-naming-project-layout-and-architecture)
4. [feed_autoplay: feature details, decisions and findings](#4-feed_autoplay-feature-details-decisions-and-findings)
   - 4.1 [Automation tool](#41-automation-tool)
   - 4.2 [Finding videos in the timeline](#42-finding-videos-in-the-timeline)
   - 4.3 [Opening a video](#43-opening-a-video)
   - 4.4 [2x speed](#44-2x-speed)
   - 4.5 [Detecting the end of a video](#45-detecting-the-end-of-a-video)
   - 4.6 [Followed vs. suggested accounts](#46-followed-vs-suggested-accounts)
   - 4.7 [Liking](#47-liking), [reposting](#47b-reposting), [copying links](#47d-copying-links)
     and [saving](#47c-saving) — done in this order, the order of the buttons on screen
   - 4.8 [Navigation and recovery](#48-navigation-and-recovery)
   - 4.9 [Device connection](#49-device-connection)
   - 4.10 [Keyboard controls](#410-keyboard-controls)
   - 4.11 [Statistics and pace estimate](#411-statistics-and-pace-estimate)
   - 4.12 [Languages](#412-languages) — English and Brazilian Portuguese
5. [How things were tested (and how to re-test)](#5-how-things-were-tested-and-how-to-re-test)
6. [Known limitations and ideas](#6-known-limitations-and-ideas)
7. [Pitfalls checklist](#7-pitfalls-checklist)
8. [Commit messages (Conventional Commits)](#8-commit-messages-conventional-commits)

---

## 1. feed_autoplay: what it does / how to run

Walks the Instagram **home timeline** on an Android phone and plays every video/reel one
after another, so the phone (mirrored with scrcpy on a second display) is always playing
something:

find a video post in the feed → tap it (full-screen player, with sound) → optionally lock
**2x** speed (`--2x`) → watch until the video **ends** → optionally **like**, **repost**, **copy
its link** and/or **save** it (in that order — the buttons' order on screen) → Back → scroll on
→ repeat.

```bash
cd ~/android-instagram-tools
uv run feed_autoplay.py                          # defaults: --play followed --like followed, 1x
uv run feed_autoplay.py --2x --play all --like none   # everything at 2x, no likes
```

Options are grouped the same way in `--help` (argparse argument groups). Every setting lists
its values in the same order, **none → followed → all** ("do nothing" to "do it for
everything"); play has no "none" (**followed → all**). The order is defined once, by the mode
lists in the code (`PLAY_MODES` … `SAVE_MODES`), which `--help`, the keys and the in-app help
all use.

| Group | Option | Default | Meaning |
|---|---|---|---|
| **playback** | `--play followed\|all` | `followed` | skip videos from accounts you don't follow, or play everything |
| | `--2x` | (off) | lock 2x speed for each video (normal speed otherwise) |
| | `--loops N` | 1 | passes to watch per video |
| | `--max-watch S` | 300 | cap per video |
| **actions** on videos watched to the end, done in screen order | `--like none\|followed\|all` | `followed` | which ones get liked |
| | `--repost none\|followed\|all` | `none` | which get reposted (reposts show on your profile; `all` on long runs hits Instagram's repost limit, see 4.7b) |
| | `--share-link none\|followed\|all` | `none` | which get Share → Copy link; links are appended to `runs/shared-links.txt` |
| | `--save none\|followed\|all` | `none` | which get saved (to your private Saved collection) |
| **device** | `-s SERIAL` | auto | adb serial; only needed with several *different* phones |
| **advanced tuning** | `--no-log` | (log on) | end-of-video by frame comparison only |
| | `--ref-start`, `--loop-thresh`, `--loop-rel` | per-speed profile | override the frame-comparison profile (see 4.5) |
| | `--move-thresh`, `--min-watch` | 12 / 3 | frame-comparison tuning (see 4.5) |
| | `--static-watch S` | 45 | move on if a video shows no motion at all for this long |
| | `--max-scrolls N` | 40 | scrolls without finding a video before refreshing the feed |

Keys while running (only when started from a terminal):

| Key | Action |
|---|---|
| **n** | next video (skipped videos are never liked, reposted, link-copied or saved) |
| **p** | pause: hand the phone over (the tool stops touching it) / resume (4.10) |
| **w** | cycle play mode: followed → all |
| **l** | cycle like mode: none → followed → all |
| **r** | cycle repost mode: none → followed → all |
| **c** | cycle copy-link mode: none → followed → all |
| **b** | cycle save mode: none → followed → all |
| **s** | show the statistics so far (same block as the automatic one every 20 videos) |
| **h**, **?** | show the keys, grouped, with each mode's cycle and the current one in brackets |
| **q** | quit |

At startup the app prints a block with the phone, the Instagram version and the settings:

```
── feed_autoplay ───────────────────────────────────────────────
   phone      Samsung SM-A515F · Android 11 · serial R58N91XKQZT · Wi-Fi
   instagram  451.0.0.53.80
   playback   play all · 2x on · max 300 s per video
   actions    like all · repost followed · copy link none · save none
   end        Instagram's log + frame comparison
   keys       press h for help
```

`phone` comes from `getprop` (the hardware serial, not adb's Wi-Fi connection name), `Wi-Fi`/`USB`
from the adb serial's form. On an Instagram version not in `TESTED_INSTAGRAM` the `instagram`
line adds "⚠ untested version" — selectors, texts and icon masks (4.7) may need re-checking.
`keys` says "off" when stdin isn't a terminal (background runs).

Unattended runs (keys don't work there — no terminal). Stop with `kill <pid>` (SIGTERM is handled
like Ctrl-C), or by creating `runs/STOP` (any system; `stop.bat` on Windows) — either way the
final statistics are printed. Pause by creating `runs/PAUSE`, resume by deleting it (`pause.bat`
toggles it on Windows; 4.10):

```bash
nohup uv run feed_autoplay.py --play all --2x --like all < /dev/null >> runs/longrun-<date>.log 2>&1 &
```

**Setup — uv** (native on Linux, macOS and Windows). `pyproject.toml` declares the project and
pins the tested versions (uiautomator2 3.7.0, adbutils 2.12.0, numpy 2.2.6, Pillow 12.3.0;
`requires-python >=3.10,<3.14` — these pins have wheels up to 3.13); `uv.lock` (committed) pins
the whole dependency tree. `uv run <script>` creates/syncs `.venv` from the lock on first use
(about a second once the packages are cached) and fetches a matching Python if none is
installed — no `pip`/`venv` steps. `tool.uv.package = false`: not an installable package, the
tools are scripts. Change dependencies with `uv add` / `uv lock` (and mirror the pins in the
`Dockerfile`, which installs with pip). A system `adb` is **not** required: the one bundled with
`adbutils` is used, and `tools/adb.py` exposes it (`uv run tools/adb.py pair|connect|devices`).
USB debugging or Wi-Fi debugging must be enabled on the phone; the screen must be unlocked.

**Windows (native):** `run.bat` (= `uv run feed_autoplay.py %*`, checks that uv is installed,
`chcp 65001`, keeps the window open at the end), `stop.bat` (creates `runs\STOP`) and
`pause.bat` (creates / deletes `runs\PAUSE`: pause / resume); all are
kept with CRLF line endings by `.gitattributes`. Code differences, all behind `WINDOWS = os.name ==
"nt"`: keys via `msvcrt` instead of termios/select (4.10); Ctrl+Break handled like Ctrl-C;
stdout/stderr reconfigured to UTF-8 (all systems) so the symbols/emoji can't crash an old console
or a redirected file. Windows has no SIGTERM for console apps (`taskkill` without `/F` doesn't
reach them, `/F` loses the statistics) — hence the stop file. USB works natively (vendor USB
driver needed). **Tested on Windows 11** by the owner (2026-10-21): `run.bat` over Wi-Fi
debugging, the keys (msvcrt) and `stop.bat` all work. USB on Windows (vendor driver) is not
tried yet. Linux runs the same uv workflow (tested: setup, a background run stopped via the stop
file).

**In a container (Docker or Podman — no Python on the host):** see `CONTAINER.md`.
Image `feed-autoplay` (named in `compose.yaml`; the code is copied in, so rebuild after code
changes). Files: `Dockerfile` (python:3.12-slim + the tested package versions, adbutils' adb linked as
`adb`, `FEED_AUTOPLAY_CONTAINER=1`), `docker/entrypoint.sh` (`pair`, `adb …`, `tool <script>`,
otherwise `adb connect $PHONE` with retries, then the app), `compose.yaml` (`./runs` mounted,
named volume `adb-keys` for the pairing key, default `command:` for `up -d`), `.env.example`
(`PHONE`, `TZ`), `.dockerignore`. The app runs unchanged (Linux inside the container). Findings:
- Wi-Fi only; connect by `ip:port` (the mDNS auto-connect names don't reach the container);
  the port changes when wireless debugging is re-enabled or the phone restarts.
- The phone accepts the container's adb and the PC's own adb connected at the same time.
- Instagram's end-of-video log reaches the app inside the container (`EndWatcher` uses the same
  bundled adb). Head-to-head, back to back, `--play all --2x --like none`, ~10 min each
  (2026-10-20): container 10 played, ends log 8 / frames 1, ~56 videos/h; host 9 played, log 5 /
  frames 3, ~55/h; no failed taps/2x/errors in either. The container is on par (the log-share
  gap is within chance for ~9 ends). A first attempt had been spoiled by the owner's own
  instance running on the phone at the same time (see 7).
- Container default time zone is UTC → `TZ` + `tzdata` so log times match the PC.
- `compose up -d` has no terminal → keys off (`tty` deliberately not set); `compose run` has one.
- `docker/podman stop` sends SIGTERM → now handled like Ctrl-C (stats printed); verified.
- Messages that print a command (max-watch diagnosis) show the container form when
  `FEED_AUTOPLAY_CONTAINER` is set.
- Not tried: the container on Windows (native Windows with uv is tested, see above), Podman, `pair` from the container, likes/reposts/links/saves inside
  the container (tested outside, same code).

Instagram's terms forbid automated access. Playing and liking at human pace is low-key, but
keep it in mind before adding anything that interacts at volume (follows, comments, ...).

## 2. Test environment

Everything below was measured on this setup; coordinates and IDs may differ elsewhere.

| | |
|---|---|
| Phone | a mid-range Samsung Galaxy, Android 11 (SDK 30), 1080×2340, buttons navigation bar |
| Instagram | **451.0.0.53.80** — auto-updated from 450.0.0.50.77 on 2026-10-16 19:23, a few hours into development; only the first exploration (feed headers, first player dumps) ran on 450. All recordings, tuning, icon masks and long runs are on 451. The app warns at startup on any other version (`TESTED_INSTAGRAM`). |
| PC | Ubuntu; Python 3.10 (development, pip venv) → Python 3.13 via uv (since 2026-10-21); uiautomator2 3.7.0, adbutils 2.12.0, numpy 2.2.6, Pillow 12.3.0 |
| Connection | USB at first, later Wi-Fi debugging |
| Phone settings | pattern screen lock; Developer options → **Stay awake** on (since 2026-10-18, after 5.1) |

Useful screen landmarks (1080×2340): status bar ends ~83 px; Instagram tab bar starts at
y ≈ 2088 (0.89·h); system navigation bar 2214–2340.

## 3. Naming, project layout and architecture

**Naming.** The repository is **`android-instagram-tools`** — an umbrella for tools that drive
the Instagram app on an Android phone. Each tool is named for its job, without repeating
"android"/"instagram" (the repository says that): this one is **`feed_autoplay`** (Python
module/file, snake_case) and **`feed-autoplay`** (Docker image/command, kebab-case);
environment variables use `FEED_AUTOPLAY_…`. Future tools follow the same object + action
pattern (e.g. `story_viewer`). History: `insta_autoplay` → `instagram_autoplay` → `feed_autoplay`
(old run logs in `runs/` still show the old names).

**Planned layout once a second tool exists** (not before — the shared interface should be
shaped by two real users): code any Instagram tool needs (phone connection and `pick_serial`,
lock-screen wait, error recovery, `EndWatcher`, `Keys`, the stats block, icon masks, follow
detection) moves into a shared package, each tool into its own subpackage:

```
android-instagram-tools/
├── android_instagram/            shared (device, logwatch, keys, stats, ui, …)
│   └── feed_autoplay/            this tool → python -m android_instagram.feed_autoplay
├── tools/                        dev tools, per tool
├── tests/                        checks without a phone (test_ui_text.py, 4.12)
└── Dockerfile, compose.yaml, README.md, DEVELOPMENT.md, CONTAINER.md
```

Until then everything lives in `feed_autoplay.py`:


| Piece | Role |
|---|---|
| `Keys` | non-blocking key reader (termios/select on Linux/macOS, msvcrt on Windows); inert when stdin isn't a TTY |
| `STOP_FILE` (`runs/STOP`) | checked in `Player.poll()`: creating it stops the run cleanly (stats printed); cleared at startup |
| `PAUSE_FILE` (`runs/PAUSE`) | checked in `Player.key()`: while it exists the run is paused (`Player.pause`); cleared at startup |
| `Player.pause` / `Resumed` | the hand-the-phone-over pause (4.10); `Resumed` sends the run back to the Home feed |
| `Player.key` | handles global keys (q, w, l, r, c, b, s, h/?) wherever it is polled; returns n/p to the caller |
| `MODE_KEYS` / `cycle_text` | the five mode keys in one table (attribute, label, cycle, note); `followed → [all]`-style cycle text |
| `PLAY_MODES` … `SAVE_MODES` | the mode lists — the single definition of each setting's values and their order (also used as `--help` choices) |
| `Player.help` | the in-app help block (key **h** / **?**), current modes inline |
| `startup_report` | the startup block: phone, Instagram version (warns if not in `TESTED_INSTAGRAM`), settings |
| `EndWatcher` | background thread following `adb logcat` for Instagram's end-of-video line |
| `Player.find_video_header` | one hierarchy dump → topmost unhandled video post + followed flag |
| `Player.post_id` / `is_seen` / `remember` | short memory of handled posts, robust to the "N minutes ago" label moving on |
| `Player.open_next_video` | scroll/pull/tap until a video is playing; returns `("player"\|"feed", desc, followed)` |
| `Player.speed_2x` | edge press-and-hold + slide down to lock 2x |
| `Player.watch` | waits for the end (log signal or frame comparison; log lines from pauses ignored), skip key, caps |
| `Player.player_author_followed` | follow check inside the full-screen player |
| `Player.like_in_player` / `like_in_feed` / `tap_like` | verified like via the like button |
| `Player.is_liked` / `heart_looks_liked` / `exact_count` | "already liked?" from flag, label and the heart's outline; count-drop safety net |
| `Player.repost_state` / `repost_in_player` | reposted / not reposted / unclear from the icon's shape; tap only when clearly not reposted |
| `Player.repost_confirmed` / `repost_refused` | catch Instagram's delayed "Unable to repost"; pause reposting with back-off |
| `Player.icon_white` + `assets/icon_masks.npz` | white-pixel map of a player icon, compared against recorded icon shapes |
| `Player.should_like` / `should_repost` / `should_share` / `should_save` | apply `--like` / `--repost` / `--share-link` / `--save` (none / followed / all) |
| `Player.copy_link_in_player` / `close_share_sheet` | Share → "Copy link", read the link from the phone's clipboard, log it to `runs/shared-links.txt` |
| `Player.save_in_player` | save only when not saved; close the collections sheet; count-drop safety net |
| `Player.locked` / `wake` | lock-screen detection; waits for an unlock, never gestures on it |
| `Player.run` / `recover` | main loop; survives errors with back-off + reconnect |
| `Player.report` | stats every 20 played videos, on quit, and on key **s** (incl. reposts refused by Instagram, links copied, saves) — see 4.11 |
| `Player.mark_played` / `pace` + `PACE_*` | cycle times of played videos (waits excluded) → pace estimate with likely range (4.11) |
| `Player.save_max_watch_frames` | saves the frames of a video that hit `--max-watch` for diagnosis |
| `Player.play_in_player` / `play_in_feed` | the two playback paths |
| `Player.ensure_feed` | gets back to the Home timeline from anywhere |
| `pick_serial` | chooses the adb device (copes with duplicate Wi-Fi entries) |

Supporting tools (see section 5): `tools/adb.py` (the bundled adb: pair/connect/devices),
`tools/record_traces.py` (record test videos),
`tools/tune_fallback.py` (score detector settings), `tools/period.py` (period estimate; also
analyses `runs/maxwatch-*.npz`), `tools/backtest_pace.py` (backtest the stats' pace estimate on
run logs, 4.11), `tools/traces/` (13 2x recordings), `tools/traces_1x/`
(22 1x recordings) and `tools/icon_samples/` — the data folders are **local only**
(git-ignored, see 5). Run logs and max-watch dumps go to `runs/`. Container setup: `Dockerfile`,
`compose.yaml`, `docker/entrypoint.sh`, `.env.example`, guide `CONTAINER.md`. Native setup:
`pyproject.toml` + `uv.lock` (uv), `run.bat` / `stop.bat` / `pause.bat` (Windows), `.gitattributes` (CRLF for
`.bat`).

---

## 4. feed_autoplay: feature details, decisions and findings

### 4.1 Automation tool

**Chosen: uiautomator2** (Python, talks to an agent on the phone over adb). It reads the
UI tree (resource IDs, content descriptions, bounds), injects taps/swipes and raw touch
down/move/up, and takes screenshots (~0.3–0.9 s each).

Alternatives considered: plain adb `input` (coordinates only, no UI tree), py-scrcpy-client
(video frames + input, no UI tree), Airtest (image matching — not needed since Instagram's
UI is readable), Appium (works, but adds a server for nothing). scrcpy itself is only used to
*watch* the phone; the automation does not go through it.

### 4.2 Finding videos in the timeline

**How:** every feed post has a header `com.instagram.android:id/row_feed_profile_header`
whose content description says what the post is:

- `"<user> posted a video <when>"` ← what we look for (feed reels and regular videos)
- `"<user> posted a photo …"`, `"<user> posted a carousel …"` ← skipped

Do **not** use `video_container` to detect videos — photo posts contain it too. Headers
containing "Sponsored" are skipped (ad detection has not actually been observed/verified).
Carousels may contain videos; they are skipped entirely (not implemented).

**One dump per look.** `find_video_header` parses a single `dump_hierarchy()` with regexes
instead of querying each header through selectors (one round trip each). Reason: every
second spent here is a second the video autoplays in the feed (see 4.3).

**Short memory of handled posts.** `remember()` keeps only the last 6 posts.
*Lesson:* a long memory (50) skipped later videos whose header text was identical
("x posted a video 2 hours ago" twice from the same account). Since the feed is only walked
forward, the memory only needs to stop re-picking posts still on screen after Back.
Posts are identified by author/location text + **estimated posting time** (`post_id`), not the
raw header text: the relative label moves on while a post is watched. *Bug fixed:* a post
labelled "23 minutes ago" was replayed right after because its label had become "25 minutes
ago" (seen in a live run; the replay correctly found it "already liked/reposted"). Tolerance:
3 min for minute labels, ~1.1 units for hours/days (covers a "5 → 6 hours" rollover); absolute
dates ("7 October") compare as text.

**Scrolling:** swipe of 0.55·h over 0.4 s, then settle. Measured displacement 1252–1306 px
for 1287 px intended — no fling overshoot, so no header is scrolled past unseen.

*Bug fixed:* uiautomator2 selectors like `d(resourceId=HEADER)[i]` are **positional**
(`instance: 1`). After a swipe the Nth header is a different post or gone →
`UiObjectNotFoundError`, or worse, tapping the wrong post. Always re-locate a post by its
content description, never keep a positional selector across a scroll.

### 4.3 Opening a video

Tapping a feed video opens the **full-screen reels player** (`clips_viewer_container`),
with sound. Back returns to the feed at the same position.

**Tap position matters.** *Measured:* every tap at y ≈ 1800–2039 (post low on the screen)
failed to open the player — it landed on the strip at the bottom of the video where
Instagram shows "Turn sound on"; taps at y ≈ 555 / 792 worked. A speed optimisation that
tapped videos "wherever they are" caused streaks of 4–5 failures in a row.
**Current rule:** if the header's top is below 35 % of the screen, pull the post up to ~12 %
first, then tap 0.15·h below the header; if the player doesn't open within 5 s, tap once more
at the centre of the video (`media_box`). Only then fall back to the in-feed path.

**In-feed path (`play_in_feed`).** For a video that still doesn't open, the script watches it
where it is (no 2x; a pause leaves it, see 4.10) and likes via the feed's `row_feed_button_like`.
⚠ This path is barely tested: most "failures" turned out to be the tap-position problem above.
In its only real run it stopped after 41 s with a false "video closed" (a single missed
lookup); `still_open` now needs 4 misses in a row. Not re-verified since.

**The player resumes where the feed autoplay was.** Feed videos autoplay (muted) as soon as
they are on screen, and the full-screen player continues from that position — so the
beginning of each video is missed. *Measured head start* (from `(duration/2 − time to end)·2`):

| Version | Head start into the video |
|---|---|
| first version (per-header selector queries, swipe then tap) | ~12 s |
| single dump + tap where it is | ~8 s (but taps low on screen failed, see above) |
| current (pull up when low, then tap) | ~10–12 s |

About 5 s of that happens inside the player (opening + the 2x gesture), the rest in the feed.

*Tried and rejected:* **restarting the video** by swiping to the next reel and back.
Trial 1 restarted it (head start dropped); trial 2 the swipe back landed on a *different*
reel, which was then played. It also plays ~1 s of a random reel's audio. Not reliable
enough.

### 4.4 2x speed

Opt-in with `--2x` (it was the default until the CLI was changed; normal speed is now the
default); key **x** switches it on/off during a run, from the next video (4.10). Instagram plays at 2x **while** the screen edge is pressed. Holding for the whole video would
interfere with screenshots, so the script **locks** it:

1. `touch.down` at **x = 60, y = 0.3·h** (left edge, upper third).
2. After 1.2 s, read the hint Instagram shows while the finger is down (it *is* in the UI tree):
   - `"Slide down to lock 2X speed"` → not locked: move the finger down 400 px in 10 steps, release.
   - `"Slide down for normal speed"` → already locked: release without sliding (sliding would undo it).
3. On release Instagram shows "Locked at 2X speed" — this toast is **not** in the UI tree.
4. The finger is always lifted in a `finally` (errors, quit).

Findings:
- The edge zone is ~130 px wide on both sides (x = 5…130 and 950…1075 worked; x = 200 did not).
- The **first** press ever showed a one-time tip "Press edge to fast-forward" instead — hence
  one retry.
- The 2x lock **resets for every video** ("already locked" never appeared) → done per video.
- ⚠ *Accident during testing:* pressing the **right** edge at mid-height hit the like/comment
  column; on release it opened the comments sheet, and the next hold long-pressed a comment
  (Reply / Share / **Report** / **Block** menu). Nothing was selected, but: never touch the right
  column (x > ~0.85·w, y ≈ 0.38–0.8·h) or the caption area.
- Raw `touch.down`/`move`/`up` keep working while screenshots and dumps are taken.

### 4.5 Detecting the end of a video

Reels loop forever, and the player has **no progress bar** in the UI tree. Things checked
that do **not** help: `dumpsys media_session` (Instagram registers nothing), `dumpsys audio`
(player state doesn't change on loop; feed videos are muted), `dumpsys media.metrics`,
codec buffer log lines (no pattern).

#### Primary signal: Instagram's player log

At the end of a pass, Instagram logs:

```
W ServicePlayerState: position=45763 bigger than duration=45718
```

`EndWatcher` runs `adb logcat -T 1 -s ServicePlayerState:W` in a thread, timestamps lines on
**arrival (PC clock)** — avoids phone/PC clock skew — and `watch()` asks for events after the
moment playback started. Bursts within 2 s count as one end. It also gives the exact duration.

Reliability at 2x: it fires on most passes but **not all** — e.g. one 24 s video logged only 3 of 6
real ends; one 25 s video's first logged end came at 33 s. Some videos log nothing at all.
Hence the fallback.

**At normal speed (1x) it misses much more.** The line only appears when the polled position
overshoots the duration, which happens more easily at 2x. Measured at 1x: a 90 s video
watched for 130 s logged **nothing**; in the 10 recorded 1x traces, 2 videos logged no end at
all in 150 s and the others logged only about half their passes (e.g. 2 of 5, 3 of 5). At 1x the
frame fallback does most of the work.

#### Fallback: frame comparison

Small grayscale crops of the video area (`player_box`: x 0–0.8·w, y top–0.70·h, i.e.
without the side buttons and caption) resized to 48×64; the mean absolute pixel difference
between frames is the metric.

The settings depend on the speed the video **actually** plays at (`DETECTOR` in the script;
`speed_2x()` returns whether the lock worked; in-feed videos are always 1x):

| | 2x profile | 1x profile |
|---|---|---|
| `top` (crop upper edge) | 0.12·h | 0.20·h |
| references | up to 5 frames from 1.0 s | up to 15 frames between 0.5 and 3.5 s |
| `loop_thresh` | 6 | 6 |
| `loop_rel` | 0.5 | off |
| offline result (section 5 scoring) | 13/13, 0 early | 19/20, 0 early |

Algorithm in `watch()`:
1. From `ref_start` (1.0 s at 2x, 0.5 s at 1x), take up to `max_refs` frames within `ref_window`
   (3 s) as references.
2. For each new frame: `diff` = min difference to the references; keep the history of diffs.
3. `moved` once `diff > move_thresh` (12).
4. Loop detected when `moved` and (`diff < loop_thresh` **or**, if enabled, `diff < loop_rel` ×
   median(diffs)) and at least `min_watch` after the references — evaluated **independently**
   of step 3 (a relative match can be above `move_thresh`; see v6 below).
   Frame timestamps are taken *after* the screenshot, as in the recorded traces.
5. Static guard: no motion at all for `static_watch` (45 s) → move on. Cap: `max_watch`.

`--ref-start`, `--loop-thresh`, `--loop-rel` override the profile for both speeds.

**Inherent latency.** The picture only matches the references when the *next* pass reaches the
point where they were taken. Because the player opens several seconds into the video (4.3),
detection comes ~5 s after the real end at 2x and ~6 s at 1x. At 2x the log usually wins; at
1x the fallback ends most videos.

**Tuning history** (scored against log ground truth, see section 5):

| Version | Result |
|---|---|
| v1: 3 refs at 1 s, absolute threshold 6, static guard 15 s | first data set: 4/6 correct. Live: some videos cut short, others replayed |
| v2: 5 refs at 2.5 s (after the "Locked at 2X" toast) | first data set 6/6 offline, but live 6–9 s late, once 21 s, one video missed both loops |
| v3: + relative threshold 0.45×median, refs at 1.0 s, static guard 45 s | 2x: **13/13, 0 early, ~5 s mean latency** (old settings on the same 13: 9/13, 2 missed, 2 late by 25–34 s). 1x (later, 8 traces): 6/8 — **2 early fires** (25 s and 14 s before the end: videos cut short) |
| v4: per-speed profiles; 1x: 15 refs from 1.0 s, threshold 8, no relative rule | 2x unchanged 13/13; 1x 8/8 on the first 8 traces — but on 20 traces 18/20 with **1 early fire** (106 s early on a 129 s video) |
| v5: 1x threshold 6, refs from 0.5 s | 2x 13/13, 1x **19/20, 0 early**; the remaining 1x miss is missed by every setting tried |
| v6 (current): **app/tuner mismatch fixed**, 2x `loop_rel` 0.5 | see below |

**v6 — the app didn't run what was tuned.** `watch()` had `if diff > move_thresh: moved = True`
`elif moved and back: loop`, so a match with diff > 12 could never count; the tuner evaluates
the match independently, so every relative-threshold result above was optimistic for the app.
Found via the max-watch dumps of a live run (5.2): 2 of 3 videos that hit the 300 s cap had
**looped** (86.8 s and 44.5 s periods) with loop-point diffs of 13–17 against medians of 36–42
— a clear relative match, blocked by the `elif`. Also the app timestamped frames *before* the
screenshot, the traces *after* (one-frame shift of the references; it flipped one of these
cases). After both fixes the app's `watch()`, driven by a fake clock over the recordings,
fires exactly where `tools/tune_fallback.detect` does: 13/13 (2x), 20/20 (1x), and on the
max-watch dumps. With the two looping dumps added, 2x `loop_rel` 0.5 catches one on its first
pass (88 s) and the other at 180 s (3rd pass) instead of 300 s, still 13/13 and 0 early on the
13 traces (0.55+ fires early, see sensitivity). *Lesson:* keep one detector implementation, or
test the app's against the tuner's (the fake-clock harness used here is easy to rebuild).

Why v1 failed: the 15 s static guard cut **talking-head** videos (they never exceed
`move_thresh` against their references); single-frame matches with a fixed threshold missed
loops in low-contrast videos. The relative threshold is what fixed the misses.

Parameter sensitivity (13 traces, refs at 1.0 s; measured with the tuner's logic):
`loop_rel` 0.35–0.40 → 12/13 (one miss);
0.45–0.50 → 13/13; 0.55–0.60 → early fires (cuts videos). Refs at 0.5 s with 0.50 fired early
once, so 1.0 s was kept for margin. Requiring 2 consecutive matching frames made it worse.
Cropping lower (y from 0.2) made no difference at 2x.

At 1x: the relative threshold is what causes early fires (−30 s on one video), so it is off
there; 15 references over 3 s instead of 5 fixed a miss; `loop_thresh` 8 caused the −106 s
early fire, 6 doesn't. Refs from 0.5 s and 1.5 s both score 19/20; 0.5 s was chosen because
all its detections land at or after the loop point (offsets 0…+2 s), while 1.5 s has −1 s
ones. **No single setting works at both speeds:** scored on 21 traces together the best one
reached 20/21 (loses a 2x video), and the others fire early at one speed or the other.

*Lesson:* the first 1x choice (8/8 on 8 traces) turned out to fire early once 12 more traces
were added. Small trace sets flatter settings; prefer ≥ 20 traces before trusting a change.

### 4.6 Followed vs. suggested accounts

The timeline mixes posts from followed accounts with suggestions. Signs found:

**In the feed** (checked inside the header's vertical range):
- `com.instagram.android:id/inline_follow_button` ("Follow <Name>") in the header, or
- `secondary_label` with content-desc "Suggested for you".
(Also present but not used: "Suggested for you" carousels `netego_carousel_*`,
`suggested_user_card_follow_button`.)

**In the full-screen player:**
- `inline_follow_button` next to `clips_author_username`, or
- a social-context line `text="Followed by X and 13 others"` that replaces the Follow button
  on some suggestions.

*Measured:* feed and player verdicts agreed on 11 of 12 posts. The feed **misses** some
suggestions, so `--play followed` checks again right after the player opens and leaves
immediately (before 2x) if the author isn't followed.

**Collaboration posts** ("news.channel and 2 others", "chef.marco and cityfoodtour") show a
Follow button for a co-author you don't follow. Decision: a collab counts as followed unless
the **feed** marks it suggested — it is in your timeline because you follow one of the
co-authors. Consequence: `chef.marco and cityfoodtour` gets liked because you follow
cityfoodtour. A `sports.central` collab that the feed labelled "Suggested for you" is still treated as
not followed (the feed verdict is ANDed with the player verdict). Mapping the Follow button
to a specific co-author is not possible reliably (its label is the display name, not the
username).

### 4.7 Liking

- **When:** after the video has been watched to its end, right before Back. Reasons: nothing
  touches the screen while 2x is locked or while the reference frames are taken; skipped
  videos (n) and videos left early are never liked. Earlier moments (on open, right after
  the 2x lock) were rejected for those reasons.
- **How:** the like button only (`like_button` in the player, `row_feed_button_like` in the
  feed), never a double tap (the player's double tap also pauses/plays).
- **Never tap an already liked post** (it's a toggle: the tap would remove the like, e.g. one
  you made by hand). `is_liked()` says liked if ANY of these does:
  - `selected=true` — in the **player the label stays `"Like"` when liked**, only `selected`
    flips (verified live); in the **feed** the label becomes `"Liked"` and `selected=true`;
  - content-desc other than `"Like"`;
  - in the full-screen player, the heart has **lost its white outline** (`heart_looks_liked`):
    an unliked heart is a white outline on any background, a liked one is filled red. Only the
    outline's own pixels are compared (`heart_outline` mask in `assets/icon_masks.npz`), so the
    video behind the icon doesn't matter. Measured: outline ≥ 98 % white on 16 unliked hearts,
    0 % on a liked one; live on 20 more videos it agreed with `selected` 20/20. When only the
    icon says "liked", it is checked once more 1 s later.
  - Feed like buttons: flag and label only (the feed's label is reliable, its icon differs).
  ⚠ *Bug fixed (2026-10-18):* the first icon check counted **red pixels over the whole button**
  (> 5 %). On videos with a red background behind the heart (common in this feed: party
  colours, flags) an unliked heart read as liked (31.7 % red measured) → "already liked" →
  **missed likes**. The "safe direction" argument hid the bug: a skipped like is safe for the
  account but still wrong. Check icon *shape*, not colour amounts.
- **Safety net:** in the player the exact like count ("The like number is 22759. View likes")
  is read before and after the tap; if it went **down**, the post had been liked after all and
  the tap removed it → tap again to restore, log `⚠ like had been on … restored it`. Only
  works with exact counts ("18.5K" → unknown). Tested offline with a simulated button whose
  signals all lie; never triggered live.
- **After the tap:** the flag/label is polled for up to 3 s (`wait_liked`; the UI can lag). If it
  still isn't liked: count safety net first; otherwise **one more tap** — it ends liked both
  when the first tap was lost and when the post had been liked and the first tap removed it
  (with an abbreviated count the net can't tell). Logs `♥ liked`, `♥ liked (second tap)` or
  `like did not register`. *Why:* a live run logged 2 × "like did not register" (with the old
  single 0.8 s read) on posts with "K" counts; the cause couldn't be determined from the log.
- `--like none` / `followed` (default) / `all`. `--play` and `--like` are independent.

### 4.7b Reposting

Same model as liking: `--repost none|followed|all` (default **none** — unlike a like, a repost is
published on your profile), key **r** to cycle, only for videos watched to the end, done right
after the like and before leaving the player. In-feed videos: not supported (the Repost
button only exists in the full-screen player; logged).

Findings (player, Instagram 451):
- The button has **no resource-id**: content-desc `"Repost"`, clickable. Right below it is
  `repost_count` ("Reposted 2945 times") which opens the list of reposters — match the
  content-desc exactly.
- Tapping shows at once a snackbar `snackbar_message` "Reposted" + `snackbar_text_button`
  "Undo" (gone after a few seconds) and a notes bubble ("Add a thought…"); when Instagram
  accepts it the count goes +1 — but it can still refuse a few seconds later (see below).
- **Repost is a toggle and its state is not in the UI tree** (same desc, `selected=false` in
  both states). Tapping an already reposted video **removes** the repost (count −1, no message).
- The state is visible only in the icon: when reposted, the **arrowhead tips vanish** and a
  **checkmark** appears in the middle. `repost_state()` checks both regions (`repost_tips`,
  `repost_check` masks, made by differencing a plain and a reposted icon on the same video):
  reposted = check ≥ 70 % white and tips ≤ 30 %; not reposted = tips ≥ 70 % and check ≤ 40 %;
  anything else = **unclear** → re-checked up to twice, 1 s apart (the background is a playing
  video), then skipped with a log line. Measured: plain icons tips ≥ 89 %, check ≤ 21 %
  (16 samples); reposted tips 0 %, check 100 %; live on 20 more videos: 1 reposted (correct),
  18 not reposted, 1 unclear.
  ⚠ *Bug fixed (2026-10-18):* the first check only counted white pixels in the middle box; a
  light-grey/bright background there read as a checkmark (e.g. `urban.sketches`) → "already
  reposted" → **missed reposts**. Needing evidence in *both* regions fixes it.
- End-to-end after both fixes (first 10 min of a `--play all --2x --like all --repost
  followed` run, `runs/run-2026-10-18-likefix.log`): 13/13 finished videos liked, 0 "already
  liked"; 4 reposts confirmed by the snackbar, 9 not reposted (not followed), 0 unclear.
  (Counted by the "Reposted" snackbar only, before refusal detection existed — see below.)
- Icon masks: `assets/icon_masks.npz` (`heart_outline`, `repost_tips`, `repost_check`, 116×116,
  white = all channels > 235 and saturation < 25 — strict so grey backgrounds don't count).
  Recorded on this phone/Instagram 451; another screen density or app version needs new ones
  (collect crops of plain/liked/reposted icons, consensus over ~16 videos — see 5).
- **Instagram can refuse reposts** (rate limit — seen after a run with `--repost all` that
  reposted ~96 videos in 1.7 h). The refusal is **delayed**: tap → snackbar "Reposted" + Undo
  at 0.7 s (optimistic) → **5.1 s** later the same `snackbar_message` reads **"Unable to
  repost"**; the count stays, the icon goes back to plain. So "Reposted" alone is not success.
  `repost_confirmed()` keeps watching for up to 8 s for "unable / couldn't / can't / try again"
  and then requires the icon to show reposted (or an exact count +1 when the icon is
  unclear). A refusal → `repost_refused()`: counted as "refused by Instagram" (not reposted),
  and reposting **pauses** 30 min, doubling per further refusal up to 4 h, reset by a confirmed
  repost (`REPOST_BACKOFF_MIN/MAX`). Liking and playback go on. Retrying straight into a rate
  limit risks a longer action block.
  ⚠ Runs before this fix counted every "Reposted" as a repost, so all earlier repost numbers
  (5.2, 5.3) are upper bounds; how many were refused is unknown (refusals probably started
  in the 01:25 `--repost all` run, 5.3).
  Verified live: refusal detected at ~5 s, not counted, 30 min pause started. **Not yet seen
  live:** a repost confirmed by the new check (Instagram was refusing all reposts when it was
  built) — the success path and the back-off reset are tested offline only, with a simulated
  Instagram. Check the first `🔁 reposted` lines of the next run.
- `repost_in_player()` flow: skip if paused after a refusal (`not reposted: paused … until HH:MM`)
  → check icon → tap only if clearly not reposted → wait for "Reposted" (3 s) → confirm (8 s
  window, no refusal, icon reposted) → `🔁 reposted`; refusal → `⚠ Instagram refused the
  repost … pausing reposts for N min`. Without any "Reposted" message: if the exact repost
  count ("Reposted 6592 times") went **down**, the tap removed an existing repost → tap again
  to restore (`⚠ repost had been on … restored it`); otherwise `repost not confirmed`.
  A confirmed repost takes ~8 s more before leaving the video.
- Count regexes: `[\d,]+(?:\.\d+)?[KM]?` — the like label ends with a sentence period
  ("22759. View likes"); a first version took it as part of the number and silently never
  read a count.

### 4.7c Saving

`--save none|followed|all` (default **none**), key **b** to cycle, only for videos watched to the
end, done **last** — like → repost → copy link → save, the order of the buttons on screen, so
the log reads in screen order. Its collections sheet is closed before the video is left.
Saved posts go to the private Saved collection (not visible to others). In-feed videos: not
supported (the feed's save button hasn't been inspected; logged).

Findings (player, Instagram 451):
- `save_button`, content-desc `"Save"` in **both** states — only `selected` flips (true =
  saved), as with the player's like button. Below it `save_count` ("Save number is 39").
- Saving: `selected` → true within ~1.7 s, count +1, and a **bottom sheet** opens: title "Saved",
  "Save posts in collections just for you…", "Start a collection" (`empty_state_body`,
  `primary_action_button`). Back closes it and stays in the player.
- Tapping a **saved** post is **inconsistent**: once it reopened the sheet with a row "Media is
  saved in current private collection. Tap this row to unsave media."; another time the tap
  **unsaved directly**. ⇒ treat Save as a toggle.
- `save_in_player()`: `selected` → `🔖 already saved` (no tap) → otherwise tap, poll `selected`
  for 3 s (a refusal snackbar "unable / try again" → `⚠ Instagram refused the save`, not
  counted) → read the exact count → close the sheet. If the exact count went **down**, the post
  had been saved and the tap removed it → tap again (`⚠ save had been on … restored it`); if it
  stayed the same → `already saved (count unchanged)`; else `🔖 saved` (counted).
- No icon-shape check (unlike like/repost): `selected` was right in every observation; the
  count net covers a stale flag when counts are exact.
- Tested: live on one video — saved (count 39 → 40, sheet closed, still in the player), then
  `already saved` with no tap; the test save was then undone (count back to 39). The restore
  path is tested offline (simulated button whose flag lies). Not seen yet: an Instagram
  refusal of a save (no limit observed so far).

### 4.7d Copying links

`--share-link none|followed|all` (default **none**), key **c** to cycle, only for videos watched to
the end, done after like and repost and **before save** (screen order: like, repost, share,
save). The share sheet is closed before saving starts. In-feed videos: not supported (logged).
Tested in that order on one video: link copied, then saved, both sheets closed, still in the
player.

Findings (player, Instagram 451):
- Share = `direct_share_button` (content-desc "Share"; `ufi_text_component` below it is the
  reshare count "Reshare number is 7"). It opens a share sheet with:
  - a grid of **chat recipients** (`direct_share_sheet_grid_view_pog`, "… Chat not selected") —
    tapping one **selects it to send the post**;
  - a bottom row of buttons (`button`, label below): "Add to story", "WhatsApp", "Share",
    **"Copy link"**, "WhatsApp status";
  - a note "Links you share are unique to you and may be used to improve suggestions and ads".
  ⚠ Only the element with content-desc exactly **"Copy link"** (clickable, in Instagram's
  package) is ever tapped; everything else in this sheet publishes or sends something.
- Copy link → text **"Copied"** within ~1 s; the link is on the phone's clipboard; the **sheet
  stays open** → Back closes it. Back is pressed only while the sheet is showing
  (`close_share_sheet`) — on the player it would leave the video.
- uiautomator2 can **read the phone's clipboard** (`d.clipboard`). The link looks like
  `https://www.instagram.com/reel/<code>/?exln=<id>`; `exln` ties it to this account ("unique
  to you"). Logged and written **without** the query: `https://www.instagram.com/reel/<code>/`.
  The phone's clipboard keeps Instagram's version (and is overwritten by the next copy — hence
  the file).
- `runs/shared-links.txt`: one line per copy — `date time <TAB> post header <TAB> clean link`.
- Log lines: `🔗 link copied: <link>`; `🔗 link copied (couldn't read it back …)` when the
  clipboard can't be read but "Copied" appeared; `link not copied (no "Copied" message)`;
  `no link copied: "Copy link" not found in the share sheet`.
- Tested: live on one video (link read back, file written, sheet closed, still in the player),
  then a 4-min run with `--share-link all`: 3/3 finished videos copied and logged, the run
  carried on normally. Not seen yet: an Instagram refusal or a missing "Copy link" button.

⚠ *Mistake during testing:* a test script tapped Repost to "undo" its own repost without
checking the icon first; the video had been reposted earlier by the account owner, so the tap
removed the owner's repost (it was re-reposted at once, but that counts as a new repost).
Any test that taps Repost must check `repost_state()` before **every** tap, including undos.

### 4.8 Navigation and recovery

- `ensure_feed()`: relaunch Instagram if another app is in front; Back out of the player;
  tap Instagram's Home tab; after 4 tries restart the app.
- ⚠ *Bug fixed:* the **system** navigation bar's Home button also has content-desc "Home"
  (`com.android.systemui:id/home`). `d(description="Home")` tapped it and sent the phone to the
  launcher. Always add `packageName=PKG` to selectors that could match system UI.
- `run()` catches `UiObjectNotFoundError` (UI changed mid-step), logs it and recovers.
- *Bug fixed:* the startup steps (`screen_on`, first `ensure_feed`) ran **before** the recovery
  loop, so a uiautomator2 agent restart right at startup (`RemoteDisconnected`, seen once)
  crashed the app with a traceback. They now run inside the loop and are retried like any
  other error.
- **Unattended runs:** any other exception (adb/Wi-Fi drop, uiautomator2 agent restart, …) is
  logged and retried after a growing pause (10 s × consecutive failures, max 120 s) with a
  reconnect (`recover(reconnect=True)`); the run never exits on its own. The log watcher's
  `adb logcat` is restarted whenever it has died (`EndWatcher.ensure_running`, checked every
  watch-loop turn and between videos), and its event list is capped.
- **Statistics** are logged every 20 played videos, on quit and on key **s** — format, the pace
  estimate and its alternatives: see 4.11.
- *Tested live* during a long run (nothing touched on screen):
  - killed the run's `adb logcat` → first version only checked between videos, so the video
    playing lost the log signal (ended by frames after 228 s); now checked inside `watch()`
    too → restarted within the same second;
  - killed the uiautomator2 agent on the phone (`app_process … com.wetest.uia2.Main -p 9008`)
    → `RemoteDisconnected` logged, 10 s pause, reconnect; uiautomator2 restarted the agent and
    the next video played, ended and was liked normally (the interrupted one was not liked).
  To find the logcat process from a shell without matching your own command line, use
  `pgrep -f "[l]ogcat -T 1 -s ServicePlayerState"` (a plain pattern also matched — and once
  killed — the test shell itself).
- No video after `max_scrolls` (40) → tap Home twice (scroll to top + refresh) and clear the memory.
- **Lock screen.** The phone must be unlocked. "Screen on" doesn't tell: the lock screen is on
  too. `locked()` reads `isKeyguardShowing=true` from `dumpsys window` (verified on this phone).
  `wake()` turns the screen on and, if locked, **waits** (checks every 15 s, q still quits)
  until someone unlocks it, then carries on.
  ⚠ This phone has a **pattern lock** (swiping up shows "Draw unlock pattern"). Never gesture
  on the lock screen: a vertical swipe through the middle crosses the pattern's centre column
  and can count as a wrong attempt; repeated ones lock the phone out. `wm dismiss-keyguard`
  and swipes don't unlock it. *Mistake made during testing:* turning the screen off on purpose
  (`input keyevent KEYCODE_SLEEP`) to test recovery locked the phone, and it stayed locked
  until its owner came back. Don't test with the screen off on a phone with a secure lock.

### 4.9 Device connection

- With Wi-Fi debugging the same phone can be listed **twice** (`192.168.x.x:port` from
  `adb connect`, and `adb-<serial>-xxxx._adb-tls-connect._tcp` from Android's auto-connect).
  `u2.connect()` without a serial then fails with "more than one device/emulator".
  `pick_serial()` groups entries by `ro.serialno` and picks one if they're all the same phone;
  with several different phones it lists them and asks for `-s`.
- The system `/usr/bin/adb` disappeared at some point; `EndWatcher` now runs
  `adbutils.adb_path()` (the adb bundled with the pip package). Without this fix the log signal
  silently failed and only the slower frame fallback worked.

### 4.10 Keyboard controls

`Keys` puts the terminal in cbreak mode and polls stdin with `select` (Linux/macOS), or polls
`msvcrt.kbhit()`/`getwch()` (Windows; the two-code arrow/function keys are ignored), so the main
loop never blocks. `Player.poll()` also checks the stop file `runs/STOP` first: if it exists it is
removed and the run ends like `q` (works without a terminal, on every system); `Player.key()`
adds the pause (key p or `runs/PAUSE`, below). `Player.key()` is polled both while scanning the feed and while watching; it handles
the global keys itself (q raises `Quit`; w / l / r / c / b cycle `args.play` / `args.like` /
`args.repost` / `args.share_link` / `args.save` in place (one table, `MODE_KEYS`) and log the
new mode with its cycle, e.g. `like mode: all   (none → followed → [all])`; x toggles
`args.speed2x` (2x on/off, `SPEED_MODES`); s prints the stats;
h/? prints the help block; p pauses) and
returns only n to the caller.

The help (`Player.help`) uses the same block style as the statistics, grouped like `--help`,
with the current mode marked inside each key's cycle:

```
── keys ────────────────────────────────────────────────────────
   playback   n  next video (a skipped video gets no like/repost/link/save)
              p  pause: the phone is yours until p again (also runs/PAUSE)
              x  2x speed         off → [on]                from the next video
              w  play mode        followed → [all]
   actions    l  like mode        none → followed → [all]
   (screen    r  repost mode      none → [followed] → all  shows on your profile
    order)    c  copy link mode   [none] → followed → all  → runs/shared-links.txt
              b  save mode        [none] → followed → all  private to you
   info       s  statistics so far
              h  this help (also ?)
              q  quit
```

**x (2x) applies from the next video**, unlike the modes below: the playing video keeps its
speed, so the end detector's per-speed settings (`DETECTOR`, chosen when the video opens) stay
right, and no extra hold-and-slide is needed mid-video. Turning it off needs no unlock either —
Instagram resets the lock for every video (4.4). Tested live 2026-10-21 (pseudo-terminal, `--2x`,
x pressed during video 1 → video 2 at 1x, x again → videos 3–4 locked 2x).

Mode changes apply immediately: the like, repost, copy-link and save decisions are made when
a video ends, so a new mode applies to the video currently playing; switching play to "followed" while a suggested
video plays skips it at once (`watch(..., followed=...)`). Play has two modes only — a "none"
play mode would mean playing nothing. When stdin isn't a TTY (pipes, background runs, tests) keys are simply disabled —
needed because `termios` (and `msvcrt`'s console reading) fail without a terminal.

#### Pause: handing the phone over

Meant for "I want to use the phone for a while". Until 2026-10-21 `p` only toggled play/pause in
the full-screen player, and that wasn't safe for using the phone (analysis of that date):
- it didn't work while the feed was being scanned or in-feed videos played;
- resume tapped the centre of *whatever* was on screen (another app, another reel);
- after resume the app saw "video closed unexpectedly" and its recovery pulled the phone back
  to Instagram's Home feed;
- the end-of-video log was still read while paused, and any reel *the user* watched writes
  those lines → the app could "finish" the video and **like/repost/save the reel on screen**;
- paused time counted in the pace; background runs had no pause at all.

Now (`Player.pause`, entered from `Player.key()`, which is polled everywhere: feed scan, player,
in-feed video, lock-screen wait):
1. **Pause** (key p, or the file `runs/PAUSE` appears): in the full-screen player one tap
   pauses the video and, 1 s later, the author and a frame of the paused video are recorded.
   In the feed or an in-feed video nothing is tapped (a tap there toggles sound).
2. **While paused** the app doesn't touch the phone (no taps, swipes, screenshots or dumps);
   it only polls keys / files — q, the stop file, s, h and the mode keys still work.
3. **Resume** (p again, or the file deleted when the pause came from the file): the video
   continues in place (one tap) **only if** the screen is on and unlocked, Instagram is in
   front, the full-screen player shows the same author **and** the frame still matches
   (`PAUSE_SAME_FRAME`, mean difference < 4 grey levels) — i.e. nobody touched it. Otherwise
   the video is left (counted as skipped, no actions) and `Resumed` is raised: `run()` sets
   `need_feed`, so the next loop turn goes to the Home feed (`ensure_feed`, which waits for an
   unlock without gesturing if the phone got locked).
4. Each pause is stored (`self.pauses`): end-of-video log lines during a pause (+2 s slack) are
   ignored, watch time excludes it (`paused_since`), and the stats count it as waiting
   (`waits … paused`), out of the pace — like locked time. Recorded in a `finally`, so a stop
   while paused counts it too.

The 2x lock survives a pause in place (checked by holding the edge after resuming: "…normal
speed" hint). Tested live 2026-10-21 (`--2x`, likes and links off; pseudo-terminal for keys,
plus a background run for the file):

| Scenario | Result |
|---|---|
| p in the player, phone untouched for 23 s, p | resumed in place; end detected at 29 s (pause excluded) |
| p in the player, Settings opened, p | "the phone was used, so this video is left"; back to the feed, next video played |
| p in the player, swiped to other reels, let them play/loop 70 s, p | no end-of-video during the pause, no actions; left, back to the feed |
| p right after a video ended (feed scan), p | back to the Home feed, carried on |
| s / h while paused, q while paused | stats/help shown; quit with stats |
| `runs/PAUSE` created in the player, deleted 15 s later (no terminal) | resumed in place, 2x still locked; 36 s video ended at 19 s |
| `runs/PAUSE` during the feed scan / `runs/STOP` while paused | back to the feed / stopped, pause counted (`paused 1m`) |

Not tried live: a pause during an in-feed video (rare path; same handling as the feed scan),
the phone locked during a pause (avoided: it has a pattern lock — the code path is the normal
unlock wait), `pause.bat` on Windows.


### 4.11 Statistics and pace estimate

#### The block

Logged every 20 played videos, on quit and on key **s** (`Player.report`):

```
── stats after 10h 42m (active 5h 04m) ─────────────────────────
   videos   played 304 · skipped 0 · suggested not played 0
   pace     ~62 videos/h at the current pace (likely 46–77)
            whole run 28.4/h (60.0/h active)
   actions  liked 302 · reposted 0 (refused 0) · links copied 0 · saved 0
   ends     log 231 · frames 67 · static 1 · max-time 3
   waits    errors recovered 17 · locked 5h 14m · reconnecting 24m
```

- **header:** elapsed time; "active" = elapsed minus waits, shown once ≥ 1 min was spent waiting.
- **pace:** the estimate below. **whole run:** the plain average (videos ÷ elapsed hours), and per
  *active* hour when there were waits — e.g. 28/h overall but 60/h while actually playing.
- **waits:** time at the lock screen (`wake`) and in the error back-off sleeps (`run`); the
  latter undercounts a long outage slightly (only the sleeps are timed).
- Searching a log for "stats after" finds the blocks (one header line each).

#### Current implementation (v2, weighted mean)

*Question it answers:* "if things go on as they are, how many videos will the next hour bring?"

- **Data — cycle times.** `Player.mark_played()` runs at the start of every *played* video
  (not for skipped suggestions): cycle = time since the previous played video's start, minus
  the waiting time (`waited`) accrued in between. The last `PACE_KEEP` = 300 cycles are kept.
- **Estimate.** `Player.pace()`: pace = 3600 ÷ the **time-weighted mean** of the cycles, the
  weight halving every `PACE_HALF_LIFE` = 30 videos back (exponentially weighted mean).
- **Range.** "likely" = pace × `PACE_RANGE` = (0.75, 1.25), calibrated empirically (below).
- **Guards.** No estimate below `PACE_MIN` = 5 cycles ("estimate after 6 videos"); "rough"
  below `PACE_ROUGH` = 20.
- **Code.** Constants and both methods sit together in `Player` (search for `PACE_`); the
  report line is built in `Player.report`.

*Measured* (backtest below): mean absolute error **10.0 videos/h**, bias **+2.2**; the actual
next-hour count was inside the range at **79 %** of checkpoints (44/56); calibrated on 3 runs
and tested on the 4th: 59–100 % (59 % for the 10.7 h run, the least steady pace).

#### How it was measured — `tools/backtest_pace.py`

```bash
uv run tools/backtest_pace.py runs/*.log
```

Rebuilds every video's start time from the `▶` lines of run logs; at a checkpoint every 10
videos it computes each estimator from the cycle times so far and compares it with the number
of videos actually played in the next hour. Hours containing a gap > 15 min (lock, outage) are
skipped and such gaps are left out of the cycles, as the app does. It imports the app's
`PACE_HALF_LIFE` / `PACE_RANGE`, so it always tests the current settings. Baseline (4 runs of
2026-10-18/19, 56 checkpoints) — the numbers to beat:

| Estimator | mean abs error (videos/h) | bias | note |
|---|---|---|---|
| median of last 20 cycles | 20.5 | **+20.1** | v1, replaced |
| mean of last 20 cycles | 11.7 | +3.9 | |
| mean of last 40 / 60 cycles | 10.5 / 10.3 | +2.3 / +2.0 | (one-off test, not in the script) |
| mean of the whole run | 10.0 | +3.1 | |
| **weighted mean, half-life 30** | **10.0** | **+2.2** | **v2, current** |

| Range method | actual inside | note |
|---|---|---|
| middle half of recent cycles (25th–75th percentile), with the median pace | ~59 % (16/27, first backtest) | v1, replaced |
| theoretical: renewal-process sd (independent cycles), ±1.28 sd for 80 % | 38 % | too narrow: the pace drifts |
| **empirical ×0.75–×1.25** | **79 %** | **v2, current** |

#### Alternatives (for a future change)

*Estimators*
- **Median of recent cycles** (v1) — ✗ systematically ~20/h too high. Cycle times are skewed:
  long videos are rare but take a large share of the hour, and the hourly count follows the
  **mean** cycle. Don't use a median (or other "robust" centre) to project counts.
- **Mean of the last N cycles** — simple, adapts; N = 40–60 performed like the current one,
  N = 20 a bit worse (noisier).
- **Mean of the whole run** — as accurate here (the runs' pace was steady) but never adapts:
  after switching `--2x` or play mode mid-run it would stay wrong for a long time.
- **Weighted mean** (v2) — accuracy of the best, adapts; `PACE_HALF_LIFE` is the knob (smaller =
  faster reaction, noisier). Only 30 was tested.
- *Untested ideas:* mean over the last 30/60 **minutes** instead of N videos (adapts in clock
  time); separate pace per playback speed (1x and 2x differ a lot; would make a mid-run switch
  correct instantly); excluding cycles that ended at max-watch (they're "real" time though).

*Ranges*
- **Percentiles of cycle times** (v1) — describes how long single videos are, not how many fit
  in an hour; too narrow/misplaced.
- **Theoretical (renewal process)** — elegant but assumes independent cycle times; real runs
  drift (feed content comes in streaks, waits vary) → 38 % coverage instead of 80 %.
- **Empirical calibration** (v2) — honest by construction on the data it was fitted to; refit
  `PACE_RANGE` from the backtest's actual/estimate ratios (10th–90th percentile) when more runs
  exist. *Untested:* a range that widens with the run's own observed drift.

*Presentation* (offered when the feature was designed; "recent pace + range" was picked)
- **Recent pace + range** — current: one number with a likely range, plus the whole-run average.
- **Projection over time** — the same pace turned into totals: "next hour ≈ N · by 06:00 ≈ M
  total · in 24 h ≈ K". Adds nothing statistically (same pace × time) but answers "how many by
  …?" directly; its error grows with the horizon.
- **Whole-run estimate + range** — steadier, slow to reflect changes (see whole-run mean).

#### Replacing the strategy

1. Add the candidate to `ESTIMATORS` in `tools/backtest_pace.py` and run it on all logs in
   `runs/`; compare with the baseline tables above (mean abs error and bias first).
2. If it wins, change `Player.pace()` (and the `PACE_*` constants); refit `PACE_RANGE` if the
   estimator changed (ratios actual/estimate, 10th–90th percentile).
3. The script's `weighted` function mirrors the app — keep them in sync or have the script
   call the app's method.
4. Update this section: the current version, the tables, and the reason for the change.

---

### 4.12 Languages

The tool reads Instagram's own texts (content-descs, labels, hints) to find video posts, tell
followed from suggested accounts, read the like state, counts, the 2x hints, the share sheet and
the snackbars. Instagram translates them with the **app language** (Instagram → Settings →
Language), which can differ from the phone's system language. Supported: **English** (the
original, UK; US English too) and **Brazilian Portuguese** (pt-BR, added 2026-10-21). Resource IDs
(`row_feed_profile_header`, `clips_author_username`, `inline_follow_button`, …) don't change
with the language — only texts do.

**Design: one table, English untouched.** All texts live in `UI_TEXT` (and the count regexes in
`COUNTS`) at the top of `feed_autoplay.py`. Each entry lists English first, exactly as before,
then the other languages; every check accepts *any* entry (`has_any()`, or a regex alternation
built from the table). So adding a language only widens a check — it can't change what an
English screen matches, unless the new text happens to appear on an English screen (keep
translations specific, e.g. "postou um video", not "video"). There is no language setting and
no detection: a run can't break because a language was guessed wrong.

| Key | English | pt-BR | Where |
|---|---|---|---|
| `home_tab` | Home | Página inicial | Home tab content-desc (`HOME_TAB` regex) |
| `video_post` | posted a video | postou um video / vídeo | feed post header |
| `sponsored` | Sponsored | Patrocinado *(assumed, no ad seen)* | ad header |
| `suggested` | Suggested for you | Sugestões para você | header `secondary_label` |
| `speed_locked` / `speed_unlocked` | …normal speed / …lock 2X speed (US: …lock 2x speed) | …voltar à velocidade normal / …ativar a velocidade 2x | 2x hint while holding (4.4) |
| `followed_by` | Followed by | Seguido(a) por | player: suggested account (4.6) |
| `like_unliked` | Like | Curtir | like label (stays the same when liked; `selected` flips) |
| `copy_link` / `copied` | Copy link / Copied | Copiar link / Copiado | share sheet (4.7d) |
| `reposted` | Reposted | Repostado | snackbar after Repost (4.7b) |
| `REFUSED` | unable, couldn't, can't, try again | não foi possível, tente novamente | repost refusal |
| `COUNTS` | The like number is 1,204 (US: Like number is 1,204) · Reposted 6592 times · Save number is 39 | O número de curtidas é 2.118 · Repostado 49 vezes · O número de salvamentos é 19.103 | exact counts (safety nets) |

Other language-dependent spots in the code:
- **Post time** (`post_id`, dedupe): English "… 5 hours ago" / "… in Lisbon on 1 day ago";
  pt-BR "… em Há 7 horas" (also "há"), "… em Lisboa em Há 2 dias", and older posts with a date
  ("… em 10 de outubro", handled like English dates: no tolerance) — `AGO_PT` / `PT_UNIT`.
- **Collab authors** in the player: "a and 2 others" / "a and b" vs "a e mais 2" / "a e b".
- **Numbers:** pt-BR uses "." for thousands and "," for decimals; abbreviated values
  ("18.5K", "1,2 mil") aren't exact, so the count safety nets skip them (as before).
- Labels that are the same in both: the Repost button ("Repost"), "Liked" in the English feed.

Texts also differ *within* a language: the tool was written with Instagram in **UK English**;
**US English** (Instagram's default English) says "Slide down to lock 2x speed" (lowercase x,
UK "2X") and "Like number is …" (UK "The like number is …"), and writes dates "October 7"
(UK "7 October"; both are treated as absolute dates). The first US run played every video at
1x ("could not switch to 2x") until the US spelling was added. Everything else checked is the
same (Like, Repost, "Reposted N times", "Save number is N", Share, Home, Follow). When a check
suddenly fails on every video, open the screen and dump it before suspecting the logic.

Findings on the pt-BR screens: Save shows a snackbar ("Salvo" + "Adicionar à coleção"), not a
sheet, as in English; reposts were still refused ("Não foi possível repostar"), caught by text
and icon; a new player element `scrubber` ("Barra de pesquisa") appeared (see 6). Not seen in
pt-BR yet, so taken from the obvious translation or left English-only: ads ("Patrocinado"), a
collab author line, the feed's liked label.

**How it was tested.**
1. *English unchanged* — a differential test ran the code from before the change and the new
   code side by side on the English inputs of every changed function (headers, ads,
   suggestions, post times, counts, collab/followed checks, like labels, hints, refusal and
   Home texts): 89 checks, 0 differences.
2. *pt-BR offline* — the same functions on real pt-BR screen dumps (feed, player, share sheet,
   save): 62/62.
3. *pt-BR live* — 12 min `--play followed --2x --like followed --share-link followed`: 11 played,
   10 liked, 10 links copied, 7 suggested skipped, ends from the log 5 / from frames 5, 0
   errors; headers with dates and locations were handled.
4. **`tests/test_ui_text.py`** keeps 1 and 2 as a permanent check without the private dumps
   (made-up accounts, texts as recorded): `uv run tests/test_ui_text.py`. Run it after any
   change to the texts; it fails if an English expectation changes (checked: removing
   "posted a video" makes 8 checks fail).

**Adding a language:** switch Instagram's language; dump the feed, the player (with the 2x hint
showing), the share sheet and the snackbars (5, "Diagnostics"); append each text to its
`UI_TEXT` entry (after the existing ones), add `COUNTS` patterns with that language's
thousands separator, extend `post_id` if the time label has another shape, add cases to
`tests/test_ui_text.py`, run it, then a short live run with `--like none` first.

## 5. How things were tested (and how to re-test)

**Without a phone.** `uv run tests/test_ui_text.py` checks all language-dependent text
matching, English and pt-BR (4.12).

**Live runs.** Run the script for a few minutes with `timeout -s INT 300 … < /dev/null > log`
and read the log. To test keys without a person at the keyboard, feed them through a
pseudo-terminal: `(sleep 15; printf h; sleep 15; printf w; …; printf q) | timeout 220 script -qfc "uv run feed_autoplay.py" /dev/null`. Useful derived numbers:
- *end detection correct?* with the log's duration D at 2x, one pass takes D/2 seconds; the
  first end should come at `D/2 − head_start/2`.
- *head start into the video* = `(D/2 − time_to_first_end) × 2`.
- Use `--like none` while testing to avoid liking things on the account.

**Recording ground truth.** `tools/record_traces.py` opens videos, locks 2x (or not), records
small screenshots plus the times of the log's end lines:

```bash
uv run tools/record_traces.py tools/traces 10 75 --first 13      # 2x: 10 more, from r13
uv run tools/record_traces.py tools/traces_1x 10 150 --speed 1 --first 10   # 1x
```

(~1.5 min per video at 2x, ~2.7 min at 1x, where ~2 passes are needed; the phone is busy
meanwhile.) At 1x most videos log no end line at all — they get ground truth from the period
estimate below.

**Period estimate (`tools/period.py`).** A looping video repeats exactly, so the frame at t
matches the frame at t + T all along the trace: the median frame difference over all pairs at
lag T is minimal at the period. Two refinements were needed: (1) a video also repeats at 2T,
3T…, so the shortest divisor of the best lag that repeats nearly as well wins (without it, 5
of 25 estimates were multiples); (2) only clear repetitions count — "contrast" (score at T ÷
median score over all lags) ≤ 0.45. Validated against the log on 25 traces: 24 agree within
1 s; the one disagreement had contrast 0.96 and is excluded by the rule.

**Scoring detector settings offline.** `uv run tools/tune_fallback.py tools/traces`
(or `tools/traces_1x`; ~10–30 min, CPU only) replays the traces through a grid of detector settings and ranks them. The
detector can only match once playback returns to the point where the references were taken,
at ≈ ref_start + T, so offsets are reported relative to that:
- **miss**: no fire, or later than ref_start + T + 6 s (the video replays);
- **early** (cuts the video short): before the true end when the log gives it (reconstructed
  from duration + one logged end); for period-estimate-only traces, conservatively before
  ref_start + T − 1 s. Firing between the true end and ref_start + T is fine — the restarting
  video can look like the references (seen as −5/−3 s offsets at 2x).

*Lesson:* the first version scored "early" against ref_start + T for every trace and wrongly
flagged two good 2x detections; use the true end whenever it's known.
Keep `detect()` and `CURRENT` in sync with `Player.watch()` and `DETECTOR`.

`tools/traces/`: 13 2x traces (r0–r12, 48 MB, all with logged ends). `tools/traces_1x/`: 22 1x
traces (r0–r21, 160 MB); 12 have logged ends, 8 more get a period estimate, r14 and r16 have
no clear repetition and are excluded → 20 usable.

**The recorded data is not in the repository** (`.gitignore`; decided 2026-10-21). The traces
are 13,449 small grayscale screenshots of 35 videos of the owner's feed, and the icon samples
are button crops with the video behind them: third-party content that also reveals what the
feed contains, ~210 MB. Consequences:
- The baseline numbers in this document (13/13 at 2x, 19/20 at 1x, 4.11's backtest) were
  measured on that private data; they can be re-checked only by whoever holds a copy.
- Anyone else: record your own with `tools/record_traces.py` (~1.5 min per video at 2x, ~2.7 at
  1x; ≥ 20 videos per speed recommended, see 4.5) and re-score the current settings on them
  before tuning — a different phone, screen or Instagram version may need different settings.
- The app itself needs none of it — only `assets/icon_masks.npz` (shapes, no content).
- Keep a private copy (private repository, drive) if the data matters to you: ignoring it in
  git doesn't back it up.

**Icon masks** (`assets/icon_masks.npz`) were built from crops of the like/repost buttons on 16
videos (read-only): pixels white in ≥ 90 % of them = the icon's shape (backgrounds vary, the
icon doesn't). The liked/reposted variants came from liking and reposting one followed video.
The crops are kept locally in `tools/icon_samples/` (`like_*`/`repost_*` = unliked/plain, plus
`liked_sample`, `reposted_sample`, `plain_sample`; git-ignored, see above) to re-check or
rebuild the masks; on another phone, collect new ones the same way.

**Diagnostics used during development** (patterns worth reusing):
- dump the hierarchy and grep resource IDs / content-descs to discover elements;
- for "why did X fail", save `dump_hierarchy()` + a screenshot at the failure point;
- compare two independent signals (feed vs player follow verdicts; log vs frames) to find
  which one is wrong.

### 5.1 Long-run test (2026-10-18)

Unattended run, `--play all --2x --like all`, Wi-Fi debugging, phone charging,
log in `runs/longrun-2026-10-18.log`. 04:55 → 15:45 (10.7 h, one restart at 05:05 to load a fix).

| | |
|---|---|
| played / liked | 304 / 302 (the 2 not liked were interrupted on purpose: restart, agent-kill test) |
| failed likes, skips, in-feed fallback | 0 / 0 / 0 |
| how videos ended | Instagram log 231, frame comparison 67, static 1, max-watch 3 |
| errors recovered | 17 (1 deliberate agent kill, 16 during a connection drop) |
| time actually playing | ~5 h of 10.7 h (see issue 1) |

Recovery paths exercised for real: uiautomator2 agent death, logcat death, Wi-Fi adb drop with
automatic reconnect, waiting at the lock screen.

**Issues found**

1. **Connection drop → phone locked → 5 h idle** (environment, not a script bug).
   08:25 the Wi-Fi debugging connection dropped ("device … not found") for 24 min; the script
   retried with growing pauses and reconnected by itself at 08:49. But with nothing playing
   in the meantime the screen timed out and the phone (pattern lock) locked; the script then
   waited at the lock screen, as designed, until it was unlocked at 14:03 (5 h 14 min).
   The script cannot prevent this — it can't reach the phone while disconnected.
   *Mitigation (phone side):* Developer options → **Stay awake** (screen stays on while
   charging), and prefer **USB** over Wi-Fi debugging for long runs.
2. **3 videos hit the 300 s max-watch** (06:09 techreview.hub, 07:16 garden_tales,
   07:27 weekly.podcast). None produced a log line, so it's unknown whether they were really
   longer than 10 min (300 s at 2x) — plausible for a podcast clip — or loops that both end
   signals missed (bad behaviour: up to 5 min of replays). → Resolved in 5.2/4.5 v6: in the
   next run the dumps showed real missed loops, caused by a detector bug. Diagnostic added:
   on max-watch the script now saves the frames it compared to `runs/maxwatch-*.npz` and
   prints the command to analyse them; `tools/period.py <file>` reports "LOOPED every X s"
   (→ a detection miss, worth a trace + tuning) or "no clear repetition" (→ a long video).
   Verified offline on a looping trace (29.2 s found) and a non-repeating one.
3. **22 % of ends came from frame comparison at 2x** (67/298). Expected, not a bug: the log
   misses passes (4.5). Each such end costs the fallback's built-in delay (a few seconds of
   replay). Only worth revisiting if a stronger end signal is found.

### 5.2 Run of 2026-10-18 evening (like fix)

`--play all --2x --like all --repost followed`, `runs/run-2026-10-18-likefix.log`, after the icon
fixes of 4.7. First 4.7 h: 330 played, 326 liked, 107 reposted, 220 not reposted (not
followed), 0 errors, 0 lock waits. Ends: log 253, frames 73, max-watch 3. Findings (all fixed
in the same session, the run was then restarted with the fixes):
- 1 "already liked" + "already reposted": the same post replayed (label 23 → 25 min) → dedupe
  fix (4.2). The icon checks were right: the run itself had liked/reposted it 30 s earlier.
- 2 "like did not register" → like confirmation with polling + second tap (4.7).
- 1 repost "unclear" → skipped as designed.
- 3 max-watch: `tools/period.py` said 2 LOOPED (missed loops) + 1 long video → detector bug
  (4.5 v6).

**After the fixes** (same settings, `runs/run-2026-10-18-fixes2.log`, 23:01 → 01:15, 2.2 h):
160 played, **160 liked** (0 second taps, 0 "already liked", 0 not registered), 51 reposted,
109 not reposted (not followed), 0 unclear, 0 errors. Ends: log 122, frames 37, max-watch 1 —
`tools/period.py`: no repetition (a long video, cap working as intended).

### 5.3 Run of 2026-10-19 01:25 (`--repost all`)

`--play all --2x --like all --repost all`, `runs/run-2026-10-19-0125.log`, 01:25 → 03:07
(1.7 h): 97 played, 96 liked, **96 "reposted"** (all of them — counted by the optimistic
"Reposted" snackbar), 0 errors; ends: log 65, frames 30, max-watch 1 (`tools/period.py`: no
repetition → a long video). Afterwards the account owner saw Instagram's **"Unable to
repost"** message, and every repost tap was refused → repost refusal detection and back-off
(4.7b). ~1 repost per minute is evidently too many for Instagram; prefer `--repost followed`
(about a third as many) for long runs.

## 6. Known limitations and ideas

- Native Windows (uv, `run.bat`): tested on Windows 11 over Wi-Fi (keys, `stop.bat`); USB with
  the vendor driver and `pause.bat` (added later) are not tried yet.

- Container runs (CONTAINER.md): Wi-Fi debugging only; if the phone restarts mid-run its
  wireless-debugging port changes and the app can't reconnect on its own (new `PHONE` needed);
  untested on Windows/Podman.

- Long runs over Wi-Fi: a connection drop lets the phone lock (5.1, issue 1). Use Stay awake
  and/or USB.
- After runs, check `runs/maxwatch-*.npz` with `tools/period.py`: "LOOPED" ones are detector
  misses worth adding to the tuning set (they are already cropped; see 4.5 v6).
- High-motion videos can still be caught a pass or two late by the frame fallback (4.5 v6).
- One 1x trace is missed by every detector setting tried; a fundamentally different signal
  would be needed for such videos (max-watch caps them).
- Videos open ~10–12 s in (feed autoplay). Ideas: shave time between the post appearing and
  the tap; find a reliable restart gesture (the next/back swipe was not reliable).
- Frame fallback is ~5–6 s late by construction (see 4.5).
- In-feed videos: rarely happen, path barely tested (see 4.3); they can't be reposted (4.7b),
  link-copied (4.7d) or saved (4.7c).
- Carousel videos are skipped; ad ("Sponsored") detection unverified.
- Collab posts count as followed (see 4.6).
- Instagram rate-limits reposts (4.7b); `--repost all` on a long run hits it. Likes may have a
  limit too — no refusal message for likes has been seen so far.
- All IDs/texts were found on Instagram 450/451 in English (UK and US) and Brazilian Portuguese (4.12); an
  update or another app language can break them — add the texts to `UI_TEXT`. pt-BR ads, collab
  lines and the feed's liked label weren't seen yet.
- Idea: the player's `scrubber` element (pt-BR "Barra de pesquisa", seen on 451) may expose the
  playback position — a possible end-of-video signal better than frame comparison (4.5).
- `--loops > 1` has not been exercised much.

## 7. Pitfalls checklist

- **Before any test on the phone, check nothing else is using it** — e.g. the owner running the
  app themselves. Two automations on one phone fight (taps land on the wrong screen; results are
  worthless). *It happened:* container tests ran while the owner's instance was running; the
  owner stopped theirs. Check `ps`/`docker ps` here **and ask** when the owner may be running it.
- **Docs and examples use made-up data**: no real phone serials, IP addresses, home paths,
  Instagram accounts from the feed or the owner's time zone (they were replaced on 2026-10-20,
  e.g. serial `R58N91XKQZT`, `192.168.1.23:41235`, `chef.marco`). Copy log excerpts into docs
  only after replacing real names. Run data (`runs/`, `.env`) is git-ignored.
- **The stop and pause files are shared:** every running instance in the folder watches
  `runs/STOP` and `runs/PAUSE`. Tests
  must not create the real one while a real run may be active — point the test at another path
  (`feed_autoplay.STOP_FILE = Path(...)`). (A test once created it while the owner's instance was
  running; that instance happened to predate the stop file.)
- `pkill -f <pattern>` also matches the shell whose command line contains the pattern — use the
  bracket trick (`[l]ogcat …`); this killed a test command twice.

- Never keep positional uiautomator2 selectors across scrolls; re-find by content-desc.
- Scope selectors with `packageName=PKG` (system UI reuses labels like "Home").
- Don't touch the right action column or the caption in the player; don't double-tap.
- Tap videos high on the screen, not on their bottom strip.
- Re-check the 2x hint before sliding — sliding when already locked turns 2x off.
- Always lift a raw `touch.down` in `finally`.
- Use PC arrival time for log events; filter by "after playback started".
- Test with `--like none` (and the defaults `--repost none`, `--share-link none`, `--save none`);
  verify on the phone, not just in the log.
- Repost is a toggle with no state in the UI tree: check the icon (`repost_state`) before every tap.
- Save can act as a toggle too (4.7c): check `selected` before tapping; test saves must be
  undone only after confirming they are ours and still on.
- The share sheet holds chat recipients and "Add to story": tap only the exact "Copy link"
  element, and press Back only while the sheet is showing (4.7d).
- Icon checks must test the icon's **shape** (its own pixels), never colour amounts over the
  whole button: the video behind it can be any colour (4.7 bugs).
- When changing the frame detector, re-run `tools/tune_fallback.py` on **both** trace sets
  and compare against 13/13, 0 early (2x) and 19/20, 0 early (1x); and check the app's
  `watch()` still fires where `detect()` does (4.5 v6).
- Never turn the screen off / lock a phone with a secure lock during tests (see 4.8).
- New mode-style settings: keep the order none → followed → all, add the list next to the
  others and use it for `choices=` and `MODE_KEYS`, so `--help`, keys and help can't drift.

## 8. Commit messages (Conventional Commits)

Commits follow [Conventional Commits 1.0](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <summary>

<body: what changed and why — the reasoning a reader of `git log` needs>

<footers: BREAKING CHANGE: …, Refs: …>
```

**Types**

| Type | For | Example |
|---|---|---|
| `feat` | a new capability for users | `feat(feed_autoplay): add copy-link action` |
| `fix` | a bug fix | `fix(feed_autoplay): count reposts only after Instagram confirms them` |
| `perf` | faster / lighter, same behaviour | `perf(feed_autoplay): one hierarchy dump per feed scan` |
| `refactor` | code change without behaviour change | `refactor(feed_autoplay): one table for the mode keys` |
| `docs` | documentation only | `docs: add Windows container guide` |
| `test` | tests, backtests, test data handling | `test(tools): backtest the pace estimate on run logs` |
| `build` | Dockerfile, compose, dependencies | `build(container): pin uiautomator2 3.7.0` |
| `ci` | CI configuration | `ci: build the image on pull requests` |
| `chore` | maintenance (`.gitignore`, renames, cleanup) | `chore: keep recorded feed data out of the repository` |
| `revert` | reverting a commit | `revert: feat(feed_autoplay): …` |

**Scopes** follow the project layout (3): a tool's name — `feed_autoplay` (later e.g.
`story_viewer`) —, `android_instagram` for the shared package once it exists, `container`
(Dockerfile, compose, entrypoint), `tools` (dev tools under `tools/`). Leave the scope out for
project-wide changes (`docs: …`, `chore: …`).

**Rules**
- Summary in the imperative, lower case, no final period, ≤ 72 characters ("add", not
  "added"/"adds").
- One logical change per commit; a feature and its docs may go together, unrelated fixes don't.
- The body says **why** and records measurements when a change was tuned or tested (e.g. "13/13
  at 2x, 0 early"), the way this document does.
- **Breaking changes** — anything that breaks existing command lines, `.env`/compose setups or
  saved files (renamed or removed options, changed defaults that change behaviour, new required
  settings): `!` after the type/scope **and** a `BREAKING CHANGE:` footer saying what to do.
  Example: `feat(feed_autoplay)!: rename --no-like to --like none|followed|all`.
- **No `Co-authored-by:` footer** — not even for changes made with an AI assistant (the
  owner's choice for this repository). Assistants that add one by default must leave it out.

**Before every commit — privacy** (see 7 and the Privacy section of `README.md`)
- `git status` / `git diff --cached --stat`: no `runs/`, `.env`, `tools/traces*/`,
  `tools/icon_samples/`, adb keys or `.test-*` files.
- No real data in the staged text: phone serials, IP addresses, home paths, real Instagram
  accounts or captions from the feed, personal time zones — use the made-up examples.
- **Commit identity:** `git config user.name` / `user.email` are public on every commit. This
  repository uses a repo-local GitHub noreply identity (`git config --local user.email
  <id>+<user>@users.noreply.github.com`), so a global work identity isn't published.
