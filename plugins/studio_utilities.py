"""Local calculations and comparisons; inputs must be supplied by the user."""
import json
from core import studio_utilities as utilities

PLUGIN = {
    "name": "studio_utilities", "tier": "core",
    "description": (
        "Yerel, salt okunur kesin hesaplar. operation ve arguments (JSON nesnesi) ver. "
        "convert {value,source,target}; portions {items:[{name,amount,unit}],old,new}; "
        "split_cost {amount,weights:[...]}; stats {values:[...]}; compare {before,after}; "
        "conflicts {events:[{start,end}]} (saat dilimli ISO tarihleri); "
        "text_diff {before,after}; dice {count,sides}; check_total {values,expected}; "
        "formula {kind,column,first,last} (SUM,AVERAGE,MIN,MAX,COUNT). "
        "task_schedule {tasks:[{id,minutes,depends:[id]}],workers?:1-20}: kritik yol, gecikme payı, isteğe bağlı kapasite çizelgesi; "
        "savings_plan {target,saved,months}: kalan tutarı tam aylar ve kuruşlar halinde böl; "
        "budget_summary {income,expenses:[{category,amount}]} aynı para birimi; "
        "weighted_options {weights:{criterion:weight},options:[{name,ratings:{criterion:0-10}}]}. "
        "trend {values:[...]}: eşit aralıklı gözlenen doğrusal eğilim, tahmin değil; "
        "data_quality {rows:[{column:value,...}]}: eksik değer ve karışık tür kontrolü. "
        "priority_matrix {tasks:[{name,important:bool,urgent:bool}]}: önem/aciliyet grupları; "
        "Bilinmeyen veri uydurma, dosya veya takvime eriştiğini iddia etme."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "operation": {"type": "STRING", "enum": list(utilities.OPERATIONS)},
        "arguments": {"type": "STRING", "description": "JSON object with exact inputs"},
    }, "required": ["operation","arguments"]},
}

def run(parameters, player=None, session_memory=None):
    try:
        raw = parameters.get("arguments", "{}")
        if isinstance(raw, str):
            if len(raw) > 90000:
                raise ValueError("Girdi çok uzun.")
            raw = json.loads(raw)
        result = utilities.run(parameters.get("operation"), raw)
        return "status=done\n" + json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, ArithmeticError, KeyError) as exc:
        return "status=failed\n" + str(exc)[:240]
