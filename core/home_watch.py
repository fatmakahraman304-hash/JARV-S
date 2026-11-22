"""
The house, watched — "Ön kapı açıldı, efendim." / "Mutfakta su kaçağı algılandı!"

When Home Assistant is connected (plugins/smart_home.py), AETHER keeps an eye on
the sensors that matter and says when they change:

  * doors, windows and the garage door opening or closing;
  * smoke, gas, water leak and carbon monoxide — these are ALARMS: they are said
    even in quiet mode and also sent to the phone, because a leak does not wait
    for a meeting to end.

Only the change is said, once; the first look after starting just learns the
current state. The kinds can be switched off (home_alerts off doors).
"""
from __future__ import annotations

OPENINGS = ("door", "window", "garage_door", "opening")
ALARMS = ("smoke", "gas", "moisture", "carbon_monoxide", "safety")
ALARM_NAMES = {"smoke": "smoke", "gas": "gas", "moisture": "a water leak", "carbon_monoxide": "carbon monoxide",
               "safety": "a safety problem"}


def settings() -> dict:
    out = {"doors": True, "alarms": True, "presence": True}
    try:
        from memory.config_manager import get_plugin_config
        cfg = get_plugin_config("home_alerts") or {}
        out.update({k: bool(cfg[k]) for k in out if k in cfg})
    except Exception:
        pass
    return out


def watched(states: list[dict]) -> dict[str, dict]:
    """{entity_id: {"name", "class", "state"}} for the binary sensors worth watching, and people."""
    out = {}
    for e in states or []:
        eid = str(e.get("entity_id", ""))
        if eid.startswith("person."):
            a = e.get("attributes") or {}
            out[eid] = {"name": str(a.get("friendly_name") or eid), "class": "person", "state": e.get("state")}
            continue
        if not eid.startswith("binary_sensor."):
            continue
        a = e.get("attributes") or {}
        cls = str(a.get("device_class") or "")
        if cls in OPENINGS or cls in ALARMS:
            out[eid] = {"name": str(a.get("friendly_name") or eid), "class": cls, "state": e.get("state")}
    return out


def diff(before: dict, after: dict, cfg: dict | None = None) -> list[tuple[str, str]]:
    """[(severity, text)] for what changed; severity 'alarm' or 'info'."""
    cfg = cfg or settings()
    notes = []
    for eid, now in after.items():
        was = before.get(eid)
        if was is None or was["state"] == now["state"] or now["state"] in ("unavailable", "unknown"):
            continue
        if was["state"] in ("unavailable", "unknown"):
            continue                       # coming back online is not an event
        cls, name, on = now["class"], now["name"], now["state"] == "on"
        if cls == "person":
            if not cfg.get("presence", True):
                continue
            if now["state"] == "home":
                notes.append(("arrive", f"{name} arrived home."))
            elif was["state"] == "home":
                notes.append(("leave", f"{name} left home."))
            continue
        if cls in ALARMS and cfg.get("alarms", True):
            if on:
                notes.append(("alarm", f"ALARM: {name} detects {ALARM_NAMES.get(cls, cls)}."))
            else:
                notes.append(("info", f"{name} is clear again."))
        elif cls in OPENINGS and cfg.get("doors", True):
            notes.append(("info", f"{name} was {'opened' if on else 'closed'}."))
    return notes


class HomeWatch:
    def __init__(self):
        self.last: dict | None = None

    def tick(self, states: list[dict], cfg: dict | None = None) -> list[tuple[str, str]]:
        now = watched(states)
        if self.last is None:
            self.last = now
            return []
        notes = diff(self.last, now, cfg)
        self.last = now
        return notes


def lights_left_on(states: list[dict]) -> list[str]:
    """Names of lights and plugs still on — what someone leaving may have forgotten."""
    return [str((e.get("attributes") or {}).get("friendly_name") or e.get("entity_id"))
            for e in states or [] if str(e.get("entity_id", "")).split(".")[0] in ("light",)
            and e.get("state") == "on"]


def leaving_note(names: list[str], left_on: list[str], rain: dict | None = None) -> tuple[str, str] | None:
    """(title, body) for the phone when the user leaves with lights on or rain coming; None when nothing."""
    parts = []
    if left_on:
        shown = ", ".join(left_on[:5]) + (f" (+{len(left_on) - 5})" if len(left_on) > 5 else "")
        parts.append(f"açık kalan ışıklar — {shown}. Kapatmamı isterseniz söyleyin.")
    if rain:
        parts.append(f"Saat {rain['at']} civarı yağmur ihtimali %{rain['prob']}; şemsiye almak isteyebilirsiniz.")
    if not parts:
        return None
    return ("AETHER — evden çıktınız", f"{', '.join(names)}: " + " ".join(parts))


def instruction(notes: list[tuple[str, str]]) -> str:
    alarm = any(sev == "alarm" for sev, _ in notes)
    text = " ".join(t for _, t in notes)
    if any(sev == "arrive" for sev, _ in notes) and not alarm:
        return ("[WELCOME_HOME] " + text + " Greet them in your usual style — one "
                "short, warm sentence ('Eve hoş geldiniz, efendim.'); add one useful thing at most (something "
                "waiting, or the house's state). Do not call any tool.")
    if alarm:
        return ("[HOME_ALARM] " + text + " Tell the user at once, calmly and clearly, in one or two sentences "
                "(e.g. 'Efendim, mutfakta su kaçağı algılandı.'), and offer the obvious step (turning a valve "
                "or device off through smart_home, if there is one).")
    return ("[ENVIRONMENT] " + text + " Mention it the way AETHER would — one short sentence "
            "('Ön kapı açıldı, efendim.'). Do not call any tool.")
