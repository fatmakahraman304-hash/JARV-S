"""Pure local utilities for FRIDAY's workflows. No eval, file access or external actions."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation
import difflib
import math
import secrets
import statistics


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Sayı gerekli.")
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Geçersiz sayı.") from exc
    if not d.is_finite() or abs(d) > Decimal("1e12") or (d and abs(d) < Decimal("1e-12")):
        raise ValueError("Sayı desteklenen aralık dışında.")
    return d


def positive(value):
    d = number(value)
    if d <= 0:
        raise ValueError("Pozitif değer gerekli.")
    return d


def sequence(value, limit=1000):
    if not isinstance(value, list) or not value or len(value) > limit:
        raise ValueError(f"1–{limit} öğe gerekli.")
    return value


def clean(d):
    return format(d.normalize(), "f") if d else "0"


# factor to base unit; dimensions must match. Temperature handled separately.
UNITS = {
    "mm": ("length", "0.001"), "cm": ("length", "0.01"), "m": ("length", "1"),
    "km": ("length", "1000"), "in": ("length", "0.0254"), "ft": ("length", "0.3048"),
    "mi": ("length", "1609.344"), "mg": ("mass", "0.001"), "g": ("mass", "1"),
    "kg": ("mass", "1000"), "lb": ("mass", "453.59237"),
    "ml": ("volume", "0.001"), "l": ("volume", "1"),
    "s": ("time", "1"), "min": ("time", "60"), "h": ("time", "3600"),
    "day": ("time", "86400"), "m/s": ("speed", "1"), "km/h": ("speed", "0.2777777777777777777777777778"),
}


def convert(value, source, target):
    d = number(value)
    a, b = str(source).strip().lower(), str(target).strip().lower()
    if a in ("c", "f", "k") and b in ("c", "f", "k"):
        c = (d - 32) * 5 / 9 if a == "f" else d - Decimal("273.15") if a == "k" else d
        if c < Decimal("-273.15"):
            raise ValueError("Mutlak sıfırın altında sıcaklık.")
        return clean(c * 9 / 5 + 32 if b == "f" else c + Decimal("273.15") if b == "k" else c)
    if a not in UNITS or b not in UNITS or UNITS[a][0] != UNITS[b][0]:
        raise ValueError("Bilinmeyen veya uyumsuz birim.")
    return clean(d * Decimal(UNITS[a][1]) / Decimal(UNITS[b][1]))


def portions(items, old, new):
    factor = positive(new) / positive(old)
    result = []
    for item in sequence(items, 200):
        if not isinstance(item, dict):
            raise ValueError("Malzeme nesnesi gerekli.")
        amount = number(item.get("amount"))
        if amount < 0:
            raise ValueError("Negatif miktar olamaz.")
        result.append({"name": str(item.get("name", ""))[:120], "amount": clean(amount * factor),
                       "unit": str(item.get("unit", ""))[:40]})
    return result


def split_cost(amount, weights):
    total = number(amount)
    if total < 0:
        raise ValueError("Negatif gider olamaz.")
    weights = [positive(x) for x in sequence(weights, 200)]
    cents = total * 100
    if cents != cents.to_integral_value():
        raise ValueError("Tutar en fazla iki ondalık basamak içermeli.")
    shares = [cents * w / sum(weights) for w in weights]
    result = [int(x) for x in shares]
    remainder = int(cents) - sum(result)
    order = sorted(range(len(weights)), key=lambda i: (shares[i] - result[i], -i), reverse=True)
    for i in order[:remainder]:
        result[i] += 1
    return [f"{Decimal(x)/100:.2f}" for x in result]


def stats(values):
    data = [float(number(v)) for v in sequence(values)]
    mean = statistics.mean(data)
    median = statistics.median(data)
    sd = statistics.pstdev(data)
    if len(data) >= 4:
        q1, _, q3 = statistics.quantiles(data, n=4, method="inclusive")
        lower, upper = q1 - 1.5 * (q3-q1), q3 + 1.5 * (q3-q1)
        outliers = [i for i, x in enumerate(data) if x < lower or x > upper]
    else:
        outliers = []
    return {"count": len(data), "sum": math.fsum(data), "mean": mean, "median": median,
            "min": min(data), "max": max(data), "population_sd": sd,
            "outlier_indices_zero_based": outliers, "outlier_method": "1.5 IQR, en az 4 değer"}


def compare(before, after):
    a, b = number(before), number(after)
    return {"difference": clean(b-a), "percentage_change": clean((b-a)/abs(a)*100) if a else None}


def conflicts(events):
    parsed = []
    for i, event in enumerate(sequence(events, 200)):
        if not isinstance(event, dict):
            raise ValueError("Etkinlik nesnesi gerekli.")
        start, end = (datetime.fromisoformat(str(event.get(k, ""))) for k in ("start", "end"))
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("Saat dilimli ISO tarihleri ve bitiş > başlangıç gerekli.")
        parsed.append((i, start, end))
    return [[i,j] for a,(i,s,e) in enumerate(parsed) for j,t,u in parsed[a+1:] if s < u and t < e]


def text_diff(before, after):
    if not isinstance(before, str) or not isinstance(after, str) or len(before)+len(after) > 40000:
        raise ValueError("İki metin ve toplam en çok 40000 karakter gerekli.")
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile="önce", tofile="sonra", lineterm=""))
    result = "\n".join(lines)
    return {"identical": before == after, "diff": result[:12000], "truncated": len(result)>12000,
            "line_endings_ignored": True}


def dice(count, sides):
    if type(count) is not int or type(sides) is not int or not 1 <= count <= 100 or not 2 <= sides <= 1000:
        raise ValueError("1–100 zar ve 2–1000 yüz gerekli.")
    rolls = [secrets.randbelow(sides)+1 for _ in range(count)]
    return {"rolls": rolls, "total": sum(rolls)}


def check_total(values, expected):
    actual = sum(number(v) for v in sequence(values))
    exp = number(expected)
    return {"actual": clean(actual), "expected": clean(exp), "difference": clean(actual-exp), "matches": actual == exp}


def formula(kind, column, first, last):
    import re
    if kind not in ("SUM", "AVERAGE", "MIN", "MAX", "COUNT") or not isinstance(column, str):
        raise ValueError("Desteklenen formül: SUM, AVERAGE, MIN, MAX, COUNT.")
    col = column.upper()
    if not re.fullmatch(r"[A-Z]{1,3}", col) or type(first) is not int or type(last) is not int or not 1 <= first <= last <= 1048576:
        raise ValueError("Geçersiz hücre aralığı.")
    return f"={kind}({col}{first}:{col}{last})"


OPERATIONS = {"convert": convert, "portions": portions, "split_cost": split_cost,
              "stats": stats, "compare": compare, "conflicts": conflicts,
              "text_diff": text_diff, "dice": dice, "check_total": check_total, "formula": formula}


def run(operation, args):
    if operation not in OPERATIONS or not isinstance(args, dict):
        raise ValueError("Geçersiz işlem veya parametre.")
    return OPERATIONS[operation](**args)
