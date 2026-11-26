"""
dashboard/devices.py — who is on the network: this computer, the other
computers running FRIDAY, and the screens (TVs) paired to it.

Every FRIDAY announces itself on the local network once every few seconds with
a small UDP broadcast, and listens for the others. That is all the phone needs
to show one "BAĞLI CİHAZLAR" list and command the laptop as easily as the
desktop: it talks to each computer's own dashboard directly, with a token that
computer issued.

No dependencies beyond the standard library, and nothing here can raise into
the caller: a network without broadcast simply shows this computer alone.
"""

from __future__ import annotations

import json
import platform
import secrets
import socket
import threading
import time
import uuid
from pathlib import Path


def _log(msg: str) -> None:
    """print() that cannot fail (cp1252 consoles, pythonw without a console)."""
    try:
        print(msg)
    except Exception:
        try:
            print(str(msg).encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass

BASE_DIR = Path(__file__).resolve().parent.parent
DISCOVERY_PORT = 8002          # UDP, beside the dashboard's 8000/8001
ANNOUNCE_EVERY = 4.0           # seconds between announcements
PEER_TIMEOUT = 15.0            # a computer not heard for this long is offline
from core.identity import LEGACY_DISCOVERY_MAGIC
_MAGIC = LEGACY_DISCOVERY_MAGIC


# ── this computer ─────────────────────────────────────────────────────────────

def _id_file() -> Path:
    return BASE_DIR / "config" / "device_id"


def device_id() -> str:
    """A stable id for this install, created once."""
    p = _id_file()
    try:
        v = p.read_text(encoding="utf-8").strip()
        if v:
            return v
    except Exception:
        pass
    v = uuid.uuid4().hex[:12]
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v, encoding="utf-8")
    except Exception:
        pass
    return v


def _is_laptop() -> bool:
    try:
        import psutil
        return psutil.sensors_battery() is not None
    except Exception:
        return False


def device_name() -> str:
    """The user's own name for this computer if set, else its host name."""
    try:
        from memory.config_manager import read_config
        cfg = read_config(BASE_DIR / "config" / "api_keys.json")
        name = str(cfg.get("device_name") or "").strip()
        if name:
            return name[:40]
    except Exception:
        pass
    return (platform.node() or "Bilgisayar")[:40]


def os_label() -> str:
    system = platform.system()
    if system == "Windows":
        rel = platform.release()
        return f"Windows {rel}".strip()
    if system == "Darwin":
        return "macOS " + (platform.mac_ver()[0] or "")
    return system or "Linux"


def self_info(url: str) -> dict:
    return {
        "id": device_id(),
        "name": device_name(),
        "os": os_label(),
        "kind": "laptop" if _is_laptop() else "desktop",
        "url": url,
    }


# ── discovery ─────────────────────────────────────────────────────────────────

def encode_announce(info: dict) -> bytes:
    return json.dumps({"m": _MAGIC, **{k: info.get(k) for k in
                                       ("id", "name", "os", "kind", "url")}}).encode("utf-8")


def decode_announce(data: bytes, sender_ip: str = "") -> dict | None:
    """A peer announcement, or None for anything else on the port. The URL a
    peer reports is trusted only for its port: the host is taken from where
    the packet actually came from, so a peer cannot point the phone elsewhere."""
    try:
        msg = json.loads(data.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(msg, dict) or msg.get("m") not in (_MAGIC, "FRIDAY-DEVICE-1"):
        return None
    did = str(msg.get("id") or "")[:32]
    url = str(msg.get("url") or "")
    if not did or not url.startswith(("http://", "https://")):
        return None
    if sender_ip:
        scheme, rest = url.split("://", 1)
        hostport = rest.split("/", 1)[0]
        port = hostport.rsplit(":", 1)[1] if ":" in hostport else ""
        if not port.isdigit():
            return None
        url = f"{scheme}://{sender_ip}:{port}"
    kind = msg.get("kind") if msg.get("kind") in ("desktop", "laptop") else "desktop"
    return {"id": did, "name": str(msg.get("name") or "FRIDAY")[:40],
            "os": str(msg.get("os") or "")[:40], "kind": kind, "url": url}


class Discovery:
    """Announces this computer and keeps the list of the others."""

    def __init__(self, info_fn):
        self._info_fn = info_fn          # () -> self_info dict (url may change)
        self._peers: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        threading.Thread(target=self._listen, daemon=True, name="aether-discovery-rx").start()
        threading.Thread(target=self._announce, daemon=True, name="aether-discovery-tx").start()

    def stop(self) -> None:
        self._stop.set()

    def note(self, peer: dict) -> None:
        if not peer or peer.get("id") == device_id():
            return
        with self._lock:
            self._peers[peer["id"]] = {**peer, "seen": time.time()}

    def peers(self) -> list[dict]:
        now = time.time()
        with self._lock:
            out = []
            for p in self._peers.values():
                q = {k: v for k, v in p.items() if k != "seen"}
                q["online"] = now - p["seen"] < PEER_TIMEOUT
                out.append(q)
        return sorted(out, key=lambda p: (not p["online"], p["name"].casefold()))

    def _announce(self) -> None:
        while not self._stop.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(encode_announce(self._info_fn()), ("255.255.255.255", DISCOVERY_PORT))
                s.close()
            except Exception:
                pass
            self._stop.wait(ANNOUNCE_EVERY)

    def _listen(self) -> None:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
            s.settimeout(1.0)
        except Exception as exc:
            _log(f"[Devices] Discovery off ({exc.__class__.__name__}); only this computer is listed.")
            return
        while not self._stop.is_set():
            try:
                data, (ip, _port) = s.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                time.sleep(1.0)
                continue
            peer = decode_announce(data, ip)
            if peer:
                self.note(peer)


# ── paired screens (TVs) ──────────────────────────────────────────────────────

class ScreenRegistry:
    """TVs and other big screens that show the FRIDAY screen page.

    A TV cannot scan a QR code and typing on a TV remote is miserable, so the
    pairing goes the other way round, as with streaming apps: the TV page asks
    for a code and shows it in large digits, and the already-paired phone
    enters that code. The TV then holds its own token, which can only watch.
    """

    CODE_TTL = 300.0

    def __init__(self):
        self._pending: dict[str, dict] = {}   # code -> {screen_id, ts}
        self._screens: dict[str, dict] = {}   # screen_id -> {name, token, seen, approved}
        self._lock = threading.Lock()

    def hello(self, name: str = "") -> dict:
        """A new screen asks to be paired: returns its id and the code to show."""
        with self._lock:
            now = time.time()
            self._pending = {c: v for c, v in self._pending.items() if now - v["ts"] < self.CODE_TTL}
            code = "".join(secrets.choice("0123456789") for _ in range(6))
            while code in self._pending:
                code = "".join(secrets.choice("0123456789") for _ in range(6))
            sid = "tv-" + secrets.token_hex(5)
            self._pending[code] = {"screen_id": sid, "ts": now}
            self._screens[sid] = {"name": (name or "Televizyon")[:40], "token": "",
                                  "seen": now, "approved": False}
            return {"screen_id": sid, "code": code}

    def approve(self, code: str, name: str = "") -> dict | None:
        code = "".join(ch for ch in str(code) if ch.isdigit())
        with self._lock:
            entry = self._pending.pop(code, None)
            if not entry or time.time() - entry["ts"] >= self.CODE_TTL:
                return None
            sc = self._screens.get(entry["screen_id"])
            if sc is None:
                return None
            sc["approved"] = True
            sc["token"] = secrets.token_urlsafe(24)
            if name.strip():
                sc["name"] = name.strip()[:40]
            return {"screen_id": entry["screen_id"], "name": sc["name"]}

    def add_local(self, name: str = "Bu bilgisayarın ekranı") -> dict:
        """A screen opened on this very computer is trusted without a code."""
        with self._lock:
            sid = "tv-" + secrets.token_hex(5)
            tok = secrets.token_urlsafe(24)
            self._screens[sid] = {"name": name[:40], "token": tok, "seen": time.time(),
                                  "approved": True}
            return {"screen_id": sid, "token": tok}

    def poll(self, screen_id: str) -> dict:
        """What a waiting TV page sees: its token once approved."""
        with self._lock:
            sc = self._screens.get(screen_id)
            if not sc:
                return {"state": "unknown"}
            sc["seen"] = time.time()
            if sc["approved"]:
                return {"state": "paired", "token": sc["token"], "name": sc["name"]}
            return {"state": "waiting"}

    def screen_for_token(self, token: str) -> str | None:
        if not token:
            return None
        with self._lock:
            for sid, sc in self._screens.items():
                if sc["approved"] and sc["token"] and secrets.compare_digest(sc["token"], token):
                    sc["seen"] = time.time()
                    return sid
        return None

    def touch(self, screen_id: str) -> None:
        with self._lock:
            if screen_id in self._screens:
                self._screens[screen_id]["seen"] = time.time()

    def remove(self, screen_id: str) -> bool:
        with self._lock:
            return self._screens.pop(screen_id, None) is not None

    def listing(self, online_ids: set[str] | None = None) -> list[dict]:
        now = time.time()
        with self._lock:
            out = []
            for sid, sc in self._screens.items():
                if not sc["approved"]:
                    continue
                live = (sid in online_ids) if online_ids is not None else now - sc["seen"] < 30
                out.append({"id": sid, "name": sc["name"], "kind": "tv", "online": live})
            return out
