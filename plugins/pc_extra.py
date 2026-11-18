"""
Bilgisayar kontrolünün computer_control / computer_settings'te olmayan kısmı:

  windows    açık pencereleri listele; adıyla öne getir, küçült, büyüt, kapat
  processes  en çok işlemci/bellek kullanan programlar; adıyla kapat
  clipboard  panodakini oku ya da panoya yaz
  wifi       Wi-Fi ağlarını listele, bir ağa bağlan, bağlı ağı söyle (Windows)
  power      zamanlı kapat / yeniden başlat / uyku, ya da iptal — confirm=true şart
  info       işletim sistemi, işlemci, bellek, disk, pil, açık kalma süresi
"""

import platform
import subprocess
import sys
import time

PLUGIN = {
    "name": "pc_extra",
    "description": (
        "Bilgisayarı daha derin kontrol: "
        "windows (op: list | focus | minimize | maximize | close; name: pencere başlığından bir parça) | "
        "processes (op: top | kill; name) | clipboard (op: read | write; text) | "
        "wifi (op: list | connect | status; ssid, password) | "
        "power (op: shutdown | restart | sleep | cancel; minutes; confirm: kullanıcı açıkça onayladıysa true) | "
        "info. Kapatma/yeniden başlatma ve program kapatma için önce kullanıcıdan onay al."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "windows | processes | clipboard | wifi | power | info"},
            "op": {"type": "STRING"}, "name": {"type": "STRING"}, "text": {"type": "STRING"},
            "ssid": {"type": "STRING"}, "password": {"type": "STRING"},
            "minutes": {"type": "NUMBER"}, "confirm": {"type": "BOOLEAN"},
        },
        "required": ["action"],
    },
}

WIN = sys.platform == "win32"
_NOWIN = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if WIN else {}


def _sh(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, **_NOWIN)
        raw = r.stdout + r.stderr
        for enc in ("utf-8", "cp857", "cp1254", "latin-1"):
            try:
                return r.returncode, raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return r.returncode, raw.decode("utf-8", "replace")
    except Exception as exc:
        return 1, str(exc)


# ── windows ──────────────────────────────────────────────────────────────────

def _windows() -> list[tuple[int, str]]:
    if not WIN:
        return []
    import win32gui
    out = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h):
            t = win32gui.GetWindowText(h).strip()
            if t and t not in ("Program Manager", "Windows Input Experience"):
                out.append((h, t))
    win32gui.EnumWindows(cb, None)
    return out


def windows(op: str, name: str) -> str:
    if not WIN:
        return "Pencere yönetimi şimdilik yalnızca Windows'ta."
    import win32con
    import win32gui
    wins = _windows()
    if op in ("", "list"):
        return "Açık pencereler: " + "; ".join(t[:60] for _, t in wins[:25]) if wins else "Açık pencere yok."
    n = str(name or "").casefold()
    hit = next(((h, t) for h, t in wins if n and n in t.casefold()), None)
    if not hit:
        return f"'{name}' başlıklı pencere bulamadım."
    h, t = hit
    if op == "focus":
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(h)
        except Exception:
            pass
        return f"Öne getirildi: {t[:60]}"
    if op == "minimize":
        win32gui.ShowWindow(h, win32con.SW_MINIMIZE)
        return f"Küçültüldü: {t[:60]}"
    if op == "maximize":
        win32gui.ShowWindow(h, win32con.SW_MAXIMIZE)
        return f"Büyütüldü: {t[:60]}"
    if op == "close":
        win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
        return f"Kapatılıyor: {t[:60]} (kaydedilmemiş iş varsa program soracak)."
    return "Bilinmeyen pencere işlemi."


# ── processes ────────────────────────────────────────────────────────────────

_PROTECTED = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe", "services.exe",
              "lsass.exe", "svchost.exe", "explorer.exe", "dwm.exe", "python.exe", "pythonw.exe", "fontdrvhost.exe"}


def processes(op: str, name: str) -> str:
    import psutil
    if op in ("", "top"):
        procs = []
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                procs.append((p, p.cpu_percent(None)))
            except Exception:
                continue
        time.sleep(0.6)
        rows = []
        for p, _ in procs:
            try:
                rows.append((p.cpu_percent(None) / (psutil.cpu_count() or 1), p.info["memory_info"].rss / 2**20, p.info["name"]))
            except Exception:
                continue
        by_cpu = sorted(rows, reverse=True)[:5]
        by_mem = sorted(rows, key=lambda r: -r[1])[:5]
        return ("En çok işlemci: " + ", ".join(f"{n} %{c:.0f}" for c, _, n in by_cpu)
                + ". En çok bellek: " + ", ".join(f"{n} {m:.0f} MB" for _, m, n in by_mem) + ".")
    if op == "kill":
        n = str(name or "").casefold().strip()
        if not n:
            return "Hangi program?"
        if n in _PROTECTED or n + ".exe" in _PROTECTED:
            return f"{name} sistemin ya da JARVIS'in bir parçası; kapatmıyorum."
        killed = 0
        for p in psutil.process_iter(["name"]):
            pn = str(p.info.get("name") or "").casefold()
            if n in pn and pn not in _PROTECTED:
                try:
                    p.terminate()
                    killed += 1
                except Exception:
                    continue
        return f"{killed} işlem kapatıldı ({name})." if killed else f"'{name}' adında çalışan program yok."
    return "Bilinmeyen işlem."


# ── clipboard ────────────────────────────────────────────────────────────────

def clipboard(op: str, text: str) -> str:
    if WIN:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if op == "write":
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(str(text or ""), win32clipboard.CF_UNICODETEXT)
                return "Panoya yazıldı."
            try:
                data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            except Exception:
                data = ""
            return f"Panoda: {data[:3000]}" if data else "Pano boş (ya da yazı değil)."
        finally:
            win32clipboard.CloseClipboard()
    tool = ["pbcopy"] if sys.platform == "darwin" else ["xclip", "-selection", "clipboard"]
    if op == "write":
        try:
            subprocess.run(tool, input=str(text or "").encode(), timeout=5)
            return "Panoya yazıldı."
        except Exception as exc:
            return f"Panoya yazılamadı: {exc}"
    code, out = _sh(["pbpaste"] if sys.platform == "darwin" else tool + ["-o"])
    return f"Panoda: {out[:3000]}" if code == 0 and out else "Pano okunamadı."


# ── wi-fi (Windows: netsh) ───────────────────────────────────────────────────

def wifi(op: str, ssid: str, password: str) -> str:
    if not WIN:
        return "Wi-Fi yönetimi şimdilik yalnızca Windows'ta."
    if op in ("", "status"):
        code, out = _sh(["netsh", "wlan", "show", "interfaces"])
        ss = next((ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.strip().startswith("SSID") and "BSSID" not in ln), "")
        sig = next((ln.split(":", 1)[1].strip() for ln in out.splitlines() if "Sinyal" in ln or "Signal" in ln), "")
        return f"Bağlı ağ: {ss} ({sig})." if ss else "Wi-Fi'ye bağlı değil."
    if op == "list":
        code, out = _sh(["netsh", "wlan", "show", "networks"])
        names = [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.strip().startswith("SSID") and ln.split(":", 1)[1].strip()]
        return "Görünen ağlar: " + ", ".join(dict.fromkeys(names)) if names else "Ağ bulunamadı."
    if op == "connect":
        if not ssid:
            return "Hangi ağ?"
        code, out = _sh(["netsh", "wlan", "connect", f"name={ssid}"])
        if code != 0 and password:
            import tempfile
            from xml.sax.saxutils import escape
            prof = f"""<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
<name>{escape(ssid)}</name><SSIDConfig><SSID><name>{escape(ssid)}</name></SSID></SSIDConfig>
<connectionType>ESS</connectionType><connectionMode>auto</connectionMode><MSM><security><authEncryption>
<authentication>WPA2PSK</authentication><encryption>AES</encryption><useOneX>false</useOneX></authEncryption>
<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>{escape(password)}</keyMaterial></sharedKey>
</security></MSM></WLANProfile>"""
            with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
                f.write(prof)
            _sh(["netsh", "wlan", "add", "profile", f"filename={f.name}", "user=current"])
            code, out = _sh(["netsh", "wlan", "connect", f"name={ssid}"])
        return f"'{ssid}' ağına bağlanıyor." if code == 0 else f"Bağlanamadı: {out.strip()[:200]}"
    return "Bilinmeyen Wi-Fi işlemi."


# ── power ────────────────────────────────────────────────────────────────────

def power(op: str, minutes, confirm: bool) -> str:
    op = str(op or "").lower()
    if op == "cancel":
        if WIN:
            _sh(["shutdown", "/a"])
        else:
            _sh(["shutdown", "-c"])
        return "Zamanlı kapatma iptal edildi."
    if not confirm:
        return "Bunu yapmadan önce kullanıcıdan açık onay al, sonra confirm=true ile tekrar çağır."
    secs = max(0, int(float(minutes or 0) * 60))
    if op == "sleep":
        if WIN:
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], **_NOWIN)
        return "Bilgisayar uykuya geçiyor."
    if op in ("shutdown", "restart"):
        if WIN:
            code, out = _sh(["shutdown", "/s" if op == "shutdown" else "/r", "/t", str(max(secs, 30))])
        else:
            code, out = _sh(["shutdown", "-h" if op == "shutdown" else "-r", f"+{max(1, secs // 60)}"])
        what = "kapanacak" if op == "shutdown" else "yeniden başlayacak"
        return (f"Bilgisayar {max(secs, 30) // 60 or 'yarım'} dakika sonra {what}; iptal için 'kapatmayı iptal et' de."
                if code == 0 else f"Olmadı: {out[:200]}")
    return "Bilinmeyen güç işlemi."


def info() -> str:
    import psutil
    vm = psutil.virtual_memory()
    up = time.time() - psutil.boot_time()
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    try:
        disk = psutil.disk_usage("C:\\" if WIN else "/")
        dtxt = f"disk {disk.used / 2**30:.0f}/{disk.total / 2**30:.0f} GB"
    except Exception:
        dtxt = ""
    return (f"{platform.system()} {platform.release()}, işlemci {platform.processor() or platform.machine()} "
            f"({psutil.cpu_count()} çekirdek, şu an %{psutil.cpu_percent(0.3):.0f}), bellek {vm.used / 2**30:.1f}/"
            f"{vm.total / 2**30:.1f} GB, {dtxt}" + (f", pil %{bat.percent:.0f}{' şarjda' if bat.power_plugged else ''}" if bat else "")
            + f", {int(up // 3600)} saattir açık.")


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        p = parameters or {}
        a = str(p.get("action") or "info").lower()
        op = str(p.get("op") or "").lower()
        if a == "windows":
            return windows(op, str(p.get("name") or ""))
        if a == "processes":
            return processes(op, str(p.get("name") or ""))
        if a == "clipboard":
            return clipboard(op, str(p.get("text") or ""))
        if a == "wifi":
            return wifi(op, str(p.get("ssid") or ""), str(p.get("password") or ""))
        if a == "power":
            return power(op, p.get("minutes"), bool(p.get("confirm")))
        return info()
    except Exception as exc:
        return f"Olmadı: {exc}"
