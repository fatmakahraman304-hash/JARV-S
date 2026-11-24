"""Türkçe öncelikli, yalnızca açıkça belirtilen AETHER uygulama komutları.

Komutlar hem ses dökümünden hem de yazılı girişten gelir. Burada yalnızca
AETHER uygulamasını kapatan kesin ifadeler eşleştirilir; "bilgisayarı kapat",
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
    "aether uygulamasini kapat",
    "aether uygulamasini kapatir misin",
    "aether uygulamasini kapatin",
    "aether uygulamasini kapat lutfen",
    "lutfen aether uygulamasini kapat",
    "aether uygulamasindan cik",
    "aether programini kapat",
    "aether programindan cik",
    "aether i kapat",
    "aether i kapatir misin",
    "aetheri kapat",
    "aetheri kapatir misin",
    "aether kapat kendini",
    "aether kendini kapat",
    "aether kapan",
    "aether cik",
    "aether cikis yap",
    "aethertan cik",
    "aether tan cik",
    "aether i sonlandir",
    "aetheri sonlandir",
    "uygulamadan cik",
    "programdan cik",
    # Eski komutları kullananlar için geriye dönük uyumluluk.
    "close the aether app",
    "quit aether",
}


def is_close_command(text: str) -> bool:
    """Yalnızca AETHER'ı kapatma niyeti açık olan tam komutları kabul et."""
    command = normalize_command(text)
    # Legacy name remains a valid explicit command during the FRIDAY upgrade.
    return command in _CLOSE_COMMANDS or command in {
        c.replace("aether", "friday") for c in _CLOSE_COMMANDS
    }
