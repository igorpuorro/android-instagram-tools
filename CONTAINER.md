# Running android-instagram-tools in a container — the detailed guide

The short version (setup, phone preparation, the essential commands) is in
**[README.md](README.md)**. This guide covers the container-specific details: pairing, background
runs, port changes, mirroring alongside, Podman and troubleshooting.

A container holds Python, the packages, adb and the tools, so the computer only needs **Docker
Desktop** or **Podman Desktop** (both set up WSL2 on Windows by themselves; Podman is free for any
use, Docker Desktop needs a paid plan in larger companies). The phone is reached over **Wi-Fi
debugging** — a container can't use the phone's USB connection on Windows.

> **Status.** Built and tested on Linux (Docker 28): Wi-Fi connection, startup, 2x,
> end-of-video detection, local time zone, keys on/off, stop with final statistics, and
> coexisting with the computer's own adb connection. Side by side with running directly on the
> computer it performed the same (~55 videos/h, end detection on par).
> **Not tried yet:** Windows itself, Podman, the one-time `pair`, and likes / reposts / copied
> links / saves from inside the container (same code as outside, which is tested).

**Which tool runs:** the compose service `app` runs **feed_autoplay** — currently the only tool;
its options go after `app` (`docker compose run --rm app --play all --2x`). The image is called
`feed-autoplay` (section 6).

## 1. Configure and pair (once)

`.env` holds the phone's address and your time zone (copy `.env.example`):

```
PHONE=192.168.1.23:41235     # Wireless debugging → "IP address & Port"
TZ=Europe/Berlin             # so log times match your clock (the container default is UTC)
```

The phone has to trust the container's adb key once. On the phone: Wireless debugging →
**Pair device with pairing code** — it shows a *different* IP:port and a 6-digit code:

```powershell
docker compose run --rm app pair <pairing IP:port> <code>
```

The key is kept in the `adb-keys` volume: pairing is needed again only if you delete the volume
(`docker compose down -v`) or the phone forgets the computer.

## 2. Running in the background

```powershell
docker compose up -d          # starts with the settings under "command:" in compose.yaml
docker compose logs -f        # follow the output (Ctrl-C stops following, not the app)
docker compose stop           # stop: the app prints its final statistics first
docker compose logs --no-log-prefix app > runs\run-<date>.log    # keep the output as a file
```

- **Settings for background runs:** edit `command:` in `compose.yaml`, e.g.
  `["--play", "all", "--2x", "--like", "all", "--repost", "followed"]`.
- **Keys** don't work in background runs (no terminal). For keys, use
  `docker compose run --rm app <options>` instead.
- **Output** stays in Docker's log until the container is removed — save it as above. The
  `runs\` folder next to `compose.yaml` gets `shared-links.txt` (copied links) and
  `maxwatch-*.npz` (diagnostics).

**Helpers:**
- `docker compose run --rm app adb devices` — what adb sees.
- `docker compose run --rm app tool period.py runs/maxwatch-<time>.npz` — analyse a video that
  hit the time limit (the app prints this command).
- `docker compose run --rm app --help` — all feed_autoplay options (works without the phone).

## 3. When the phone's port changes

The port under Wireless debugging changes whenever wireless debugging is switched on again or
the phone restarts. The container then says *"could not connect to the phone at …"*: put the new
IP:port in `.env` (`PHONE=`) and start again — no new pairing needed.

If it happens **during** a background run (phone restarted), the app keeps retrying the old
address: stop it, fix `.env`, start again.

## 4. Mirroring with scrcpy at the same time

The container and scrcpy (running on the computer) can be connected to the phone at the same
time — tested with the computer's own adb connected while the container ran. scrcpy brings its
own adb; that's fine, the container's adb is separate. Start scrcpy with
`scrcpy --tcpip=<IP:port>`.

## 5. Podman instead of Docker

The same commands with `podman`:

```powershell
podman compose build
podman compose run --rm app pair <pairing IP:port> <code>
podman compose run --rm app --play all --2x
podman compose up -d ; podman compose logs -f ; podman compose stop
```

`podman compose` uses `docker-compose` or `podman-compose` behind the scenes; Podman Desktop
can install it.

## 6. Updating and removing

The image is called **`feed-autoplay`** (set in `compose.yaml`).

- **After changing or pulling the code** (e.g. `git pull`): `docker compose build` — the
  container runs the code copied into the image, not the files in the folder.
- **Remove everything:** `docker compose down -v` (container, network and the `adb-keys`
  volume — pairing needed again afterwards), then `docker image rm feed-autoplay`.

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `could not connect to the phone at …` | wrong or old IP:port in `.env` (3), phone not on the same Wi-Fi, or wireless debugging off |
| `unauthorized` in `adb devices` | pair again (1) |
| changes to the code have no effect | rebuild: `docker compose build` (6) |
| keys do nothing | use `compose run` (not `up`); on Windows, run it in a real terminal window |
| log times are off | set `TZ=` in `.env` (e.g. `Europe/Berlin`, `America/New_York`) |
| `⚠ untested version` at startup | Instagram updated; see DEVELOPMENT.md if likes/reposts/2x misbehave |

How the app works: **[DEVELOPMENT.md](DEVELOPMENT.md)**.
