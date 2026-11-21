"""Türkçe öncelikli, yalnızca açıkça belirtilen MAYK uygulama komutları.

Komutlar hem ses dökümünden hem de yazılı girişten gelir. Burada yalnızca
MAYK uygulamasını kapatan kesin ifadeler eşleştirilir; "bilgisayarı kapat",
"pencereyi kapat" gibi başka hedeflere dokunulmaz.
"""

import re
import unicodedata


def normalize_command(text: str) -> str:
    """Türkçe büyük/küçük harf, noktalama ve aksan farklarını eşitle."""
    value = (text or "").replace("İ", "i").replace("I", "ı").casefold()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ı", "i")
    return " ".join(re.findall(r"[^\W_]+", value, re.UNICODE))


_CLOSE_COMMANDS = {
    "mayk uygulamasini kapat",
    "mayk uygulamasini kapatir misin",
    "mayk uygulamasini kapatin",
    "mayk uygulamasini kapat lutfen",
    "lutfen mayk uygulamasini kapat",
    "mayk uygulamasindan cik",
    "mayk programini kapat",
    "mayk programindan cik",
    "mayk i kapat",
    "mayk i kapatir misin",
    "mayki kapat",
    "mayki kapatir misin",
    "mayk kapat kendini",
    "mayk kendini kapat",
    "mayk kapan",
    "mayk cik",
    "mayk cikis yap",
    "mayktan cik",
    "mayk tan cik",
    "mayk i sonlandir",
    "mayki sonlandir",
    "uygulamadan cik",
    "programdan cik",
    # Eski komutları kullananlar için geriye dönük uyumluluk.
    "close the mayk app",
    "quit mayk",
}


def is_close_command(text: str) -> bool:
    """Yalnızca MAYK'ı kapatma niyeti açık olan tam komutları kabul et."""
    return normalize_command(text) in _CLOSE_COMMANDS
