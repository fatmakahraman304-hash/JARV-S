"""Arrange explicitly selected windows, or politely close selected apps."""

from pathlib import Path
import sys
import threading

PLUGIN = {
    "name": "workspace_mode",
    "description": (
        "Windows workspace controls. For tasarım modu, arrange two already open apps. "
        "For oyun modu, ask which apps the user wants closed if they did not specify. "
        "Never infer what is expendable, close a system process, or claim improved FPS."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "mode": {"type": "STRING", "enum": ["design", "game"]},
        "main_app": {"type": "STRING", "description": "Primary app executable name, e.g. blender.exe"},
        "reference_app": {"type": "STRING", "description": "Reference app executable name, e.g. firefox.exe"},
        "close_apps": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Only apps explicitly named by the user."},
    }, "required": ["mode"]},
}


def _visible(name):
    from core import appidentity

    exact = Path(name).stem.casefold()
    return [
        entry for entry in appidentity.running(name)
        if Path(entry.name).stem.casefold() == exact and entry.titles and not entry.is_self
    ]


def arrange(main, reference):
    import win32api
    import win32con
    import win32gui
    from core.appidentity import _hwnds_for

    monitors = [win32api.GetMonitorInfo(item[0]) for item in win32api.EnumDisplayMonitors()]
    primary = [item for item in monitors if item["Flags"] & 1]
    secondary = [item for item in monitors if not item["Flags"] & 1]
    if not primary or not secondary:
        return "Tasarım düzeni için iki ekran gerekiyor."

    main_match, ref_match = _visible(main), _visible(reference)
    if len(main_match) != 1 or len(ref_match) != 1 or main_match[0].pid == ref_match[0].pid:
        return "İki farklı uygulama penceresi açık olmalı. Birden çok eşleşme varsa fazlasını kapat."

    windows = [_hwnds_for(entry.pid) for entry in (main_match[0], ref_match[0])]
    if any(len(handles) != 1 for handles in windows):
        return "Her uygulama için tek bir görünür pencere bırak."
    for handles, monitor in zip(windows, (primary[0], secondary[0])):
        hwnd = handles[0]
        left, top, right, bottom = monitor["Work"]
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(hwnd, 0, left, top, right-left, bottom-top,
                              win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        actual = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        if win32api.GetMonitorInfo(actual)["Monitor"] != monitor["Monitor"]:
            return "Pencerelerden biri beklenen ekrana taşınamadı."
    return f"{main} ana ekrana, {reference} ikinci ekrana yerleştirildi."


def close_selected(names):
    from core.appidentity import request_close

    lines = []
    for name in names:
        matches = _visible(name)
        if len(matches) != 1:
            lines.append(f"{name}: tek bir açık pencere bulunamadı.")
            continue
        closed, detail = request_close(matches[0])
        lines.append(f"{name}: kapandı." if closed else f"{name}: {detail}")
    return "\n".join(lines)


def run(parameters, player=None, session_memory=None):
    if sys.platform != "win32":
        return "Bu pencere düzeni Windows’ta çalışır."
    mode = parameters.get("mode")
    if mode == "design":
        names = [parameters.get("main_app"), parameters.get("reference_app")]
        handler = arrange
    elif mode == "game":
        names = parameters.get("close_apps")
        handler = close_selected
    else:
        return "Tasarım veya oyun modu seç."
    if not isinstance(names, list) or not 1 <= len(names) <= 5 or any(
        not isinstance(name, str) or not name.strip() or len(name) > 80 for name in names
    ):
        return "Taşınacak veya kapatılacak uygulamaların adlarını belirt."
    if player is None:
        return "Pencere işlemleri için JARVIS arayüzü gerekli."

    def work():
        try:
            result = handler(*names) if mode == "design" else handler(names)
        except Exception as exc:
            result = f"Pencere işlemi tamamlanamadı: {exc}"
        player.write_log("ÇALIŞMA ALANI: " + result)

    threading.Thread(target=work, daemon=True, name="jarvis-workspace").start()
    return "Pencere işlemi başladı. Sonuç etkinlik günlüğünde görünecek."
