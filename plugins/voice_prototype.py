"""Create or revise a single-file web, OBJ or Python draft."""

from pathlib import Path
import threading

from core import gemini
from memory.config_manager import BASE_DIR

_LOCK = threading.Lock()
_FORMATS = {
    "web": ("html", "one complete standalone HTML file with inline CSS/JS, no external requests"),
    "object": ("obj", "one valid Wavefront OBJ file with vertices and faces, no external materials"),
    "python": ("py", "one complete Python 3 file using only the standard library"),
}
_ROOT = BASE_DIR / "downloads" / "prototypes"

PLUGIN = {
    "name": "voice_prototype",
    "description": (
        "Create a benign web interface, 3D OBJ or Python prototype in the background. "
        "Use revise for a follow-up change to the last draft of the same format. "
        "Do not use for security exploits, intrusion, malware or offensive automation."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "format": {"type": "STRING", "enum": ["web", "object", "python"]},
        "instruction": {"type": "STRING"},
        "revise": {"type": "BOOLEAN"},
    }, "required": ["format", "instruction"]},
}


def run(parameters, player=None, session_memory=None):
    format_name = parameters.get("format")
    instruction = parameters.get("instruction")
    if format_name not in _FORMATS or not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 4000:
        return "Prototip türünü ve ne yapmasını istediğini belirt."
    if not player:
        return "Prototip sonucunu göstermek için JARVIS arayüzü gerekli."
    if not _LOCK.acquire(False):
        return "Önceki prototip işlemi devam ediyor."

    def work():
        try:
            extension, spec = _FORMATS[format_name]
            path = _ROOT / f"prototype.{extension}"
            previous = ""
            if parameters.get("revise"):
                if not path.is_file() or path.stat().st_size > 120_000:
                    raise ValueError("Revize edilecek prototip bulunamadı.")
                previous = path.read_text(encoding="utf-8")
            prompt = (
                f"Produce {spec}. Return only the file contents. "
                "Follow the user's request for a benign prototype. Refuse code enabling "
                "exploitation, intrusion, malware, or offensive automation. "
                f"\nUser request: {instruction}\nCurrent draft:\n{previous}"
            )
            text = (gemini.text(prompt, tier=gemini.SMART, timeout_ms=60_000) or "").strip()
            if text.startswith("```") and text.endswith("```"):
                text = text.partition("\n")[2][:-3].strip()
            if not text or len(text.encode("utf-8")) > 120_000:
                raise ValueError("Model kullanılabilir bir prototip döndürmedi.")
            if extension == "py":
                compile(text, str(path), "exec")
            elif extension == "html" and "<html" not in text.lower():
                raise ValueError("Model geçerli bir HTML belgesi döndürmedi.")
            elif extension == "obj" and not (
                any(line.startswith("v ") for line in text.splitlines()) and
                any(line.startswith("f ") for line in text.splitlines())
            ):
                raise ValueError("Model köşe ve yüz bilgisi içeren bir OBJ döndürmedi.")
            _ROOT.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
            player.write_log(f"PROTOTİP: {path}")
            if extension == "html" and callable(getattr(player, "show_prototype", None)):
                player.show_prototype(text)
            else:
                player.show_content("Prototip hazır", f"{path}\n\nÇalıştırmak veya açmak için dosyayı incele.\n\n{text[:2500]}")
        except Exception as exc:
            player.write_log(f"PROTOTİP: {exc}")
        finally:
            _LOCK.release()

    try:
        threading.Thread(target=work, daemon=True, name="jarvis-prototype").start()
    except Exception:
        _LOCK.release()
        raise
    return "Prototip arka planda hazırlanıyor. Sonuç JARVIS’te görünecek."
