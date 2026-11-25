"""Voice control of the bounded local workspace, with a real UI receipt."""
PLUGIN={
    "name":"holo_desk",
    "description":"Open/close Holo Desk (Holo Masa); display a 3D cube, sphere, pyramid or reactor, or reset its view. Hand/camera permission is exclusively a real UI button, never enabled by this tool. No 3D printer or OS mouse control.",
    "parameters":{"type":"OBJECT","properties":{
        "mode":{"type":"STRING","enum":["open","close","reset","object","status"]},
        "shape":{"type":"STRING","enum":["Çekirdek","Küp","Küre","Piramit"]}
    },"required":["mode"]}}


def run(parameters,player=None,session_memory=None):
    try:
        mode=parameters.get("mode","open")
        shape=parameters.get("shape","Küp")
        if mode not in {"open","close","reset","object","status"} or shape not in {"Çekirdek","Küp","Küre","Piramit"}:
            return "[failed] Geçersiz Holo Masa işlemi."
        command=getattr(player,"holo_desk_command",None)
        if not callable(command):return "[unverified] Holo Masa için masaüstü arayüzü gerekli."
        result=command({"mode":mode,"shape":shape})
        if result.get("status")!="done":
            return f"[{result.get('status','unverified')}] Holo Masa doğrulanmadı: {result.get('error') or result.get('reason','sonuç yok')}"
        if mode=="status":
            control="duraklatıldı" if result.get("hand_control_paused") else "etkin"
            release=" Yeniden tutmak için parmaklarını ayır." if result.get("awaiting_hand_release") else ""
            return f"[done] Holo Masa {'açık' if result.get('visible') else 'kapalı'}; kamera isteği {'açık' if result.get('camera_requested') else 'kapalı'}; kamera işlemi {'çalışıyor' if result.get('camera_thread_alive') else 'çalışmıyor'}; el kontrolü {control}; izlenen el: {result.get('hands',0)}.{release}"
        return {"open":"[done] Holo Masa açıldı. Kamera yalnızca ekrandaki düğmeyle açılır.",
                "close":"[done] Holo Masa kapatıldı; kamera durduruldu.",
                "reset":"[done] 3D görünüm sıfırlandı.",
                "object":f"[done] {shape} Holo Masa üzerinde gösterildi."}[mode]
    except Exception as exc:return f"[failed] Holo Masa çalışmadı: {exc}"
