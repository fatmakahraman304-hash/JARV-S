"""Pure local utilities for FRIDAY's workflows. No eval, file access or external actions."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import difflib
import math
import secrets
import statistics


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Sayı gerekli.")
    raw = str(value)
    if len(raw) > 100:
        raise ValueError("Sayı metni çok uzun.")
    try:
        d = Decimal(raw)
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
    exact = [Fraction(w) for w in weights]
    denominator = sum(exact)
    shares = [int(cents) * w / denominator for w in exact]
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
    col_number = 0
    for char in col:
        col_number = col_number * 26 + ord(char) - ord("A") + 1
    if col_number > 16384:
        raise ValueError("Excel sütunu XFD sınırını aşıyor.")
    return f"={kind}({col}{first}:{col}{last})"


def task_schedule(tasks):
    """Earliest-start schedule, critical path and slack from supplied durations."""
    # Inputs are bounded to 100 characters and 200 tasks. Use a local context
    # large enough for exact forward and backward sums, without global changes.
    with localcontext() as ctx:
        ctx.prec = 128
        return _task_schedule(tasks)


def _task_schedule(tasks):
    """No calendar or actual execution."""
    rows = sequence(tasks, 200)
    data = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Görev nesnesi gerekli.")
        key = row.get("id")
        if not isinstance(key, str) or not key.strip() or len(key) > 80 or key in data:
            raise ValueError("Görev kimliği geçersiz veya tekrarlı.")
        duration = positive(row.get("minutes"))
        if duration > 1000000:
            raise ValueError("Süre sınırı aşıldı.")
        deps = row.get("depends", [])
        if not isinstance(deps, list) or len(deps) > 200 or any(not isinstance(d,str) for d in deps):
            raise ValueError("Bağımlılık listesi geçersiz.")
        data[key] = (duration, tuple(dict.fromkeys(deps)))
    if any(dep not in data for _, deps in data.values() for dep in deps):
        raise ValueError("Bilinmeyen görev bağımlılığı.")
    remaining = dict(data)
    times = {}
    while remaining:
        ready = [key for key, (_, deps) in remaining.items() if all(d in times for d in deps)]
        if not ready:
            raise ValueError("Döngüsel görev bağımlılığı; plan kurulamadı.")
        for key in ready:
            duration, deps = remaining.pop(key)
            start = max((times[d][1] for d in deps), default=Decimal(0))
            times[key] = (start, start + duration)
    # Backward pass: identify tasks that can delay the entire plan.
    finish = max(end for _,end in times.values())
    successors = {key: [] for key in data}
    for key,(_,deps) in data.items():
        for dep in deps:
            successors[dep].append(key)
    late = {}
    for key in reversed(times):
        duration,_ = data[key]
        end = min((late[child][0] for child in successors[key]), default=finish)
        late[key] = (end-duration,end)
    slack = {key:late[key][0]-times[key][0] for key in times}
    # One deterministic critical path, with all zero-slack tasks separately.
    end_key = next(key for key,(_,end) in times.items() if end == finish)
    path = [end_key]
    while data[path[-1]][1]:
        key = path[-1]
        dep = next(d for d in data[key][1] if times[d][1] == times[key][0])
        path.append(dep)
    path.reverse()
    return {"tasks":[{"id":key, "start_minutes":clean(start), "end_minutes":clean(end),
                      "latest_start_minutes":clean(late[key][0]),
                      "slack_minutes":clean(slack[key]), "critical":slack[key]==0}
                     for key,(start,end) in times.items()],
            "minimum_elapsed_minutes":clean(finish),
            "total_work_minutes":clean(sum(duration for duration,_ in data.values())),
            "critical_path":path,
            "critical_tasks":[key for key in times if slack[key]==0],
            "assumption":"Bağımsız görevler paralel yapılabilir; süreler verilen tahminlerdir, tarih veya kaynak ataması yok."}


def priority_matrix(tasks):
    """Classify only explicitly supplied importance and urgency flags."""
    groups = {"do_first": [], "schedule": [], "delegate_or_review": [], "defer_or_review": []}
    seen = set()
    for row in sequence(tasks,200):
        if not isinstance(row,dict):
            raise ValueError("Görev nesnesi gerekli.")
        name = row.get("name")
        important, urgent = row.get("important"),row.get("urgent")
        if not isinstance(name,str) or not name.strip() or len(name)>200 or name.strip() in seen:
            raise ValueError("Benzersiz görev adı gerekli.")
        if type(important) is not bool or type(urgent) is not bool:
            raise ValueError("Önem ve aciliyet için açık boolean değerleri gerekli.")
        name = name.strip()
        seen.add(name)
        key = ("do_first" if urgent else "schedule") if important else (
               "delegate_or_review" if urgent else "defer_or_review")
        groups[key].append(name)
    return {"groups":groups,"count":len(seen),
            "assumption":"Önem ve aciliyet verilen değerlendirmelerdir; hiçbir görev yürütülmez veya silinmez."}


def budget_summary(income, expenses):
    """Same currency amounts only, no exchange rate or financial advice."""
    total = number(income)
    if total < 0:
        raise ValueError("Gelir negatif olamaz.")
    if not isinstance(expenses, list) or len(expenses) > 500:
        raise ValueError("En fazla 500 gider gerekli.")
    categories = {}
    for row in expenses:
        if not isinstance(row,dict) or not isinstance(row.get("category"),str):
            raise ValueError("Gider kategorisi gerekli.")
        category = row["category"].strip()
        amount = number(row.get("amount"))
        if not category or len(category) > 100 or amount < 0:
            raise ValueError("Geçersiz gider.")
        categories[category] = categories.get(category,Decimal(0)) + amount
    spent = sum(categories.values(),Decimal(0))
    return {"income":clean(total), "expenses":clean(spent), "remaining":clean(total-spent),
            "by_category":{key:clean(value) for key,value in categories.items()},
            "assumption":"Tüm tutarlar aynı para biriminde olmalıdır."}


def weighted_options(weights, options):
    """Weighted 0–10 ratings supplied by user, not model-selected preferences."""
    if not isinstance(weights,dict) or not 1 <= len(weights) <= 30:
        raise ValueError("1–30 ölçüt gerekli.")
    if any(not isinstance(k,str) or not k.strip() or len(k)>100 for k in weights):
        raise ValueError("Geçersiz ölçüt.")
    parsed = {k:positive(v) for k,v in weights.items()}
    denominator = sum(parsed.values())
    result = []
    names = set()
    for row in sequence(options,100):
        if not isinstance(row,dict) or not isinstance(row.get("name"),str):
            raise ValueError("Seçenek adı gerekli.")
        name = row["name"].strip()
        values = row.get("ratings")
        if not name or len(name)>120 or name in names or not isinstance(values,dict) or set(values)!=set(parsed):
            raise ValueError("Tekil seçenek ve tüm ölçütlerin puanı gerekli.")
        names.add(name)
        ratings = {k:number(v) for k,v in values.items()}
        if any(not 0 <= v <= 10 for v in ratings.values()):
            raise ValueError("Puan 0–10 arasında olmalı.")
        score = sum(parsed[k]*ratings[k] for k in parsed)/denominator
        result.append((name,score))
    result.sort(key=lambda r:-r[1])
    return {"ranking":[{"name":name,"score":clean(score)} for name,score in result],
            "assumption":"Kullanıcının ölçüt ve puanları; nihai karar kullanıcıya ait."}


def trend(values):
    """Least-squares line over equally spaced observed values; no forecast."""
    data = [float(number(v)) for v in sequence(values)]
    if len(data) < 2:
        raise ValueError("Trend için en az iki gözlem gerekli.")
    x = list(range(len(data)))
    mx, my = statistics.mean(x), statistics.mean(data)
    sxx = math.fsum((i-mx)**2 for i in x)
    sxy = math.fsum((i-mx)*(y-my) for i,y in zip(x,data))
    slope = sxy / sxx
    intercept = my - slope * mx
    syy = math.fsum((y-my)**2 for y in data)
    r2 = min(1.0,max(0.0,sxy*sxy/(sxx*syy))) if syy else None
    return {"count":len(data), "slope_per_step":slope, "intercept_at_step_zero":intercept,
            "r_squared":r2, "first":data[0], "last":data[-1],
            "assumption":"Eşit aralıklı gözlemler, doğrusal betimleme; gelecek tahmini değildir."}


def data_quality(rows):
    """Describe supplied table rows; no files, imputation or writes."""
    records = sequence(rows, 1000)
    columns = set()
    for row in records:
        if not isinstance(row,dict) or len(row)>100:
            raise ValueError("En fazla 100 sütunlu satır nesnesi gerekli.")
        for k,v in row.items():
            if not isinstance(k,str) or not k.strip() or len(k)>120:
                raise ValueError("Geçersiz sütun adı.")
            if type(v) not in (str,int,float,bool,type(None)):
                raise ValueError("Hücreler basit değer olmalı.")
            if isinstance(v,str) and len(v)>10000:
                raise ValueError("Hücre metni çok uzun.")
            if type(v) in (int,float):
                number(v)
        columns.update(row)
        if len(columns)>100:
            raise ValueError("Toplam sütun sayısı en fazla 100.")
    result=[]
    for name in sorted(columns):
        counts={}
        missing=0
        for row in records:
            value=row.get(name)
            if value is None or isinstance(value,str) and not value.strip():
                missing+=1
                continue
            kind="boolean" if type(value) is bool else "number" if type(value) in (int,float) else "text"
            counts[kind]=counts.get(kind,0)+1
        result.append({"column":name,"missing":missing,"present":len(records)-missing,
                       "types":counts,"mixed_types":len(counts)>1})
    return {"row_count":len(records),"column_count":len(columns),"columns":result,
            "assumption":"Eksik anahtar, null ve boş metin eksik sayılır; veri değiştirilmez."}


OPERATIONS = {"convert": convert, "portions": portions, "split_cost": split_cost,
              "stats": stats, "compare": compare, "conflicts": conflicts,
              "text_diff": text_diff, "dice": dice, "check_total": check_total, "formula": formula,
              "task_schedule": task_schedule, "budget_summary": budget_summary,
              "weighted_options": weighted_options, "trend": trend, "data_quality": data_quality,
              "priority_matrix": priority_matrix}


def run(operation, args):
    if operation not in OPERATIONS or not isinstance(args, dict):
        raise ValueError("Geçersiz işlem veya parametre.")
    return OPERATIONS[operation](**args)
