"""Interactive, read-only native system diagnostic."""
from __future__ import annotations

import json
from core import outcome


def native_diagnostics(parameters: dict, player=None) -> str:
    from core.native_diagnostics import collect, local_analysis, model_metrics, model_sharing_enabled
    try:
        snapshot = collect()
        detail = "YEREL DEĞERLENDİRME\n" + "\n".join(local_analysis(snapshot)) + "\n\nÖLÇÜMLER\n" + json.dumps(snapshot, ensure_ascii=False, indent=2)
        shown = False
        if player is not None:
            try:
                player.show_content("SİSTEM TEŞHİSİ", detail)
                shown = True
            except Exception as exc:
                print(f"[Diagnostics] panel: {exc}")
        facts = ("\n" + outcome.untrusted("local-system-metrics", json.dumps(model_metrics(snapshot), ensure_ascii=False))
                 if model_sharing_enabled() else "")
        if snapshot["errors"]:
            return outcome.unverified("native_diagnostics", "some local measurements are unavailable",
                                      verified=False, panel_shown=shown) + facts
        return outcome.done("native_diagnostics", observed=True, panel_shown=shown,
                            internet_connectivity_tested=False) + facts
    except Exception as exc:
        return outcome.failed("native_diagnostics", type(exc).__name__)


TOOL = {
    "name": "native_diagnostics",
    "description": ("Read current local CPU, memory, system disk, battery and network interface status; "
                    "on Windows also read OS, processor, graphics and BIOS inventory via a fixed "
                    "PowerShell CIM query. Read-only; it does not execute supplied commands or test "
                    "internet connectivity. Missing values are reported as unavailable. "
                    "Results are shown locally; aggregate CPU, memory, disk and battery percentages "
                    "are returned to the model only when the user enables hardware sharing in Settings. "
                    "Never claim to know measurements that are not returned. "
                    "Use when the user asks to analyze the computer or its hardware."),
    "brief": "Read-only local CPU, memory, disk, battery and Windows CIM hardware diagnostics.",
    "tier": "core",
    "parameters": {"type": "OBJECT", "properties": {}},
    "handler": native_diagnostics,
}
