"""
Ambient awareness — FRIDAY notices what changes around the user.

In the films FRIDAY mentions things as they happen: a device connected,
power lost, a transfer done. Here the computer is watched for the few changes
worth a sentence, each compared against what was there a moment ago:

  * a USB drive / memory card plugged in or taken out (name, size);
  * the charger unplugged or plugged back in (laptops; with the level and,
    unplugged, the time left);
  * the internet lost and back (said when it is back — while it is down there
    is no voice session anyway — with how long it was gone);
  * a download finished in the Downloads folder (a real file, at least 1 MB,
    whose size stopped changing; browsers' partial files ignored).

Each kind can be switched off ('USB takınca söyleme' → awareness off usb).
Everything is read locally; nothing leaves the computer. Announcements go
through the same channel as plugins' speech, so they wait for the user to be
back when nobody is at the desk (core/away.py).
"""
from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

KINDS = ("usb", "power", "network", "downloads")
PARTIAL = (".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload", ".!ut")
MIN_DOWNLOAD = 1 << 20
NET_CONFIRM = 2                 # this many checks in a row before a change counts
NET_MIN_DOWN = 20               # shorter outages are not worth a sentence


def settings() -> dict:
    out = {k: True for k in KINDS}
    try:
        from memory.config_manager import get_plugin_config
        cfg = get_plugin_config("awareness") or {}
        out.update({k: bool(cfg[k]) for k in KINDS if k in cfg})
    except Exception:
        pass
    return out


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _span(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    m = s // 60
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60} min"


# ── probes (each returns plain data; the diffing below is pure) ───────────────

def removable_drives() -> dict[str, dict]:
    """{mountpoint: {"label", "total"}} for removable drives."""
    out: dict[str, dict] = {}
    try:
        import psutil
        for p in psutil.disk_partitions(all=False):
            removable = ("removable" in (p.opts or "").lower()
                         or str(p.mountpoint).startswith(("/media/", "/run/media/", "/Volumes/")))
            if not removable:
                continue
            try:
                total = psutil.disk_usage(p.mountpoint).total
            except Exception:
                continue          # an empty card reader slot
            out[p.mountpoint] = {"label": _label(p.mountpoint), "total": total}
    except Exception:
        pass
    return out


def _label(mount: str) -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(261)
            if ctypes.windll.kernel32.GetVolumeInformationW(mount, buf, 261, None, None, None, None, 0):
                return buf.value or mount
        except Exception:
            pass
        return mount
    return os.path.basename(mount.rstrip("/")) or mount


def power() -> dict | None:
    try:
        import psutil
        b = psutil.sensors_battery()
    except Exception:
        return None
    if b is None:
        return None
    return {"plugged": bool(b.power_plugged), "percent": float(b.percent), "secsleft": b.secsleft}


def online(timeout: float = 2.0) -> bool:
    for host in (("1.1.1.1", 53), ("8.8.8.8", 53)):
        try:
            with socket.create_connection(host, timeout=timeout):
                return True
        except OSError:
            continue
    return False


def downloads_dir() -> Path | None:
    home = Path.home()
    for name in ("Downloads", "İndirilenler"):
        if (home / name).is_dir():
            return home / name
    return None


def download_listing(folder: Path | None) -> dict[str, int]:
    out: dict[str, int] = {}
    if not folder:
        return out
    try:
        with os.scandir(folder) as it:
            for e in it:
                try:
                    if e.is_file():
                        out[e.name] = e.stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return out


# ── diffing ───────────────────────────────────────────────────────────────────

# ── what just happened, for "az önce indirdiğim dosyayı aç" ───────────────────

RECENT_PATH = Path(__file__).resolve().parent.parent / "memory" / "recent_events.json"
RECENT_MAX = 25


def remember(kind: str, text: str, path: str = "") -> None:
    """Keep a happening with its path, so a later 'that file' / 'the USB' can be resolved."""
    import json
    try:
        items = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            items = []
    except Exception:
        items = []
    items.append({"at": time.time(), "kind": kind, "text": text, "path": path})
    try:
        RECENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECENT_PATH.write_text(json.dumps(items[-RECENT_MAX:], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def recent(kind: str = "", limit: int = 8) -> list[dict]:
    import json
    try:
        items = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(items, list):
        return []
    items = [i for i in items if isinstance(i, dict) and (not kind or i.get("kind") == kind)]
    return items[-limit:][::-1]


def diff_drives(before: dict, after: dict) -> list[str]:
    notes = []
    for m in after.keys() - before.keys():
        d = after[m]
        notes.append(f"A removable drive was plugged in: {d['label']} ({_size(d['total'])}, at {m}).")
        remember("usb", f"{d['label']} plugged in", m)
    for m in before.keys() - after.keys():
        notes.append(f"The removable drive {before[m]['label']} was taken out.")
    return notes


def diff_power(before: dict | None, after: dict | None) -> list[str]:
    if not before or not after or before["plugged"] == after["plugged"]:
        return []
    pct = round(after["percent"])
    if after["plugged"]:
        return [f"The charger was plugged in; battery at {pct}%."]
    left = after.get("secsleft")
    tail = (f", about {_span(left)} left" if isinstance(left, (int, float)) and 0 < left < 48 * 3600 else "")
    return [f"The charger was unplugged; running on battery at {pct}%{tail}."]


class NetWatch:
    """Online/offline with confirmation, so one lost packet is not an outage."""

    def __init__(self):
        self.state: bool | None = None
        self.pending: bool | None = None
        self.count = 0
        self.down_since: float | None = None

    def feed(self, is_online: bool, now: float) -> list[str]:
        if self.state is None:
            self.state = is_online
            return []
        if is_online == self.state:
            self.pending, self.count = None, 0
            return []
        if self.pending != is_online:
            self.pending, self.count = is_online, 0
        self.count += 1
        if self.count < NET_CONFIRM:
            return []
        self.state, self.pending, self.count = is_online, None, 0
        if not is_online:
            self.down_since = now
            return []                       # nobody to tell: the voice session is down too
        gone = now - (self.down_since or now)
        self.down_since = None
        return [f"The internet connection is back; it was down for about {_span(gone)}."] \
            if gone >= NET_MIN_DOWN else []


class DownloadWatch:
    """A new file that stopped growing: a finished download."""

    def __init__(self, listing: dict[str, int], folder: Path | None = None):
        self.folder = folder
        self.known = set(listing)
        self.growing: dict[str, int] = {}

    def feed(self, listing: dict[str, int]) -> list[str]:
        notes = []
        for name, size in listing.items():
            if name in self.known:
                continue
            if name.lower().endswith(PARTIAL) or name.startswith((".", "~$")):
                continue
            if self.growing.get(name) == size:
                self.known.add(name)
                self.growing.pop(name, None)
                if size >= MIN_DOWNLOAD:
                    full = str(self.folder / name) if self.folder else name
                    notes.append(f"A download finished: {name} ({_size(size)}) at {full}.")
                    remember("download", f"{name} ({_size(size)})", full)
            else:
                self.growing[name] = size
        for name in list(self.growing):
            if name not in listing:
                self.growing.pop(name)
        return notes


class Sentinel:
    """Holds the last view of everything; tick() returns what changed since."""

    def __init__(self):
        self.drives = removable_drives()
        self.power = power()
        self.net = NetWatch()
        self.folder = downloads_dir()
        self.downloads = DownloadWatch(download_listing(self.folder), self.folder)

    def tick(self, now: float | None = None, cfg: dict | None = None) -> list[str]:
        now = time.monotonic() if now is None else now
        cfg = cfg or settings()
        notes: list[str] = []
        drives = removable_drives()
        if cfg.get("usb", True):
            notes += diff_drives(self.drives, drives)
        self.drives = drives
        pw = power()
        if cfg.get("power", True):
            notes += diff_power(self.power, pw)
        self.power = pw
        net = self.net.feed(online(), now)
        if cfg.get("network", True):
            notes += net
        found = self.downloads.feed(download_listing(self.folder))
        if cfg.get("downloads", True):
            notes += found
        return notes


def instruction(notes: list[str]) -> str:
    return ("[ENVIRONMENT] " + " ".join(notes) + " Mention it the way FRIDAY would — one short "
            "sentence, the useful detail only (e.g. 'USB bellek takıldı, efendim: KINGSTON, 64 GB.'), "
            "offering the obvious next step at most once. Do not call any tool.")
