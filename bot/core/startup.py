from shutil import which as _which
from asyncio import create_subprocess_exec, create_subprocess_shell, gather, sleep
from asyncio.subprocess import DEVNULL
from importlib import import_module
from os import environ, name as os_name, path as ospath, getenv
from shutil import which
from sys import executable as python_exe

from aiofiles import open as aiopen
from aiofiles.os import makedirs, remove, path as aiopath
from aioshutil import rmtree


from .. import (
    LOGGER,
    bot_loop,
    aria2_options,
    auth_chats,
    categories_dict,
    drives_ids,
    drives_names,
    index_urls,
    list_drives_dict,
    shortener_dict,
    var_list,
    user_data,
    excluded_extensions,
    nzb_options,
    qbit_options,
    rss_dict,
    sabnzbd_client,
    sudo_users,
)
from ..helper.ext_utils.bot_utils import cmd_exec, derive_service_password
from ..helper.ext_utils.deprecations import Deprecations
from ..helper.ext_utils.db_handler import database
from .config_manager import Config, BinConfig
from .tg_client import TgClient, db_partition_id
from .torrent_manager import TorrentManager


def _qbit_password():
    return derive_service_password(
        (Config.BOT_TOKEN or "").split(":", 1)[0] or "0",
        "qbit",
    )


async def update_qb_options():
    LOGGER.info("Get qBittorrent options from server")
    pwd = _qbit_password()
    if not qbit_options:
        if not TorrentManager.qbittorrent:
            LOGGER.warning(
                "qBittorrent is not initialized. Skipping qBittorrent options update."
            )
            return
        opt = await TorrentManager.qbittorrent.app.preferences()
        qbit_options.update(opt)
        del qbit_options["listen_port"]
        for k in list(qbit_options.keys()):
            if k.startswith("rss"):
                del qbit_options[k]
        qbit_options["web_ui_password"] = pwd
        await TorrentManager.qbittorrent.app.set_preferences({"web_ui_password": pwd})
        await TorrentManager._auth_qbit()
    else:
        if qbit_options.get("web_ui_password") in ("admin", "admin1", ""):
            qbit_options["web_ui_password"] = pwd
        await TorrentManager.qbittorrent.app.set_preferences(qbit_options)
        await TorrentManager._auth_qbit()


async def update_aria2_options():
    if not TorrentManager.aria2:
        LOGGER.warning("aria2 is not initialized. Skipping aria2 options update.")
        return
    LOGGER.info("Get aria2 options from server")
    if not aria2_options:
        op = await TorrentManager.aria2.getGlobalOption()
        aria2_options.update(op)
    else:
        await TorrentManager.aria2.changeGlobalOption(aria2_options)


async def update_nzb_options():
    if Config.DISABLE_NZB or not Config.USENET_SERVERS:
        return
    LOGGER.info("Get SABnzbd options from server")
    retries = 10
    for i in range(retries):
        try:
            no = (await sabnzbd_client.get_config())["config"]["misc"]
            nzb_options.update(no)
            break
        except Exception as e:
            if i == retries - 1:
                LOGGER.error(
                    f"Failed to get SABnzbd options after {retries} retries: {e}"
                )
                return
            LOGGER.warning(f"SABnzbd not ready, retrying ({i + 1}/{retries}): {e}")
            await sleep(2)


async def load_settings():
    if not Config.DATABASE_URL:
        return
    for p in ["thumbnails", "tokens", "rclone"]:
        if await aiopath.exists(p):
            await rmtree(p, ignore_errors=True)
    await database.connect()
    if database.db is not None:
        if TgClient.PARTITION:
            PART = str(TgClient.PARTITION)
        else:
            BOT_ID = Config.BOT_TOKEN.split(":", 1)[0]
            PART = db_partition_id(BOT_ID)
            TgClient.PARTITION = PART
        deploy_filter = {"_id": PART}
        try:
            settings = import_module("config")
            config_file = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in vars(settings).items()
                if not key.startswith("__")
            }
        except ModuleNotFoundError:
            config_file = {}
        config_file.update(
            {
                key: value.strip() if isinstance(value, str) else value
                for key, value in environ.items()
                if key in var_list
            }
        )

        old_config = await database.db.settings.deployConfig.find_one(
            deploy_filter, {"_id": 0}
        )

        results = await gather(
            database.db.settings.config.find_one(deploy_filter, {"_id": 0}),
            database.db.settings.files.find_one(deploy_filter, {"_id": 0}),
            database.db.settings.aria2c.find_one(deploy_filter, {"_id": 0}),
            database.db.settings.qbittorrent.find_one(deploy_filter, {"_id": 0})
            if not Config.DISABLE_TORRENTS
            else sleep(0),
            database.db.settings.nzb.find_one(deploy_filter, {"_id": 0}),
            database.db.users[PART].find_one(),
            database.db.rss[PART].find_one(),
        )

        (
            config_dict,
            pf_dict,
            a2c_options,
            qbit_opt,
            nzb_opt,
            user_exists,
            rss_exists,
        ) = results

        if old_config is None:
            await database.db.settings.deployConfig.replace_one(
                deploy_filter, config_file, upsert=True
            )
            config_dict = config_dict or {}
            for k, v in config_file.items():
                if v is not None:
                    config_dict.setdefault(k, v)
        elif old_config != config_file:
            LOGGER.info(
                "Updating.. Deploy Config changed, merging new config.py values"
            )
            config_dict = config_dict or {}
            for k, v in config_file.items():
                if k not in old_config or old_config.get(k) != v:
                    if v is not None:
                        config_dict[k] = v
            await database.db.settings.deployConfig.replace_one(
                deploy_filter, config_file, upsert=True
            )
        else:
            LOGGER.info("Updating.. Saved Config imported from MongoDB")
            config_dict = config_dict or {}

        if config_dict:
            Config.load_dict(config_dict)

        if pf_dict:
            for key, value in pf_dict.items():
                if value:
                    file_ = key.replace("__", ".")
                    async with aiopen(file_, "wb+") as f:
                        await f.write(value)

        if a2c_options:
            aria2_options.update(a2c_options)

        if qbit_opt:
            qbit_options.update(qbit_opt)

        if nzb_opt:
            if await aiopath.exists("configs/sabnzbd/SABnzbd.ini.bak"):
                await remove("configs/sabnzbd/SABnzbd.ini.bak")
            for key, value in nzb_opt.items():
                if value:
                    file_ = key.replace("__", ".")
                    async with aiopen(f"configs/sabnzbd/{file_}", "wb+") as f:
                        await f.write(value)
            LOGGER.info("Loaded.. Sabnzbd Data from MongoDB")

        if user_exists:
            migrated = []
            rows = database.db.users[PART].find({})
            async for row in rows:
                uid = row["_id"]
                del row["_id"]
                paths = {
                    "THUMBNAIL": f"thumbnails/{uid}.jpg",
                    "RCLONE_CONFIG": f"rclone/{uid}.conf",
                    "TOKEN_PICKLE": f"tokens/{uid}.pickle",
                    "USER_COOKIE_FILE": f"cookies/{uid}/cookies.txt",
                }

                async def save_file(file_path, content):
                    dir_path = ospath.dirname(file_path)
                    if not await aiopath.exists(dir_path):
                        await makedirs(dir_path)
                    if file_path.startswith("cookies/") and file_path.endswith(".txt"):
                        async with aiopen(file_path, "wb") as f:
                            if isinstance(content, str):
                                content = content.encode("utf-8")
                            await f.write(content)
                    else:
                        async with aiopen(file_path, "wb+") as f:
                            if isinstance(content, str):
                                content = content.encode("utf-8")
                            await f.write(content)

                for key, path in paths.items():
                    if row.get(key):
                        await save_file(path, row[key])
                        row[key] = path
                if dead := Deprecations.migrate_user(row):
                    migrated.append((uid, dead))
                user_data[uid] = row
            LOGGER.info("Users Data has been imported from MongoDB")
            for uid, dead in migrated:
                await database.update_user_data(uid)
                for key in dead:
                    await database.update_user_doc(uid, key)
            if migrated:
                LOGGER.info(
                    f"Cleared deprecated settings for {len(migrated)} user(s)"
                )

        if rss_exists:
            rows = database.db.rss[PART].find({})
            async for row in rows:
                user_id = row["_id"]
                del row["_id"]
                rss_dict[user_id] = row
            LOGGER.info("RSS data has been imported from MongoDB")


async def save_settings():
    if database.db is None:
        return
    config_file = Config.get_all()
    if TgClient.PARTITION:
        PART = str(TgClient.PARTITION)
    else:
        PART = db_partition_id(TgClient.ID)
        TgClient.PARTITION = PART
    deploy_filter = {"_id": PART}
    await database.db.settings.config.update_one(
        deploy_filter, {"$set": config_file}, upsert=True
    )
    if await database.db.settings.aria2c.find_one(deploy_filter) is None:
        await database.db.settings.aria2c.update_one(
            deploy_filter, {"$set": aria2_options}, upsert=True
        )
    if await database.db.settings.qbittorrent.find_one(deploy_filter) is None:
        await database.save_qbit_settings()
    if await database.db.settings.nzb.find_one(deploy_filter) is None:
        async with aiopen("configs/sabnzbd/SABnzbd.ini", "rb+") as pf:
            nzb_conf = await pf.read()
        await database.db.settings.nzb.update_one(
            deploy_filter, {"$set": {"SABnzbd__ini": nzb_conf}}, upsert=True
        )


async def update_variables():
    if (
        Config.LEECH_SPLIT_SIZE > TgClient.MAX_SPLIT_SIZE
        or Config.LEECH_SPLIT_SIZE == 2097152000
        or not Config.LEECH_SPLIT_SIZE
    ):
        Config.LEECH_SPLIT_SIZE = TgClient.MAX_SPLIT_SIZE

    if Config.AUTHORIZED_CHATS:
        aid = Config.AUTHORIZED_CHATS.split()
        for id_ in aid:
            chat_id, *thread_ids = id_.split("|")
            chat_id = int(chat_id.strip())
            if thread_ids:
                thread_ids = list(map(lambda x: int(x.strip()), thread_ids))
                auth_chats[chat_id] = thread_ids
            else:
                auth_chats[chat_id] = []

    if Config.SUDO_USERS:
        aid = Config.SUDO_USERS.split()
        for id_ in aid:
            sudo_users.append(int(id_.strip()))

    if Config.EXCLUDED_EXTENSIONS:
        fx = Config.EXCLUDED_EXTENSIONS.split()
        for x in fx:
            x = x.lstrip(".")
            excluded_extensions.append(x.strip().lower())

    if Config.GDRIVE_ID:
        drives_names.append("Main")
        drives_ids.append(Config.GDRIVE_ID)
        index_urls.append(Config.INDEX_URL)
        list_drives_dict["Main"] = {
            "drive_id": Config.GDRIVE_ID,
            "index_link": Config.INDEX_URL,
        }
        categories_dict["Root"] = {
            "drive_id": Config.GDRIVE_ID,
            "index_link": Config.INDEX_URL,
        }

    if await aiopath.exists("list_drives.txt"):
        async with aiopen("list_drives.txt", "r+") as f:
            lines = await f.readlines()
            for line in lines:
                temp = line.split()
                drives_ids.append(temp[1])
                drives_names.append(temp[0].replace("_", " "))
                if len(temp) > 2:
                    index_urls.append(temp[2])
                else:
                    index_urls.append("")

                sep = 2 if temp[-1].startswith("http") else 1
                tmp = line.strip().rsplit(maxsplit=sep)
                name = "Main Custom" if tmp[0].casefold() == "Main" else tmp[0]
                list_drives_dict[name] = {
                    "drive_id": tmp[1],
                    "index_link": (tmp[2] if sep == 2 else ""),
                }

    if await aiopath.exists("shortener.txt"):
        async with aiopen("shortener.txt", "r+") as f:
            lines = await f.readlines()
            for line in lines:
                temp = line.strip().split()
                if len(temp) == 2:
                    shortener_dict[temp[0]] = temp[1]

    if await aiopath.exists("categories.txt"):
        async with aiopen("categories.txt", "r+") as f:
            lines = await f.readlines()
            for line in lines:
                sep = 2 if line.strip().split()[-1].startswith("http") else 1
                temp = line.strip().rsplit(maxsplit=sep)
                name = "Root Custom" if temp[0].casefold() == "Root" else temp[0]
                categories_dict[name] = {
                    "drive_id": temp[1],
                    "index_link": (temp[2] if sep == 2 else ""),
                }


_ARIA2_PROCESS = None


async def _start_aria2_windows():
    """Start aria2c with the RPC options the bot relies on (no setpkgs.sh on Windows)."""
    global _ARIA2_PROCESS
    binary = BinConfig.ARIA2_NAME
    if not (ospath.isfile(binary) or which(binary)):
        LOGGER.warning(
            "aria2c not found; torrent and aria2 RPC downloads are disabled. "
            "Install aria2 and set ARIA2C_BIN to enable them."
        )
        return
    await makedirs("downloads", exist_ok=True)
    args = [
        binary,
        "--enable-rpc=true",
        "--rpc-listen-all=true",
        "--rpc-listen-port=6800",
        "--rpc-max-request-size=1024M",
        "--max-connection-per-server=10",
        "--max-concurrent-downloads=1000",
        "--split=10",
        "--min-split-size=10M",
        "--seed-ratio=0",
        "--continue=true",
        "--check-integrity=true",
        "--check-certificate=false",
        "--auto-file-renaming=true",
        "--allow-overwrite=true",
        "--bt-remove-unselected-file=true",
        "--dir=downloads",
        "--summary-interval=0",
    ]
    try:
        _ARIA2_PROCESS = await create_subprocess_exec(
            *args, stdout=DEVNULL, stderr=DEVNULL
        )
        LOGGER.info("aria2c started on port 6800")
    except Exception as exc:
        LOGGER.warning(f"Could not start aria2c: {exc}")


async def load_configurations():
    if not await aiopath.exists(".netrc"):
        async with aiopen(".netrc", "w"):
            pass

    try:
        home_netrc = ospath.expanduser("~/.netrc")
        if not ospath.exists(home_netrc):
            async with aiopen(home_netrc, "w"):
                pass
            await cmd_exec(["chmod", "600", home_netrc])
    except Exception:  # noqa: BLE001
        pass

    if os_name == "nt":
        await _start_aria2_windows()
    else:
        from .cpu import service_cores

        shell_bin = _which("bash") or "sh"
        cmd = (
            f'chmod 600 .netrc; {shell_bin} setpkgs.sh {BinConfig.ARIA2_NAME} '
            f'"{service_cores()}" {Config.CPU_LIMIT}'
        )
        if not Config.DISABLE_NZB:
            cmd += f" {BinConfig.SABNZBD_NAME}"
        await (await create_subprocess_shell(cmd)).wait()

    if await aiopath.exists("cfg.zip"):
        if await aiopath.exists("/JDownloader/cfg"):
            await rmtree("/JDownloader/cfg", ignore_errors=True)
        await cmd_exec(["7z", "x", "cfg.zip", "-o/JDownloader"])

    if await aiopath.exists("accounts.zip"):
        if await aiopath.exists("accounts"):
            await rmtree("accounts", ignore_errors=True)
        await cmd_exec(["7z", "x", "-o.", "-aoa", "accounts.zip", "accounts/*.json"])
        if os_name != "nt":
            await cmd_exec(["chmod", "-R", "777", "accounts"])
        await remove("accounts.zip")

    if not await aiopath.exists("accounts"):
        Config.USE_SERVICE_ACCOUNTS = False

    await TorrentManager.initiate()

    if Config.DISABLE_TORRENTS or not TorrentManager.qbittorrent:
        LOGGER.info("Torrents are disabled. Skipping qBittorrent initialization.")
    else:
        try:
            await TorrentManager.qbittorrent.app.set_preferences(qbit_options)
        except Exception as e:
            LOGGER.error(f"Failed to configure qBittorrent: {e}")
        await TorrentManager._auth_qbit()

    PORT = getenv("PORT", "") or "8080"
    if PORT:
        access_pwd = getenv("WEB_ACCESS_PASSWORD", "") or Config.WEB_ACCESS_PASSWORD
        if not access_pwd:
            from secrets import token_bytes

            access_pwd = token_bytes(32).hex()
            Config.WEB_ACCESS_PASSWORD = access_pwd
        environ["WEB_ACCESS_PASSWORD"] = access_pwd
        environ["PORT"] = str(PORT)
        bot_loop.create_task(cmd_exec(
            [
                python_exe,
                "-m",
                "uvicorn",
                "web.wserver:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ]
        ))
        bot_loop.create_task(cmd_exec([python_exe, "cron_boot.py"]))

    if Config.DISABLE_STREAM:
        LOGGER.info("Streaming is disabled. Skipping stream server.")
    else:
        from .stream_server import spawn_stream_server

        spawn_stream_server()

    from ..helper.ext_utils.tunnel_monitor import apply_tunnel_url_once

    await apply_tunnel_url_once()
