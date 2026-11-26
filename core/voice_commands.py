"""Türkçe öncelikli, yalnızca açıkça belirtilen FRIDAY uygulama komutları.

Komutlar hem ses dökümünden hem de yazılı girişten gelir. Burada yalnızca
FRIDAY uygulamasını kapatan kesin ifadeler eşleştirilir; "bilgisayarı kapat",
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
    "friday uygulamasini kapat",
    "friday uygulamasini kapatir misin",
    "friday uygulamasini kapatin",
    "friday uygulamasini kapat lutfen",
    "lutfen friday uygulamasini kapat",
    "friday uygulamasindan cik",
    "friday programini kapat",
    "friday programindan cik",
    "friday i kapat",
    "friday i kapatir misin",
    "fridayi kapat",
    "fridayi kapatir misin",
    "friday kapat kendini",
    "friday kendini kapat",
    "friday kapan",
    "friday cik",
    "friday cikis yap",
    "fridaytan cik",
    "friday tan cik",
    "friday i sonlandir",
    "fridayi sonlandir",
    "uygulamadan cik",
    "programdan cik",
    # Eski komutları kullananlar için geriye dönük uyumluluk.
    "close the friday app",
    "quit friday",
}


def is_close_command(text: str) -> bool:
    """Yalnızca FRIDAY'ı kapatma niyeti açık olan tam komutları kabul et."""
    command = normalize_command(text)
    from core.identity import LEGACY_SPOKEN_NAME
    return command in _CLOSE_COMMANDS or command in {
        c.replace("friday", LEGACY_SPOKEN_NAME) for c in _CLOSE_COMMANDS
    }
