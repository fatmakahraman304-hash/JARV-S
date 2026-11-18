"""
Ortak yapılacaklar listesi — bilgisayar, telefon, tablet, TV ve saat aynı listeyi görür.

Liste ortak hafızada (notes / "yapılacak: …") tutulur; sync_hub onu bütün
cihazlarla eşitler, web uygulamasındaki `todo` aracı da aynı biçimi kullanır
(web/app.js todoTool). Telefonda "listeye süt ekle" denirse bilgisayar da bilir.
"""

PLUGIN = {
    "name": "todo_list",
    "description": (
        "Ortak yapılacaklar listesi (tüm cihazlarla paylaşılır): 'listeye süt ekle', "
        "'yapılacaklarım ne', 'faturayı ödedim listeden sil', 'biten işleri temizle'. "
        "action: add | list | done | clear_done. Zamanlı hatırlatma için bunu değil reminder aracını kullan."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "add | list | done | clear_done"},
            "item": {"type": "STRING", "description": "eklenecek ya da tamamlanan madde"},
        },
        "required": ["action"],
    },
}

PREFIX = "yapılacak: "


def _items() -> list[str]:
    from memory.memory_manager import load_memory
    notes = (load_memory() or {}).get("notes", {}) or {}
    return [k for k in notes if isinstance(k, str) and k.startswith(PREFIX)]


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from memory import memory_manager as mm
        p = parameters or {}
        action = str(p.get("action") or "list").strip().lower()
        item = str(p.get("item") or "").strip()
        items = _items()
        if action == "add":
            if not item:
                return "Listeye neyi ekleyeyim?"
            mm.remember(PREFIX + item[:120], "açık", "notes")
            return f"Listeye eklendi: {item}"
        if action == "done":
            q = item.casefold()
            hit = next((k for k in items if q and q in k[len(PREFIX):].casefold()), None)
            if not hit:
                return "Listede böyle bir madde bulamadım."
            mm.forget(hit, "notes")
            return f"Tamamlandı, listeden çıktı: {hit[len(PREFIX):]}"
        if action in ("clear_done", "clear"):
            for k in items:
                mm.forget(k, "notes")
            return f"{len(items)} madde silindi."
        if not items:
            return "Yapılacaklar listesi boş."
        return "\n".join(f"{i}. {k[len(PREFIX):]}" for i, k in enumerate(items, 1))
    except Exception as exc:
        return f"Yapılacaklar listesine ulaşamadım: {exc}"
