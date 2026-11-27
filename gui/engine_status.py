"""Local, non-sensitive engine lifecycle presentation.

Ready means a session was opened, not that every provider/tool was probed.
No network probes or raw exception messages are exposed here.
"""
PHASES = {
    "initial": ("BEKLEMEDE", "TEXT_DIM"),
    "connecting": ("BAĞLANIYOR", "PRI"),
    "ready": ("OTURUM HAZIR", "GREEN"),
    "retry": ("YENİDEN BAĞLANIYOR", "ACC"),
    "configuration": ("AYAR GEREKLİ", "ACC"),
    "error": ("BAĞLANTI HATASI", "RED"),
    "offline": ("BAĞLI DEĞİL", "TEXT_DIM"),
}

MODES = {"realtime": "OPENAI REALTIME", "gemini": "GEMINI LIVE",
         "pipeline": "PIPELINE", "unknown": "MOTOR"}


def engine_status(phase, mode="unknown"):
    phase = phase if phase in PHASES else "initial"
    mode = mode if mode in MODES else "unknown"
    label, color = PHASES[phase]
    return label, color, MODES[mode]
