"""Mayk checks itself: "kendini kontrol et", "bir sorun var mı?", "neden çalışmıyor?".

Every check really tries the thing (reaches the model, opens the network, finds
the microphone …), each within a few seconds, all at once; the report says what
works, what does not, and the concrete fix for each problem.
"""
from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import json
import os
import shutil
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLUGIN = {
    "name": "self_check",
    "description": (
        "Mayk checks itself end to end: the AI model and API key, internet, microphone and speakers, disk space, "
        "memory file, plugins, Blender and its live link, key packages, recent errors, background watchers, smart home — each really tested, with a fix for "
        "every problem. Use for 'kendini kontrol et', 'sistem kontrolü', 'bir sorun var mı?', 'neden çalışmıyor?'; "
        "action=errors for 'son hataları göster', 'neden kapandı?', 'dün ne hata oldu?'."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "check (default) | errors — the last problems from Mayk's logbook "
                                                    "('son hataları göster', 'neden kapandı?')"},
    }},
}

OK, WARN, FAIL = "✅", "⚠️", "❌"


def check_model():
    from memory.config_manager import get_gemini_key
    if not (get_gemini_key() or os.environ.get("GEMINI_API_KEY")):
        return FAIL, "Yapay zekâ anahtarı yok", "Ayarlar → API anahtarı bölümüne Gemini anahtarını gir (aistudio.google.com)."
    from core import gemini
    t0 = time.monotonic()
    text = gemini.text("Reply with the single word: OK", tier=gemini.FAST)
    if text and "ok" in text.lower():
        return OK, f"Yapay zekâ yanıt veriyor ({(time.monotonic() - t0) * 1000:.0f} ms)", ""
    return FAIL, "Yapay zekâ yanıt vermedi", "Anahtarın geçerli mi ve kotası dolmuş mu kontrol et; internet bağlantısına bak."


def check_internet():
    for host in ("generativelanguage.googleapis.com", "www.google.com"):
        try:
            with socket.create_connection((host, 443), timeout=4):
                return OK, "İnternet bağlantısı var", ""
        except OSError:
            continue
    return FAIL, "İnternete ulaşılamıyor", "Wi-Fi / kablo bağlantısını ve güvenlik duvarını kontrol et."


def check_audio():
    try:
        import sounddevice as sd
    except Exception as exc:
        return FAIL, "Ses sistemi yüklenemedi", f"Ses kütüphanesi (PortAudio) eksik: {str(exc)[:80]}"
    try:
        devs = sd.query_devices()
        ins = [d for d in devs if d.get("max_input_channels", 0) > 0]
        outs = [d for d in devs if d.get("max_output_channels", 0) > 0]
    except Exception as exc:
        return FAIL, "Ses aygıtları okunamadı", str(exc)[:120]
    if not ins:
        return FAIL, "Mikrofon bulunamadı", "Mikrofonu tak ya da Windows Ayarlar → Gizlilik → Mikrofon iznini aç."
    if not outs:
        return FAIL, "Hoparlör bulunamadı", "Ses çıkış aygıtını kontrol et."
    try:
        di, do = sd.default.device
        name_in = sd.query_devices(di)["name"] if di is not None and di >= 0 else ins[0]["name"]
        name_out = sd.query_devices(do)["name"] if do is not None and do >= 0 else outs[0]["name"]
    except Exception:
        name_in, name_out = ins[0]["name"], outs[0]["name"]
    return OK, f"Mikrofon: {name_in}; hoparlör: {name_out}", ""


def check_disk():
    free = shutil.disk_usage(ROOT).free / (1 << 30)
    if free < 2:
        return FAIL, f"Diskte çok az yer kaldı ({free:.1f} GB)", "Gereksiz dosyaları sil; 'diski temizle' diyebilirsin."
    if free < 10:
        return WARN, f"Disk yeri azalıyor ({free:.1f} GB)", "Yakında yer açmak iyi olur."
    return OK, f"Diskte {free:.0f} GB boş yer var", ""


def check_memory():
    from memory import memory_manager as mm
    try:
        if mm.MEMORY_PATH.exists():
            data = json.loads(mm.MEMORY_PATH.read_text(encoding="utf-8"))
            n = sum(len(v) for v in data.values() if isinstance(v, dict))
            backup = "yedeği var" if mm.BACKUP_PATH.exists() else "henüz yedeği yok (ilk kayıtta oluşur)"
            return OK, f"Hafıza sağlam: {n} bilgi, {backup}", ""
        return OK, "Hafıza henüz boş", ""
    except Exception as exc:
        return WARN, f"Hafıza dosyası okunamadı ({str(exc)[:60]})", "Bir sonraki açılışta son sağlam kopyadan geri yüklenecek."


def check_plugins():
    bad = []
    files = [f for f in sorted((ROOT / "plugins").glob("*.py")) if not f.name.startswith("_")]
    for f in files:
        name = f"plugins.{f.stem}"
        if name in sys.modules:
            continue
        try:
            spec = importlib.util.find_spec(name)
            if spec is None:
                bad.append(f.stem)
        except Exception:
            bad.append(f.stem)
    if bad:
        return WARN, f"{len(files)} eklentiden {len(bad)} tanesi yüklenemedi: {', '.join(bad[:5])}", "Konsoldaki hata satırına bak."
    return OK, f"{len(files)} eklentinin hepsi yerinde", ""


def check_blender():
    try:
        from plugins import blender_studio
        exe = blender_studio.executable()
    except Exception:
        return WARN, "Blender bulunamadı", "İstersen 'Blender'ı kur' de."
    parts = [f"Blender bulundu"]
    try:
        from plugins import _blender_live as live
        parts.append("açık pencereye bağlı" if live.available() else "canlı bağlantı yok (Blender kapalı olabilir)")
    except Exception:
        pass
    try:
        from plugins import _blender_knowledge as know
        parts.append("bilgi bankası hazır" if know.API.is_file() else "bilgi bankası ilk komutta kurulacak")
    except Exception:
        pass
    return OK, "; ".join(parts) + f" ({Path(exe).name})", ""


def check_packages():
    need = {"PyQt6": "PyQt6", "google.genai": "google-genai", "numpy": "numpy", "cv2": "opencv-python",
            "PIL": "pillow", "psutil": "psutil"}
    missing = [pkg for mod, pkg in need.items() if importlib.util.find_spec(mod.split(".")[0]) is None
               or (mod == "google.genai" and importlib.util.find_spec("google.genai") is None)]
    py = f"Python {sys.version_info.major}.{sys.version_info.minor}"
    if missing:
        return FAIL, f"{py}; eksik paketler: {', '.join(missing)}", f"Komut satırında: pip install {' '.join(missing)}"
    return OK, f"{py}; temel paketler tam", ""


def check_errors():
    from core import logbook
    errs = logbook.recent_errors(hours=24, limit=5)
    if not errs:
        return OK, "Son 24 saatte kayda geçen hata yok", ""
    crashes = [e for e in errs if "ÇÖKME" in e]
    last = errs[-1][20:140]
    return (FAIL if crashes else WARN), f"Son 24 saatte {len(errs)} hata kaydı; en sonuncusu: {last}", \
        "Ayrıntı için 'son hataları göster' de."


NAMES = {"away": "siz-yokken takibi", "vigil": "mola notları", "sentinel": "çevre farkındalığı",
         "say_queue": "konuşma sırası"}


def check_watchers():
    from core import heartbeat
    st = heartbeat.status()
    started = {k: v for k, v in st.items() if v["age"] is not None or not v["ok"]}
    if not started:
        return OK, "Arka plan görevleri henüz başlamadı (oturum yeni ya da bağlı değil)", ""
    bad = [f"{NAMES.get(k, k)} ({v['why']})" for k, v in st.items() if not v["ok"]]
    if bad:
        return FAIL, "Duran arka plan görevi: " + ", ".join(bad), \
            "Mayk'ı yeniden başlat; tekrar ederse 'son hataları göster' de."
    return OK, f"{len(started)} arka plan görevi çalışıyor", ""


def check_home():
    from plugins import smart_home
    cfg = smart_home._cfg()
    if not (cfg.get("url") and cfg.get("token")):
        return OK, "Akıllı ev bağlı değil (isteğe bağlı)", ""
    try:
        n = len(smart_home._states())
        return OK, f"Home Assistant bağlı, {n} cihaz/sensör", ""
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == 401:
            return FAIL, "Home Assistant jetonu reddedildi", "Ayarlar → Bağlantılar → Akıllı ev: yeni jeton yapıştır."
        return FAIL, f"Home Assistant'a ulaşılamıyor ({str(getattr(exc, 'reason', exc))[:60]})", \
            "Home Assistant açık mı, bilgisayar aynı ağda mı?"


CHECKS = (("Yapay zekâ", check_model), ("İnternet", check_internet), ("Ses", check_audio), ("Disk", check_disk),
          ("Hafıza", check_memory), ("Eklentiler", check_plugins), ("Blender", check_blender), ("Paketler", check_packages),
          ("Hata kaydı", check_errors), ("Arka plan", check_watchers), ("Akıllı ev", check_home))


def run_checks(timeout: float = 12.0) -> list[tuple[str, str, str, str]]:
    out = []
    pool = cf.ThreadPoolExecutor(max_workers=len(CHECKS))       # not a `with`: a hung check must not be waited for
    futs = {pool.submit(fn): label for label, fn in CHECKS}
    done, _pending = cf.wait(futs, timeout=timeout)
    for fut, label in futs.items():
        if fut in done:
            try:
                mark, text, fix = fut.result()
            except Exception as exc:
                mark, text, fix = WARN, f"kontrol edilemedi ({str(exc)[:80]})", ""
        else:
            mark, text, fix = WARN, "zamanında yanıt vermedi", "Biraz sonra tekrar dene."
        out.append((label, mark, text, fix))
    pool.shutdown(wait=False, cancel_futures=True)
    order = [label for label, _ in CHECKS]
    return sorted(out, key=lambda r: order.index(r[0]))


def errors_report() -> str:
    from core import logbook
    errs = logbook.recent_errors(hours=72, limit=20)
    if not errs:
        return f"Son 3 günde günlükte hata yok. (Günlük: {logbook.path()})"
    return (f"Günlükteki son hatalar (en yenisi en altta; dosya: {logbook.path()}):\n" + "\n".join(errs) +
            "\n(Kullanıcıya teknik ayrıntıya boğmadan anlat: ne bozuldu, ne zaman, büyük ihtimalle neden, ne yapılmalı.)")


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        if str((parameters or {}).get("action") or "").lower() == "errors":
            report = errors_report()
            if player is not None and hasattr(player, "show_content"):
                player.show_content("Mayk günlüğü — son hatalar", report)
            return report
        rows = run_checks()
        lines = [f"{mark} {label}: {text}" + (f"\n    → {fix}" if fix else "") for label, mark, text, fix in rows]
        bad = [r for r in rows if r[1] != OK]
        head = "Her şey çalışıyor." if not bad else f"{len(bad)} konuda sorun var."
        report = head + "\n" + "\n".join(lines)
        if player is not None and hasattr(player, "show_content"):
            player.show_content("Mayk öz-denetim", report)
        return report + "\n(Kullanıcıya kısaca söyle: önce sorunları ve çözümlerini, sonra 'gerisi çalışıyor'.)"
    except Exception as exc:
        return f"Öz-denetim yapılamadı: {exc}"
