"""Install a library JARVIS needs, after the user agreed ('evet kur').

Only packages from JARVIS's own dependency lists can be installed — the request
comes from a tool's error text, which must never choose an arbitrary package.
"""
from __future__ import annotations

PLUGIN = {
    "name": "install_package",
    "description": (
        "Install a missing Python package that one of JARVIS's own tools needs (offered after a tool failed with "
        "[MISSING_PACKAGE]). Call only after the user agreed. Only JARVIS's own dependencies can be installed."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "package": {"type": "STRING", "description": "The package named in [MISSING_PACKAGE]"},
    }, "required": ["package"]},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import installer
        pkg = str((parameters or {}).get("package") or "").strip()
        if not pkg:
            return "Hangi paketi kurayım?"
        log = (lambda m: player.write_log(m)) if player is not None and hasattr(player, "write_log") else None
        ok, msg = installer.install(pkg, log)
        if ok:
            return (msg + " Şimdi kullanıcının az önceki isteğini tekrar dene. Yine aynı hata çıkarsa JARVIS'in yeniden "
                    "başlatılması gerekiyor; bunu kullanıcıya söyle.")
        return msg
    except Exception as exc:
        return f"Paket kurulamadı: {exc}"
