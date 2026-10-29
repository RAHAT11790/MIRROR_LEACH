"""Built-in aria2 replacement powered by aiohttp.

When the ``aria2c`` binary is missing (no root, no ``apt``), the bot falls back
to this class. It exposes the small subset of the aria2 JSON-RPC API that the
rest of the code uses (addUri, tellStatus, forcePause, ...), so Aria2Status,
DirectListener, the queue system and the aria2 listeners keep working
unchanged.

Supported : http / https links (resume, redirects, headers, Content-Disposition
            names, multi-connection download when the server allows ranges).
Not supported: magnet / .torrent / ftp / metalink (these need aria2 or qBittorrent).
"""

from __future__ import annotations

import re
from asyncio import (
    CancelledError,
    TimeoutError as AsyncTimeout,
    create_task,
    gather,
    sleep,
)
from collections import deque
from os import makedirs, path as ospath
from secrets import token_hex
from time import time
from urllib.parse import parse_qs, unquote, urlencode, urljoin, urlparse

from aiofiles import open as aiopen
from aiohttp import ClientError, ClientSession, ClientTimeout, TCPConnector

from .. import LOGGER

MIN_SPLIT = 16 * 1024 * 1024  # only split files bigger than this
CHUNK = 256 * 1024
MAX_TRIES = 5
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class HttpAria2Error(Exception):
    pass


def _clean_name(name: str) -> str:
    name = unquote(name or "").strip().replace("\\", "_").replace("/", "_")
    name = name.strip(". ")
    return name[:200]


def _name_from_disposition(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", value, re.I)
    if m:
        return _clean_name(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', value, re.I) or re.search(
        r"filename\s*=\s*([^;]+)", value, re.I
    )
    return _clean_name(m.group(1).strip()) if m else ""


def _parse_headers(raw) -> dict:
    headers = {}
    if not raw:
        return headers
    if isinstance(raw, str):
        raw = raw.splitlines()
    for item in raw:
        if isinstance(item, str) and ":" in item:
            k, v = item.split(":", 1)
            headers[k.strip()] = v.strip()
    return headers


def _gdrive_id(url: str):
    p = urlparse(url)
    if p.netloc not in ("drive.google.com", "docs.google.com", "drive.usercontent.google.com"):
        return None
    q = parse_qs(p.query)
    if q.get("id"):
        return q["id"][0]
    m = re.search(r"/d/([\w-]+)", p.path)
    return m.group(1) if m else None


class _Task:
    def __init__(self, gid, url, options):
        self.gid = gid
        self.url = url
        self.options = {k: str(v) for k, v in (options or {}).items()}
        self.dir = self.options.get("dir") or "downloads"
        self.out = _clean_name(self.options.get("out", ""))
        if not self.out:
            self.out = _clean_name(urlparse(url).path.rsplit("/", 1)[-1]) or "download"
        self.status = "waiting"
        self.total = 0
        self.completed = 0
        self.error = ""
        self.supports_range = False
        self.runner = None
        self.samples = deque()
        self.fetch_url = url
        self.part_done = {}

    @property
    def file_path(self):
        return f"{self.dir}/{self.out}"

    def tick(self):
        now = time()
        self.samples.append((now, self.completed))
        while len(self.samples) > 2 and now - self.samples[0][0] > 4:
            self.samples.popleft()

    @property
    def speed(self):
        if self.status != "active" or len(self.samples) < 2:
            return 0
        t0, b0 = self.samples[0]
        t1, b1 = self.samples[-1]
        span = max(t1, time()) - t0 if time() - t1 < 2 else t1 - t0
        if span < 0.2:
            return 0
        return max(int((b1 - b0) / span), 0)

    def info(self):
        return {
            "gid": self.gid,
            "status": self.status,
            "totalLength": str(self.total),
            "completedLength": str(self.completed),
            "uploadLength": "0",
            "downloadSpeed": str(self.speed),
            "uploadSpeed": "0",
            "connections": "1" if self.status == "active" else "0",
            "dir": self.dir,
            "errorMessage": self.error,
            "errorCode": "1" if self.error else "0",
            "files": [
                {
                    "index": "1",
                    "path": self.file_path,
                    "length": str(self.total),
                    "completedLength": str(self.completed),
                    "selected": "true",
                    "uris": [{"uri": self.url, "status": "used"}],
                }
            ],
        }


class HttpAria2:
    """Drop-in (partial) replacement for the aioaria2 client."""

    is_fallback = True

    def __init__(self):
        self._tasks: dict[str, _Task] = {}
        self._callbacks = {}
        self._session = None
        self.global_options = {}
        self._api = self

    # ----- aria2 callbacks ------------------------------------------------
    def _register(self, name, fn):
        self._callbacks.setdefault(name, []).append(fn)

    def onDownloadStart(self, fn):
        self._register("start", fn)

    def onDownloadComplete(self, fn):
        self._register("complete", fn)

    def onDownloadError(self, fn):
        self._register("error", fn)

    def onDownloadStop(self, fn):
        self._register("stop", fn)

    def onBtDownloadComplete(self, fn):
        self._register("bt", fn)

    def _fire(self, name, gid):
        for fn in self._callbacks.get(name, []):
            create_task(self._safe_cb(fn, gid))

    async def _safe_cb(self, fn, gid):
        try:
            await fn(self._api, {"params": [{"gid": gid}]})
        except Exception as e:  # noqa: BLE001
            LOGGER.error(f"HttpAria2 callback error: {e}")

    # ----- session --------------------------------------------------------
    def _get_session(self):
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                connector=TCPConnector(ssl=False, limit=0),
                timeout=ClientTimeout(total=None, sock_connect=30, sock_read=90),
                headers={"User-Agent": USER_AGENT},
            )
        return self._session

    # ----- RPC surface ----------------------------------------------------
    async def addUri(self, uris, options=None, position=None):
        url = uris[0] if isinstance(uris, (list, tuple)) else uris
        scheme = urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise HttpAria2Error(
                f"'{scheme or url[:20]}' links need aria2 or qBittorrent, which are "
                "not installed. Only http/https direct links work in this mode."
            )
        gid = token_hex(8)
        task = _Task(gid, url, options)
        self._tasks[gid] = task
        if task.options.get("pause", "").lower() == "true":
            task.status = "paused"
        else:
            self._start(task)
        return gid

    async def addTorrent(self, *args, **kwargs):
        raise HttpAria2Error(
            "Torrent files need aria2 or qBittorrent, which are not installed."
        )

    async def jsonrpc(self, method, params=None):
        if method in ("addTorrent", "addMetalink"):
            raise HttpAria2Error(
                "Torrent/metalink files need aria2 or qBittorrent, which are not installed."
            )
        raise HttpAria2Error(f"Unsupported aria2 RPC call: {method}")

    def _get(self, gid) -> _Task:
        task = self._tasks.get(gid)
        if not task:
            raise HttpAria2Error(f"GID#{gid} is not found")
        return task

    async def tellStatus(self, gid, keys=None):
        return self._get(gid).info()

    async def getOption(self, gid):
        return dict(self._get(gid).options)

    async def getFiles(self, gid):
        return self._get(gid).info()["files"]

    async def tellActive(self, keys=None):
        return [t.info() for t in self._tasks.values() if t.status == "active"]

    async def tellWaiting(self, offset=0, num=1000, keys=None):
        res = [t.info() for t in self._tasks.values() if t.status in ("waiting", "paused")]
        return res[offset : offset + num]

    async def tellStopped(self, offset=0, num=1000, keys=None):
        res = [
            t.info()
            for t in self._tasks.values()
            if t.status in ("complete", "error", "removed")
        ]
        return res[offset : offset + num]

    async def getGlobalStat(self):
        active = [t for t in self._tasks.values() if t.status == "active"]
        return {
            "downloadSpeed": str(sum(t.speed for t in active)),
            "uploadSpeed": "0",
            "numActive": str(len(active)),
            "numWaiting": str(
                sum(1 for t in self._tasks.values() if t.status in ("waiting", "paused"))
            ),
            "numStopped": str(
                sum(
                    1
                    for t in self._tasks.values()
                    if t.status in ("complete", "error", "removed")
                )
            ),
        }

    async def getGlobalOption(self):
        return dict(self.global_options)

    async def changeGlobalOption(self, options):
        self.global_options.update({k: str(v) for k, v in (options or {}).items()})
        return "OK"

    async def changeOption(self, gid, options):
        self._get(gid).options.update({k: str(v) for k, v in (options or {}).items()})
        return "OK"

    async def pause(self, gid):
        return await self.forcePause(gid)

    async def forcePause(self, gid):
        task = self._get(gid)
        if task.status in ("active", "waiting"):
            await self._stop_runner(task)
            task.status = "paused"
        return gid

    async def pauseAll(self):
        return await self.forcePauseAll()

    async def forcePauseAll(self):
        for task in list(self._tasks.values()):
            if task.status in ("active", "waiting"):
                await self.forcePause(task.gid)
        return "OK"

    async def unpause(self, gid):
        task = self._get(gid)
        if task.status == "paused":
            self._start(task)
        return gid

    async def unpauseAll(self):
        for task in list(self._tasks.values()):
            if task.status == "paused":
                self._start(task)
        return "OK"

    async def remove(self, gid):
        return await self.forceRemove(gid)

    async def forceRemove(self, gid):
        task = self._get(gid)
        await self._stop_runner(task)
        if task.status not in ("complete", "error"):
            task.status = "removed"
        return gid

    async def removeDownloadResult(self, gid):
        self._get(gid)
        self._tasks.pop(gid, None)
        return "OK"

    async def purgeDownloadResult(self):
        for gid in [
            g
            for g, t in self._tasks.items()
            if t.status in ("complete", "error", "removed")
        ]:
            self._tasks.pop(gid, None)
        return "OK"

    async def close(self):
        for task in list(self._tasks.values()):
            await self._stop_runner(task)
        if self._session and not self._session.closed:
            await self._session.close()

    # ----- download engine -----------------------------------------------
    def _start(self, task: _Task):
        task.status = "active"
        task.samples.clear()
        task.tick()
        task.runner = create_task(self._run(task))

    async def _stop_runner(self, task: _Task):
        runner, task.runner = task.runner, None
        if runner and not runner.done():
            runner.cancel()
            try:
                await runner
            except (CancelledError, Exception):  # noqa: BLE001
                pass

    async def _run(self, task: _Task):
        try:
            makedirs(task.dir, exist_ok=True)
            self._fire("start", task.gid)
            await self._download(task)
            if task.status == "active":
                task.status = "complete"
                task.samples.clear()
                self._fire("complete", task.gid)
        except CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            task.status = "error"
            task.error = str(e) or e.__class__.__name__
            LOGGER.error(f"HttpAria2 download failed ({task.url[:80]}): {task.error}")
            self._fire("error", task.gid)

    async def _resolve_gdrive(self, task, session):
        """Public Google Drive links without API credentials (handles the virus-scan page)."""
        fid = _gdrive_id(task.url)
        if not fid:
            return
        url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
        for _ in range(2):
            async with session.get(url, headers=self._request_headers(task)) as resp:
                ctype = resp.headers.get("Content-Type", "")
                if resp.status >= 400:
                    raise HttpAria2Error(f"Google Drive returned HTTP {resp.status}")
                if "text/html" not in ctype:
                    task.fetch_url = url
                    return
                html = await resp.text()
            action = re.search(r'<form[^>]+action="([^"]+)"', html)
            fields = dict(
                re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', html)
            )
            if not action or not fields:
                raise HttpAria2Error(
                    "Google Drive file is private, deleted, or its download quota is exceeded."
                )
            url = urljoin(url, action.group(1).replace("&amp;", "&")) + "?" + urlencode(fields)
        task.fetch_url = url

    def _request_headers(self, task, extra=None):
        headers = _parse_headers(task.options.get("header"))
        if extra:
            headers.update(extra)
        return headers

    async def _download(self, task: _Task):
        session = self._get_session()
        await self._resolve_gdrive(task, session)
        resume_from = 0
        if ospath.isfile(task.file_path):
            resume_from = ospath.getsize(task.file_path)
        last_error = None
        for attempt in range(1, MAX_TRIES + 1):
            try:
                extra = {"Range": f"bytes={resume_from}-"} if resume_from else None
                async with session.get(
                    task.fetch_url, headers=self._request_headers(task, extra)
                ) as resp:
                    if resp.status == 416 and resume_from:
                        # already fully downloaded
                        task.completed = task.total = resume_from
                        return
                    if resp.status >= 400:
                        raise HttpAria2Error(f"HTTP {resp.status} {resp.reason}")
                    partial = resp.status == 206
                    if not partial:
                        resume_from = 0
                    task.supports_range = (
                        partial or resp.headers.get("Accept-Ranges", "").lower() == "bytes"
                    )
                    length = int(resp.headers.get("Content-Length", "0") or 0)
                    task.total = (resume_from + length) if length else 0
                    if not task.options.get("out"):
                        disp = _name_from_disposition(
                            resp.headers.get("Content-Disposition", "")
                        )
                        if disp:
                            task.out = disp
                        elif "." not in task.out:
                            ctype = resp.headers.get("Content-Type", "")
                            if "video/mp4" in ctype:
                                task.out += ".mp4"
                    task.completed = resume_from

                    use_parallel = (
                        not partial
                        and not resume_from
                        and task.supports_range
                        and task.total >= MIN_SPLIT
                        and int(task.options.get("split", "8") or 8) > 1
                    )
                    if not use_parallel:
                        await self._stream(task, resp, resume_from)
                        return
                # server allows ranges: use several connections for big files
                await self._download_parallel(task)
                return
            except HttpAria2Error:
                raise
            except (ClientError, AsyncTimeout, OSError) as e:
                last_error = e
                LOGGER.warning(
                    f"HttpAria2 retry {attempt}/{MAX_TRIES} for {task.out}: {e}"
                )
                if ospath.isfile(task.file_path) and task.supports_range:
                    resume_from = ospath.getsize(task.file_path)
                else:
                    resume_from = 0
                await sleep(min(2 * attempt, 8))
        raise HttpAria2Error(f"Download failed after {MAX_TRIES} tries: {last_error}")

    async def _stream(self, task, resp, resume_from):
        mode = "ab" if resume_from else "wb"
        async with aiopen(task.file_path, mode) as f:
            async for chunk in resp.content.iter_chunked(CHUNK):
                await f.write(chunk)
                task.completed += len(chunk)
                task.tick()
        if task.total and task.completed < task.total:
            raise ClientError("connection closed before the file was complete")
        if not task.total:
            task.total = task.completed

    async def _download_parallel(self, task: _Task):
        session = self._get_session()
        parts = max(2, min(int(task.options.get("split", "8") or 8), 8))
        size = task.total
        step = size // parts
        ranges = [
            (i * step, (size - 1) if i == parts - 1 else ((i + 1) * step - 1))
            for i in range(parts)
        ]
        async with aiopen(task.file_path, "wb") as f:
            await f.truncate(size)
        task.completed = 0
        task.samples.clear()
        task.tick()

        async def worker(start, end):
            pos = start
            tries = 0
            while pos <= end:
                try:
                    async with session.get(
                        task.fetch_url,
                        headers=self._request_headers(
                            task, {"Range": f"bytes={pos}-{end}"}
                        ),
                    ) as resp:
                        if resp.status != 206:
                            raise HttpAria2Error(
                                f"server ignored Range request (HTTP {resp.status})"
                            )
                        async with aiopen(task.file_path, "r+b") as f:
                            await f.seek(pos)
                            async for chunk in resp.content.iter_chunked(CHUNK):
                                if pos + len(chunk) > end + 1:
                                    chunk = chunk[: end + 1 - pos]
                                await f.write(chunk)
                                pos += len(chunk)
                                task.completed += len(chunk)
                                task.tick()
                                if pos > end:
                                    break
                except (ClientError, AsyncTimeout, OSError) as e:
                    tries += 1
                    if tries >= MAX_TRIES:
                        raise HttpAria2Error(f"segment failed: {e}") from e
                    await sleep(min(2 * tries, 8))

        results = await gather(*(worker(s, e) for s, e in ranges), return_exceptions=True)
        for r in results:
            if isinstance(r, CancelledError):
                raise r
            if isinstance(r, Exception):
                # fall back to a simple single-stream download of the whole file
                LOGGER.warning(f"Parallel download failed ({r}); using single stream")
                task.completed = 0
                async with session.get(task.fetch_url, headers=self._request_headers(task)) as resp:
                    if resp.status >= 400:
                        raise HttpAria2Error(f"HTTP {resp.status} {resp.reason}")
                    await self._stream(task, resp, 0)
                return


class HybridAria2:
    """Real aria2 for magnet/torrent/ftp, built-in aiohttp engine for http(s).

    http/https links never touch aria2c, so a broken or blocked aria2 build
    ("Download aborted.") cannot break normal downloads. Set HTTP_VIA_ARIA2=1
    to send http links to aria2c again.
    """

    is_fallback = False

    def __init__(self, real):
        self.real = real
        self.http = HttpAria2()
        self.http._api = self

    def __getattr__(self, name):
        return getattr(self.real, name)

    def _engine(self, gid):
        return self.http if gid in self.http._tasks else self.real

    # callbacks: the handlers must always receive *this* object as `api`
    def _wrap_real_cb(self, fn):
        async def inner(_api, data):
            await fn(self, data)

        return inner

    def onDownloadStart(self, fn):
        self.http.onDownloadStart(fn)
        self.real.onDownloadStart(self._wrap_real_cb(fn))

    def onDownloadComplete(self, fn):
        self.http.onDownloadComplete(fn)
        self.real.onDownloadComplete(self._wrap_real_cb(fn))

    def onDownloadError(self, fn):
        self.http.onDownloadError(fn)
        self.real.onDownloadError(self._wrap_real_cb(fn))

    def onDownloadStop(self, fn):
        self.http.onDownloadStop(fn)
        self.real.onDownloadStop(self._wrap_real_cb(fn))

    def onBtDownloadComplete(self, fn):
        self.real.onBtDownloadComplete(self._wrap_real_cb(fn))

    async def addUri(self, uris, options=None, position=None):
        url = uris[0] if isinstance(uris, (list, tuple)) else uris
        if urlparse(str(url)).scheme.lower() in ("http", "https"):
            return await self.http.addUri(uris, options, position)
        return await self.real.addUri(uris=uris, options=options, position=position)

    async def tellStatus(self, gid, keys=None):
        return await self._engine(gid).tellStatus(gid)

    async def getOption(self, gid):
        return await self._engine(gid).getOption(gid)

    async def getFiles(self, gid):
        return await self._engine(gid).getFiles(gid)

    async def changeOption(self, gid, options):
        return await self._engine(gid).changeOption(gid, options)

    async def forcePause(self, gid):
        return await self._engine(gid).forcePause(gid)

    async def pause(self, gid):
        return await self._engine(gid).pause(gid)

    async def unpause(self, gid):
        return await self._engine(gid).unpause(gid)

    async def forceRemove(self, gid):
        return await self._engine(gid).forceRemove(gid)

    async def remove(self, gid):
        return await self._engine(gid).remove(gid)

    async def removeDownloadResult(self, gid):
        return await self._engine(gid).removeDownloadResult(gid)

    async def _merged(self, name, *args):
        res = list(await getattr(self.http, name)(*args))
        try:
            res = list(await getattr(self.real, name)(*args)) + res
        except Exception:  # noqa: BLE001
            pass
        return res

    async def tellActive(self, keys=None):
        return await self._merged("tellActive")

    async def tellWaiting(self, offset=0, num=1000, keys=None):
        return await self._merged("tellWaiting", offset, num)

    async def tellStopped(self, offset=0, num=1000, keys=None):
        return await self._merged("tellStopped", offset, num)

    async def getGlobalStat(self):
        stat = await self.http.getGlobalStat()
        try:
            real = await self.real.getGlobalStat()
            for k in ("downloadSpeed", "uploadSpeed", "numActive", "numWaiting", "numStopped"):
                stat[k] = str(int(stat.get(k, 0)) + int(real.get(k, 0)))
        except Exception:  # noqa: BLE001
            pass
        return stat

    async def getGlobalOption(self):
        return await self.real.getGlobalOption()

    async def changeGlobalOption(self, options):
        await self.http.changeGlobalOption(options)
        return await self.real.changeGlobalOption(options)

    async def forcePauseAll(self):
        await self.http.forcePauseAll()
        try:
            return await self.real.forcePauseAll()
        except Exception:  # noqa: BLE001
            return "OK"

    async def purgeDownloadResult(self):
        await self.http.purgeDownloadResult()
        try:
            return await self.real.purgeDownloadResult()
        except Exception:  # noqa: BLE001
            return "OK"

    async def close(self):
        await self.http.close()
        return await self.real.close()
