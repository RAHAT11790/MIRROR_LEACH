# ============================================================
# RS MIRROR LEECH BOT — CONFIGURATION
# Every setting the bot reads lives in this file.
# Edit the values below, then start the bot with:  python main.py
# Environment variables with the same name override this file.
# ============================================================


# ============================================================
# REQUIRED — CORE
# ============================================================

BOT_TOKEN = "8963100948:AAFUSKmosVS_eochlzcJqhKrN3ga1oohq-E"
# Telegram -> @BotFather -> /newbot -> copy the token.

OWNER_ID = 6621572366
# Telegram -> @userinfobot -> /start -> copy the numeric ID.

TELEGRAM_API = 25976192
# https://my.telegram.org -> API development tools -> api_id

TELEGRAM_HASH = "8ba23141980539b4896e5adbc4ffd2e2"
# https://my.telegram.org -> API development tools -> api_hash

DATABASE_URL = "mongodb+srv://RAHAT1132:RAHAT11a@rahat.txn4lkk.mongodb.net/?appName=Rahat"
# MongoDB URI. Leave "" to run without a database (settings reset on restart).
# IMPORTANT: keep these credentials private and rotate them if shared.


# ============================================================
# GENERAL
# ============================================================

DEFAULT_LANG = "en"            # available: en, bn
TG_PROXY = None                # e.g. {"scheme": "socks5", "hostname": "127.0.0.1", "port": 1080, "username": "", "password": ""}
USER_SESSION_STRING = ""       # optional user session (premium features)
USER_SESSION_KEY_TTL = 43200
USER_SESSION_IDLE = 600
USER_SESSION_MAX_CLIENTS = 8
CMD_SUFFIX = ""                # e.g. "rs" -> /mirrors
AUTHORIZED_CHATS = "-1004366562744"   # space separated chat/user IDs allowed to use the bot
SUDO_USERS = "6621572366"      # space separated user IDs with sudo access
STATUS_LIMIT = 10              # tasks shown in /status
STATUS_UPDATE_INTERVAL = 15    # seconds
DEFAULT_UPLOAD = "rc"          # "rc" (rclone) or "gd" (Google Drive)
BOT_MAX_TASKS = 5
USER_MAX_TASKS = 5
USER_TIME_INTERVAL = 30
VERIFY_TIMEOUT = 30            # shortlink verification window (0 = disabled)
LOGIN_PASS = "RS"              # /login password ("" = login disabled)
TIMEZONE = "Asia/Dhaka"
BOT_PM = False
SET_COMMANDS = True
DELETE_LINKS = False
MEDIA_STORE = True
BASE_URL = ""                  # public URL of this host, e.g. https://mybot.example.com
WEB_ACCESS_PASSWORD = ""       # extra secret for the web UI (auto-generated when empty)
WEB_PINCODE = True
ENABLE_TELEMETRY = False       # crash/telemetry reporting
INC_TASK_NOTIFY = False
INC_TASK_RESUME = False


# ============================================================
# BRANDING
# ============================================================

AUTHOR_NAME = "RS Mirror Leech Bot"
AUTHOR_URL = "https://rsanime03.lovable.app/"
GD_DESP = "Uploaded with RS Mirror Leech Bot"
YT_DESP = "Uploaded with RS Mirror Leech Bot"
UPSTREAM_REPO = ""             # optional auto-update source
UPSTREAM_BRANCH = "main"


# ============================================================
# LOG CHANNELS
# ============================================================

LOG_CHANNEL = "-1004396221478"               # numeric channel ID for mirror/leech logs
LOG_GROUP = "-1004396221478"                 # numeric group ID for link logs
MIRROR_LOG_ID = "-1004396221478"             # overrides LOG_CHANNEL for mirror logs
LEECH_LOG_CHAT = "-1004396221478"            # overrides LOG_CHANNEL for leech logs
LINKS_LOG_ID = "-1004396221478"              # overrides LOG_GROUP for link logs
LEECH_DUMP_CHATS = {}          # {"name": chat_id, ...} clone/leech destinations


# ============================================================
# FEATURE SWITCHES (True = disabled)
# ============================================================

DISABLE_TORRENTS = False
DISABLE_LEECH = False
DISABLE_MIRROR = False
DISABLE_BULK = False
DISABLE_MULTI = False
DISABLE_SEED = False
DISABLE_FF_MODE = False
DISABLE_JD = False
DISABLE_NZB = False
DISABLE_SEEDR = False
DISABLE_RSS = False
DISABLE_SEARCH = False
DISABLE_STREAM = False
DISABLE_YTDLP = False
DISABLE_MEGA = False
DISABLE_PLUGINS = True


# ============================================================
# TASK LIMITS (0 = unlimited)
# ============================================================

DIRECT_LIMIT = 0
MEGA_LIMIT = 0
TORRENT_LIMIT = 0
GD_DL_LIMIT = 0
RC_DL_LIMIT = 0
CLONE_LIMIT = 0
JD_LIMIT = 0
NZB_LIMIT = 0
SEEDR_LIMIT = 0
YTDLP_LIMIT = 0
PLAYLIST_LIMIT = 0
LEECH_LIMIT = 0
EXTRACT_LIMIT = 0
ARCHIVE_LIMIT = 0
STORAGE_LIMIT = 0
CLONE_TG_LIMIT = 10000         # messages per telegram clone (0 = no limit)


# ============================================================
# CPU / FFMPEG / MEMORY
# ============================================================

CPU_LIMIT = 20
FFMPEG_CORES = "auto"
THROTTLE_SERVICES = "auto"
MEM_BUDGET = 0
MEM_DEEP_STATS = False


# ============================================================
# HYPER DOWNLOADER / STREAM PIPELINE
# ============================================================

USE_HYPER = True
HELPER_TOKENS = ""             # comma separated helper bot tokens
HELPER_STRINGS = ""            # comma separated helper user sessions
STREAM_TOKENS = ""             # comma separated stream bot tokens
HELPER_BOT_PROXIES = ""
HELPER_USER_PROXIES = ""
HYPER_THREADS = 0
HYPER_PIPELINE = 4
HYPER_CHUNK = 524288
STREAM_PIPELINE = 8
STREAM_CHUNK = 1048576
STREAM_PER_CLIENT = 6
STREAM_GATE = 96


# ============================================================
# MEGA
# ============================================================

MEGA_EMAIL = ""
MEGA_PASSWORD = ""


# ============================================================
# GOOGLE DRIVE
# ============================================================

GDRIVE_ID = ""                 # destination folder ID
IS_TEAM_DRIVE = False
STOP_DUPLICATE = False
INDEX_URL = ""
USE_SERVICE_ACCOUNTS = False
DRIVE_CATEGORY_MODE = False
DRIVE_CATEGORY_SA = ""


# ============================================================
# RCLONE
# ============================================================

RCLONE_PATH = ""               # e.g. "remote:folder"
RCLONE_FLAGS = ""
RCLONE_SERVE_URL = ""
RCLONE_SERVE_PORT = 8081
RCLONE_SERVE_USER = ""
RCLONE_SERVE_PASS = ""
SHOW_CLOUD_LINK = True


# ============================================================
# LEECH
# ============================================================

LEECH_SPLIT_SIZE = 0           # 0 = automatic (Telegram premium limit)
AS_DOCUMENT = False
EQUAL_SPLITS = False
MEDIA_GROUP = False
TRANSMISSION_MODE = "both"     # "leech", "mirror" or "both"
LEECH_PREFIX = ""
LEECH_SUFFIX = ""
LEECH_CAPTION = ""
LEECH_FONT = ""
THUMBNAIL_LAYOUT = ""
AUTO_THUMBNAIL = True
TMDB_ACCESS_TOKEN = ""
# TMDb v3 API key (used LAST, only when IMDb/AniList/Jikan/Kitsu/TVmaze found nothing)
TMDB_API_KEY = "37f4b185e3dc487e4fd3e56e2fab2307"
# Thumbnail sources in order (tmdb is always tried last)
THUMBNAIL_PROVIDERS = "imdb,anilist,jikan,kitsu,tvmaze,tmdb"


# ============================================================
# TORRENT / ARIA2 / QUEUE
# ============================================================

TORRENT_TIMEOUT = 0
QUEUE_ALL = 0
QUEUE_DOWNLOAD = 0
QUEUE_UPLOAD = 0
EXCLUDED_EXTENSIONS = ""


# ============================================================
# JDOWNLOADER
# ============================================================

JD_EMAIL = ""
JD_PASS = ""


# ============================================================
# SABNZBD / USENET
# ============================================================

USENET_SERVERS = [
    {
        "name": "main",
        "host": "",
        "port": 563,
        "timeout": 60,
        "username": "",
        "password": "",
        "connections": 8,
        "ssl": 1,
        "ssl_verify": 2,
        "ssl_ciphers": "",
        "enable": 1,
        "required": 0,
        "optional": 0,
        "retention": 0,
        "send_group": 0,
        "priority": 0,
    }
]


# ============================================================
# RSS
# ============================================================

RSS_CHAT = ""
RSS_DELAY = 600
RSS_SIZE_LIMIT = 0


# ============================================================
# SEARCH
# ============================================================

SEARCH_API_LINK = ""
SEARCH_LIMIT = 0
SEARCH_PLUGINS = [
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/piratebay.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/limetorrents.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torlock.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/torrentscsv.py",
    "https://raw.githubusercontent.com/qbittorrent/search-plugins/master/nova3/engines/eztv.py",
    "https://raw.githubusercontent.com/MaurizioRicci/qBittorrent_search_engines/master/kickass_torrent.py",
    "https://raw.githubusercontent.com/MaurizioRicci/qBittorrent_search_engines/master/yts_am.py",
    "https://raw.githubusercontent.com/MadeOfMagicAndWires/qBit-plugins/master/engines/linuxtracker.py",
    "https://raw.githubusercontent.com/MadeOfMagicAndWires/qBit-plugins/master/engines/nyaasi.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/ettv.py",
    "https://raw.githubusercontent.com/LightDestory/qBittorrent-Search-Plugins/master/src/engines/glotorrents.py",
    "https://raw.githubusercontent.com/LightDestory/1337x-qBittorrent-search-plugin/master/leetx.py",
    "https://raw.githubusercontent.com/nindogo/qbtSearchScripts/master/magnetdl.py",
    "https://raw.githubusercontent.com/msagca/qbtSearchScripts/main/uniondht.py",
    "https://raw.githubusercontent.com/khensolomon/leyts/master/yts.py",
]
HYDRA_IP = ""
HYDRA_API_KEY = ""


# ============================================================
# IMAGES
# ============================================================

USE_IMAGES = False
IMAGES = []
IMG_SEARCH = ""
IMG_PAGE = 1
IMG_SOURCES = ["wallpaperflare"]


# ============================================================
# EXTERNAL APIS / UPLOAD HOSTS
# ============================================================

FILELION_API = ""
STREAMWISH_API = ""
ALLDEBRID_API_KEY = ""
ALLDEBRID_NO_SEED_TIMEOUT = 180
DEBRID_LINK_API = ""
INSTADL_API = ""
GOFILE_API = ""
GOFILE_FOLDER_ID = ""
GOFILE_AUTO_CREATE_FOLDER = False
PIXELDRAIN_KEY = ""
PROTECTED_API = ""
BUZZHEAVIER_API = ""
DEVUPLOADS_KEY = ""
DEVUPLOADS_FOLDER = ""
VIKINGFILE_HASH = ""
VIKINGFILE_FOLDER = ""
SEEDR_EMAIL = ""
SEEDR_PASSWORD = ""
SEEDR_DELETE_FOLDER = False
IMDB_TEMPLATE = ""
NAME_SWAP = ""
FFMPEG_CMDS = {}
UPLOAD_PATHS = {}
YT_DLP_OPTIONS = {}
FORCE_SUB_IDS = ""


# ============================================================
# CLONE FILTERS
# ============================================================

CLONE_CONTENT_TYPE = "all"     # "all", "doc" or "med"
CLONE_EXCLUDED_EXTENSIONS = ""
CLONE_FILTERS = {}
CLONE_DUMP_CHATS = {}


# ============================================================
# PLUGINS
# ============================================================

PLUGIN_INDEXES = []


# ============================================================
# YOUTUBE
# ============================================================

YT_TAGS = ["telegram", "bot", "youtube"]
YT_CATEGORY_ID = 22
YT_PRIVACY_STATUS = "unlisted"


# ============================================================
# SHORTCUTS — fill LOG_CHANNEL / LOG_GROUP above if you prefer
# one place for both mirror and leech logs.
# ============================================================

if LOG_CHANNEL:
    MIRROR_LOG_ID = MIRROR_LOG_ID or LOG_CHANNEL
    LEECH_LOG_CHAT = LEECH_LOG_CHAT or LOG_CHANNEL

if LOG_GROUP:
    LINKS_LOG_ID = LINKS_LOG_ID or LOG_GROUP

