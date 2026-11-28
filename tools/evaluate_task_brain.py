"""Run with python -m tools.evaluate_task_brain --live. Uses the configured provider."""
import argparse
import json
import time

CASES = (
    ("turkish_schedule", "Saat 09:40'ta başlayan 55 dakikalık ders ne zaman biter? "
     'Yalnızca {"bitis":"SS:DD"} biçiminde JSON ver.', {"bitis": "10:35"}),
    ("dependencies", "C için A ve B bitmeli. B için A bitmeli. Geçerli tek sırayı "
     'yalnızca {"sira":[...]} biçiminde JSON ver.', {"sira": ["A", "B", "C"]}),
    ("uncertain_action", "Bir ödeme sunucuya iletildi ancak yanıt kesildi. "
     'Çift ödemeyi önlemek için otomatik tekrar yapılsın mı? JSON: {"tekrar":true veya false}.',
     {"tekrar": False}),
)


def evaluate(call, tier):
    for name, prompt, expected in CASES:
        start = time.monotonic()
        status = "unavailable"
        input_tokens = output_tokens = model = None
        try:
            response = call(prompt, tier=tier, timeout_ms=15000)
            usage = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage, "prompt_token_count", None)
            output_tokens = getattr(usage, "candidates_token_count", None)
            model = getattr(response, "model_version", None)
            response = response if isinstance(response, str) else getattr(response, "text", None)
            if response:
                try:
                    actual = json.loads(response)
                    # JSON booleans and integers have different types.
                    passed = json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
                except ValueError:
                    passed = False
                status = "passed" if passed else "failed"
        except Exception:
            status = "error"
        yield {"case": name, "tier": tier, "status": status,
               "model": model, "input_tokens": input_tokens, "output_tokens": output_tokens,
               "cost_usd": None,
               "elapsed_ms": round((time.monotonic() - start) * 1000) if status in ("passed", "failed") else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", required=True, action="store_true", help="send three synthetic prompts")
    parser.add_argument("--tier", choices=("fast", "smart"), default="fast")
    args = parser.parse_args()
    from core.gemini import call
    results = list(evaluate(call, args.tier))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    raise SystemExit(int(any(row["status"] != "passed" for row in results)))
