"""
core/sync_hub.py — one MAYK on every device: the shared memory and the
mailbox, kept in a private GitHub gist.

The web MAYK (web/, served from GitHub Pages over HTTPS) runs on the phone,
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
from pathlib import Path

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
REPLY_WAIT = 90.0                      # how long a command waits for MAYK's answer

_state = {"thread": None, "stop": threading.Event(), "inject": None, "pending": [],
          "etag": "", "last_memory": 0.0, "last_beat": 0.0, "turns": [], "lock": threading.Lock(),
          "status": "kapalı", "done": set(), "claim": "", "active": True,
          "owner": None, "on_owner": None, "devices": [], "rem_new": [], "on_reminder": None,
          "rem_known": None, "out_cmds": [], "recent": [], "img_new": [], "gallery": [],
          "arch_queue": [], "arch_last": 0.0, "arch_id": "",
          "push_keys": None, "push_subs": {}, "pushed": set(), "push_gone": set()}


def _log(msg: str) -> None:
    """print() that cannot fail: a Windows console in cp1252 raises on Turkish
    letters, and under pythonw there may be no console at all."""
    try:
        print(msg)
    except Exception:
        try:
            print(str(msg).encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


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
        _log(f"[Sync] Ayar kaydedilemedi: {exc}")


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
    body = {"description": "MAYK — ortak hafıza (gizli, silme)", "public": False,
            "files": {"memory.json": {"content": json.dumps(_empty_memory(), ensure_ascii=False)},
                      "recent.json": {"content": "[]"},
                      "README.md": {"content": "MAYK'ın cihazlar arası ortak hafızası. Silme."}}}
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
    return {c: mem.get(c, {}) for c in (*_CATS, "_deleted") if isinstance(mem.get(c, {}), dict)}


def _save_local_categories(cats: dict) -> None:
    from memory import memory_manager as mm
    with mm._lock:
        mem = mm.load_memory()
        for c in (*_CATS, "_deleted"):
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
    turn = {"ts": _now(), "device": device_name(),
            "role": "user" if role.lower().startswith(("kullan", "user")) else "jarvis",
            "text": str(text)[:600]}
    with _state["lock"]:
        _state["turns"].append(turn)
        _state["arch_queue"].append(turn)


def note_reply(text: str) -> None:
    """MAYK just answered: the oldest waiting remote command gets this answer."""
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


# ── shared reminders (reminders.json; web/app.js mergeReminders) ────────────
REM_KEEP_MS = 24 * 3600 * 1000
_REM_FILE = Path(__file__).resolve().parent.parent / "config" / "shared_reminders.json"


def merge_reminders(a, b, now_ms: float | None = None) -> list[dict]:
    """Union by id; a cancellation on any side wins; a day after it was due an
    entry is dropped. Same rule as mergeReminders in web/app.js."""
    now_ms = time.time() * 1000 if now_ms is None else now_ms
    by: dict[str, dict] = {}
    for r in list(a or []) + list(b or []):
        if not isinstance(r, dict) or not r.get("id"):
            continue
        try:
            due = float(r.get("due") or 0)
        except (TypeError, ValueError):
            continue
        if not due:
            continue
        old = by.get(r["id"])
        merged = {**(old or {}), **r, "due": due}
        merged["cancelled"] = (old or {}).get("cancelled") or r.get("cancelled") or ""
        by[r["id"]] = merged
    # a daily one that came due brings its next day; the id says which day,
    # so every device adds the very same entry and the merge keeps one
    day = 86_400_000
    for r in list(by.values()):
        if r.get("repeat") != "daily" or r.get("cancelled") or r["due"] > now_ms:
            continue
        nxt = r["due"] + day * max(1, int((now_ms - r["due"]) // day) + 1)
        nid = f"{str(r['id']).split('@')[0]}@{int(nxt)}"
        if nid not in by:
            by[nid] = {**r, "id": nid, "due": float(nxt), "cancelled": ""}
    out = [r for r in by.values() if r["due"] > now_ms - REM_KEEP_MS]
    return sorted(out, key=lambda r: r["due"])


def _rem_sig(items) -> str:
    return "\n".join(f"{r.get('id')}|{float(r.get('due') or 0):.0f}|{r.get('text', '')}|{r.get('cancelled') or ''}"
                     for r in items)


def new_reminder_id() -> str:
    return f"{device_id()}-{int(time.time() * 1000):x}"


def add_reminder(text: str, due_ts: float, rid: str = "") -> str:
    """Share a reminder set on this computer with every device. Returns its id."""
    rid = rid or new_reminder_id()
    with _state["lock"]:
        _state["rem_new"].append({"id": rid, "text": str(text)[:200], "due": int(due_ts * 1000),
                                  "from": device_name(), "cancelled": ""})
    _known().add(rid)
    _save_known()
    return rid


def cancel_reminder(rid: str) -> bool:
    """Cancel a shared reminder on every device (a cancellation always wins
    the merge). False when it is not known here."""
    with _state["lock"]:
        r = next((x for x in _state.get("reminders") or [] if x.get("id") == rid), None)
        r = r or next((x for x in _state["rem_new"] if x.get("id") == rid), None)
        if r is None:
            return False
        _state["rem_new"].append({**r, "cancelled": _now()})
    return True


def on_reminder(fn) -> None:
    """fn(event, reminder) — event "new" for one set on another device,
    "cancelled" for one cancelled anywhere."""
    _state["on_reminder"] = fn


def _known() -> set:
    if _state["rem_known"] is None:
        try:
            _state["rem_known"] = set(json.loads(_REM_FILE.read_text("utf-8")).get("known", []))
        except Exception:
            _state["rem_known"] = set()
    return _state["rem_known"]


def _save_known() -> None:
    try:
        _REM_FILE.parent.mkdir(parents=True, exist_ok=True)
        _REM_FILE.write_text(json.dumps({"known": sorted(_known())[-500:]}), "utf-8")
    except OSError:
        pass


def _sync_reminders(files: dict, writes: dict, now: float) -> None:
    try:
        cloud = json.loads(files.get("reminders.json") or "[]")
    except Exception:
        cloud = []
    with _state["lock"]:
        mine, _state["rem_new"] = _state["rem_new"], []
    merged = merge_reminders(cloud if isinstance(cloud, list) else [], mine, now * 1000)
    _state["reminders"] = merged
    _push_due_reminders(merged, now)
    known, cb, changed = _known(), _state.get("on_reminder"), False
    for r in merged:
        key_c = r["id"] + "#cancelled"
        if r["id"] not in known:
            known.add(r["id"])
            changed = True
            if not r.get("cancelled") and r["due"] > now * 1000 and cb:
                try:
                    cb("new", r)
                except Exception as exc:
                    _log(f"[Sync] reminder: {exc}")
        if r.get("cancelled") and key_c not in known:
            known.add(key_c)
            changed = True
            if cb:
                try:
                    cb("cancelled", r)
                except Exception as exc:
                    _log(f"[Sync] reminder: {exc}")
    if changed:
        _save_known()
    if _rem_sig(merged) != _rem_sig(merge_reminders(cloud if isinstance(cloud, list) else [], [], now * 1000)):
        writes["reminders.json"] = json.dumps(merged, ensure_ascii=False)


# ── this computer → another device (phone, tablet, TV …) ────────────────────
_KIND_WORDS = (("phone", ("telefon", "phone", "cep")), ("tablet", ("tablet", "ipad")),
               ("projector", ("projeksiyon", "projekt")), ("tv", ("televizyon", "tv", "tele")),
               ("watch", ("saat", "watch")), ("pc", ("bilgisayar", "laptop", "pc", "dizüstü", "masaüstü")))


def devices() -> list[dict]:
    """The other devices seen in the shared gist (latest heartbeat each)."""
    return [dict(d) for d in _state["devices"]]


def device_online(d: dict, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    return now - _ts(d.get("seen", "")) < 180


def find_device(name: str, devs: list[dict] | None = None) -> dict | None:
    devs = [d for d in (devices() if devs is None else devs)
            if d.get("id") != device_id() and d.get("kind") != "receiver"]    # the Alıcı takes only remote commands
    n = str(name or "").strip().casefold()
    if not n:
        return None
    for d in devs:
        if str(d.get("name", "")).casefold() == n:
            return d
    for d in devs:
        if n in str(d.get("name", "")).casefold():
            return d
    kind = next((k for k, words in _KIND_WORDS if any(w in n for w in words)), None)
    if not kind:
        return None
    pool = [d for d in devs if d.get("kind") == kind or (kind == "tv" and d.get("kind") == "projector")]
    pool.sort(key=lambda d: (device_online(d), _ts(d.get("seen", ""))), reverse=True)
    return pool[0] if pool else None


def send_to_device(name: str, cmd: dict) -> tuple[bool, str]:
    """Queue `cmd` ({"kind": open|image|code|text|say, ...}) for another
    device; web/app.js runInbox carries it out there. Delivered on the next
    sync cycle (a few seconds)."""
    s = settings()
    if not (s.get("github_token") and s.get("gist_id")):
        return False, "Cihazlar bağlı değil; önce 'MAYK'ı her cihaza kur' de."
    d = find_device(name)
    if not d:
        names = ", ".join(x.get("name", "?") for x in devices()) or "yok"
        return False, f"'{name}' adında ya da türünde bir cihaz bulamadım. Bilinen cihazlar: {names}."
    if d.get("kind") == "pc":
        return False, f"{d.get('name')} bir bilgisayar; bilgisayarlar arası gönderme henüz yok."
    item = dict(cmd)
    item.update({"id": f"{device_id()}-{int(time.time() * 1000):x}", "from": device_name(), "ts": _now()})
    if len(json.dumps(item)) > 4_000_000:
        return False, "Gönderilecek şey çok büyük."
    with _state["lock"]:
        _state["out_cmds"].append((d["id"], item))
    tail = "" if device_online(d) else " (şu an kapalı görünüyor; açılınca görecek)"
    return True, f"{d.get('name')} cihazına gönderiyorum{tail}."


def _deliver_out(files: dict, writes: dict) -> None:
    with _state["lock"]:
        out, _state["out_cmds"] = _state["out_cmds"], []
    by: dict[str, list] = {}
    for dev_id, item in out:
        by.setdefault(dev_id, []).append(item)
    for dev_id, items in by.items():
        name = f"inbox-{dev_id}.json"
        try:
            box = json.loads(writes.get(name) or files.get(name) or "[]")
        except Exception:
            box = []
        box = [b for b in box if isinstance(b, dict)] + items
        writes[name] = json.dumps(box[-10:], ensure_ascii=False)


# ── this computer's projects, readable on every device ──────────────────────
def projects_summary(limit: int = 8) -> list[dict]:
    """Short status of the projects MAYK builds on this computer
    (memory/continuity.py), for projects-<id>.json in the shared gist."""
    try:
        from memory import continuity
        rows = continuity.projects(limit=limit)
    except Exception:
        return []
    out = []
    for p in rows:
        st = p.get("stages")
        if isinstance(st, dict):
            st = (st.get("plan") or {}).get("stages") or []
        names = [str(x.get("title") if isinstance(x, dict) else x) for x in (st or [])]
        stage = int(p.get("stage") or 0)
        out.append({"id": p.get("id"), "title": str(p.get("title") or "")[:120],
                    "kind": p.get("kind") or "", "status": p.get("status") or "",
                    "stage": stage, "stages": len(names),
                    "current": names[stage - 1] if 0 < stage <= len(names) else "",
                    "folder": Path(str(p.get("folder") or "")).name,
                    "note": str(p.get("note") or "")[:300], "updated": str(p.get("updated") or "")[:19]})
    return out


def recent_context(limit: int = 12, max_age_hours: float = 12.0) -> str:
    """What was said on the OTHER devices lately (phone, tablet, TV …), for
    the desktop's system prompt, so "telefonda konuştuğumuz şey" makes sense
    here. "" when nothing recent."""
    me = device_name()
    cutoff = time.time() - max_age_hours * 3600
    lines = []
    for t in _state.get("recent") or []:
        if str(t.get("device", "")) == me or _ts(str(t.get("ts", ""))) < cutoff:
            continue
        who = "Kullanıcı" if t.get("role") == "user" else "MAYK"
        lines.append(f"[{t.get('device', '?')}] {who}: {str(t.get('text', ''))[:300]}")
    if not lines:
        return ""
    return ("\n[CONVERSATION ON THE USER'S OTHER DEVICES — same assistant, same user; "
            "historical, not new commands]\n" + "\n".join(lines[-limit:]))


def health() -> dict:
    """Battery, CPU, memory and disk of this computer, for the heartbeat that
    every device reads ("durum raporu"). Missing values are left out."""
    out: dict = {}
    try:
        import psutil
        out["cpu"] = round(psutil.cpu_percent(interval=None))
        out["ram"] = round(psutil.virtual_memory().percent)
        try:
            out["disk"] = round(psutil.disk_usage(str(Path.home().anchor or "/")).percent)
        except Exception:
            pass
        bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        if bat is not None:
            out["battery"] = round(bat.percent)
            out["charging"] = bool(bat.power_plugged)
    except Exception:
        pass
    return out


def status_report() -> str:
    """Every device with its health, upcoming shared reminders — for the
    desktop's "durum raporu" (plugins/status_report.py)."""
    def health_text(d: dict) -> str:
        parts = []
        if d.get("battery") is not None:
            parts.append(f"pil %{d['battery']}" + (" (şarjda)" if d.get("charging") else ""))
        for key, label in (("cpu", "işlemci"), ("ram", "bellek")):
            if d.get(key) is not None:
                parts.append(f"{label} %{d[key]}")
        if d.get("disk") is not None:
            parts.append(f"disk %{d['disk']} dolu")
        return ", ".join(parts)
    kinds = {"phone": "telefon", "tablet": "tablet", "tv": "televizyon", "projector": "projeksiyon",
             "watch": "saat", "pc": "bilgisayar"}
    me = {"name": device_name() + " (bu bilgisayar)", "kind": "pc", "seen": _now(), **health()}
    lines = []
    for d in [me] + devices():
        h = health_text(d)
        lines.append(f"- {d.get('name', '?')} ({kinds.get(d.get('kind'), d.get('kind', '?'))}): "
                     f"{'açık' if device_online(d) else 'kapalı'}" + (f", {h}" if h else ""))
    now_ms = time.time() * 1000
    rem = [r for r in _state.get("reminders") or [] if not r.get("cancelled") and r.get("due", 0) > now_ms][:4]
    rem_lines = [f"- {datetime.fromtimestamp(r['due'] / 1000).strftime('%d.%m %H:%M')}: {r.get('text', '')}" for r in rem]
    linked = bool(settings().get("gist_id"))
    return ("CİHAZLAR:\n" + "\n".join(lines)
            + ("" if linked else "\n(Diğer cihazlar bağlı değil: 'MAYK'ı her cihaza kur' denmeli.)")
            + "\n\nSIRADAKİ ORTAK HATIRLATICILAR:\n" + ("\n".join(rem_lines) or "- yok"))


# ── low battery: said once, by the device that has the voice ────────────────
LOW_BATTERY = 15
DISK_FULL = 92
RECHARGED = 30


def low_battery(devs: list[dict], alerted: set, now: float | None = None) -> list[dict]:
    """Devices that just went low (≤15 %, not charging, online) and were not
    announced yet. A device that charges or climbs back over 30 % is forgotten,
    so it is announced again next time. Same rule as lowBattery in web/app.js."""
    out = []
    for d in devs:
        b = d.get("battery")
        if b is None:
            continue
        if d.get("charging") or b > RECHARGED:
            alerted.discard(d.get("id"))
            continue
        if b <= LOW_BATTERY and device_online(d, now) and d.get("id") not in alerted:
            alerted.add(d.get("id"))
            out.append(d)
    return out


def _battery_watch(me: str) -> None:
    alerted = _state.setdefault("bat_alerted", set())
    mine = {"id": me, "name": device_name(), "kind": "pc", "seen": _now(), **health()}
    low = low_battery(devices() + [mine], alerted)
    notes = []
    if low:
        notes.append("Pili azalan cihaz: " + ", ".join(f"{d.get('name')} %{d.get('battery')}" for d in low)
                     + ". Şarja takmasını öner.")
    # a nearly full disk on any computer: once a day
    day = time.strftime("%Y-%m-%d")
    for d in devices() + [mine]:
        if d.get("disk") is not None and d["disk"] >= DISK_FULL and device_online(d):
            key = f"{d.get('id')}:{day}"
            if key not in _state.setdefault("disk_alerted", set()):
                _state["disk_alerted"].add(key)
                notes.append(f"{d.get('name')} diski %{d['disk']} dolu; yer açmayı öner.")
    if not notes or _state.get("owner") not in (None, me):
        return
    inject = _state.get("inject")
    _log("[Sync] uyarı: " + " ".join(notes))
    if inject:
        try:
            inject("[Sistem notu, kullanıcı söylemedi] " + " ".join(notes) + " Kullanıcıya kısaca söyle.")
        except Exception:
            pass


# ── shared picture gallery (images.json): every device's pictures that can be
# opened from a link (the free painter's) ─────────────────────────────────────
GALLERY_MAX = 40


def merge_gallery(a, b) -> list[dict]:
    by = {}
    for g in list(a or []) + list(b or []):
        if isinstance(g, dict) and g.get("id") and str(g.get("url", "")).startswith("https://"):
            by[g["id"]] = {**by.get(g["id"], {}), **g}
    return sorted(by.values(), key=lambda g: str(g.get("ts", "")))[-GALLERY_MAX:]


def add_image(prompt: str, url: str, **extra) -> None:
    if not str(url).startswith("https://"):
        return
    with _state["lock"]:
        _state["img_new"].append({"id": f"{device_id()}-{int(time.time() * 1000):x}", "prompt": str(prompt)[:200],
                                  "url": url, "from": device_name(), "ts": _now(), **extra})


def gallery() -> list[dict]:
    return list(_state.get("gallery") or [])


# ── the archive: every conversation from every device, for good ─────────────
# A second secret gist (its id in archive.json of the main one), one file a
# month: history-YYYY-MM.json. Read only when searching. Same format as
# Archive in web/app.js.
ARCHIVE_EVERY = 180.0


def _archive_id(token: str, files: dict | None = None, create: bool = True) -> str:
    if _state.get("arch_id"):
        return _state["arch_id"]
    try:
        aid = json.loads((files or {}).get("archive.json") or "{}").get("gist", "")
    except Exception:
        aid = ""
    if not aid and files is None:
        got, _, err = read_gist(token, settings().get("gist_id", ""))
        if not err and got:
            return _archive_id(token, got, create)
    if not aid and create:
        st, js, _ = _req("POST", "/gists", token, {"description": "MAYK — konuşma arşivi (gizli, silme)",
                                                    "public": False,
                                                    "files": {"README.md": {"content": "MAYK konuşma arşivi. Silme."}}})
        if st == 201 and js and js.get("id"):
            aid = js["id"]
            write_files(token, settings().get("gist_id", ""), {"archive.json": json.dumps({"gist": aid})})
    _state["arch_id"] = aid
    return aid


def _archive_files(token: str, aid: str) -> dict[str, list]:
    got, _, err = read_gist(token, aid)
    out = {}
    for name, text in (got or {}).items():
        if name.startswith("history-") and name.endswith(".json"):
            try:
                v = json.loads(text or "[]")
                out[name] = v if isinstance(v, list) else []
            except Exception:
                out[name] = []
    return out


def _archive_flush(token: str, files: dict, now: float) -> None:
    with _state["lock"]:
        batch = list(_state["arch_queue"])
    if not batch or now - _state["arch_last"] < ARCHIVE_EVERY:
        return
    _state["arch_last"] = now
    aid = _archive_id(token, files)
    if not aid:
        return
    months = _archive_files(token, aid)
    writes: dict[str, list] = {}
    for t in batch:
        name = f"history-{t['ts'][:7]}.json"
        lst = writes.get(name) or list(months.get(name, []))
        if not any(x.get("ts") == t["ts"] and x.get("device") == t["device"] and x.get("text") == t["text"] for x in lst):
            lst.append(t)
        writes[name] = lst
    if write_files(token, aid, {k: json.dumps(v, ensure_ascii=False) for k, v in writes.items()}):
        with _state["lock"]:
            _state["arch_queue"] = _state["arch_queue"][len(batch):]


def search_archive(query: str, days: float = 0) -> str:
    """Search every device's past conversations (desktop search_history)."""
    import re
    s = settings()
    token = s.get("github_token", "")
    if not (token and s.get("gist_id")):
        return "Cihazlar bağlı değil; konuşma arşivi yok."
    aid = _archive_id(token, None, create=False)
    if not aid:
        return "Konuşma arşivi henüz oluşmadı."
    months = _archive_files(token, aid)
    since = time.time() - days * 86400 if days and days > 0 else 0
    rows = [t for name in sorted(months) for t in months[name] if isinstance(t, dict) and _ts(str(t.get("ts", ""))) >= since]
    with _state["lock"]:
        rows += [t for t in _state["arch_queue"] if t not in rows]

    def stem(w: str) -> str:
        return w[:max(4, len(w) - 3)] if len(w) > 5 else w
    words = [stem(w) for w in re.findall(r"\w+", str(query).casefold()) if len(w) > 2]
    scored = []
    for i, t in enumerate(rows):
        txt = str(t.get("text", "")).casefold()
        sc = sum(1 for w in words if w in txt) if words else 1
        if sc:
            scored.append((sc, i))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    pick = sorted({j for _, i in scored[:8] for j in (i - 1, i, i + 1) if 0 <= j < len(rows)})
    if not pick:
        return "Arşivde bununla ilgili bir konuşma bulamadım."
    lines = [f"{str(rows[j].get('ts', ''))[:16].replace('T', ' ')} [{rows[j].get('device', '?')}] "
             f"{'Kullanıcı' if rows[j].get('role') == 'user' else 'MAYK'}: {rows[j].get('text', '')}" for j in pick]
    return f"Arşivden ({len(rows)} satır arandı):\n" + "\n".join(lines)[:6000]


# ── notifications to devices whose MAYK page is closed (core/webpush) ─────
def _push_setup(files: dict, writes: dict) -> None:
    """The VAPID keys are shared in push.json (made by the first computer);
    each device that turned notifications on has push-sub-<id>.json."""
    try:
        keys = json.loads(files.get("push.json") or "{}")
    except Exception:
        keys = {}
    if not (keys.get("publicKey") and keys.get("privateKey")):
        try:
            from core import webpush
            priv, pub = webpush.new_keys()
            keys = {"publicKey": pub, "privateKey": priv}
            writes["push.json"] = json.dumps(keys)
        except Exception as exc:
            _log(f"[Push] keys: {exc}")
            keys = {}
    _state["push_keys"] = keys or None
    subs = {}
    for name, text in files.items():
        if name.startswith("push-sub-") and name.endswith(".json"):
            try:
                sub = json.loads(text or "{}")
            except Exception:
                continue
            if isinstance(sub, dict) and sub.get("endpoint"):
                subs[name[len("push-sub-"):-len(".json")]] = sub
    _state["push_subs"] = subs
    for dev_id in list(_state["push_gone"]):
        writes[f"push-sub-{dev_id}.json"] = "{}"
        _state["push_gone"].discard(dev_id)


def push_to(dev_id: str, title: str, body: str, tag: str = "jarvis") -> bool:
    """Send a notification to `dev_id` if it turned notifications on. In the
    background; True when one was sent off."""
    sub = (_state.get("push_subs") or {}).get(dev_id)
    keys = _state.get("push_keys") or {}
    if not sub or not keys.get("privateKey"):
        return False

    def go():
        try:
            from core import webpush
            ok, status = webpush.send(sub, {"title": title[:120], "body": body[:400], "tag": tag},
                                      keys["privateKey"], keys["publicKey"])
            if status in (404, 410):           # unsubscribed or expired: forget it
                _state["push_gone"].add(dev_id)
            elif not ok:
                _log(f"[Push] {dev_id}: {status}")
        except Exception as exc:
            _log(f"[Push] {exc}")
    threading.Thread(target=go, daemon=True, name="webpush").start()
    return True


def _offline_subscribers(now: float | None = None) -> list[str]:
    seen = {d.get("id"): d for d in devices()}
    return [dev for dev in (_state.get("push_subs") or {})
            if dev != device_id() and not (seen.get(dev) and device_online(seen[dev], now))]


_WHAT = {"image": "bir resim gönderdi", "code": "kod gönderdi", "text": "bir yazı gönderdi",
         "open": "bir bağlantı gönderdi", "report": "bir sonuç gönderdi", "say": "bir mesaj gönderdi",
         "ring": "bu cihazı arıyor", "guard": "güvenlik modunu değiştirdi"}


def _push_inboxes(files: dict, now: float) -> None:
    """Something waits in the inbox of a device whose page is closed (sent by
    this computer or by another device — a guard photo, a report, a link): a
    notification says so, once per item."""
    seen = _state.setdefault("inbox_seen", set())
    first = not _state.get("inbox_primed")
    for dev in _offline_subscribers(now):
        try:
            box = json.loads(files.get(f"inbox-{dev}.json") or "[]")
        except Exception:
            continue
        fresh = [it for it in box if isinstance(it, dict) and it.get("id") and it["id"] not in seen]
        for it in fresh:
            seen.add(it["id"])
        if fresh and not first:
            it = fresh[-1]
            alarm = it.get("kind") == "image" and "hareket" in str(it.get("title", "")).lower()
            push_to(dev, ("🚨 " if alarm else "") + f"{it.get('from') or 'MAYK'} {_WHAT.get(it.get('kind'), 'bir şey gönderdi')}",
                    str(it.get("title") or it.get("text") or "Açınca görürsün.")[:300],
                    tag="alarm" if alarm else "inbox")
    _state["inbox_primed"] = True


def _push_due_reminders(merged: list[dict], now: float) -> None:
    """A reminder comes due: devices whose page is closed get a notification."""
    pushed = _state["pushed"]
    for r in merged:
        if r.get("cancelled") or r["id"] in pushed:
            continue
        if now * 1000 - 600_000 <= r["due"] <= now * 1000:
            pushed.add(r["id"])
            title = "⚡ Protokol zamanı" if r.get("protocol") else "⏰ MAYK hatırlatıyor"
            for dev in _offline_subscribers(now):
                push_to(dev, title, str(r.get("text") or ""), tag=f"rem-{r['id']}")


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


def on_update(fn) -> None:
    """fn() presses GÜNCELLE here — when another device asks every device to update."""
    _state["on_update"] = fn


def request_update_all() -> bool:
    """Ask every device to update: web apps reload, computers press GÜNCELLE."""
    s = settings()
    if not (s.get("github_token") and s.get("gist_id")):
        return False
    ok = write_files(s["github_token"], s["gist_id"], {"update.json": json.dumps({"ts": _now(), "by": device_name()})})
    if ok:
        _state["update_seen"] = _now()
    return ok


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
            _log(f"[Sync] {exc}")
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
        has_turns = (bool(_state["turns"]) or bool(_state["rem_new"]) or bool(_state["out_cmds"])
                     or bool(_state["img_new"]))
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

    # 0b. "update every device" — pressed on another device
    try:
        upd = json.loads(files.get("update.json") or "{}")
    except Exception:
        upd = {}
    ts = str(upd.get("ts") or "")
    if ts:
        seen = _state.get("update_seen")
        if seen is None:
            _state["update_seen"] = ts                # first look: remember, don't act
        elif ts > seen:
            _state["update_seen"] = ts
            cb = _state.get("on_update")
            if cb:
                _log(f"[Sync] {upd.get('by', 'Bir cihaz')} bütün cihazları güncelliyor.")
                try:
                    cb()
                except Exception as exc:
                    _log(f"[Sync] update: {exc}")

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
        if cmd.get("kind") in _ITEM_KINDS:
            _receive_item(cid, cmd, str(cmd.get("from") or "cihaz"))
        else:
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
    try:
        recent = json.loads(files.get("recent.json") or "[]")
    except Exception:
        recent = []
    recent = [t for t in (recent if isinstance(recent, list) else []) if isinstance(t, dict)]
    if turns:
        recent = recent + turns
        writes["recent.json"] = json.dumps(recent[-RECENT_MAX:], ensure_ascii=False)
    _state["recent"] = recent[-RECENT_MAX:]

    # 3-. notifications: shared keys and who turned them on
    _push_setup(files, writes)

    _push_inboxes(files, now)

    # 3a. things this computer sends to the phone, tablet, TV …
    _deliver_out(files, writes)

    # 3c. the picture gallery
    try:
        cloud_g = json.loads(files.get("images.json") or "[]")
    except Exception:
        cloud_g = []
    with _state["lock"]:
        new_g, _state["img_new"] = _state["img_new"], []
    merged_g = merge_gallery(cloud_g if isinstance(cloud_g, list) else [], new_g)
    _state["gallery"] = merged_g
    if new_g:
        writes["images.json"] = json.dumps(merged_g, ensure_ascii=False)

    # 3b. reminders, shared by every device
    _sync_reminders(files, writes, now)

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
                local.setdefault("_deleted", {}).update({k: _now() for k in gone})
            # added here since the last sync: a re-add beats an older deletion
            # (desktop entries carry only a date, so the timestamps can't tell)
            fresh = keys_now - prev
            if fresh and isinstance(cloud.get("_deleted"), dict):
                cloud["_deleted"] = {k: t for k, t in cloud["_deleted"].items() if k not in fresh}
        _state["local_keys"] = keys_now
        merged = merge_memory(local, cloud)
        local_norm = {c: {k: _entry(v) for k, v in local.get(c, {}).items()} for c in _CATS}
        if (any(merged.get(c, {}) != local_norm[c] for c in _CATS)
                or merged.get("_deleted", {}) != local.get("_deleted", {})):
            _save_local_categories(merged)
            _state["local_keys"] = {f"{c}/{k}" for c in _CATS for k in merged.get(c, {})}
        if merged != cloud:
            writes["memory.json"] = json.dumps(merged, ensure_ascii=False)

    # 4b. this computer's projects, so the phone can tell how they are going
    if _state.get("last_projects", 0.0) + MEMORY_EVERY < now:
        _state["last_projects"] = now
        summary = json.dumps({"computer": device_name(), "projects": projects_summary()}, ensure_ascii=False)
        if summary != (files.get(f"projects-{me}.json") or ""):
            writes[f"projects-{me}.json"] = summary

    # 4b2. the conversation archive (every few minutes)
    try:
        _archive_flush(token, files, now)
    except Exception as exc:
        _log(f"[Sync] archive: {exc}")

    # 4c. a device's battery is running out: the voice says so, once
    _battery_watch(me)

    # 5. heartbeat
    if now - _state["last_beat"] > HEARTBEAT_EVERY:
        _state["last_beat"] = now
        info = {"id": me, "name": device_name(), "kind": "pc", "os": platform.system(),
                "seen": _now(), "commands": True, "active": _state["active"],
                "claim": _state["claim"], **health()}
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
            _log(f"[Sync] owner callback: {exc}")


# ── things sent to this computer (a picture, code, a link) ───────────────────
_ITEM_KINDS = ("image", "code", "text", "open", "screenshot")


def on_item(fn) -> None:
    """fn(kind, path_or_url, title, text) — show what another device sent."""
    _state["on_item"] = fn


def _reply(cid: str, text: str) -> None:
    with _state["lock"]:
        _state["pending"].append({"id": cid, "at": time.time(), "reply": text})


def _received_dir() -> Path:
    for base in (Path.home() / "Documents", Path.home() / "Belgeler", Path.home() / "Desktop", Path.home()):
        if base.exists():
            d = base / "JARVIS" / "Gelenler"
            try:
                d.mkdir(parents=True, exist_ok=True)
                return d
            except OSError:
                continue
    d = Path(__file__).resolve().parent.parent / "received"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(name: str, default: str) -> str:
    import re
    n = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(name or "")).strip(" ._")
    return (n or default)[:80]


def _show(kind: str, target: str, title: str, text: str = "") -> None:
    cb = _state.get("on_item")
    if cb:
        try:
            cb(kind, target, title, text)
        except Exception as exc:
            _log(f"[Sync] show: {exc}")


def _receive_item(cid: str, cmd: dict, sender: str) -> None:
    kind, title = cmd.get("kind"), str(cmd.get("title") or "")
    try:
        if kind == "open":
            url = str(cmd.get("url") or "")
            if not url.lower().startswith(("http://", "https://")):
                return _reply(cid, "Geçerli bir adres değil.")
            import webbrowser
            webbrowser.open(url)
            _show("open", url, title or url)
            return _reply(cid, f"Bilgisayarda açıldı: {title or url}")
        if kind in ("code", "text"):
            body = str(cmd.get("text") or "")
            name = _safe_name(cmd.get("filename") or title, "kod.txt" if kind == "code" else "not.txt")
            path = _received_dir() / name
            if path.exists():
                path = path.with_name(f"{path.stem}_{time.strftime('%H%M%S')}{path.suffix}")
            path.write_text(body, encoding="utf-8")
            _show(kind, str(path), f"{sender}: {name}", body)
            return _reply(cid, f"Bilgisayara kaydedildi ve ekranda: {path}")
        if kind == "screenshot":
            threading.Thread(target=_send_screenshot, args=(cid, cmd), daemon=True, name="sync-shot").start()
            return
        if kind == "image":
            threading.Thread(target=_receive_image, args=(cid, cmd, sender), daemon=True,
                             name="sync-image").start()
            return
    except Exception as exc:
        _reply(cid, f"Bilgisayar alamadı: {exc}")


def _queue_to(dev_id: str, cmd: dict) -> None:
    item = dict(cmd)
    item.update({"id": f"{device_id()}-{int(time.time() * 1000):x}", "from": device_name(), "ts": _now()})
    with _state["lock"]:
        _state["out_cmds"].append((dev_id, item))


def deliver_to_voice(title: str, text: str) -> str:
    """When another device has the voice (the user is on the phone), send a
    finished result there: it shows it and says the headline. Returns the
    device name, or "" when this computer has the voice or nothing is linked."""
    owner = _state.get("owner")
    if not owner or owner == device_id() or not settings().get("gist_id"):
        return ""
    dev = next((d for d in devices() if d.get("id") == owner), None)
    if not dev or dev.get("kind") == "pc":
        return ""
    _queue_to(owner, {"kind": "report", "title": str(title)[:200], "text": str(text)[:20000]})
    return str(dev.get("name") or "")


def _send_screenshot(cid: str, cmd: dict) -> None:
    """The phone asked to see this computer's screen: a picture of it goes
    back to that device, which shows it and lets its brain look at it."""
    import base64
    try:
        from core import remote_control
        data = remote_control.screenshot_jpeg(1400, 65)
        target = str(cmd.get("reply_to") or "")
        if not data:
            return _reply(cid, "Ekran görüntüsü alınamadı.")
        if not target:
            return _reply(cid, "Görüntüyü kime göndereceğimi bilmiyorum.")
        _queue_to(target, {"kind": "image", "data": base64.b64encode(data).decode(), "mime": "image/jpeg",
                           "title": f"{device_name()} ekranı, {time.strftime('%H:%M')}", "see": True,
                           "question": str(cmd.get("question") or "")})
        _reply(cid, "Ekran görüntüsü gönderildi; birkaç saniyede gelir.")
    except Exception as exc:
        _reply(cid, f"Ekran görüntüsü gönderilemedi: {exc}")


def _receive_image(cid: str, cmd: dict, sender: str) -> None:
    import base64
    try:
        from core import image_studio
        data, mime = b"", str(cmd.get("mime") or "image/png")
        if cmd.get("data"):
            data = base64.b64decode(cmd["data"])
        elif str(cmd.get("url") or "").startswith("https://"):
            req = urllib.request.Request(cmd["url"], headers={"User-Agent": "JARVIS/1.0"})
            with urllib.request.urlopen(req, timeout=150) as r:
                mime = (r.headers.get("Content-Type") or mime).split(";")[0]
                data = r.read()
        if len(data) < 100:
            return _reply(cid, "Resim bilgisayara gelmedi.")
        ext = {"image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
        prompt = str(cmd.get("prompt") or cmd.get("title") or "")
        path = image_studio.out_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}_{_safe_name(sender, 'cihaz')}{ext}"
        path.write_bytes(data)
        # remembered like one drawn here, so "değiştir" works on it too
        image_studio._remember(path, prompt or f"{sender} gönderdi", en=cmd.get("en") or "",
                               seed=cmd.get("seed") or None, url=cmd.get("url") or "",
                               engine="free" if cmd.get("url") else "received")
        _show("image", str(path), f"{sender} gönderdi" + (f": {prompt[:60]}" if prompt else ""))
        _reply(cid, f"Resim bilgisayara kaydedildi ve ekranda: {path}")
    except Exception as exc:
        _reply(cid, f"Resim bilgisayara kaydedilemedi: {exc}")


def _run_command(cid: str, text: str, sender: str) -> None:
    text = text.strip()
    if not text:
        return
    if text.startswith("update:"):
        cb = _state.get("on_update")
        reply = "Güncelleme başladı; MAYK kendini yeniden açacak." if cb else "Güncelleme burada başlatılamıyor."
        with _state["lock"]:
            _state["pending"].append({"id": cid, "at": time.time(), "reply": reply})
        if cb:
            try:
                cb()
            except Exception:
                pass
        return
    if text.startswith("adb:"):
        # the phone's projector/TV remote: "adb:key:up", "adb:app:youtube", "adb:type:…", "adb:url:…"
        def go():
            try:
                from core import adb_control as A
                _, kind, arg = (text.split(":", 2) + ["", ""])[:3]
                dev = ""                        # the projector/TV used last
                fn = {"key": lambda: A.press(arg, dev), "app": lambda: A.open_app(arg, dev),
                      "type": lambda: A.type_text(arg, dev, True), "url": lambda: A.open_url(arg, dev),
                      "search": lambda: A.search(arg, "youtube", dev)}.get(kind)
                ok, msg = fn() if fn else (False, "bilinmeyen kumanda komutu")
            except Exception as exc:
                msg = f"Kumanda: {exc}"
            with _state["lock"]:
                _state["pending"].append({"id": cid, "at": time.time(), "reply": msg})
        threading.Thread(target=go, daemon=True, name="sync-adb").start()
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
    """The link that sets up the web MAYK on another device in one tap."""
    import base64
    s = settings()
    payload = {"g": gemini_key or "", "t": s.get("github_token", ""), "i": s.get("gist_id", ""),
               "n": _assistant_name()}
    blob = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode().rstrip("=")
    return f"{WEB_URL}#s={blob}"


def _assistant_name() -> str:
    try:
        from memory.config_manager import get_assistant_name
        return get_assistant_name() or "MAYK"
    except Exception:
        return "MAYK"
