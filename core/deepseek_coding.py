"""DeepSeek is called only by the coding tools."""

from types import SimpleNamespace
import threading
import time

import httpx

MODEL = "deepseek-flash"
ENDPOINT = "https://api.deepseek.com/chat/completions"
_COOLDOWN = {401: 300, 402: 300, 429: 60}
_lock = threading.Lock()
_active_keys = ()
_retry_after = {}


def generate_content(prompt: str, keys: tuple[str, ...]):
    """Try keys in order, skipping those recently rejected by DeepSeek."""
    global _active_keys
    with _lock:
        if keys != _active_keys:
            _retry_after.clear()
            _active_keys = keys

    for index, key in enumerate(keys):
        with _lock:
            if time.monotonic() < _retry_after.get(index, 0):
                continue
        try:
            response = httpx.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "thinking": {"type": "disabled"},
                    "max_tokens": 16000,
                },
                timeout=httpx.Timeout(120.0, connect=15.0),
            )
        except httpx.RequestError:
            raise RuntimeError("DeepSeek bağlantısı kurulamadı. İnterneti kontrol et.") from None

        if response.status_code in _COOLDOWN:
            with _lock:
                if keys == _active_keys:
                    _retry_after[index] = time.monotonic() + _COOLDOWN[response.status_code]
            continue
        if not response.is_success:
            raise RuntimeError(f"DeepSeek kod isteğini tamamlayamadı (HTTP {response.status_code}).")
        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
            if choice["finish_reason"] == "length":
                raise RuntimeError("DeepSeek çıktı sınırına ulaştı. Değişikliği daha küçük parçalara böl.")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty content")
        except (ValueError, KeyError, IndexError, TypeError):
            raise RuntimeError("DeepSeek kullanılabilir bir kod yanıtı döndürmedi.") from None
        return SimpleNamespace(text=content)

    raise RuntimeError("DeepSeek anahtarları şu an kullanılamıyor. Anahtarları, bakiyeyi ve kotayı kontrol et.")
