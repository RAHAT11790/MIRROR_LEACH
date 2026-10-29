"""Optional Mega SDK wrapper.

``mega.py`` 1.0.8 pins ``tenacity<6``, which conflicts with
``google-api-core`` (needs ``tenacity>=6.6``). Mega therefore stays optional:
when a compatible package is installed it is used normally, otherwise the
placeholders below keep the bot importable and Mega actions raise a clear
error instead of crashing at startup.

To enable Mega (for example with a patched fork):
    pip install mega.py --no-deps
"""

try:
    from mega import (
        MegaApi,
        MegaCancelToken,
        MegaError,
        MegaListener,
        MegaRequest,
        MegaTransfer,
        MegaUploadOptions,
    )

    MEGA_AVAILABLE = True
except Exception:  # pragma: no cover - depends on optional dependency
    MEGA_AVAILABLE = False

    class MegaApi:
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "Mega support is not installed. Run: pip install mega.py --no-deps"
            )

    class MegaCancelToken:
        def __init__(self, *args, **kwargs):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

        def isCancelled(self):
            return self.cancelled

    class MegaListener:
        def __init__(self, *args, **kwargs):
            pass

    class MegaError(Exception):
        API_OK = 0

    class MegaRequest:
        TYPE_ACCOUNT_DETAILS = 0

    class MegaTransfer:
        pass

    class MegaUploadOptions:
        pass
