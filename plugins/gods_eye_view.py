"""Let JARVIS discover and use the installed God's Eye View commands."""

import json

from core.gods_eye import Reply, read_catalog

PLUGIN = {
    "name": "gods_eye_view",
    "description": (
        "God's Eye View is JARVIS's integrated 3D globe. Use for explicit globe, God's Eye "
        "View or 3D world requests. Ordinary street-map requests use normal_map. "
        "Use open or close to switch between the globe and CORE. Use catalog to discover "
        "available commands, describe to read a specific command's exact argument schema, "
        "and call to execute it. For a city use fly_to_location with {query: place}; "
        "for layer changes describe set_layer_visibility; for zoom describe adjust_camera_zoom; "
        "for the whole globe use zoom_to_globe; inspect current state with get_current_view_state. "
        "The catalog also covers map styles, scene controls, routes, annotations, imagery and "
        "data queries where available. Use exact argument keys; do not guess coordinates, layer "
        "IDs, availability, or success. Pending commands report their result in the JARVIS log."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["open", "close", "catalog", "describe", "call"]},
            "command": {"type": "STRING", "description": "Exact name from the upstream command catalog."},
            "arguments_json": {"type": "STRING", "description": "JSON object with the described argument keys, or {}."},
        },
        "required": ["action"],
    },
}


def run(parameters, player=None, session_memory=None):
    action = parameters.get("action")
    try:
        if action in ("catalog", "describe", "call"):
            catalog = read_catalog()
            if action == "catalog":
                return "God's Eye View komutları: " + ", ".join(sorted(catalog))
            name = parameters.get("command")
            if not isinstance(name, str) or name not in catalog:
                return "God's Eye View komut adı bulunamadı. Önce catalog kullan."
            if action == "describe":
                return json.dumps(catalog[name], ensure_ascii=False)
            args = parameters.get("arguments_json") or "{}"
            if not isinstance(args, str) or len(args) > 12000:
                return "Komut argümanları geçerli bir JSON nesnesi olmalı."
            args = json.loads(args)
            if not isinstance(args, dict):
                return "Komut argümanları geçerli bir JSON nesnesi olmalı."
            json.dumps(args, allow_nan=False)
            payload = {"name": name, "args": args}
        elif action in ("open", "close"):
            payload = {"kind": action}
        else:
            return "Geçersiz God's Eye View işlemi."

        dispatch = getattr(player, "control_gods_eye", None)
        if not callable(dispatch):
            return "God's Eye View kontrolü JARVIS masaüstü arayüzünü gerektirir."
        reply = Reply()
        dispatch(payload, reply)
        return reply.wait(2) or "God's Eye View isteği sırada. Sonuç JARVIS günlüğüne yazılacak."
    except (RecursionError, json.JSONDecodeError):
        return "Geçersiz JSON argümanları."
    except ValueError as exc:
        return str(exc)
