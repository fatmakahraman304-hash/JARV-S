"""Schedule a source review and research briefing in the desktop routine engine."""

from datetime import datetime
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from core.routines.desktop import engine
from memory.config_manager import CONFIG_DIR

PLUGIN = {
    "name": "night_shift",
    "description": (
        "Schedule AETHER night work when the user asks for gece mesaisi. "
        "Ask for research topic or Git project path, night time and morning time as needed. "
        "Reviews pending changes and searches for articles, then opens a short morning report. "
        "Use show for the latest report and off to disable both routines."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "mode": {"type": "STRING", "enum": ["schedule", "show", "off"]},
        "topic": {"type": "STRING"},
        "folder": {"type": "STRING"},
        "night": {"type": "STRING", "description": "Local time HH:MM, default 02:00"},
        "morning": {"type": "STRING", "description": "Local time HH:MM, default 08:00"},
    }, "required": ["mode"]},
}


def _report_path():
    return CONFIG_DIR / "night_shift_report.txt"


def _run_git(folder, *args):
    return subprocess.run(
        ["git", "-C", str(folder), *args],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", timeout=25,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def build_report(options):
    lines = [f"Gece mesaisi · {datetime.now():%d.%m.%Y %H:%M}"]
    folder = options.get("folder")
    if folder:
        lines.append("Kod kontrolü")
        try:
            status = _run_git(folder, "status", "--short", "--untracked-files=no")
            check = _run_git(folder, "diff", "--check", "HEAD", "--")
            if status.returncode:
                lines.append("Git çalışma alanı okunamadı.")
            else:
                changed = status.stdout.strip().splitlines()
                lines.extend(changed[:7] or ["İzlenen dosyalarda bekleyen değişiklik yok."])
                if check.returncode == 0:
                    lines.append("Git biçim kontrolü geçti. Çalışma kopyasında işlev testi yapılmadı.")
                else:
                    lines.append("Git biçim kontrolünde uyarı var. Ayrıntıları git diff --check HEAD komutuyla incele.")
                if changed:
                    lines.append("Öneri: Değişen dosyalara odaklanan testleri çalıştır, ardından ölçümle yavaş bölümleri belirle.")
        except (OSError, subprocess.TimeoutExpired):
            lines.append("Git çalıştırılamadı veya süre doldu.")
    if topic := options.get("topic"):
        lines.append(f"Araştırma · {topic}")
        try:
            from actions.web_search import _ddg_news
            articles = _ddg_news(topic, max_results=4)
            seen = set()
            for article in articles:
                title = str(article.get("title") or "").strip()
                link = str(article.get("url") or "").strip()
                try:
                    parsed = urlsplit(link)
                except ValueError:
                    continue
                key = parsed._replace(fragment="").geturl()
                if not title or parsed.scheme not in {"https", "http"} or not parsed.hostname or key in seen:
                    continue
                seen.add(key)
                source = article.get("source") or parsed.hostname
                summary = " ".join(str(article.get("snippet") or "").split())[:260]
                lines.append("\n".join(part for part in (f"{title[:150]} · {str(source)[:65]}", summary, link) if part))
                if len(seen) == 4:
                    break
            if not seen:
                lines.append("Bu aramada geçerli bir kaynak adresi bulunamadı.")
        except Exception:
            lines.append("Araştırma servisine ulaşılamadı.")
    path = _report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n\n".join(lines), encoding="utf-8")
    tmp.replace(path)


def show_report(player):
    try:
        report = _report_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return "Gece mesaisi raporu henüz oluşmadı."
    if player:
        player.show_content("Sabah brifingi", report)
    else:
        return report
    return "Son gece mesaisi raporu hazır."


def run(parameters, player=None, session_memory=None):
    mode = parameters.get("mode")
    try:
        if mode == "show":
            return show_report(player)
        routines = engine()
        if routines is None:
            return "AETHER’ın görev zamanlayıcısı henüz hazır değil."
        if mode == "off":
            for name in ("night_review", "night_briefing"):
                if existing := routines.find_builtin(name):
                    routines.update(existing["id"], enabled=False)
            return "Gece mesaisi ve sabah brifingi kapatıldı."
        if mode != "schedule":
            return "Gece mesaisi için schedule, show veya off seç."
        topic = str(parameters.get("topic") or "").strip()[:160]
        folder = str(parameters.get("folder") or "").strip()
        if not topic and not folder:
            return "Araştırma konusunu veya Git proje klasörünü belirt."
        if folder:
            project = Path(folder).expanduser().resolve()
            if not (project / ".git").exists():
                return "Bir Git proje klasörü belirt."
            folder = str(project)
        night, morning = parameters.get("night", "02:00"), parameters.get("morning", "08:00")
        if not all(isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)
                   for value in (night, morning)):
            return "Saatleri 24 saat biçiminde, örneğin 02:00 ve 08:00 olarak gir."
        for name, label, at in (("night_review", "Gece mesaisi", night),
                                 ("night_briefing", "Sabah brifingi", morning)):
            trigger = {"type": "time", "rule": {"type": "weekly", "time": at, "days": list(range(1, 8))}}
            options = {"folder": folder, "topic": topic}
            if existing := routines.find_builtin(name):
                routines.update(existing["id"], enabled=True, trigger=trigger, options=options)
            else:
                routines.add(name=label, kind="builtin", builtin=name, trigger=trigger,
                             options=options, quiet=False, enabled=True)
        return f"Gece mesaisi {night}, sabah brifingi {morning} için kuruldu. Bilgisayar ve AETHER açık olmalı."
    except (ValueError, OSError) as exc:
        return f"Gece mesaisi ayarlanamadı: {exc}"
