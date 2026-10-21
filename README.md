# android-instagram-tools

Tools that drive the **Instagram app on an Android phone** from a computer, over adb (with
[uiautomator2](https://github.com/openatx/uiautomator2)): they read the screen and tap and swipe
like a person would — no Instagram API, no browser.

| Tool | What it does | Status |
|---|---|---|
| **[feed_autoplay](#feed_autoplay)** | plays the videos of your home timeline one after another, optionally at 2x, liking / reposting / copying links / saving them | the only tool so far |

> ⚠ Instagram's terms don't allow automated use. Acting at volume can get the account limited
> (Instagram already refused reposts after ~100 in under 2 hours). Use the tools at your own
> risk, with sensible settings.

---

## Setup (once, for all tools)

### What you need

- An **Android phone** with the Instagram app, logged in.
- A **computer** on Linux, Windows or macOS.
- The phone connected to the computer by **USB** or **Wi-Fi debugging** (Android 11+).

| Computer | How to run the tools | Status |
|---|---|---|
| **Linux** | natively (Python) — or in a container (Docker/Podman) | both tested |
| **Windows** | in a **container** (Docker Desktop or Podman Desktop), phone over Wi-Fi | built & tested on Linux; not yet tried on Windows itself |
| **macOS** | natively (Python) — or in a container | expected to work, not tested |

Running natively on **Windows** is not supported (the tools' keyboard controls use
Linux/macOS-only Python modules) — use the container.

### 1. Prepare the phone

1. Settings → About phone → tap **Build number** 7 times (enables Developer options).
2. Developer options:
   - **USB debugging** on (for USB), and/or **Wireless debugging** on (for Wi-Fi; phone and
     computer on the same network);
   - **Stay awake** on (screen stays on while charging) — recommended for long runs.
3. Keep the phone **unlocked** with Instagram available. If it locks, the tools wait until you
   unlock it (they never try to unlock it themselves).
4. On first connection over USB, accept the "Allow USB debugging?" prompt on the phone.

### 2a. Install natively (Linux / macOS)

Needs Python 3.10+.

```bash
git clone <repository URL> android-instagram-tools
cd android-instagram-tools
python3 -m venv .venv
.venv/bin/pip install uiautomator2 numpy
```

No separate adb install is needed on Linux: one comes with the Python packages, in
`.venv/lib/python3*/site-packages/adbutils/binaries/adb` (called `adb` below). On macOS, if that
folder has no `adb`, install it with `brew install android-platform-tools`.

**Connect the phone:**
- **USB:** plug it in — nothing else to do.
- **Wi-Fi:** pair once with `adb pair <ip:port> <code>` (on the phone: Wireless debugging →
  "Pair device with pairing code"), then `adb connect <ip:port>` with the IP & port shown on the
  Wireless debugging screen. Check with `adb devices`.

### 2b. Install in a container (Windows, or any system)

Needs **Docker Desktop** or **Podman Desktop** only — no Python. The phone is reached over
**Wi-Fi debugging**. In a terminal in the project folder:

```powershell
copy .env.example .env      # Linux/macOS: cp .env.example .env
                            # then edit .env: PHONE=<IP:port from Wireless debugging>, TZ=<time zone>
docker compose build        # again after updating the code
docker compose run --rm app pair <pairing IP:port> <code>    # once: the phone trusts the container
```

With Podman, use `podman compose` instead of `docker compose`. Details — background runs, port
changes, mirroring alongside, troubleshooting: **[CONTAINER.md](CONTAINER.md)**.

### Mirroring the phone (optional)

[scrcpy](https://github.com/Genymobile/scrcpy) shows the phone on the computer: Linux
`apt install scrcpy` or `snap install scrcpy`, macOS `brew install scrcpy`, Windows: the zip from
its releases page. The tools don't need it.

---

## feed_autoplay

Plays the videos of your **Instagram home timeline**, one after another, without you touching the
phone — so a mirrored phone (e.g. scrcpy on a second screen) is always playing something.
Optionally at **2x**, and it can **like**, **repost**, **copy the link of** and/or **save** each
video it watched to the end.

### Run it

| | Natively (2a) | In the container (2b) |
|---|---|---|
| **with keys** | `.venv/bin/python feed_autoplay.py --play all --2x` | `docker compose run --rm app --play all --2x` |
| **in the background** | `mkdir -p runs`<br>`nohup .venv/bin/python -u feed_autoplay.py --play all --2x < /dev/null >> runs/run.log 2>&1 &` | `docker compose up -d` (settings: `command:` in `compose.yaml`) |
| **follow the output** | `tail -f runs/run.log` | `docker compose logs -f` |
| **stop** | `q` — or `kill <pid>` in the background | `q` — or `docker compose stop` |
| **all options** | `.venv/bin/python feed_autoplay.py --help` | `docker compose run --rm app --help` |

Stopping always prints the final statistics. Keys work only in the "with keys" rows (a
terminal is needed).

### Options

| Option | Values (default in bold) | What it does |
|---|---|---|
| `--play` | **followed** · all | play only videos from accounts you follow, or every video |
| `--2x` | (off) | play each video at 2x speed |
| `--like` | none · **followed** · all | like the videos watched to the end |
| `--repost` | **none** · followed · all | repost them (shown on your profile) |
| `--share-link` | **none** · followed · all | Share → Copy link; links collected in `runs/shared-links.txt` |
| `--save` | **none** · followed · all | save them to your private Saved collection |
| `--max-watch S` | **300** | stop watching a video after S seconds |

"followed" = only for accounts you follow. Actions happen only for videos watched to the end, in
the order of the buttons on screen (like → repost → share → save), and never twice: a post
already liked/reposted/saved is left alone. Example:
`feed_autoplay.py --play all --2x --like all --repost followed`

### Keys

| Key | | Key | |
|---|---|---|---|
| **n** | next video | **r** | repost mode |
| **p** | pause / resume | **c** | copy-link mode |
| **w** | play mode | **b** | save mode |
| **l** | like mode | **s** | statistics |
| **h** / **?** | help | **q** | quit |

### What it shows

At start: the phone, the Instagram version and the settings. While running: one line per video
and action (`▶` opened, `⏩` 2x, `♥` liked, `🔁` reposted, `🔗` link, `🔖` saved). Every 20
videos (and on **s** / when stopping) a statistics block, including the **pace** — how many
videos an hour to expect.

Files go to `runs/`: copied links (`shared-links.txt`) and diagnostics of videos that hit the
time limit (`maxwatch-*.npz`).

### Good to know

- **Instagram limits reposts.** After many reposts it answers "Unable to repost"; the tool
  notices, doesn't count it, and pauses reposting (30 min, longer if it repeats).
  `--repost followed` is much gentler than `all`.
- **Tested on** a Samsung Galaxy phone (Android 11, 1080×2340 screen) with Instagram 451, in
  English. Another phone, screen size, Instagram version or language may need adjustments — it
  warns at startup when the Instagram version is one it wasn't tested with.
- **Wi-Fi debugging:** the phone's port changes when wireless debugging is switched on again or
  the phone restarts; reconnect with the new one (container: update `PHONE` in `.env`). USB is
  the more stable choice for long runs (native only).
- The beginning of each video (~10 s) is usually missed: Instagram starts it in the feed before
  the tool opens it.

---

## Privacy

The `runs/` folder (run logs with the accounts that were played, your copied links,
diagnostics) and `.env` (your phone's address) are personal — `.gitignore` keeps them out of the
repository. So is the **tuning data** (`tools/traces*/`, `tools/icon_samples/`): screenshots of
a real feed, used only to tune the tools and kept off the repository — record your own with
`tools/record_traces.py` if you need them (DEVELOPMENT.md 5).

## More

- **[CONTAINER.md](CONTAINER.md)** — running in Docker/Podman, step by step.
- **[DEVELOPMENT.md](DEVELOPMENT.md)** — how the tools work, the decisions behind them, what was
  tested, naming and project layout, and how to change things.
