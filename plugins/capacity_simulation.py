"""Compare architecture capacity under explicit, hypothetical demand assumptions."""

import math

PLUGIN = {
    "name": "capacity_simulation",
    "description": (
        "Compare software architectures or decisions with a local capacity simulation. "
        "Use for Turkish requests such as 'alternatifleri simüle et' or 'ne zaman darboğaz olur'. "
        "Supply measured or user-provided assumptions, or clearly label example values as hypothetical. "
        "Compare 2–6 alternatives at the same demand. Do not present the output as a real prediction."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "initial_daily_load": {"type": "NUMBER", "description": "Demand on day 1 in jobs or requests per day."},
            "daily_growth_pct": {"type": "NUMBER", "description": "Percentage growth from one day to the next."},
            "days": {"type": "INTEGER", "description": "Number of days to simulate, 1–365."},
            "alternatives": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING"},
                    "daily_capacity": {"type": "NUMBER", "description": "Sustainable completed jobs per day."},
                },
                "required": ["name", "daily_capacity"],
            }},
        },
        "required": ["initial_daily_load", "daily_growth_pct", "days", "alternatives"],
    },
}


def _number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError("Talep, büyüme ve kapasite için geçerli sayılar gerekli.")
    return float(value)


def simulate(initial, growth, days, alternatives):
    initial = _number(initial, 0, 1e12)
    growth = _number(growth, -99, 100)
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError("Süre 1–365 tam gün olmalı.")
    if not isinstance(alternatives, list) or not 2 <= len(alternatives) <= 6:
        raise ValueError("2–6 mimari alternatif ver.")
    demand = [initial * (1 + growth / 100) ** i for i in range(days)]
    results = []
    for option in alternatives:
        name = option.get("name") if isinstance(option, dict) else None
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Her alternatif için kısa bir ad gir.")
        capacity = _number(option.get("daily_capacity"), 1, 1e12)
        backlog = 0.0
        peak_backlog = 0.0
        first = None
        first_demand = None
        cleared = None
        for day, arrivals in enumerate(demand, 1):
            outstanding = backlog + arrivals
            backlog = 0.0 if math.isclose(outstanding, capacity) else max(0.0, outstanding - capacity)
            peak_backlog = max(peak_backlog, backlog)
            if first is None and backlog > 0:
                first, first_demand = day, arrivals
            elif first is not None and backlog == 0 and cleared is None:
                cleared = day
        results.append({
            "name": name.strip(), "capacity": capacity, "first": first,
            "first_demand": first_demand, "backlog": backlog,
            "peak_backlog": peak_backlog, "cleared": cleared,
        })
    return results, demand[-1]


def run(parameters, player=None, session_memory=None):
    try:
        initial = parameters.get("initial_daily_load")
        growth = parameters.get("daily_growth_pct")
        days = parameters.get("days")
        results, final_load = simulate(initial, growth, days, parameters.get("alternatives"))
    except (AttributeError, ValueError) as exc:
        return f"Simülasyon başlatılamadı: {exc}"

    lines = [f"Varsayımlar · İlk gün {initial:,.0f} iş · Günlük büyüme %{growth:g} · {days} gün"]
    lines.append(f"Son günün talebi: {final_load:,.0f} iş.")
    for option in results:
        if option["first"] is None:
            status = "Bu süre içinde günlük kapasite aşılmadı."
        else:
            status = f"{option['first']}. günde darboğaz: {option['first_demand']:,.0f} iş talebi."
            status += f" En yüksek kuyruk: {option['peak_backlog']:,.0f} iş."
            if option["cleared"] is not None:
                status += f" Kuyruk {option['cleared']}. günde temizlenir."
        lines.append(
            f"{option['name']} · Kapasite {option['capacity']:,.0f} iş/gün. "
            f"{status} Son gün bekleyen: {option['backlog']:,.0f} iş."
        )
    best = max(results, key=lambda option: option["capacity"])
    lines.append(
        f"Kapasite açısından öneri: {best['name']}. "
        "Gerçek karar için maliyeti ve ölçülen kapasiteyi karşılaştır."
    )
    lines.append("Koşullu simülasyon. Gün içi trafik sıçramaları, arızalar ve maliyet hesaplanmadı.")
    report = "\n\n".join(lines)
    show = getattr(player, "show_content", None) if player is not None else None
    if callable(show):
        show("Mimari kapasite simülasyonu", report)
    return report
