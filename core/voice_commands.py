"""Direct application commands recognized from user input."""

import re
import unicodedata


def is_close_command(text: str) -> bool:
    text = unicodedata.normalize("NFKC", text).replace("İ", "i").casefold()
    words = " ".join(re.findall(r"[^\W_]+", text, re.UNICODE))
    return words in {
        "jarvis uygulamasını kapat",
        "jarvis uygulamasından çık",
        "close the jarvis app",
        "quit jarvis",
    }
