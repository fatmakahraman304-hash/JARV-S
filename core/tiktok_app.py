"""Launch the TikTok application registered for the current Windows user."""

import os
import re
import subprocess
import sys


def launch_tiktok() -> str:
    if sys.platform != "win32":
        return "Kurulu TikTok uygulamasını açma Windows’ta kullanılabilir."

    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                "Get-StartApps -Name 'TikTok' -ErrorAction Stop | "
                "Where-Object { $_.Name -eq 'TikTok' } | Select-Object -ExpandProperty AppID",
            ],
            capture_output=True,
            check=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return "Windows’taki TikTok kaydı okunamadı. TikTok’u Başlat menüsünden açmayı dene."

    app_ids = {
        line.strip().decode("ascii")
        for line in result.stdout.splitlines()
        if re.fullmatch(rb"[A-Za-z0-9][A-Za-z0-9_.!{}-]{0,255}", line.strip())
    }
    if not app_ids:
        return "TikTok uygulaması bulunamadı. Önce Microsoft Store’dan TikTok’u yükle."
    if len(app_ids) != 1:
        return "Başlat menüsünde birden fazla TikTok uygulaması bulundu."

    try:
        os.startfile("shell:AppsFolder\\" + app_ids.pop())
    except OSError:
        return "TikTok başlatılamadı. TikTok’u Başlat menüsünden açmayı dene."
    return "TikTok’u açma isteği Windows’a iletildi."
