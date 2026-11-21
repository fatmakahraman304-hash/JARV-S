"""
Smart home through Home Assistant — "MAYK, salonun ışığını aç", "klimayı 22 dereceye ayarla",
"film sahnesini başlat", "kapı kilitli mi?".

Home Assistant is the hub most smart devices already talk to (Hue, Tuya, Xiaomi, Shelly,
Sonoff, TVs, thermostats …), so one connection covers them all. MAYK uses its REST API
with a long-lived access token the user creates in Home Assistant (Profile → Security →
Long-lived access tokens). Both are stored through memory/config_manager like every other
setting; nothing leaves the home network.

Devices are found by the names the user calls them (friendly names, area names, Turkish
or not), never by raw entity ids. Locks and alarms are read freely but only changed when
the user names them explicitly — a fuzzy match never unlocks a door.
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.error
import urllib.request

PLUGIN = {
    "name": "smart_home",
    "description": (
        "Control and check smart home devices through Home Assistant: lights, plugs/switches, climate/AC, "
        "covers/blinds, fans, media players, scenes, scripts, locks, sensors. 'salonun ışığını aç', 'bütün "
        "ışıkları kapat', 'yatak odası lambasını yüzde 30 yap', 'klimayı 22 derece yap', 'perdeyi kapat', 'film "
        "sahnesini başlat', 'kapı kilitli mi', 'evde hangi ışıklar açık', 'içerisi kaç derece'. "
        "action: on | off | toggle | set | scene | state | list | setup | status. target: the device/room/scene "
        "as the user said it ('salon ışığı', 'yatak odası', 'film'). brightness: 0–100. temperature: degrees. "
        "position: 0–100 for covers. after_minutes / at (HH:MM): do it later ('yarım saat sonra ışıkları kapat', "
        "'saat 7'de perdeyi aç'); action=timers lists them, action=cancel_timers clears them. For setup: url (e.g. "
        "http://homeassistant.local:8123) and token."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "on | off | toggle | set | scene | state | list | setup | status | timers | cancel_timers"},
        "target": {"type": "STRING", "description": "device, room or scene name as the user said it; 'all lights' allowed"},
        "brightness": {"type": "NUMBER", "description": "light brightness percent 0–100"},
        "temperature": {"type": "NUMBER", "description": "climate target temperature"},
        "position": {"type": "NUMBER", "description": "cover position percent (0 closed, 100 open)"},
        "after_minutes": {"type": "NUMBER", "description": "do it later: in this many minutes ('10 dakika sonra kapat')"},
        "at": {"type": "STRING", "description": "do it later: at this time today/tomorrow, HH:MM ('saat 23'te kapat')"},
        "url": {"type": "STRING", "description": "setup: Home Assistant address"},
        "token": {"type": "STRING", "description": "setup: long-lived access token"},
    }, "required": ["action"]},
}

NS = "home_assistant"
TIMEOUT = 8
SENSITIVE = ("lock", "alarm_control_panel")
CONTROLLABLE = ("light", "switch", "fan", "climate", "cover", "media_player", "scene", "script",
                "input_boolean", "lock", "humidifier", "vacuum", "water_heater")
DOMAIN_WORDS = {
    "light": ("isik", "lamba", "ampul", "light", "lamp", "avize", "abajur", "led"),
    "switch": ("priz", "plug", "switch", "anahtar"),
    "climate": ("klima", "kombi", "termostat", "isitici", "ac", "thermostat", "heater"),
    "cover": ("perde", "panjur", "stor", "blind", "cover", "curtain", "garaj"),
    "fan": ("fan", "vantilator", "pervane"),
    "media_player": ("tv", "televizyon", "hoparlor", "speaker", "muzik"),
    "lock": ("kilit", "kilid", "lock"),
    "vacuum": ("supurge", "vacuum", "robot"),
}
ALL_WORDS = ("hepsi", "butun", "tum", "all", "every", "tamami", "evdeki")


# ── settings and HTTP ─────────────────────────────────────────────────────────

def _cfg() -> dict:
    try:
        from memory.config_manager import get_plugin_config
        return get_plugin_config(NS) or {}
    except Exception:
        return {}


def _request(method: str, path: str, body: dict | None = None, cfg: dict | None = None):
    cfg = cfg or _cfg()
    url, token = str(cfg.get("url") or "").rstrip("/"), str(cfg.get("token") or "")
    if not url or not token:
        raise LookupError("not set up")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else None


CANDIDATES = ("http://homeassistant.local:8123", "http://homeassistant:8123")


def discover(timeout: float = 2.5) -> str | None:
    """Home Assistant's address on this network, if it answers at a usual one (no token needed:
    its /manifest.json is public)."""
    for base in CANDIDATES:
        try:
            with urllib.request.urlopen(base + "/manifest.json", timeout=timeout) as resp:
                if resp.status == 200 and b"Home Assistant" in resp.read(4096):
                    return base
        except Exception:
            continue
    return None


def connect(url: str, token: str) -> tuple[bool, str]:
    """For the settings page: try, save on success. (ok, message)."""
    out = run({"action": "setup", "url": url, "token": token})
    return out.startswith("Connected"), out


def _states(cfg: dict | None = None) -> list[dict]:
    out = _request("GET", "/api/states", cfg=cfg)
    return out if isinstance(out, list) else []


def _call(domain: str, service: str, data: dict, cfg: dict | None = None):
    return _request("POST", f"/api/services/{domain}/{service}", data, cfg=cfg)


# ── finding what the user means ───────────────────────────────────────────────

def norm(text: str) -> str:
    t = str(text or "").replace("ı", "i").replace("İ", "i").lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", t).split())


def _stem(word: str) -> str:
    """Turkish endings off: 'salonun', 'salondaki', 'lambasını' → 'salo', 'lamb' (compared by prefix)."""
    return word[:max(3, len(word) - 3)] if len(word) > 4 else word


def _same(a: str, b: str) -> bool:
    if a == b:
        return True
    a, b = _stem(a), _stem(b)
    return len(min(a, b, key=len)) >= 3 and (a.startswith(b) or b.startswith(a))


def name_of(entity: dict) -> str:
    a = entity.get("attributes") or {}
    return str(a.get("friendly_name") or entity.get("entity_id", ""))


def domain_of(entity: dict) -> str:
    return str(entity.get("entity_id", "")).split(".", 1)[0]


def _is_type_word(w: str) -> str:
    """The domain a word names ('ışığı' → light), or ''."""
    for dom, keys in DOMAIN_WORDS.items():
        if any(w.startswith(k) for k in keys if len(k) >= 3) or w in keys:
            return dom
    return ""


def wanted_domains(target: str) -> set[str]:
    return {d for d in (_is_type_word(w) for w in norm(target).split()) if d}


_FILLER = {"the", "ve", "and", "bir", "de", "da", "mi", "mu", "acik", "kapali", "kalan", "olan"}


def match(target: str, entities: list[dict], domains: tuple[str, ...] = CONTROLLABLE) -> list[dict]:
    """The entities the user means, best first. 'Bütün ışıklar' → every light (optionally in a room)."""
    words = norm(target).split()
    if not words:
        return []
    every = any(w in ALL_WORDS for w in words)
    only_on = "acik" in words and ("kalan" in words or "olan" in words) or "left on" in norm(target)
    every = every or only_on                     # 'açık kalan ışıklar' = every light that is on
    doms = wanted_domains(target) & set(domains)
    content = [w for w in words if w not in ALL_WORDS and w not in _FILLER and not _is_type_word(w)]
    pool = [e for e in entities if domain_of(e) in domains and (not doms or domain_of(e) in doms)
            and (not only_on or e.get("state") == "on")]
    t = norm(target)
    for e in pool:
        if t == norm(name_of(e)):
            return [e]
    if not content:
        if not doms:
            return []
        return pool if (every or len(pool) == 1) else pool[:0]
    scored = []
    for e in pool:
        ew = norm(name_of(e)).split() + norm(e.get("entity_id", "").replace("_", " ").replace(".", " ")).split()
        hit = sum(1 for w in content if any(_same(w, x) for x in ew))
        if hit:
            scored.append((hit, len(name_of(e)), e))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], x[1]))
    if every:
        return [e for _, _, e in scored]
    return [scored[0][2]]


# ── what to say back ──────────────────────────────────────────────────────────

def describe(e: dict) -> str:
    a = e.get("attributes") or {}
    st = e.get("state")
    dom = domain_of(e)
    bits = [f"{name_of(e)}: {st}"]
    if dom == "light" and st == "on" and a.get("brightness") is not None:
        bits.append(f"{round(int(a['brightness']) * 100 / 255)}%")
    if dom == "climate":
        if a.get("current_temperature") is not None:
            bits.append(f"inside {a['current_temperature']}°")
        if a.get("temperature") is not None:
            bits.append(f"set to {a['temperature']}°")
    if dom == "cover" and a.get("current_position") is not None:
        bits.append(f"position {a['current_position']}%")
    if dom == "sensor" and a.get("unit_of_measurement"):
        bits[0] = f"{name_of(e)}: {st} {a['unit_of_measurement']}"
    return ", ".join(bits)


def _service_for(action: str, dom: str, params: dict) -> tuple[str, str, dict]:
    """(domain, service, extra data) for an on/off/toggle/set on an entity of `dom`."""
    if dom in ("scene",):
        return "scene", "turn_on", {}
    if dom == "script":
        return "script", "turn_on", {}
    if dom == "lock":
        return "lock", ("unlock" if action in ("off", "open") else "lock"), {}
    if dom == "cover":
        if params.get("position") is not None:
            return "cover", "set_cover_position", {"position": int(params["position"])}
        return "cover", {"on": "open_cover", "off": "close_cover"}.get(action, "toggle"), {}
    if dom == "climate":
        if params.get("temperature") is not None:
            return "climate", "set_temperature", {"temperature": float(params["temperature"])}
        return "climate", {"on": "turn_on", "off": "turn_off"}.get(action, "toggle"), {}
    if dom == "light" and params.get("brightness") is not None and action != "off":
        return "light", "turn_on", {"brightness_pct": max(0, min(100, int(params["brightness"])))}
    if dom == "vacuum":
        return "vacuum", ("start" if action == "on" else "return_to_base"), {}
    service = {"on": "turn_on", "off": "turn_off", "toggle": "toggle", "set": "turn_on"}.get(action, "toggle")
    return (dom if dom != "input_boolean" else "input_boolean"), service, {}


# ── later: "yarım saat sonra ışıkları kapat" ─────────────────────────────────
# Kept on disk and run by MAYK's background loop (main._watch_sentinel → run_due_timers),
# so a restart in between does not lose them.

def _timers_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / "memory" / "home_timers.json"


def _load_timers() -> list[dict]:
    try:
        data = json.loads(_timers_path().read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_timers(items: list[dict]) -> None:
    try:
        _timers_path().parent.mkdir(parents=True, exist_ok=True)
        _timers_path().write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


TIMER_GRACE = 30 * 60


def home_summary(states: list[dict] | None = None) -> str:
    """The house in a few lines, for the status report: lights on, open doors/windows, climate."""
    states = _states() if states is None else states
    lights = [name_of(e) for e in states if domain_of(e) == "light" and e.get("state") == "on"]
    opened = [name_of(e) for e in states if domain_of(e) == "binary_sensor"
              and (e.get("attributes") or {}).get("device_class") in ("door", "window", "garage_door", "opening")
              and e.get("state") == "on"]
    climate = [describe(e) for e in states if domain_of(e) == "climate"]
    locks = [describe(e) for e in states if domain_of(e) == "lock"]
    lines = ["- açık ışıklar: " + (", ".join(lights) if lights else "yok"),
             "- açık kapı/pencere: " + (", ".join(opened) if opened else "yok")]
    if climate:
        lines.append("- iklim: " + "; ".join(climate))
    if locks:
        lines.append("- kilitler: " + "; ".join(locks))
    return "\n".join(lines)


def when_from(p: dict, now: float | None = None) -> float | None:
    """The time a delayed command should run, or None to run it now."""
    import time as _t
    from datetime import datetime, timedelta
    now = _t.time() if now is None else now
    if p.get("after_minutes") not in (None, ""):
        return now + max(0.0, float(p["after_minutes"])) * 60
    at = str(p.get("at") or "").strip()
    m = re.match(r"^(\d{1,2})(?:[:.](\d{2}))?$", at)
    if not m:
        return None
    base = datetime.fromtimestamp(now)
    target = base.replace(hour=int(m.group(1)) % 24, minute=int(m.group(2) or 0), second=0, microsecond=0)
    if target.timestamp() <= now:
        target += timedelta(days=1)
    return target.timestamp()


def run_due_timers(now: float | None = None) -> list[str]:
    """Run every delayed command whose time has come; what each did."""
    import time as _t
    now = _t.time() if now is None else now
    items = _load_timers()
    due = [t for t in items if float(t.get("at", 0)) <= now]
    if not due:
        return []
    _save_timers([t for t in items if float(t.get("at", 0)) > now])
    out = []
    for t in due:
        if now - float(t.get("at", 0)) > TIMER_GRACE:
            # MAYK was off at that time: switching lights at a random later hour helps nobody
            out.append(f"Skipped (missed by {int((now - float(t['at'])) // 60)} min while MAYK was off): "
                       f"{t['params'].get('action')} {t['params'].get('target', '')}")
            continue
        params = dict(t.get("params") or {})
        params.pop("after_minutes", None)
        params.pop("at", None)
        out.append(run(params))
    return out


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        return _run(parameters or {})
    except LookupError:
        return ("Home Assistant is not connected yet. To connect: in Home Assistant open Profile → Security → "
                "Long-lived access tokens, create one, then give me the address (e.g. http://homeassistant.local:8123) "
                "and the token — typed, not spoken.")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return "Home Assistant refused the token (401). It may have been deleted; set it up again with a new one."
        return f"Home Assistant answered with an error ({exc.code})."
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"Could not reach Home Assistant ({getattr(exc, 'reason', exc)}). Is it on, and on this network?"
    except Exception as exc:
        return f"Smart home error: {exc}"


def _run(p: dict) -> str:
    action = str(p.get("action") or "status").strip().lower()
    target = str(p.get("target") or "").strip()

    if action == "timers":
        from datetime import datetime
        items = _load_timers()
        if not items:
            return "No delayed smart-home commands."
        return "\n".join(f"- {datetime.fromtimestamp(float(t['at'])):%H:%M}: {t['params'].get('action')} "
                         f"{t['params'].get('target', '')}" for t in sorted(items, key=lambda t: t["at"]))
    if action == "cancel_timers":
        n = len(_load_timers())
        _save_timers([])
        return f"Cancelled {n} delayed smart-home command(s)."
    if action in ("on", "off", "toggle", "set", "scene"):
        later = when_from(p)
        if later is not None:
            _cfg_ok = _cfg()
            if not (_cfg_ok.get("url") and _cfg_ok.get("token")):
                raise LookupError
            from datetime import datetime
            items = _load_timers()
            items.append({"at": later, "params": {k: v for k, v in p.items() if k not in ("token", "url")}})
            _save_timers(items)
            return f"Scheduled: {action} {target} at {datetime.fromtimestamp(later):%H:%M}."

    if action == "setup":
        url = str(p.get("url") or "").strip().rstrip("/")
        token = str(p.get("token") or "").strip()
        if not token:
            raise LookupError
        if not url:
            url = discover() or ""
            if not url:
                return ("I could not find Home Assistant on this network by itself "
                        "(tried homeassistant.local:8123). Give me its address, e.g. http://192.168.1.20:8123.")
        if not re.match(r"^https?://", url):
            url = "http://" + url
        cfg = {"url": url, "token": token}
        info = _request("GET", "/api/", cfg=cfg)          # proves address and token before saving
        from memory.config_manager import save_plugin_config
        save_plugin_config(NS, cfg)
        n = len(_states(cfg))
        return f"Connected to Home Assistant ({(info or {}).get('message', 'API running')}); {n} entities found."

    if action == "status":
        states = _states()
        on = [name_of(e) for e in states if domain_of(e) == "light" and e.get("state") == "on"]
        return (f"Home Assistant connected, {len(states)} entities. Lights on: "
                + (", ".join(on) if on else "none") + ".")

    states = _states()

    if action == "list":
        doms = wanted_domains(target) or {"light", "switch", "climate", "cover", "fan", "media_player", "lock"}
        rows = [describe(e) for e in states if domain_of(e) in doms]
        if target and not wanted_domains(target):
            rows = [describe(e) for e in match(target + " hepsi", states, tuple(doms))] or rows
        return ("\n".join(rows[:40]) + (f"\n… and {len(rows) - 40} more" if len(rows) > 40 else "")) or "No such devices."

    if action == "state":
        hits = match(target, states, CONTROLLABLE + ("sensor", "binary_sensor", "alarm_control_panel",
                                                      "weather", "person", "device_tracker"))
        if not hits:
            return f"No device called '{target}' in Home Assistant."
        return "\n".join(describe(e) for e in hits[:15])

    if action == "scene":
        hits = match(target, states, ("scene", "script"))
        if not hits:
            return f"No scene or script called '{target}'."
        e = hits[0]
        _call(domain_of(e), "turn_on", {"entity_id": e["entity_id"]})
        return f"Scene started: {name_of(e)}."

    if action not in ("on", "off", "toggle", "set"):
        return "Unknown action; use on, off, toggle, set, scene, state, list, setup or status."
    hits = match(target, states)
    if not hits:
        return f"No device called '{target}' in Home Assistant. Say 'evdeki cihazları listele' to hear the names."
    done = []
    for e in hits[:25]:
        dom = domain_of(e)
        if dom in SENSITIVE:
            # a door is unlocked only when the user named that very lock, never by a loose match
            if norm(target) not in (norm(name_of(e)), norm(e["entity_id"])) and len(hits) != 1:
                continue
            if action in ("off", "toggle") and not wanted_domains(target) & {"lock"}:
                continue
        domain, service, extra = _service_for(action, dom, p)
        _call(domain, service, {"entity_id": e["entity_id"], **extra})
        done.append(f"{name_of(e)} → {service.replace('_', ' ')}"
                    + (f" {extra.get('brightness_pct', extra.get('temperature', extra.get('position', '')))}"
                       if extra else ""))
    if not done:
        return "Nothing changed: locks and alarms are only changed when you name them exactly."
    return "Done: " + "; ".join(done) + "."
