"""FRIDAY HUD presentation of conversation and microphone permission.

This is display logic, not a permission gate or a connection health probe.
Local wake detection is independent of cloud microphone permission.
"""
from __future__ import annotations


def realtime_mic_permitted(config):
    from providers.realtime_settings import enabled
    return enabled(config.get("cloud_consent")) and enabled(config.get("microphone"))


def presentation(state, *, realtime=False, mic_permitted=True, muted=False, ptt=False):
    state = str(state or "INITIALISING").upper()
    if not realtime:
        return state, ("MİKROFON · KAPALI", "MUTED_C") if muted else ("MİKROFON · AÇIK", "GREEN")
    if not mic_permitted:
        mic = ("SES AKTARIMI · KAPALI", "MUTED_C")
    elif muted:
        mic = ("MİKROFON · SESSİZ", "MUTED_C")
    elif state == "SLEEPING":
        mic = ("SES AKTARIMI · BEKLEMEDE", "PRI")
    elif ptt:
        mic = ("MİKROFON · BAS-KONUŞ", "PRI")
    else:
        mic = ("SES AKTARIMI · İZİNLİ", "GREEN")
    if state in ("LISTENING", "IDLE", "ONLINE"):
        if muted:
            state = "MUTED"
        elif not mic_permitted:
            state = "TEXT_READY"
        elif ptt:
            state = "PTT_READY"
    return state, mic
