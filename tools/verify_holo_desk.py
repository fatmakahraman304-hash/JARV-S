"""Native Qt spatial acceptance and actual MediaPipe inference on Google's sample.

No webcam, microphone, OS clicks or printer is accessed by this probe.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from urllib.request import urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("out",type=Path)
    parser.add_argument("--tracking",action="store_true")
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QPoint,Qt
    from PyQt6.QtGui import QImage
    from PyQt6.QtTest import QTest
    import numpy as np
    from gui.holo_desk import HoloDesk
    from core.holo_desk import mesh,obj_text,parse_obj,Hands
    app=QApplication(sys.argv)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"notes.json"
        desk=HoloDesk(notes_path=path);desk.resize(1180,760);desk.show()
        app.processEvents()
        assert not desk.camera.isChecked() and desk._thread is None,"Camera opened without user input"
        desk.action("Nesneler");desk.action("Widget");desk._tick()
        app.processEvents();desk.grab().save(str(args.out/"1-native-workspace.png"))
        before=desk.canvas.grab().toImage()
        QTest.mousePress(desk.canvas,Qt.MouseButton.LeftButton,pos=QPoint(600,180))
        QTest.mouseMove(desk.canvas,QPoint(690,240));QTest.mouseRelease(desk.canvas,Qt.MouseButton.LeftButton,pos=QPoint(690,240))
        after=desk.canvas.grab().toImage()
        assert before!=after,"Mouse did not change the 3D object"
        desk.notes.setPlainText("FRIDAY — doğrulanmış yerel not")
        desk.hide();app.processEvents()
        assert json.loads(path.read_text(encoding="utf-8"))["notes"]=="FRIDAY — doğrulanmış yerel not"
        assert not desk.timer.isActive() and not desk.camera.isChecked()
        desk.show();app.processEvents()
        for shape in ("Küp","Küre","Piramit","Çekirdek"):
            desk.set_shape(shape)
            vertices,faces=parse_obj(obj_text(*mesh(shape)))
            assert len(faces)>0 and np.isfinite(vertices).all()
        # Steady-state software renderer cost, not a physical-GPU claim.
        started=time.perf_counter()
        for _ in range(20):
            desk.canvas.yaw+=.02;desk.canvas.grab()
        print(f"native 3D draw: {(time.perf_counter()-started)*1000/20:.2f} ms/frame")
        if args.tracking:
            from core.holo_desk import HandTracker,install_tracking
            model=install_tracking()
            # Source fixture used by Google's own Hand Landmarker notebook.
            with urlopen("https://storage.googleapis.com/mediapipe-tasks/hand_landmarker/woman_hands.jpg",timeout=30) as response:
                sample=response.read(4000000)
            import cv2
            bgr=cv2.imdecode(np.frombuffer(sample,np.uint8),cv2.IMREAD_COLOR)
            assert bgr is not None,"Public hand fixture unavailable"
            tracker=HandTracker(model)
            try:
                rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
                result=tracker.detect(rgb,0)
                assert len(result)==2 and all(len(h["points"])==21 for h in result),"Real inference failed to find 2 hands"
                # Do not put the fixture's photograph in the public artifact.
                desk.canvas.frame=QImage()
                desk.canvas.consume_hands(Hands().update(result,aspect=rgb.shape[1]/rgb.shape[0]))
                desk.status.setText("TEST: Google örnek görselinden gerçek el çıkarımı · Canlı kamera kapalı")
                app.processEvents();desk.grab().save(str(args.out/"2-hand-inference.png"))
                print("PASS: real MediaPipe inference, 2 hands, 21 landmarks each; no webcam access")
            finally:tracker.close()
        desk.close();app.processEvents()
    print("PASS: native Qt desk, 3D rotation, OBJ roundtrip, note persistence, hide/close, camera off by default")
    return 0


if __name__=="__main__":raise SystemExit(main())
