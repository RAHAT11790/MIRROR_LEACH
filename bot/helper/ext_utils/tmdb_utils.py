import re
from asyncio import sleep
from difflib import SequenceMatcher
from urllib.parse import quote, unquote

from niquests import AsyncSession

from ... import LOGGER
from ...core.config_manager import Config

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/original"

_QUALITY_TAGS = re.compile(
    r"\b(?:\d{3,4}p|4k|x26[45]|h\.?26[45]|hevc|avc|xvid|divx|aac\d?|ac3|eac3|ddp?\d(?:\.\d)?"
    r"|dts(?:-hd)?|truehd|atmos|hdr\d*|10bit|8bit|web-?dl|web-?rip|blu-?ray|bd-?rip"
    r"|br-?rip|hd-?rip|dvd-?rip|hdts|cam-?rip|hdtv|remux|repack|esubs?|msubs?|subbed"
    r"|dubbed|dsnp|amzn|hmax|hotstar|mkv|mp4|m4v|avi|webm|mpe?g|rar|zip|7z|part\d+)\b",
    re.IGNORECASE,
)
_SITE_PREFIX = re.compile(
    r"^\W*(?:www\.)?[\w-]+\.(?:com|net|org|xyz|me|in|to|co|cc|info|tv|link|app|online"
    r"|site|club|work|icu|top|vip|pro|party|fun|cam|lol|sbs|ws)"
    r"(?:\s*[-–—]+\s*|\s+)",
    re.IGNORECASE,
)

_poster_cache = {}


def _tidy(title):
    title = re.sub(r"\s-+\s", " ", title)
    return re.sub(r"\s+", " ", title).strip(" -_.")


def _final_clean(title):
    base = re.sub(r"[\[\](){}]", " ", title)
    return _tidy(_QUALITY_TAGS.sub(" ", base)) or _tidy(base)


def clean_poster_title(raw_title):
    title = unquote(raw_title)
    title = re.sub(r"https?://\S+", " ", title)
    title = re.sub(r"\b(?:t|telegram)\.me/\S+", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"\[[^\]]*\]", " ", title)
    title = re.sub(r"[\[\](){}]", " ", title)
    title = re.sub(r"\.\w{2,4}$", "", title)
    title = _SITE_PREFIX.sub("", title)
    title = re.sub(r"\bwww\S*", " ", title, flags=re.IGNORECASE)
    title = title.replace("_", " ")
    if _QUALITY_TAGS.search(title):
        title = re.sub(r"-\w+$", "", title)
    title = title.replace(".", " ")
    title = re.sub(r"\s+", " ", title).strip()

    for pattern in (
        r"(?<!\w)S0*\d{1,2}\s?E\d{1,3}(?!\w)",
        r"\bSeason\s+\d{1,2}\b",
        r"(?<!\w)S0*\d{1,2}(?!\w)",
        r"(?<!\w)(?:E|EP|EPISODE)\s?\d{1,4}(?!\w)",
    ):
        marker = re.search(pattern, title, re.IGNORECASE)
        if marker:
            head = title[: marker.start()].strip()
            tail = title[marker.end() :].strip()
            title = head if len(head) > 1 else tail
            return _final_clean(title), None

    years = list(re.finditer(r"\b(?:19|20)\d{2}\b", title))
    if years:
        last = years[-1]
        head = title[: last.start()].strip()
        tail = title[last.end() :].strip()
        return _final_clean(head if len(head) > 1 else tail), last.group(0)

    return _final_clean(title), None


def _pick_image(images, as_doc):
    backdrops = images.get("backdrops", [])
    posters = images.get("posters", [])
    en_backdrops = [i for i in backdrops if i.get("iso_639_1") == "en"]
    no_lang_backdrops = [i for i in backdrops if i.get("iso_639_1") is None]
    en_posters = [i for i in posters if i.get("iso_639_1") == "en"]
    no_lang_posters = [i for i in posters if i.get("iso_639_1") is None]

    if as_doc:
        order = [en_posters, no_lang_posters, posters, en_backdrops, no_lang_backdrops]
    else:
        order = [en_backdrops, no_lang_backdrops, backdrops, en_posters, posters]

    for group in order:
        if group:
            return group[0]["file_path"]
    return None


def _tmdb_token():
    return str(
        getattr(Config, "TMDB_API_KEY", "") or Config.TMDB_ACCESS_TOKEN or ""
    ).strip()


async def get_tmdb_poster_link(title, year=None, as_doc=False):
    token = _tmdb_token()
    if not token:
        return None

    headers = {"accept": "application/json"}
    params = {
        "query": title,
        "include_adult": "false",
        "language": "en-US",
        "page": "1",
    }
    if len(token) < 50:
        params["api_key"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(3):
        try:
            async with AsyncSession(timeout=15) as client:
                resp = await client.get(TMDB_SEARCH_URL, params=params, headers=headers)
                if resp.status_code == 401:
                    LOGGER.warning("TMDb authentication failed, check TMDB_ACCESS_TOKEN")
                    return None
                if resp.status_code >= 500:
                    await sleep(2)
                    continue
                if resp.status_code != 200:
                    LOGGER.warning(f"TMDb returned {resp.status_code} for '{title}'")
                    return None

                results = [
                    r
                    for r in resp.json().get("results", [])
                    if r.get("media_type") != "person"
                ]
                if not results:
                    LOGGER.info(f"No TMDb results for '{title}'")
                    return None

                first = results[0]
                if year:
                    for result in results:
                        date = (
                            result.get("release_date")
                            or result.get("first_air_date")
                            or ""
                        )
                        if date.startswith(year):
                            first = result
                            break
                media_type = first.get("media_type", "movie")

                img_params = {"include_image_language": "en,null"}
                if len(token) < 50:
                    img_params["api_key"] = token
                img_resp = await client.get(
                    f"https://api.themoviedb.org/3/{media_type}/{first['id']}/images",
                    params=img_params,
                    headers=headers,
                )
                if img_resp.status_code == 200:
                    path = _pick_image(img_resp.json(), as_doc)
                    if path:
                        return f"{TMDB_IMAGE_URL}{path}"

                backdrop = first.get("backdrop_path")
                poster = first.get("poster_path")
                fallback = (poster or backdrop) if as_doc else (backdrop or poster)
                if fallback:
                    return f"{TMDB_IMAGE_URL}{fallback}"
                return None
        except Exception as e:
            LOGGER.warning(f"TMDb request failed ({attempt + 1}/3): {e}")
            await sleep(1)
    return None


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _match_score(query, candidates):
    q = _norm(query)
    best = 0.0
    for cand in candidates:
        c = _norm(cand)
        if not c or not q:
            continue
        if q == c:
            return 1.0
        if q in c or c in q:
            best = max(best, 0.9 if min(len(q), len(c)) >= 4 else 0.0)
        best = max(best, SequenceMatcher(None, q, c).ratio())
    return best


async def get_anilist_poster_link(title, as_doc=False):
    """Anime posters from AniList (free, no API key)."""
    query = (
        "query($s:String){Page(perPage:6){media(search:$s,type:ANIME,sort:SEARCH_MATCH)"
        "{title{romaji english native} synonyms bannerImage coverImage{extraLarge large}}}}"
    )
    try:
        async with AsyncSession(timeout=15) as client:
            resp = await client.post(
                "https://graphql.anilist.co",
                json={"query": query, "variables": {"s": title}},
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return None
            media = resp.json().get("data", {}).get("Page", {}).get("media", [])
    except Exception as e:
        LOGGER.warning(f"AniList request failed: {e}")
        return None
    best, best_score = None, 0.0
    for item in media:
        names = list((item.get("title") or {}).values()) + (item.get("synonyms") or [])
        score = _match_score(title, names)
        if score > best_score:
            best, best_score = item, score
    if not best or best_score < 0.6:
        return None
    cover = (best.get("coverImage") or {}).get("extraLarge") or (
        best.get("coverImage") or {}
    ).get("large")
    return cover or best.get("bannerImage")


async def get_jikan_poster_link(title):
    """Fallback anime posters from MyAnimeList via Jikan (free, no API key)."""
    try:
        async with AsyncSession(timeout=15) as client:
            resp = await client.get(
                "https://api.jikan.moe/v4/anime", params={"q": title, "limit": "6"}
            )
            if resp.status_code != 200:
                return None
            data = resp.json().get("data", [])
    except Exception as e:
        LOGGER.warning(f"Jikan request failed: {e}")
        return None
    best, best_score = None, 0.0
    for item in data:
        names = [t.get("title") for t in item.get("titles", [])]
        score = _match_score(title, names)
        if score > best_score:
            best, best_score = item, score
    if not best or best_score < 0.6:
        return None
    jpg = (best.get("images") or {}).get("jpg") or {}
    return jpg.get("large_image_url") or jpg.get("image_url")


def _make_landscape(path):
    """Portrait posters -> 16:9 thumbnail (blurred backdrop + centered poster)."""
    from PIL import Image, ImageFilter

    with Image.open(path) as img:
        img = img.convert("RGB")
        w, h = img.size
        if w >= h * 1.4:
            return
        tw = max(int(h * 16 / 9), w)
        bg = img.resize((tw, h)).filter(ImageFilter.GaussianBlur(20))
        bg.paste(img, ((tw - w) // 2, 0))
        bg.thumbnail((320, 320))
        bg.save(path, "JPEG", quality=90)


UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
DEFAULT_PROVIDERS = "imdb,anilist,jikan,kitsu,tvmaze,tmdb"


async def _get_json(url, **kwargs):
    for attempt in range(2):
        try:
            async with AsyncSession(timeout=15) as client:
                resp = await client.get(url, headers=UA, **kwargs)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code < 500:
                    return None
        except Exception as e:
            LOGGER.warning(f"Thumbnail API request failed ({url[:50]}): {e}")
        await sleep(1)
    return None


async def get_imdb_poster_link(title, year=None, as_doc=False):
    """IMDb poster through IMDb's public suggestion endpoint (no key needed)."""
    first = re.sub(r"[^a-z0-9]", "", title.lower()[:1]) or "x"
    data = await _get_json(
        f"https://v2.sg.media-imdb.com/suggestion/{first}/{quote(title.lower())}.json"
    )
    items = [
        d
        for d in (data or {}).get("d", [])
        if str(d.get("id", "")).startswith("tt") and (d.get("i") or {}).get("imageUrl")
    ]
    best, best_score = None, 0.0
    for item in items:
        score = _match_score(title, [item.get("l", "")])
        if year and str(item.get("y", "")) == str(year):
            score += 0.15
        if score > best_score:
            best, best_score = item, score
    if not best or best_score < 0.6:
        return None
    return best["i"]["imageUrl"]


async def get_kitsu_poster_link(title, year=None, as_doc=False):
    """Kitsu (anime) - has both posters and wide covers."""
    data = await _get_json(
        "https://kitsu.io/api/edge/anime",
        params={"filter[text]": title, "page[limit]": "5"},
    )
    best, best_score = None, 0.0
    for item in (data or {}).get("data", []):
        attrs = item.get("attributes") or {}
        names = [attrs.get("canonicalTitle")] + list((attrs.get("titles") or {}).values())
        names += attrs.get("abbreviatedTitles") or []
        score = _match_score(title, names)
        if score > best_score:
            best, best_score = attrs, score
    if not best or best_score < 0.6:
        return None
    poster = best.get("posterImage") or {}
    cover = best.get("coverImage") or {}
    pick = (poster.get("original") or poster.get("large")) if as_doc else (
        cover.get("original") or cover.get("large") or poster.get("original")
    )
    return pick or poster.get("original")


async def get_tvmaze_poster_link(title, year=None, as_doc=False):
    """TVmaze (TV series) - free, no key."""
    data = await _get_json("https://api.tvmaze.com/search/shows", params={"q": title})
    best, best_score = None, 0.0
    for item in data or []:
        show = item.get("show") or {}
        score = _match_score(title, [show.get("name", "")])
        if year and str(show.get("premiered", ""))[:4] == str(year):
            score += 0.15
        if score > best_score and (show.get("image") or {}).get("original"):
            best, best_score = show, score
    if not best or best_score < 0.6:
        return None
    return best["image"]["original"]


async def _anilist(title, year=None, as_doc=False):
    return await get_anilist_poster_link(title, as_doc)


async def _jikan(title, year=None, as_doc=False):
    return await get_jikan_poster_link(title)


async def _tmdb(title, year=None, as_doc=False):
    if not _tmdb_token():
        return None
    return await get_tmdb_poster_link(title, year, as_doc)


PROVIDERS = {
    "imdb": get_imdb_poster_link,
    "anilist": _anilist,
    "jikan": _jikan,
    "kitsu": get_kitsu_poster_link,
    "tvmaze": get_tvmaze_poster_link,
    "tmdb": _tmdb,
}


def _provider_order():
    raw = str(getattr(Config, "THUMBNAIL_PROVIDERS", "") or DEFAULT_PROVIDERS)
    order = [p.strip().lower() for p in re.split(r"[,\s]+", raw) if p.strip()]
    order = [p for p in order if p in PROVIDERS]
    # TMDb is always the LAST resort
    order = [p for p in order if p != "tmdb"] + ["tmdb"]
    return order


async def get_auto_thumbnail(filename, as_doc=False):
    """Try IMDb -> AniList -> Jikan -> Kitsu -> TVmaze -> TMDb (last) until one gives an image."""
    from asyncio import to_thread

    from .media_utils import download_image_thumb

    title, year = clean_poster_title(filename)
    if len(title) < 2:
        return None

    key = (title, year, as_doc)
    urls = []
    if key in _poster_cache:
        urls.append(("cache", _poster_cache[key]))

    async def candidates():
        for url_info in urls:
            yield url_info
        for name in _provider_order():
            try:
                url = await PROVIDERS[name](title, year, as_doc)
            except Exception as e:
                LOGGER.warning(f"Thumbnail provider {name} failed: {e}")
                continue
            if url:
                yield name, url
            else:
                LOGGER.info(f"Thumbnail provider {name}: nothing for '{title}'")

    async for name, url in candidates():
        thumb = await download_image_thumb(url) or None
        if not thumb:
            LOGGER.info(f"Thumbnail from {name} could not be downloaded, trying next")
            continue
        if len(_poster_cache) > 200:
            _poster_cache.clear()
        _poster_cache[key] = url
        LOGGER.info(f"Auto thumbnail for '{title}' from {name}: {url}")
        if not as_doc:
            try:
                await to_thread(_make_landscape, thumb)
            except Exception as e:
                LOGGER.warning(f"Thumbnail resize failed: {e}")
        return thumb
    LOGGER.info(f"No auto thumbnail found for '{title}'")
    return None
