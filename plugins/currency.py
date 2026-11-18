"""
Döviz kurları: "dolar kaç TL", "100 euro kaç lira", "sterlin ne kadar".
Avrupa Merkez Bankası'nın günlük referans kurları (Frankfurter, ücretsiz,
anahtarsız; core/open_data.currency). Web uygulamasında aynı servis kullanılır.
"""

PLUGIN = {
    "name": "currency",
    "description": (
        "Döviz kuru ve çevirme: 'dolar kaç TL', '250 euro kaç lira', 'sterlin ne kadar'. "
        "base: çevrilecek para (dolar, euro, sterlin, TL …), targets: virgülle hedefler, amount: miktar."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "base": {"type": "STRING", "description": "dolar | euro | sterlin | TL | USD …"},
            "targets": {"type": "STRING", "description": "örn. TRY ya da TRY,EUR"},
            "amount": {"type": "NUMBER"},
        },
        "required": ["base"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import open_data
        p = parameters or {}
        try:
            amount = float(p.get("amount") or 1)
        except (TypeError, ValueError):
            amount = 1.0
        return open_data.currency(str(p.get("base") or "USD"), str(p.get("targets") or "TRY"), amount)
    except Exception as exc:
        return f"Kur alınamadı: {exc}"
