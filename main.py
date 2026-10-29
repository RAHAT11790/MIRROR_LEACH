"""Single entry point:  python3 main.py

1. pre-flight: installs every missing Python package + command-line tool (no root needed)
2. starts the bot and keeps it alive: if it crashes it is restarted automatically
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHILD_FLAG = "RS_BOT_CHILD"


def fix_dns(force=False):
    """Termux/containers without /etc/resolv.conf: dnspython (used by pymongo for
    mongodb+srv:// URIs) crashes with 'cannot open /etc/resolv.conf'. Give it a resolver."""
    if not force and os.path.exists("/etc/resolv.conf"):
        return
    try:
        import dns.asyncresolver
        import dns.resolver

        prefix = os.environ.get("PREFIX", "")
        termux_conf = os.path.join(prefix, "etc", "resolv.conf") if prefix else ""
        if termux_conf and os.path.isfile(termux_conf):
            sync, aio = dns.resolver.Resolver(filename=termux_conf), dns.asyncresolver.Resolver(filename=termux_conf)
        else:
            servers = ["8.8.8.8", "1.1.1.1", "8.8.4.4", "1.0.0.1"]
            sync, aio = dns.resolver.Resolver(configure=False), dns.asyncresolver.Resolver(configure=False)
            sync.nameservers = list(servers)
            aio.nameservers = list(servers)
        dns.resolver.default_resolver = sync
        dns.asyncresolver.default_resolver = aio
        print("[main] /etc/resolv.conf not found -> using built-in DNS servers", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[main] DNS fix skipped: {exc}", flush=True)


def fix_android():
    """Android/Termux blocks /proc/stat, /proc/net/dev ... -> psutil raises PermissionError and
    breaks the status message. Replace the blocked calls with harmless fallbacks."""
    try:
        import psutil
    except Exception:  # noqa: BLE001
        return
    from collections import namedtuple

    proc = psutil.Process()
    cpu_tuple = namedtuple("scputimes", "user nice system idle iowait irq softirq steal guest guest_nice")
    net_tuple = namedtuple("snetio", "bytes_sent bytes_recv packets_sent packets_recv errin errout dropin dropout")

    def blocked(name):
        fn = getattr(psutil, name, None)
        if fn is None:
            return False
        try:
            fn()
            return False
        except TypeError:
            return False
        except Exception:  # noqa: BLE001  (PermissionError / OSError / anything else)
            return True

    def cpu_percent(interval=None, percpu=False):
        try:
            value = float(proc.cpu_percent(interval=None))
        except Exception:  # noqa: BLE001
            value = 0.0
        return [value] * (psutil.cpu_count() or 1) if percpu else value

    patches = {
        "cpu_percent": cpu_percent,
        "cpu_times": lambda *a, **k: cpu_tuple(*([0.0] * 10)),
        "boot_time": lambda: proc.create_time(),
        "getloadavg": lambda: (0.0, 0.0, 0.0),
        "net_io_counters": lambda *a, **k: net_tuple(*([0] * 8)),
    }
    for name, fallback in patches.items():
        if blocked(name):
            setattr(psutil, name, fallback)  # direct replacement, never calls the blocked original


def termux_extras():
    """Termux: keep the CPU awake while the bot runs, warn about the noexec shared storage."""
    if "com.termux" not in os.environ.get("PREFIX", ""):
        return
    import shutil

    if shutil.which("termux-wake-lock"):
        try:
            subprocess.run(["termux-wake-lock"], timeout=10, capture_output=True)
        except Exception:  # noqa: BLE001
            pass
    if str(HERE).startswith(("/storage/emulated", "/sdcard", "/storage/self")):
        print(
            "[main] NOTE: the project is on shared storage (/storage/emulated/0): Android blocks "
            "running programs from there. Tools are installed in ~/.rs_bin instead. For best "
            "results move the project: cp -r . ~/RS-Mirror-Leech-Bot && cd ~/RS-Mirror-Leech-Bot",
            flush=True,
        )


def run_bot():
    from runpy import run_module

    fix_dns()
    fix_android()

    run_module("bot", run_name="__main__", alter_sys=True)


PID_FILE = HERE / ".rs_main.pid"
CHILD_PID_FILE = HERE / ".rs_child.pid"


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:  # noqa: BLE001
        return True


def _is_ours(pid):
    """True only if /proc says this PID is a main.py / bot process (avoids PID-reuse accidents)."""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
    except Exception:  # noqa: BLE001
        return False
    return "main.py" in cmd or "-m bot" in cmd


def _read_pid(path):
    try:
        return int(path.read_text().strip())
    except Exception:  # noqa: BLE001
        return 0


def single_instance_guard():
    """Refuse to start twice (two instances = port 8091 in use + every command handled twice);
    kill an orphaned bot process left behind by a previous run."""
    if os.environ.get("RS_ALLOW_MULTI", "").strip().lower() in ("1", "true", "yes"):
        return
    old = _read_pid(PID_FILE)
    if old and old != os.getpid() and _pid_alive(old) and _is_ours(old):
        print(f"[main] another instance is already running (PID {old}). "
              f"Stop it first:  kill {old}   (or: pkill -f main.py)", flush=True)
        raise SystemExit(1)
    orphan = _read_pid(CHILD_PID_FILE)
    if orphan and _pid_alive(orphan) and _is_ours(orphan):
        print(f"[main] stopping leftover bot process {orphan} from a previous run", flush=True)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(orphan, sig)
            except Exception:  # noqa: BLE001
                break
            for _ in range(20):
                if not _pid_alive(orphan):
                    break
                time.sleep(0.25)
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception:  # noqa: BLE001
        pass


def stop_child(p, wait=10):
    if p and p.poll() is None:
        try:
            p.terminate()
            p.wait(timeout=wait)
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass


def supervise(cmd=None, max_quick_crashes=8, sleep=time.sleep):
    """Run the bot in a child process and restart it when it dies unexpectedly."""
    cmd = cmd or [sys.executable, str(HERE / "main.py")]
    env = dict(os.environ, **{CHILD_FLAG: "1"})
    quick_crashes = 0
    child = {"p": None}

    def _forward(signum, _frame):
        stop_child(child["p"])
        for f in (PID_FILE, CHILD_PID_FILE):
            f.unlink(missing_ok=True)
        raise SystemExit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _forward)
        except Exception:  # noqa: BLE001
            pass

    while True:
        started = time.time()
        child["p"] = subprocess.Popen(cmd, cwd=str(HERE), env=env)
        try:
            CHILD_PID_FILE.write_text(str(child["p"].pid))
        except Exception:  # noqa: BLE001
            pass
        try:
            code = child["p"].wait()
        except KeyboardInterrupt:
            stop_child(child["p"])
            return 0
        if code == 0:
            print("[main] bot exited normally", flush=True)
            return 0
        ran = time.time() - started
        quick_crashes = quick_crashes + 1 if ran < 30 else 0
        if quick_crashes >= max_quick_crashes:
            print(
                f"[main] bot crashed {quick_crashes} times in a row right after start "
                f"(exit code {code}). Check the error above, fix it, then run again.",
                flush=True,
            )
            return code or 1
        delay = min(5 * (quick_crashes or 1), 60)
        print(f"[main] bot stopped (exit code {code}); restarting in {delay}s ...", flush=True)
        sleep(delay)


if __name__ == "__main__":
    os.chdir(HERE)
    sys.path.insert(0, str(HERE))
    if os.environ.get(CHILD_FLAG) == "1":
        run_bot()
    else:
        single_instance_guard()
        termux_extras()
        try:
            from rs_setup import ensure_everything

            ensure_everything()
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[setup] pre-flight failed: {exc}", flush=True)
        if os.environ.get("RS_NO_SUPERVISOR", "").strip().lower() in ("1", "true", "yes"):
            run_bot()
        else:
            raise SystemExit(supervise())
