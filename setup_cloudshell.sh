#!/usr/bin/env bash
# One-time setup for Google Cloud Shell.   Run:  bash setup_cloudshell.sh
# Everything is installed inside this folder ($HOME), so it survives Cloud Shell restarts.
# (apt packages do NOT survive a VM restart; the static tools in ./bin do.)
set -u
cd "$(dirname "$0")"

echo "==> [1/4] Python virtual environment"
python3 -m venv .venv || { echo "python3-venv missing -> trying apt"; sudo apt-get install -y python3-venv && python3 -m venv .venv; }
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools

echo "==> [2/4] Python packages (includes yt-dlp, imageio-ffmpeg)"
python -m pip install -r requirements.txt
python -m pip install --upgrade "yt-dlp[default,curl-cffi]" || true

echo "==> [3/4] Optional system packages via apt (skipped if sudo is unavailable)"
if command -v sudo >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y >/dev/null 2>&1 || true
  sudo apt-get install -y aria2 ffmpeg p7zip-full curl >/dev/null 2>&1 \
    && echo "apt packages installed" || echo "apt install skipped/failed (static tools will be used)"
fi

echo "==> [4/4] Static tools into ./bin (aria2c, 7z, ffmpeg, ffprobe, rclone, deno, qbittorrent-nox)"
python bin_bootstrap.py

echo
echo "Setup finished.  Start the bot with:   bash run_cloudshell.sh"
