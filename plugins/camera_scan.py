"""Send an explicit camera scan request to the desktop UI."""

PLUGIN = {
    "name": "camera_scan",
    "description": (
        "Use when the user explicitly says 'verileri aktar ve yansıt', "
        "'kamerayı tara', or asks to scan a physical object or QR code with "
        "the desktop camera and show the result on AETHER. Captures one frame."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
}


def run(parameters, player=None, session_memory=None):
    request = getattr(player, "scan_camera", None)
    if not callable(request):
        return "Kamera taraması için AETHER masaüstü arayüzü gerekli."
    from core import confirm

    def capture():
        request()  # thread-safe UI signal; no widget is created on this worker
        return "status=unverified action=camera_scan — çekim istendi; sonucu ekrandan kontrol edin."

    return confirm.request("camera_scan", "Kameradan tek kare al",
                           "Masaüstü kamerasından bir görüntü alınacak ve mevcut kamera analizine aktarılacak.", capture)
