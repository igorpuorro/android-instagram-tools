# feed_autoplay and profile_blocker in a container (Docker or Podman) -- see CONTAINER.md.
# The phone is reached over Wi-Fi debugging (adb connect ip:port); no USB passthrough.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    FEED_AUTOPLAY_CONTAINER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# tzdata: so TZ=... gives log times in the PC's local time (the container default is UTC)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

# the versions the app was tested with (DEVELOPMENT.md 2) -- keep in sync with pyproject.toml
RUN pip install uiautomator2==3.7.0 adbutils==2.12.0 numpy==2.2.6 pillow==12.3.0

# One adb for everything: the app uses the adb bundled with adbutils (EndWatcher), so the
# helper commands (pair, adb, and the automatic connect) use the very same binary -- two adb versions would keep
# restarting each other's server.
RUN ln -s "$(python -c 'import adbutils; print(adbutils.adb_path())')" /usr/local/bin/adb

WORKDIR /app
COPY feed_autoplay.py profile_blocker.py ./
COPY assets/ ./assets/
COPY tools/*.py ./tools/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && mkdir -p /app/runs

ENTRYPOINT ["entrypoint.sh"]
