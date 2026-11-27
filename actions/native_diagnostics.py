"""Interactive, read-only native system diagnostic."""
from __future__ import annotations

import json
from core import outcome


def native_diagnostics(parameters: dict, player=None) -> str:
    from core.native_diagnostics import collect
    try:
        snapshot = collect()
        detail = json.dumps(snapshot, ensure_ascii=False, indent=2)
        if player is not None:
            try:
                player.show_content("SİSTEM TEŞHİSİ", detail)
            except Exception as exc:
                print(f"[Diagnostics] panel: {exc}")
        facts = outcome.untrusted("local-system-data", detail[:18000])
        if snapshot["errors"]:
            return outcome.unverified("native_diagnostics", "some local measurements are unavailable",
                                      verified=False, missing_sources=len(snapshot["errors"])) + "\n" + facts
        return outcome.done("native_diagnostics", observed=True, internet_connectivity_tested=False) + "\n" + facts
    except Exception as exc:
        return outcome.failed("native_diagnostics", f"{type(exc).__name__}: {str(exc)[:200]}")


TOOL = {
    "name": "native_diagnostics",
    "description": ("Read current local CPU, memory, system disk, battery and network interface status; "
                    "on Windows also read OS, processor, graphics and BIOS inventory via a fixed "
                    "PowerShell CIM query. Read-only; it does not execute supplied commands or test "
                    "internet connectivity. Missing values are reported as unavailable. "
                    "Use when the user asks to analyze the computer or its hardware."),
    "brief": "Read-only local CPU, memory, disk, battery and Windows CIM hardware diagnostics.",
    "tier": "core",
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": native_diagnostics,
}
