"""
Konuşma arşivinde ara: bütün cihazlarda (bilgisayar, telefon, tablet, TV)
konuşulan her şey ortak, gizli bir arşivde aylara bölünerek saklanır
(core/sync_hub.search_archive). "Geçen hafta ne konuşmuştuk?", "telefonda
bahsettiğim film neydi?", "annemin doğum günü hakkında ne demiştim?".
"""

PLUGIN = {
    "name": "search_history",
    "description": (
        "Bütün cihazlardaki geçmiş konuşmaların kalıcı arşivinde ara: 'geçen hafta ne konuşmuştuk', "
        "'dün telefonda bahsettiğim film neydi', 'annem hakkında ne demiştim'. days: kaç gün geriye (boşsa hepsi). "
        "Kalıcı kişisel bilgiler için önce hafızaya bak; bu araç geçmiş konuşmalar içindir."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "aranan konu ya da kelimeler"},
            "days": {"type": "NUMBER", "description": "kaç gün geriye"},
        },
        "required": ["query"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import sync_hub
        p = parameters or {}
        try:
            days = float(p.get("days") or 0)
        except (TypeError, ValueError):
            days = 0
        return sync_hub.search_archive(str(p.get("query") or ""), days)
    except Exception as exc:
        return f"Arşivde arayamadım: {exc}"
