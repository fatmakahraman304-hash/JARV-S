"""
core/sync_hub.py — one JARVIS on every device: the shared memory and the
mailbox, kept in a private GitHub gist.

The web JARVIS (web/, served from GitHub Pages over HTTPS) runs on the phone,
tablet, TV, projector or watch on its own — its brain is Gemini, reached
directly from the device — so it keeps working when this computer is off. What
the devices share lives in one secret gist of the user's own GitHub account:

    memory.json          the long-term facts ({category: {key: {value, updated}}}),
                         the same shape as memory/long_term.json on the desktop
    recent.json          the last turns of conversation from every device
    device-<id>.json     each device's heartbeat (name, kind, last seen)
    inbox-<id>.json      commands other devices sent to this computer
    outbox-<id>.json     this computer's answers to them

This module is the desktop side: it merges memory both ways, keeps the
heartbeat, and runs commands that arrive in the inbox through the normal voice
session (so the phone can ask the laptop to open a file, write code in the
project, look at the screen…) and writes the answer back.

Standard library only (urllib); nothing here raises into the caller.
"""

from __future__ import annotations

import json
import platform
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

API = "https://api.github.com"
NAMESPACE = "everywhere"               # plugin config block holding token + gist id
POLL_SECONDS = 4.0
MEMORY_EVERY = 45.0
HEARTBEAT_EVERY = 20.0
ALIVE_SECONDS = 60.0                   # a device not heard from for this long is away
CLAIM_SECONDS = 300.0                  # "I'm talking to THIS device" lasts this long

# Who answers out loud when several devices are on at once. Every device hears
# and understands; exactly one speaks. The phone first, then the computer, then
# the rest — unless the user just turned to a device on purpose (tapped its
# microphone, typed into it), which wins for a few minutes.
VOICE_PRIORITY = {"phone": 1, "pc": 2, "tablet": 3, "tv": 4, "projector": 4, "watch": 5}
RECENT_MAX = 40
REPLY_WAIT = 90.0                      # how long a command waits for Jarvis's answer

_state = {"thread": None, "stop": threading.Event(), "inject": None, "pending": [],
          "etag": "", "last_memory": 0.0, "last_beat": 0.0, "turns": [], "lock": threading.Lock(),
          "status": "kapalı", "done": set(), "claim": "", "active": True,
          "owner": None, "on_owner": None, "devices": []}


# ── settings ──────────────────────────────────────────────────────────────────

def settings() -> dict:
    try:
        from memory.config_manager import get_plugin_config
        return dict(get_plugin_config(NAMESPACE) or {})
    except Exception:
        return {}


def save_settings(**values) -> None:
    try:
        from memory.config_manager import save_plugin_config
        cur = settings()
        cur.update(values)
        save_plugin_config(NAMESPACE, cur)
    except Exception as exc:
        print(f"[Sync] Ayar kaydedilemedi: {exc}")


def device_id() -> str:
    try:
        from dashboard.devices import device_id as _did
        return _did()
    except Exception:
        s = settings()
        if not s.get("device_id"):
            save_settings(device_id=uuid.uuid4().hex[:12])
        return settings().get("device_id", "pc")


def device_name() -> str:
    try:
        from dashboard.devices import device_name as _dn
        return _dn()
    except Exception:
        return platform.node() or "Bilgisayar"


# ── GitHub gist ───────────────────────────────────────────────────────────────

def _req(method: str, path: str, token: str, body: dict | None = None,
         etag: str = "", timeout: float = 15.0):
    """(status, json|None, etag). Never raises."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "JARVIS-sync")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if etag:
        req.add_header("If-None-Match", etag)
    try:
        ctx = None
        try:
            from core import tls
            ctx = tls.context() if hasattr(tls, "context") else None
        except Exception:
            ctx = None
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read().decode("utf-8") or "null"
            return r.status, json.loads(raw), r.headers.get("ETag", "")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return 304, None, etag
        try:
            msg = json.loads(e.read().decode("utf-8"))
        except Exception:
            msg = None
        return e.code, msg, ""
    except Exception as exc:
        return 0, {"message": str(exc)}, ""


def create_gist(token: str) -> tuple[str, str]:
    """A new secret gist for this user. Returns (gist_id, error)."""
    body = {"description": "JARVIS — ortak hafıza (gizli, silme)", "public": False,
            "files": {"memory.json": {"content": json.dumps(_empty_memory(), ensure_ascii=False)},
                      "recent.json": {"content": "[]"},
                      "README.md": {"content": "JARVIS'in cihazlar arası ortak hafızası. Silme."}}}
    st, js, _ = _req("POST", "/gists", token, body)
    if st == 201 and js and js.get("id"):
        return js["id"], ""
    if st == 401:
        return "", "GitHub anahtarı geçersiz."
    if st in (403, 404):
        return "", "Anahtarın 'gist' izni yok."
    return "", (js or {}).get("message", f"GitHub yanıtı {st}") if isinstance(js, dict) else f"GitHub yanıtı {st}"


def read_gist(token: str, gist_id: str, etag: str = ""):
    """(files {name: text} | None when unchanged, etag, error)."""
    st, js, tag = _req("GET", f"/gists/{gist_id}", token, etag=etag)
    if st == 304:
        return None, etag, ""
    if st != 200 or not isinstance(js, dict):
        return {}, "", (js or {}).get("message", f"GitHub {st}") if isinstance(js, dict) else f"GitHub {st}"
    files = {}
    for name, f in (js.get("files") or {}).items():
        if f.get("truncated") and f.get("raw_url"):
            try:
                rq = urllib.request.Request(f["raw_url"], headers={"Authorization": f"Bearer {token}",
                                                                  "User-Agent": "JARVIS-sync"})
                with urllib.request.urlopen(rq, timeout=15) as r:
                    files[name] = r.read().decode("utf-8")
            except Exception:
                continue
        else:
            files[name] = f.get("content") or ""
    return files, tag, ""


def write_files(token: str, gist_id: str, files: dict[str, str]) -> bool:
    st, _js, _ = _req("PATCH", f"/gists/{gist_id}", token,
                      {"files": {k: {"content": v} for k, v in files.items()}})
    return st == 200


# ── memory merge ──────────────────────────────────────────────────────────────

_CATS = ("identity", "preferences", "projects", "relationships", "wishes", "notes")


def _empty_memory() -> dict:
    return {c: {} for c in _CATS}


def _entry(v) -> dict:
    if isinstance(v, dict):
        return {"value": str(v.get("value", "")), "updated": str(v.get("updated", ""))}
    return {"value": str(v), "updated": ""}


def merge_memory(a: dict, b: dict) -> dict:
    """Union of two memories; for a key in both, the newer `updated` wins
    (ties keep `a`). Unknown categories are kept as they are."""
    out: dict = {}
    tomb = dict((a or {}).get("_deleted") or {})
    for k, t in ((b or {}).get("_deleted") or {}).items():
        if k not in tomb or str(t) > str(tomb[k]):
            tomb[k] = str(t)
    for cat in set(_CATS) | set((a or {}).keys()) | set((b or {}).keys()):
        if cat == "_deleted":
            continue
        ca, cb = (a or {}).get(cat), (b or {}).get(cat)
        if not isinstance(ca, dict) and not isinstance(cb, dict):
            if ca is not None or cb is not None:
                out[cat] = ca if ca is not None else cb
            continue
        ca, cb = ca if isinstance(ca, dict) else {}, cb if isinstance(cb, dict) else {}
        merged = {}
        for key in set(ca) | set(cb):
            if key in ca and key in cb:
                ea, eb = _entry(ca[key]), _entry(cb[key])
                merged[key] = eb if eb["updated"] > ea["updated"] else ea
            else:
                merged[key] = _entry(ca[key] if key in ca else cb[key])
        for key in list(merged):
            t = tomb.get(f"{cat}/{key}")
            if t and t >= merged[key]["updated"]:
                del merged[key]
        out[cat] = merged
    if tomb:
        out["_deleted"] = tomb
    return out


def _local_memory_categories() -> dict:
    from memory.memory_manager import load_memory
    mem = load_memory()
    return {c: mem.get(c, {}) for c in _CATS if isinstance(mem.get(c, {}), dict)}


def _save_local_categories(cats: dict) -> None:
    from memory import memory_manager as mm
    with mm._lock:
        mem = mm.load_memory()
        for c in _CATS:
            if c in cats:
                mem[c] = cats[c]
        mm.save_memory(mem)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── hooks for main.py ─────────────────────────────────────────────────────────

def note_turn(role: str, text: str) -> None:
    """A line of conversation on this computer, for the other devices' context."""
    if not text or not _state["thread"]:
        return
    with _state["lock"]:
        _state["turns"].append({"ts": _now(), "device": device_name(),
                                "role": "user" if role.lower().startswith(("kullan", "user")) else "jarvis",
                                "text": str(text)[:600]})


def note_reply(text: str) -> None:
    """Jarvis just answered: the oldest waiting remote command gets this answer."""
    if not text:
        return
    with _state["lock"]:
        for p in _state["pending"]:
            if p.get("reply") is None and time.time() - p["at"] < REPLY_WAIT:
                p["reply"] = str(text)[:2000]
                break


def status() -> str:
    return _state["status"]


def _ts(iso: str) -> float:
    try:
        return datetime.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def voice_owner(devices: list[dict], now: float | None = None) -> str | None:
    """The id of the one device that should speak, or None when none is on.
    Same rule as voiceOwner() in web/app.js — keep the two in step."""
    now = time.time() if now is None else now
    live = [d for d in devices if d.get("active") and now - _ts(d.get("seen", "")) < ALIVE_SECONDS]
    if not live:
        return None
    claimed = [d for d in live if d.get("claim") and now - _ts(d["claim"]) < CLAIM_SECONDS]
    if claimed:
        return max(claimed, key=lambda d: (_ts(d["claim"]), str(d.get("id"))))["id"]
    return min(live, key=lambda d: (VOICE_PRIORITY.get(d.get("kind"), 9), str(d.get("id"))))["id"]


def claim() -> None:
    """The user turned to this computer (typed, pressed wake): it speaks for a while."""
    _state["claim"] = _now()
    _state["last_beat"] = 0.0          # tell the others on the next cycle


def set_active(active: bool) -> None:
    """Awake and unmuted — whether this computer is a candidate to speak."""
    if bool(active) != _state["active"]:
        _state["active"] = bool(active)
        _state["last_beat"] = 0.0


def on_owner_change(fn) -> None:
    """fn(this_device_speaks: bool, owner_name: str) — called from the sync thread."""
    _state["on_owner"] = fn


# ── the loop ──────────────────────────────────────────────────────────────────

def start(inject) -> bool:
    """Begin syncing if the user has set it up. inject(text) hands a remote
    command to the voice session (thread-safe)."""
    _state["inject"] = inject
    s = settings()
    if not (s.get("github_token") and s.get("gist_id")):
        _state["status"] = "kurulmadı"
        return False
    if _state["thread"] and _state["thread"].is_alive():
        return True
    _state["stop"].clear()
    t = threading.Thread(target=_loop, daemon=True, name="jarvis-sync")
    _state["thread"] = t
    t.start()
    return True


def stop() -> None:
    _state["stop"].set()


def _loop() -> None:
    _state["status"] = "bağlanıyor"
    while not _state["stop"].is_set():
        try:
            _cycle()
        except Exception as exc:
            _state["status"] = f"hata: {exc}"[:120]
            print(f"[Sync] {exc}")
        _state["stop"].wait(POLL_SECONDS)


def _cycle() -> None:
    s = settings()
    token, gid = s.get("github_token", ""), s.get("gist_id", "")
    if not token or not gid:
        _state["status"] = "kurulmadı"
        return
    me = device_id()
    now = time.time()
    writes: dict[str, str] = {}
    force = now - _state["last_memory"] > MEMORY_EVERY or now - _state["last_beat"] > HEARTBEAT_EVERY
    with _state["lock"]:
        has_turns = bool(_state["turns"])
        answered = [p for p in _state["pending"] if p.get("reply") is not None or now - p["at"] > REPLY_WAIT]
    files, tag, err = read_gist(token, gid, "" if (force or has_turns or answered) else _state["etag"])
    if err:
        _state["status"] = f"hata: {err}"[:120]
        return
    if files is None:                  # nothing changed, nothing to send
        _state["status"] = "bağlı"
        _update_owner(me)              # a device can still time out
        return
    _state["etag"] = tag
    _state["status"] = "bağlı"

    # 0. who speaks
    others = []
    for name, text in files.items():
        if name.startswith("device-") and name != f"device-{me}.json":
            try:
                d = json.loads(text)
                if isinstance(d, dict) and d.get("id"):
                    others.append(d)
            except Exception:
                pass
    _state["devices"] = others
    _update_owner(me)

    # 1. commands addressed to this computer
    inbox_name = f"inbox-{me}.json"
    try:
        inbox = json.loads(files.get(inbox_name) or "[]")
    except Exception:
        inbox = []
    for cmd in inbox if isinstance(inbox, list) else []:
        cid = str(cmd.get("id") or "")
        if not cid or cid in _state["done"]:
            continue
        _state["done"].add(cid)
        _run_command(cid, str(cmd.get("text") or ""), str(cmd.get("from") or "cihaz"))
    if inbox:
        writes[inbox_name] = "[]"

    # 2. answers
    with _state["lock"]:
        answered = [p for p in _state["pending"] if p.get("reply") is not None or now - p["at"] > REPLY_WAIT]
        _state["pending"] = [p for p in _state["pending"] if p not in answered]
    if answered:
        try:
            outbox = json.loads(files.get(f"outbox-{me}.json") or "[]")
        except Exception:
            outbox = []
        outbox = [o for o in outbox if isinstance(o, dict)][-20:]
        for p in answered:
            outbox.append({"id": p["id"], "ts": _now(),
                           "reply": p.get("reply") or "Komutu aldım ama henüz bir yanıt üretmedim."})
        writes[f"outbox-{me}.json"] = json.dumps(outbox[-30:], ensure_ascii=False)

    # 3. recent conversation
    with _state["lock"]:
        turns, _state["turns"] = _state["turns"], []
    if turns:
        try:
            recent = json.loads(files.get("recent.json") or "[]")
        except Exception:
            recent = []
        recent = (recent if isinstance(recent, list) else []) + turns
        writes["recent.json"] = json.dumps(recent[-RECENT_MAX:], ensure_ascii=False)

    # 4. memory, both ways
    if now - _state["last_memory"] > MEMORY_EVERY:
        _state["last_memory"] = now
        try:
            cloud = json.loads(files.get("memory.json") or "{}")
        except Exception:
            cloud = {}
        local = _local_memory_categories()
        # A key that was here at the last sync and is gone now was forgotten on
        # this computer: record that, or the other devices would bring it back.
        keys_now = {f"{c}/{k}" for c in _CATS for k in local.get(c, {})}
        prev = _state.get("local_keys")
        if prev is not None:
            gone = prev - keys_now
            if gone:
                local["_deleted"] = {k: _now() for k in gone}
            # added here since the last sync: a re-add beats an older deletion
            # (desktop entries carry only a date, so the timestamps can't tell)
            fresh = keys_now - prev
            if fresh and isinstance(cloud.get("_deleted"), dict):
                cloud["_deleted"] = {k: t for k, t in cloud["_deleted"].items() if k not in fresh}
        _state["local_keys"] = keys_now
        merged = merge_memory(local, cloud)
        local_norm = {c: {k: _entry(v) for k, v in local.get(c, {}).items()} for c in _CATS}
        if any(merged.get(c, {}) != local_norm[c] for c in _CATS):
            _save_local_categories(merged)
            _state["local_keys"] = {f"{c}/{k}" for c in _CATS for k in merged.get(c, {})}
        if merged != cloud:
            writes["memory.json"] = json.dumps(merged, ensure_ascii=False)

    # 5. heartbeat
    if now - _state["last_beat"] > HEARTBEAT_EVERY:
        _state["last_beat"] = now
        info = {"id": me, "name": device_name(), "kind": "pc", "os": platform.system(),
                "seen": _now(), "commands": True, "active": _state["active"],
                "claim": _state["claim"]}
        writes[f"device-{me}.json"] = json.dumps(info, ensure_ascii=False)

    if writes and write_files(token, gid, writes):
        _state["etag"] = ""


def _update_owner(me: str) -> None:
    devs = list(_state["devices"]) + [{"id": me, "name": device_name(), "kind": "pc",
                                       "active": _state["active"], "seen": _now(),
                                       "claim": _state["claim"]}]
    owner = voice_owner(devs)
    if owner == _state["owner"]:
        return
    _state["owner"] = owner
    cb = _state["on_owner"]
    if cb:
        name = next((d.get("name", "") for d in devs if d.get("id") == owner), "")
        try:
            cb(owner in (None, me), name)
        except Exception as exc:
            print(f"[Sync] owner callback: {exc}")


def _run_command(cid: str, text: str, sender: str) -> None:
    text = text.strip()
    if not text:
        return
    if text.startswith("quick:"):
        from core import remote_control
        ok, msg, extra = remote_control.perform(text.split(":", 1)[1].strip())
        with _state["lock"]:
            _state["pending"].append({"id": cid, "at": time.time(),
                                      "reply": msg if not extra.get("image") else msg + " (görüntü bilgisayarda)"})
        return
    inject = _state["inject"]
    with _state["lock"]:
        _state["pending"].append({"id": cid, "at": time.time(), "reply": None})
    if inject is None:
        with _state["lock"]:
            _state["pending"][-1]["reply"] = "Bu bilgisayarda sesli oturum açık değil."
        return
    try:
        inject(f"[{sender} cihazından komut] {text}")
    except Exception as exc:
        with _state["lock"]:
            _state["pending"][-1]["reply"] = f"Komut iletilemedi: {exc}"


# ── the setup link for other devices ─────────────────────────────────────────

WEB_URL = "https://fatmakahraman304-hash.github.io/JARV-S/"


def setup_link(gemini_key: str) -> str:
    """The link that sets up the web JARVIS on another device in one tap."""
    import base64
    s = settings()
    payload = {"g": gemini_key or "", "t": s.get("github_token", ""), "i": s.get("gist_id", ""),
               "n": _assistant_name()}
    blob = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode().rstrip("=")
    return f"{WEB_URL}#s={blob}"


def _assistant_name() -> str:
    try:
        from memory.config_manager import get_assistant_name
        return get_assistant_name() or "JARVIS"
    except Exception:
        return "JARVIS"
