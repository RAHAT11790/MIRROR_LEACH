# RS Mirror Leech Bot

A native-Python Telegram mirror/leech bot packaged under the **RS Mirror Leech Bot** project name. Docker and `.env` configuration are not used. Configure the bot in `config.py` and start it with `python3 main.py`.

## Features

- Mirror and leech tasks supported by the included bot modules
- URL-based downloads and supported source integrations from the base project
- Telegram bot, optional user session, and helper clients
- MongoDB-backed settings and task metadata
- Configurable admin, authorized chats, and logging destinations
- Native Linux setup; no Docker, Compose, or `.env` file

## Requirements

- Python 3.13 recommended (3.10–3.13 supported; on Windows 3.13 is required because `warpcrypto`, a hard dependency of `wzgram`, has no CPython 3.14 Windows wheel yet)
- MongoDB connection URI
- Telegram Bot Token, Telegram API ID, and API Hash
- Optional: `aria2`, `qBittorrent`, `rclone`, `ffmpeg`, `7z`. Missing tools are detected at startup and the related features are disabled instead of crashing the bot.

## Installation (Windows)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Binaries are resolved automatically by `wz_bin.py`: environment overrides first (`ARIA2C_BIN`, `QBIT_BIN`, `FFMPEG_BIN`, `RCLONE_BIN`, `SABNZBD_BIN`), then a local `bin/` folder, then `PATH`. Put `aria2c.exe` and `qbittorrent-nox.exe` in `bin/` to enable torrent/aria2 downloads.

## Installation (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git build-essential aria2 ffmpeg p7zip-full curl
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install -r requirements.txt
```

## Configuration

Open `config.py` and fill in the values in **RS Mirror Leech Bot: simplified primary settings**. At minimum, set:

```python
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
API_ID = 123456
API_HASH = "YOUR_TELEGRAM_API_HASH"
DATABASE_URL = "YOUR_MONGODB_URI"
ADMIN_ID = 123456789
```

Logging and authorization fields are also available in `config.py`:

- `LOG_CHANNEL`: Telegram channel ID used for task logs
- `LOG_GROUP`: Telegram group ID used for link/task logs
- `AUTHORIZED_CHANNEL`: optional authorized channel ID
- `AUTHORIZED_GROUP`: optional authorized group ID
- `ADMIN_ID`: bot owner/admin Telegram user ID

Use numeric IDs where appropriate. Leave optional values empty if you do not need them. The project retains compatibility settings for its existing modules; all settings are in `config.py`, and there is no `.env` file.

## Start

From the project root, with the virtual environment activated:

```bash
python main.py
```

On Windows:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

`main.py` is the single entry point. It launches the existing bot package; do not run Docker commands.

## Web UI

The web dashboard is served by the bot itself. Set `BASE_URL` (and optionally `PORT`) in `config.py`; the startup log prints the login links with the generated passwords:

```
Web UI: qBittorrent: /qbit/?pass=...
Web UI: SABnzbd: /nzb/?pass=...
```

The dashboard starts even when qBittorrent or aria2 are not installed; the affected panels are disabled instead of blocking startup.

## Notes

- Run from the project root so relative configuration and service paths resolve correctly.
- Some optional integrations need their own API keys or external services. Enable only the integrations you actually use in `config.py`.
- This package is based on an existing open-source mirror/leech codebase. Its original `LICENSE` file is retained; changing project branding does not transfer ownership of third-party code or dependencies.
- Test first with a private Telegram chat and non-sensitive files before running large jobs.

## Running without root / apt

`main.py` runs `bin_bootstrap.py` first. Any missing tool (aria2c, 7z, ffmpeg/ffprobe,
rclone, qbittorrent-nox) is downloaded as a static binary into `./bin` — no root needed.
`taskset` / `cpulimit` get harmless shims when absent. Set `AUTO_INSTALL_BINS=0` to disable.

If aria2c still cannot start, the bot switches to a built-in aiohttp downloader
(`bot/core/http_aria2.py`) that supports http/https direct links (resume, redirects,
multi-connection). Magnet/.torrent links need aria2 or qBittorrent.

## Leech delivery (v5)
- `LEECH_TO_PM=True` (default): files sent by `/leech` in a group go to the user's private chat with the bot
  (the user must press /start once). The group only gets the short completion message with a **View in Bot PM** button;
  the files list / store / stream links go to the PM.
- `FORCE_VIDEO=True` (default): video files are always sent as videos, never as documents.
- `AUTO_THUMBNAIL=True` (default): posters from AniList -> TMDB (if `TMDB_ACCESS_TOKEN`) -> Jikan; no key needed for anime.
- Public Google Drive links work without `token.pickle` (built-in downloader).

## Google Cloud Shell
```bash
bash setup_cloudshell.sh      # once: venv + pip (yt-dlp) + static tools into ./bin
bash run_cloudshell.sh        # start (or: bash run_cloudshell.sh bg  -> keeps running)
```
Cloud Shell keeps only `$HOME` between sessions, so tools are installed inside this folder (`./bin`),
not with apt. `main.py` re-checks them on every start and downloads anything missing.
If 7-Zip is unavailable, zip/tar archives are still extracted by a built-in Python fallback.

## One command start
```bash
python3 main.py
```
Before the bot starts, `rs_setup.py` checks every package in `requirements.txt` (and installs what is
missing), refreshes yt-dlp once a day, and `bin_bootstrap.py` downloads missing tools into `./bin`.
If a package cannot be installed the bot does NOT start (set `RS_ALLOW_MISSING=1` to override).
`main.py` then supervises the bot and restarts it automatically after a crash
(`RS_NO_SUPERVISOR=1` disables this, `RS_SKIP_SETUP=1` skips the checks).

## Thumbnails (AUTO_THUMBNAIL)
Order: **IMDb → AniList → Jikan (MyAnimeList) → Kitsu → TVmaze → TMDb (always last)**; the first source that
returns a poster wins, portrait posters are converted to 16:9 for videos. Set `TMDB_API_KEY` (v3 key) or
`TMDB_ACCESS_TOKEN` to enable the TMDb fallback. Change the order with `THUMBNAIL_PROVIDERS`.
Video screenshots use fast seeking, several positions and a hard kill on timeout.

## Automatic installs on start
`python3 main.py` -> system packages (apt/apk/dnf when root or passwordless sudo; `pkg` on Termux;
static tools in ./bin otherwise) -> every Python package -> yt-dlp refresh -> bot.
