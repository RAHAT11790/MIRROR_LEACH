"""No-root tool installer.

Hosting panels often give no root and no ``apt``. This module checks which
command-line tools the bot needs and, for every missing one, downloads a
static build into ``./bin`` (a normal user-writable folder). Nothing is
installed system-wide, nothing needs root.

  aria2c, 7z, ffmpeg + ffprobe, rclone, qbittorrent-nox   -> static downloads
  taskset, cpulimit                                       -> tiny shell shims

Every step is independent and failure-safe: if a download fails (no internet,
GitHub blocked, unsupported CPU) the bot still starts and uses its built-in
fallbacks (e.g. the aiohttp downloader instead of aria2).

Set ``AUTO_INSTALL_BINS=0`` to disable. Existing tools are never replaced.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _exec_ok(directory: Path) -> bool:
    """Can programs be executed from *directory*? (false on Android shared storage / noexec mounts)"""
    import subprocess

    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".exec_probe.sh"
        probe.write_text("#!/bin/sh\nexit 0\n")
        probe.chmod(0o755)
        ok = subprocess.run([str(probe)], capture_output=True, timeout=10).returncode == 0
        probe.unlink(missing_ok=True)
        return ok
    except Exception:  # noqa: BLE001
        return False


def _pick_bin_dir() -> Path:
    env = os.getenv("WZ_BIN_DIR")
    candidates = [Path(env)] if env else []
    candidates += [ROOT / "bin", Path.home() / ".rs_bin"]
    for c in candidates:
        if _exec_ok(c):
            return c
    return ROOT / "bin"


BIN_DIR = _pick_bin_dir()
os.environ["WZ_BIN_DIR"] = str(BIN_DIR)  # wz_bin.py (BinConfig) follows this folder
UA = {"User-Agent": "Mozilla/5.0 (RS-Mirror-Leech-Bot bootstrap)"}
TIMEOUT = 60


def _log(msg: str) -> None:
    print(f"[bootstrap] {msg}", flush=True)


def _arch() -> str | None:
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    return None


def _have(name: str) -> bool:
    return (BIN_DIR / name).is_file() or shutil.which(name) is not None


def _working(name: str) -> bool:
    """Tool exists AND can be executed (catches wrong-arch / corrupt binaries)."""
    import subprocess

    exe = str(BIN_DIR / name) if (BIN_DIR / name).is_file() else shutil.which(name)
    if not exe:
        return False
    try:
        subprocess.run([exe, "-version" if name.startswith("ff") else "--version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return True
    except Exception:
        return False


def _http_get(url: str, dest: Path | None = None, retries: int = 3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                if dest is None:
                    return resp.read()
                with open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f, 1024 * 1024)
                return dest
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"download failed: {url} ({last})")


def _github_asset(repo: str, pattern: str) -> str:
    data = json.loads(
        _http_get(f"https://api.github.com/repos/{repo}/releases/latest").decode()
    )
    rx = re.compile(pattern)
    for asset in data.get("assets", []):
        if rx.search(asset["name"]):
            return asset["browser_download_url"]
    raise RuntimeError(f"no asset matching {pattern!r} in {repo}")


def _install_file(src: Path, name: str) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    dst = BIN_DIR / name
    tmp = BIN_DIR / f".{name}.tmp"
    shutil.copyfile(src, tmp)
    tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.replace(tmp, dst)


def _extract_member(archive: Path, basename: str, work: Path) -> Path:
    """Extract the first file called *basename* from a zip/tar archive."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if n.rsplit("/", 1)[-1] == basename and not n.endswith("/"):
                    out = work / basename
                    with z.open(n) as s, open(out, "wb") as d:
                        shutil.copyfileobj(s, d)
                    return out
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                if m.isfile() and m.name.rsplit("/", 1)[-1] == basename:
                    out = work / basename
                    f = t.extractfile(m)
                    with open(out, "wb") as d:
                        shutil.copyfileobj(f, d)
                    return out
    raise RuntimeError(f"{basename} not found inside {archive.name}")


def _fetch_archive(url: str, work: Path) -> Path:
    dest = work / "archive"
    _http_get(url, dest)
    return dest


# --------------------------------------------------------------------------
# installers
# --------------------------------------------------------------------------
def install_aria2(arch):
    url = _github_asset("P3TERX/Aria2-Pro-Core", rf"static-linux-{arch}\.tar\.gz$")
    with tempfile.TemporaryDirectory() as w:
        w = Path(w)
        _install_file(_extract_member(_fetch_archive(url, w), "aria2c", w), "aria2c")


def install_7z(arch):
    suffix = "x64" if arch == "amd64" else "arm64"
    url = _github_asset("ip7z/7zip", rf"7z\d+-linux-{suffix}\.tar\.xz$")
    with tempfile.TemporaryDirectory() as w:
        w = Path(w)
        binary = _extract_member(_fetch_archive(url, w), "7zz", w)
        _install_file(binary, "7zz")
        _install_file(binary, "7z")


def install_ffmpeg(arch):
    try:
        url = (
            "https://johnvansickle.com/ffmpeg/releases/"
            f"ffmpeg-release-{arch}-static.tar.xz"
        )
        with tempfile.TemporaryDirectory() as w:
            w = Path(w)
            archive = _fetch_archive(url, w)
            for tool in ("ffmpeg", "ffprobe"):
                _install_file(_extract_member(archive, tool, w), tool)
        return
    except Exception as e:  # noqa: BLE001
        _log(f"ffmpeg static download failed ({e}); trying imageio-ffmpeg")
    import imageio_ffmpeg  # type: ignore

    _install_file(Path(imageio_ffmpeg.get_ffmpeg_exe()), "ffmpeg")


def install_rclone(arch):
    url = f"https://downloads.rclone.org/rclone-current-linux-{arch}.zip"
    with tempfile.TemporaryDirectory() as w:
        w = Path(w)
        _install_file(_extract_member(_fetch_archive(url, w), "rclone", w), "rclone")


def install_qbit(arch):
    prefix = "x86_64" if arch == "amd64" else "aarch64"
    url = (
        "https://github.com/userdocs/qbittorrent-nox-static/releases/latest/"
        f"download/{prefix}-qbittorrent-nox"
    )
    with tempfile.TemporaryDirectory() as w:
        dest = Path(w) / "qbit"
        _http_get(url, dest)
        _install_file(dest, "qbittorrent-nox")


def install_deno(arch):
    prefix = "x86_64" if arch == "amd64" else "aarch64"
    url = (
        "https://github.com/denoland/deno/releases/latest/download/"
        f"deno-{prefix}-unknown-linux-gnu.zip"
    )
    with tempfile.TemporaryDirectory() as w:
        w = Path(w)
        _install_file(_extract_member(_fetch_archive(url, w), "deno", w), "deno")


_TASKSET = """#!/bin/sh
# taskset replacement (no-op): drops "-c LIST" and runs the command.
case "$1" in
  -c|-pc|--cpu-list) shift; shift ;;
esac
exec "$@"
"""

_CPULIMIT = """#!/bin/sh
# cpulimit replacement (no-op): skips options up to "--" and runs the command.
while [ $# -gt 0 ]; do
  if [ "$1" = "--" ]; then shift; break; fi
  shift
done
exec "$@"
"""


def _is_termux() -> bool:
    return "com.termux" in os.environ.get("PREFIX", "") or Path("/data/data/com.termux").exists()


def install_termux_packages() -> None:
    """Termux: native packages via pkg (no root needed) - far more reliable than static builds.
    Packages are installed ONE BY ONE so a single unavailable package never blocks the others."""
    import subprocess

    pkg = shutil.which("pkg")
    if not pkg:
        return
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")

    def have_any(cmds):
        return any(shutil.which(c) for c in cmds)

    # (commands that prove it is installed, [package names to try in order])
    wanted = [
        (("aria2c",), ["aria2"]),
        (("ffmpeg", "ffprobe"), ["ffmpeg"]),
        (("7z", "7zz", "7za"), ["7zip", "p7zip"]),
        (("rclone",), ["rclone"]),
        (("mediainfo",), ["mediainfo"]),
        (("file",), ["file"]),
        (("node", "deno"), ["nodejs"]),
        (("curl",), ["curl"]),
    ]
    for cmds, names in wanted:
        if have_any(cmds):
            continue
        for name in names:
            _log(f"Termux: pkg install {name}")
            rc = subprocess.run([pkg, "install", "-y", name], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
            if rc == 0 and have_any(cmds):
                break
        else:
            _log(f"Termux: could not install {' / '.join(names)}")

    if shutil.which("qbittorrent-nox") is None and os.getenv("DISABLE_TORRENTS", "").lower() not in ("1", "true"):
        subprocess.run([pkg, "install", "-y", "qbittorrent-nox"], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # make sure a plain `7z` command exists (new Termux '7zip' ships 7zz)
    if shutil.which("7z") is None:
        for alt in ("7zz", "7za", "7zr"):
            src = shutil.which(alt)
            if src:
                try:
                    link = BIN_DIR / "7z"
                    BIN_DIR.mkdir(parents=True, exist_ok=True)
                    link.unlink(missing_ok=True)
                    link.symlink_to(src)
                    _log(f"7z -> {src}")
                except Exception as e:  # noqa: BLE001
                    _log(f"could not link 7z: {e}")
                break

    left = [c for c in ("aria2c", "ffmpeg", "ffprobe", "rclone") if shutil.which(c) is None]
    if not have_any(("7z", "7zz", "7za")):
        left.append("7z")
    if left:
        _log("Termux: still missing -> " + ", ".join(left))


def _privilege_prefix():
    """[] when root, ['sudo','-n'] when passwordless sudo works, None when neither."""
    import subprocess

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    sudo = shutil.which("sudo")
    if sudo:
        try:
            if subprocess.run([sudo, "-n", "true"], capture_output=True, timeout=10).returncode == 0:
                return [sudo, "-n"]
        except Exception:  # noqa: BLE001
            pass
    return None


def install_system_packages() -> None:
    """With root/sudo: install every missing system package (apt / apk / dnf) BEFORE pip runs.
    Without root this does nothing and the static tools in ./bin are used instead."""
    import subprocess

    if _is_termux() or os.name == "nt":
        return
    if os.getenv("AUTO_INSTALL_SYSTEM", "1").strip().lower() in ("0", "false", "no"):
        return
    mgr = next((m for m in ("apt-get", "apk", "dnf", "yum") if shutil.which(m)), None)
    if not mgr:
        return
    prefix = _privilege_prefix()
    if prefix is None:
        _log("no root/sudo -> system packages skipped (static tools will be used)")
        return

    torrents = os.getenv("DISABLE_TORRENTS", "").strip().lower() not in ("1", "true")
    # (commands proving it is installed) -> package name per package manager
    table = [
        (("aria2c",), {"apt-get": "aria2", "apk": "aria2", "dnf": "aria2", "yum": "aria2"}),
        (("ffmpeg", "ffprobe"), {"apt-get": "ffmpeg", "apk": "ffmpeg"}),
        (("7z", "7zz", "7za"), {"apt-get": "p7zip-full", "apk": "7zip", "dnf": "p7zip-plugins", "yum": "p7zip-plugins"}),
        (("rclone",), {"apt-get": "rclone", "apk": "rclone", "dnf": "rclone", "yum": "rclone"}),
        (("mediainfo",), {"apt-get": "mediainfo", "apk": "mediainfo", "dnf": "mediainfo", "yum": "mediainfo"}),
        (("cpulimit",), {"apt-get": "cpulimit", "apk": "cpulimit"}),
        (("taskset",), {"apt-get": "util-linux", "apk": "util-linux", "dnf": "util-linux", "yum": "util-linux"}),
        (("file",), {"apt-get": "file", "apk": "file", "dnf": "file", "yum": "file"}),
        (("curl",), {"apt-get": "curl", "apk": "curl", "dnf": "curl", "yum": "curl"}),
        (("git",), {"apt-get": "git", "apk": "git", "dnf": "git", "yum": "git"}),
        (("unzip",), {"apt-get": "unzip", "apk": "unzip", "dnf": "unzip", "yum": "unzip"}),
        (("xz",), {"apt-get": "xz-utils", "apk": "xz", "dnf": "xz", "yum": "xz"}),
    ]
    if torrents:
        table.append((("qbittorrent-nox",), {"apt-get": "qbittorrent-nox", "apk": "qbittorrent-nox"}))
    if shutil.which("cc") is None and shutil.which("gcc") is None:  # build tools for pip wheels
        table.append((("gcc",), {"apt-get": "build-essential", "apk": "build-base", "dnf": "gcc", "yum": "gcc"}))
    packages = []
    for cmds, names in table:
        if not any(shutil.which(c) for c in cmds) and mgr in names:
            packages.append(names[mgr])
    # libraries (no command to test)
    if mgr == "apt-get":
        for lib in ("libmagic1", "ca-certificates", "python3-dev", "libffi-dev", "libssl-dev"):
            if subprocess.run(["dpkg", "-s", lib], capture_output=True).returncode != 0:
                packages.append(lib)
    if not packages:
        _log("system packages: everything is already installed")
        return

    packages = sorted(set(packages))
    _log(f"system packages ({mgr}): installing " + ", ".join(packages))
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "env": env}
    if mgr == "apt-get":
        subprocess.run(prefix + ["apt-get", "update", "-y"], **quiet)
        base = prefix + ["apt-get", "install", "-y", "--no-install-recommends"]
    elif mgr == "apk":
        base = prefix + ["apk", "add", "--no-cache"]
    else:
        base = prefix + [mgr, "install", "-y"]
    if subprocess.run(base + packages, **quiet).returncode != 0:
        _log("batch install failed, installing one by one ...")
        for pkg in packages:
            rc = subprocess.run(base + [pkg], **quiet).returncode
            if rc != 0:
                _log(f"  could not install {pkg}")


def install_shims():
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for name, body in (("taskset", _TASKSET), ("cpulimit", _CPULIMIT)):
        if not _have(name):
            path = BIN_DIR / name
            path.write_text(body)
            path.chmod(0o755)
            _log(f"{name}: not available, installed a harmless shim")


# --------------------------------------------------------------------------
def ensure_binaries() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    # Always make ./bin visible to every subprocess the bot starts.
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(BIN_DIR) not in parts:
        os.environ["PATH"] = os.pathsep.join([str(BIN_DIR), *parts])

    if os.getenv("AUTO_INSTALL_BINS", "1").strip().lower() in ("0", "false", "no"):
        return
    if os.name == "nt":
        return

    if _is_termux():
        try:
            install_termux_packages()
        except Exception as e:  # noqa: BLE001
            _log(f"Termux package install failed: {e}")
        install_shims()
        return  # static glibc builds are not suitable for Android; native pkg tools are used

    install_shims()

    # drop executables in ./bin that cannot run here (e.g. copied from another machine)
    for _n in ("aria2c", "7z", "7zz", "ffmpeg", "ffprobe", "rclone", "deno"):
        _f = BIN_DIR / _n
        if _f.is_file() and not _working(_n):
            _f.unlink(missing_ok=True)

    arch = _arch()
    if arch is None:
        _log(f"unsupported CPU ({platform.machine()}); skipping downloads")
        return

    jobs = []
    if (
        os.getenv("INSTALL_ARIA2", "1").strip().lower() in ("1", "true", "yes")
        and not _have("aria2c")
        and not os.getenv("ARIA2C_BIN")
    ):
        jobs.append(("aria2c", install_aria2))
    if not _have("7z") and not _have("7zz"):
        jobs.append(("7z", install_7z))
    if not _have("ffmpeg") or not _have("ffprobe"):
        jobs.append(("ffmpeg", install_ffmpeg))
    if not _have("rclone") and not os.getenv("RCLONE_BIN"):
        jobs.append(("rclone", install_rclone))
    if not _have("qbittorrent-nox") and not os.getenv("QBIT_BIN"):
        if os.getenv("DISABLE_TORRENTS", "").strip().lower() not in ("1", "true"):
            jobs.append(("qbittorrent-nox", install_qbit))
    if not _have("deno") and not _have("node"):
        jobs.append(("deno", install_deno))
    if not jobs:
        return

    _log("missing tools: " + ", ".join(n for n, _ in jobs) + " - downloading (no root needed)")

    def run(job):
        name, fn = job
        try:
            fn(arch)
            _log(f"{name}: installed in {BIN_DIR}")
        except Exception as e:  # noqa: BLE001
            _log(f"{name}: could not install ({e}); built-in fallback will be used if any")

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, jobs))


if __name__ == "__main__":
    ensure_binaries()
