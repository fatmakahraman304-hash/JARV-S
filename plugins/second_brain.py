"""Voice entry to the read-only feature monitor, never to self-editing."""
PLUGIN = {
    "name": "second_brain",
    "description": "Open FRIDAY's feature-check panel or read its local test report. It never develops code or starts an agent. Reports distinguish local checks from unverified live services/hardware.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "enum": ["open", "report"]}}, "required": ["action"]}
}


def run(parameters, player=None, session_memory=None):
    try:
        action = parameters.get("action")
        if action == "report":
            from core.second_brain_service import results
            rows = results()
            if not rows:
                return "Henüz özellik kontrolü tamamlanmadı. Beyin panelinden izleyebilirsiniz."
            counts = {state: sum(row['status'] == state for row in rows)
                      for state in ('passed', 'failed', 'unverified')}
            return (f"Yerel kontrol: {counts['passed']} geçti, {counts['failed']} hata, "
                    f"{counts['unverified']} doğrulanmadı. Canlı hizmet ve donanım testi değildir. "
                    "Ayrıntılar ve kopyalanabilir hata raporu beyin panelinde.")
        if action != "open":
            return "İkincil beyin yalnızca özellik denetler; geliştirme fikri almaz ve kod yazmaz."
        show = getattr(player, "show_second_brain", None)
        if callable(show):
            show()
            return "Özellik denetimi açılıyor. Sonuç ve hata raporları burada görünür."
        return "Özellik denetimi paneli için FRIDAY masaüstü arayüzünü açın."
    except Exception as exc:
        return "Denetim raporu okunamadı: " + type(exc).__name__
