"""Shared, local-only interpretation of short replies; never authorizes actions."""
import re
from core.voice_commands import normalize_command

FOLLOWUPS = frozenset((
    "devam et", "devam", "kaldigin yerden devam et", "onu degistir", "bunu degistir",
    "bunu duzelt", "onu duzelt", "daha kisa", "daha kisa yap", "daha detayli",
    "daha detayli yap", "bir daha dene", "tekrar dene", "bunlari da ekle",
    "bunlari da kodla", "bunu da yap", "bunu da ekle", "boyle boyle gelistir",
    "continue", "keep going", "make it shorter", "make it longer", "try again",
    "revise it", "do that too",
))
_CONTEXT_REPLIES = frozenset((
    "sadece sonucu ver", "sadece sonuc", "daha ayrintili", "biraz daha detayli",
    "orneklendir", "ornek ver", "ayni sekilde", "ayni sekilde devam et",
    "devamini getir", "durmadan devam et", "bunu da ekle", "daha basit anlat",
    "bunu yeniden hesapla", "tekrar hesapla", "sonucu kontrol et",
    "yeniden hesapla", "sadece hesapla",
))
_NUMBER_REPLY = re.compile(r"^\s*[+-]?\d+(?:[.,]\d+)?\s*$")
_QUANTITY_REPLY = re.compile(
    r"^[+-]?\d+(?:[.,]\d+)?\s*(?:kisi|porsiyon|adet|dakika|saat|gun|hafta|ay|yil|"
    r"gram|kilogram|kg|litre|ml|tl|lira|euro|dolar)(?:\s+(?:icin|olsun|olarak))?$")


def text_content(content):
    if isinstance(content, list):
        content = " ".join(p["text"] for p in content if isinstance(p, dict)
                           and p.get("type") == "text" and isinstance(p.get("text"), str))
    return content if isinstance(content, str) else ""


def is_continuation(raw):
    if not isinstance(raw, str) or not raw.strip() or raw.lstrip().startswith("["):
        return False
    raw = raw[:16000]
    value = normalize_command(raw)
    return (value in FOLLOWUPS or value in _CONTEXT_REPLIES
            or bool(_NUMBER_REPLY.fullmatch(raw))
            or bool(_QUANTITY_REPLY.fullmatch(value)))
