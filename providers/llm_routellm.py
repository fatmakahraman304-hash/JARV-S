"""Explicit Abacus.AI ChatLLM account for the existing FRIDAY model pipeline."""
from .base import Field
from .llm_openai import OpenAICompatLLM, available


class RouteLLM(OpenAICompatLLM):
    fixed_base = "https://routellm.abacus.ai/v1"

    def __init__(self, cfg):
        if str(cfg.get("allow_usage", "")).strip().lower() not in ("true", "1"):
            raise ValueError("Önce Abacus hesap kullanımına izin verip ayarları uygulayın.")
        key = str(cfg.get("api_key") or "").strip()
        if not key:
            raise ValueError("Bu Abacus hesabı için API anahtarı gerekli.")
        super().__init__({"model": "route-llm", "api_key": key})

    def _headers(self):
        # Apply revocation even to an instance cached before a settings change.
        from memory import config_manager, secret_storage
        try:
            data = secret_storage.read_document(config_manager.CONFIG_FILE)
        except (OSError, ValueError) as exc:
            raise ValueError("Abacus hesap izni mevcut ayarlardan doğrulanamadı.") from exc
        if data.get("local_only"):
            raise ValueError("Yalnızca yerel çalışma açıkken Abacus kullanılamaz.")
        account = data.get("providers", {}).get("creds", {}).get("abacus_chat", {})
        if (str(account.get("allow_usage", "")).strip().lower() not in ("true", "1")
                or str(account.get("api_key") or "").strip() != self.key):
            raise ValueError("Abacus hesap ayarlarını uygulayın. İstek gönderilmedi.")
        return super()._headers()


PROVIDER = {
    "id": "abacus_chat", "kind": "llm", "label": "Abacus.AI · RouteLLM",
    "hint": "FRIDAY sohbeti veya arka plan görevleri için isteğe bağlı hesap bağlantısı",
    "requires": ("httpx",), "install": "httpx",
    "needs": (
        Field("api_key", "Abacus API anahtarı", kind="secret", required=True),
        Field("allow_usage", "Bu Abacus hesabını kullanmaya izin ver", kind="bool",
              default="", required=False, hint="İstekler hesabınızın kotasını veya kredisini kullanabilir."),
    ),
    "caps": {"tools": True, "tool_format": "openai"}, "factory": RouteLLM,
}
