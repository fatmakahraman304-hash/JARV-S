"""
core/open_data.py — live facts from free, keyless public services.

Weather: Open-Meteo (forecast + place search), no key, no account.
Exchange rates: Frankfurter (European Central Bank reference rates), no key.

The web app calls the same services from the phone (web/app.js weatherTool,
currencyTool). Standard library only; nothing raises — callers get text.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

WMO = {0: "açık", 1: "çoğunlukla açık", 2: "parçalı bulutlu", 3: "kapalı", 45: "sisli", 48: "kırağılı sis",
       51: "hafif çisenti", 53: "çisenti", 55: "yoğun çisenti", 56: "dondurucu çisenti", 57: "dondurucu çisenti",
       61: "hafif yağmurlu", 63: "yağmurlu", 65: "şiddetli yağmurlu", 66: "dondurucu yağmur", 67: "dondurucu yağmur",
       71: "hafif karlı", 73: "karlı", 75: "yoğun karlı", 77: "kar taneli", 80: "hafif sağanak", 81: "sağanak",
       82: "şiddetli sağanak", 85: "kar sağanağı", 86: "yoğun kar sağanağı", 95: "gök gürültülü fırtına",
       96: "dolu ile fırtına", 99: "şiddetli dolu ile fırtına"}
DAYS_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _get(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1.0"})
    ctx = None
    try:
        from core import tls
        ctx = tls.context()
    except Exception:
        ctx = None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def geocode(name: str) -> dict | None:
    q = urllib.parse.urlencode({"name": name, "count": 1, "language": "tr", "format": "json"})
    js = _get(f"https://geocoding-api.open-meteo.com/v1/search?{q}")
    res = (js.get("results") or [None])[0]
    if not res:
        return None
    return {"lat": res["latitude"], "lon": res["longitude"],
            "name": ", ".join(x for x in (res.get("name"), res.get("country")) if x)}


def weather_text(js: dict, place: str, days: int = 3) -> str:
    cur = js.get("current") or {}
    d = js.get("daily") or {}
    lines = [f"{place}: şu an {round(cur.get('temperature_2m', 0))}°C, {WMO.get(cur.get('weather_code'), 'bilinmiyor')}"
             + (f", hissedilen {round(cur['apparent_temperature'])}°C" if cur.get("apparent_temperature") is not None else "")
             + (f", rüzgâr {round(cur['wind_speed_10m'])} km/s" if cur.get("wind_speed_10m") is not None else "") + "."]
    from datetime import date
    for i, day in enumerate((d.get("time") or [])[:max(1, days)]):
        try:
            name = "Bugün" if i == 0 else "Yarın" if i == 1 else DAYS_TR[date.fromisoformat(day).weekday()]
        except ValueError:
            name = day
        rain = (d.get("precipitation_probability_max") or [None] * 20)[i]
        lines.append(f"{name}: {round(d['temperature_2m_min'][i])}–{round(d['temperature_2m_max'][i])}°C, "
                     f"{WMO.get(d['weather_code'][i], '')}" + (f", yağış ihtimali %{rain}" if rain is not None else ""))
    return "\n".join(lines)


def weather(city: str = "", lat: float | None = None, lon: float | None = None, days: int = 3) -> str:
    try:
        place = city or "Bulunduğun yer"
        if lat is None or lon is None:
            if not city:
                return "Hangi şehir?"
            g = geocode(city)
            if not g:
                return f"'{city}' diye bir yer bulamadım."
            lat, lon, place = g["lat"], g["lon"], g["name"]
        q = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": max(1, min(7, days)),
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"})
        return weather_text(_get(f"https://api.open-meteo.com/v1/forecast?{q}"), place, days)
    except Exception as exc:
        return f"Hava durumu alınamadı: {exc}"


def rain_soon(lat: float, lon: float, hours: int = 6, threshold: int = 50) -> dict | None:
    """The highest rain chance in the next `hours` if it reaches `threshold`: {"prob", "at"} — for
    'take an umbrella' when the user heads out. None when dry or unknown."""
    try:
        q = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
                                    "hourly": "precipitation_probability"})
        js = _get(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=8)
        return rain_in(js, hours, threshold)
    except Exception:
        return None


def rain_in(js: dict, hours: int, threshold: int, now_iso: str | None = None) -> dict | None:
    from datetime import datetime
    h = js.get("hourly") or {}
    times, probs = h.get("time") or [], h.get("precipitation_probability") or []
    now = now_iso or datetime.now().strftime("%Y-%m-%dT%H:00")
    ahead = [(t, p) for t, p in zip(times, probs) if t >= now and p is not None][:hours]
    if not ahead:
        return None
    t, p = max(ahead, key=lambda x: x[1])
    return {"prob": int(p), "at": t[11:16]} if p >= threshold else None


CURRENCY_WORDS = {"dolar": "USD", "usd": "USD", "euro": "EUR", "avro": "EUR", "eur": "EUR", "sterlin": "GBP",
                  "pound": "GBP", "gbp": "GBP", "tl": "TRY", "lira": "TRY", "türk lirası": "TRY", "try": "TRY",
                  "frank": "CHF", "chf": "CHF", "yen": "JPY", "ruble": "RUB", "yuan": "CNY"}


def code(word: str) -> str:
    w = str(word or "").strip().casefold()
    return CURRENCY_WORDS.get(w, w.upper()[:3])


def currency(base: str = "USD", targets: str = "TRY,EUR", amount: float = 1.0) -> str:
    try:
        b = code(base) or "USD"
        tg = [code(t) for t in str(targets or "TRY").replace(" ", ",").split(",") if t.strip()]
        tg = [t for t in tg if t and t != b] or ["TRY"]
        q = urllib.parse.urlencode({"base": b, "symbols": ",".join(tg), "amount": amount or 1})
        js = _get(f"https://api.frankfurter.dev/v1/latest?{q}")
        rates = js.get("rates") or {}
        if not rates:
            return "Kur bulunamadı (bu para birimi desteklenmiyor olabilir)."
        amt = js.get("amount", amount or 1)
        parts = [f"{amt:g} {b} = {v:,.2f} {k}".replace(",", "X").replace(".", ",").replace("X", ".") for k, v in rates.items()]
        return "; ".join(parts) + f" (Avrupa Merkez Bankası, {js.get('date', '')})."
    except Exception as exc:
        return f"Kur alınamadı: {exc}"
