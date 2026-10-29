from logging import error as logerror
from os import getenv
from time import sleep

from niquests import get as rget

BASE_URL = (getenv("BASE_URL") or "").strip().rstrip("/") or None
PORT = getenv("PORT")

if PORT and BASE_URL:
    while True:
        try:
            rget(BASE_URL).status_code
            sleep(600)
        except Exception as e:
            logerror(f"cron_boot.py: {e}")
            sleep(2)
