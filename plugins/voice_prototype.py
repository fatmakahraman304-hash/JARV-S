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
        "Use mode=undo to restore the previous version when asked to undo a revision. "
        "Do not use for security exploits, intrusion, malware or offensive automation."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "mode": {"type": "STRING", "enum": ["create", "undo"]},
        "format": {"type": "STRING", "enum": ["web", "object", "python"]},
        "instruction": {"type": "STRING"},
        "revise": {"type": "BOOLEAN"},
    }, "required": ["format"]},
}


def save_draft(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".previous")
        temp_backup = backup.with_suffix(backup.suffix + ".tmp")
        temp_backup.write_bytes(path.read_bytes())
        temp_backup.replace(backup)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def run(parameters, player=None, session_memory=None):
    mode = parameters.get("mode", "create")
    format_name = parameters.get("format")
    instruction = parameters.get("instruction")
    if mode not in {"create", "undo"} or format_name not in _FORMATS:
        return "Web, Python veya 3D obje türünü seç."
    if mode == "create" and (not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 4000):
        return "Prototip türünü ve ne yapmasını istediğini belirt."
    if not player:
        return "Prototip sonucunu göstermek için FRIDAY arayüzü gerekli."
    if not _LOCK.acquire(False):
        return "Önceki prototip işlemi devam ediyor."

    def work():
        try:
            extension, spec = _FORMATS[format_name]
            path = _ROOT / f"prototype.{extension}"
            if mode == "undo":
                previous_path = path.with_suffix(path.suffix + ".previous")
                if not previous_path.is_file():
                    raise ValueError("Geri alınacak önceki prototip bulunamadı.")
                text = previous_path.read_text(encoding="utf-8")
                save_draft(path, text)
                player.write_log(f"PROTOTİP: Önceki sürüm geri yüklendi · {path}")
                if extension == "html" and callable(getattr(player, "show_prototype", None)):
                    player.show_prototype(text)
                else:
                    player.show_content("Prototip geri yüklendi", str(path))
                return
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
            if extension == "obj":
                from core.holo_desk import parse_obj
                parse_obj(text)
            save_draft(path, text)
            player.write_log(f"PROTOTİP: {path}")
            if extension == "html" and callable(getattr(player, "show_prototype", None)):
                player.show_prototype(text)
            elif extension == "obj" and callable(getattr(player, "show_holo_object", None)):
                result=player.show_holo_object(text)
                if result.get("status")!="done":
                    player.write_log(f"PROTOTİP: Dosya kaydedildi; 3D gösterim {result.get('status','unverified')}: {result.get('error','doğrulanamadı')}")
            else:
                player.show_content("Prototip hazır", f"{path}\n\nÇalıştırmak veya açmak için dosyayı incele.\n\n{text[:2500]}")
        except Exception as exc:
            player.write_log(f"PROTOTİP: {exc}")
            player.show_content("Prototip tamamlanamadı", str(exc))
        finally:
            _LOCK.release()

    try:
        threading.Thread(target=work, daemon=True, name="aether-prototype").start()
    except RuntimeError:
        _LOCK.release()
        return "Prototip işlemi başlatılamadı. Tekrar deneyebilirsiniz."
    return "Prototip işlemi başladı. Sonuç FRIDAY’ta görünecek."
