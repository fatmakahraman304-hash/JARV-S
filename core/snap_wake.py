"""Local transient detection for manual sleep on the 16 kHz PCM stream."""

import re
import unicodedata

import numpy as np


def is_sleep_command(text: str) -> bool:
    """Yalnızca açık Türkçe uyku komutları; başka bir işlemi durdurma değil."""
    text = unicodedata.normalize(
        "NFKD", (text or "").replace("İ", "i").replace("I", "ı").casefold()
    )
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).replace("ı", "i")
    words = re.findall(r"[^\W_]+", text, re.UNICODE)
    if words and words[0] in {"friday"}:
        words = words[1:]
    return words in (
        ["uyu"],
        ["artik", "uyu"],
        ["uyku", "moduna", "gec"],
        ["uyku", "modunu", "ac"],
        ["uykuya", "gec"],
        ["uykuna", "gec"],
        ["dinlemeyi", "birak"],
        ["dinlemeyi", "durdur"],
    )

class SnapDetector:
    """Detect a short, sharp transient after quiet, across callback boundaries."""

    def __init__(self, rate: int):
        self._width = max(1, rate // 250)  # 4 ms windows
        self._remaining = np.empty(0, dtype=np.float32)
        self._noise = 80.0
        self._quiet = 0
        self._burst = []
        self._armed = False

    def feed(self, pcm) -> bool:
        data = np.concatenate((self._remaining, np.asarray(pcm, dtype=np.float32).ravel()))
        count = data.size // self._width
        self._remaining = data[count * self._width:].copy()
        windows = data[:count * self._width].reshape(count, self._width)
        for window, rms in zip(windows, np.sqrt(np.mean(windows * windows, axis=1))):
            if rms >= max(400.0, self._noise * 6):
                if not self._burst:
                    self._armed = self._quiet >= 8
                    self._quiet = 0
                if len(self._burst) < 8:
                    self._burst.append(window.copy())
                continue
            if self._burst:
                found = False
                if self._armed and len(self._burst) <= 7:
                    pulse = np.concatenate(self._burst)
                    peak = float(np.max(np.abs(pulse)))
                    energy = float(np.mean(pulse * pulse))
                    edge_energy = float(np.mean(np.diff(pulse) ** 2))
                    found = peak >= 2400 and edge_energy >= energy * 0.75
                self._burst.clear()
                self._armed = False
                if found:
                    return True
            self._noise = 0.98 * self._noise + 0.02 * min(float(rms), 300)
            self._quiet = min(self._quiet + 1, 8)
        return False
