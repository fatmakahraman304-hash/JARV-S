"""
memory/learner.py — AETHER learns about the user from the conversation itself.

Every so often (after a pause, or every ten things the user says) Gemini's
text model reads the latest conversation and files lasting facts about the
user into memory: who the people around them are, what they like, their
projects, important dates. Before this, something was remembered only when
the voice model happened to call save_memory.

Never health, religion, politics or money; never what is already known; at
most six facts a run. Memory syncs to every device (core/sync_hub), and the
web app does the same on the phone (web/app.js Learn).
"""

from __future__ import annotations

import threading

_CATS = ("identity", "preferences", "projects", "relationships", "wishes", "notes")
IDLE_SECONDS = 90.0
EVERY_USER_TURNS = 10

_lock = threading.Lock()


def _log(msg: str) -> None:
    try:
        print(msg)
    except Exception:                 # a Windows console that cannot print Turkish letters
        print(msg.encode("ascii", "replace").decode())
_buf: list[tuple[str, str]] = []
_timer: threading.Timer | None = None


def turn(role: str, text: str) -> None:
    """A line of the conversation on this computer."""
    global _timer
    text = str(text or "").strip()
    if not text:
        return
    user = str(role).lower().startswith(("kullan", "user"))
    with _lock:
        _buf.append(("user" if user else "aether", text[:600]))
        n_user = sum(1 for r, _ in _buf if r == "user")
        if _timer:
            _timer.cancel()
        if n_user >= EVERY_USER_TURNS:
            _timer = None
            threading.Thread(target=run, daemon=True, name="learner").start()
        else:
            _timer = threading.Timer(IDLE_SECONDS, run)
            _timer.daemon = True
            _timer.start()


def build_prompt(turns: list[tuple[str, str]], known: list[str]) -> str:
    convo = "\n".join(f"{'Kullanıcı' if r == 'user' else 'AETHER'}: {t}" for r, t in turns)[-6000:]
    return ("Aşağıdaki konuşmadan kullanıcı hakkında KALICI ve işe yarar yeni bilgileri çıkar (kim olduğu, "
            "ailesi ve yakınları, tercihleri, alışkanlıkları, projeleri, istekleri, önemli tarihler). Geçici "
            "şeyleri (bugünkü ruh hali, tek seferlik istekler), sağlık, din, siyaset, para bilgilerini ve zaten "
            "bilinenleri ALMA. Emin değilsen alma.\n"
            f"Kategoriler: {', '.join(_CATS)}. Bilinen anahtarlar: {', '.join(known)[:3000] or '(yok)'}\n"
            'Sadece JSON dizi döndür: [{"category":"...","key":"kısa_anahtar","value":"kısa değer"}] ya da [].\n\n'
            f"KONUŞMA:\n{convo}")


def apply(facts, memory: dict) -> dict:
    """The new facts as an update for memory_manager.update_memory."""
    update: dict = {}
    for f in (facts if isinstance(facts, list) else [])[:6]:
        if not isinstance(f, dict):
            continue
        cat = f.get("category") if f.get("category") in _CATS else "notes"
        key = str(f.get("key") or "").strip()[:60]
        val = str(f.get("value") or "").strip()[:300]
        if not key or not val:
            continue
        old = (memory.get(cat) or {}).get(key)
        old_val = old.get("value") if isinstance(old, dict) else old
        if old_val == val:
            continue
        update.setdefault(cat, {})[key] = {"value": val}
    return update


def run() -> int:
    """Learn from what is in the buffer now. Returns how many facts were filed."""
    with _lock:
        turns = list(_buf)
        _buf.clear()
    if sum(1 for r, _ in turns if r == "user") < 2:
        return 0
    try:
        from core import gemini
        from memory.memory_manager import load_memory, update_memory
        memory = load_memory() or {}
        known = [f"{c}/{k}" for c in _CATS for k in (memory.get(c) or {})]
        facts = gemini.as_json(build_prompt(turns, known), tier=gemini.FAST, default=[])
        update = apply(facts, memory)
        if update:
            update_memory(update)
            _log(f"[Learner] {sum(len(v) for v in update.values())} yeni bilgi öğrenildi")
        return sum(len(v) for v in update.values())
    except Exception as exc:
        _log(f"[Learner] {exc}")
        return 0
