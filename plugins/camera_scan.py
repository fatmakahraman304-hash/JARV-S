"""Send an explicit camera scan request to the desktop UI."""

PLUGIN = {
    "name": "camera_scan",
    "description": (
        "Use when the user explicitly says 'verileri aktar ve yansıt', "
        "'kamerayı tara', or asks to scan a physical object or QR code with "
        "the desktop camera and show the result on JARVIS. Captures one frame."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
}


def run(parameters, player=None, session_memory=None):
    request = getattr(player, "scan_camera", None)
    if not callable(request):
        return "Kamera taraması için JARVIS masaüstü arayüzü gerekli."
    request()
    return "Kamera taraması istendi. Sonucu JARVIS ekranında göstereceğim."
