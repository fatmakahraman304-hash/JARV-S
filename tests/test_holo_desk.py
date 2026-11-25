"""Native spatial workspace: permissions, real geometry and retained notes."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint,Qt
from PyQt6.QtTest import QTest
from PyQt6.QtGui import QImage

from core.holo_desk import mesh,parse_obj,obj_text,project,Hands
from gui.holo_desk import HoloDesk
from plugins import holo_desk as command


def hand(ident="Left",x=.4,pinch=True):
    p=np.tile([x,.5,0.],(21,1))
    p[5]=[x-.06,.5,0];p[17]=[x+.06,.5,0]
    p[4]=[x,.35,0];p[8]=[x+(.01 if pinch else .09),.35,0]
    return {"id":ident,"score":.95,"points":p.tolist()}


class SpatialCore(unittest.TestCase):
    def test_shapes_export_as_real_finite_geometry(self):
        for shape in ("Küp","Küre","Piramit","Çekirdek"):
            v,f=mesh(shape);decoded,faces=parse_obj(obj_text(v,f))
            self.assertEqual(faces.shape,f.shape)
            self.assertTrue(np.isfinite(decoded).all())
            posed,a=project(v,.1,.2);_,b=project(v,.7,.4)
            self.assertFalse(np.allclose(a,b))
            self.assertTrue(np.isfinite(posed).all())

    def test_obj_rejects_invalid_indices_nan_and_resource_exhaustion(self):
        for text in ("v nan 0 0\nf 1 1 1", "v 0 0 0\nf 0 1 1", "v 0 0 0\nf 1 2 3", "x"*2000001):
            with self.subTest(text=text[:30]),self.assertRaises(ValueError):parse_obj(text)
        v,f=parse_obj("mtllib https://example.invalid/never-loaded\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1")
        self.assertEqual(f.tolist(),[[0,1,2]])

    def test_pinch_hysteresis_tracking_loss_and_bad_landmarks(self):
        state=Hands()
        first=state.update([hand()]);self.assertTrue(first[0]["pinch"]);self.assertTrue(first[0]["down"])
        self.assertFalse(state.update([hand()])[0]["down"])
        self.assertEqual(state.update([]),[])
        self.assertTrue(state.update([hand()])[0]["down"])
        self.assertFalse(state.update([hand(pinch=False)])[0]["pinch"])
        bad=hand();bad["points"][3][0]=float("nan")
        self.assertEqual(state.update([bad]),[])

    def test_tool_returns_actual_receipt_and_cannot_enable_camera(self):
        player=Mock();player.holo_desk_command.return_value={"status":"done"}
        self.assertIn("[done]",command.run({"mode":"open","camera":True},player))
        player.holo_desk_command.assert_called_once_with({"mode":"open","shape":"Küp"})
        self.assertIn("[failed]",command.run({"mode":"camera"},player))
        player.holo_desk_command.return_value={"status":"failed","error":"broken"}
        self.assertIn("[failed]",command.run({"mode":"open"},player))

    def test_friday_sleep_keeps_local_transient_wake(self):
        from core.snap_wake import is_sleep_command
        self.assertTrue(is_sleep_command("FRIDAY uyku moduna geç"))
        self.assertFalse(is_sleep_command("FRIDAY bilgisayarı kapat"))


class SpatialUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"notes.json"
        self.desk=HoloDesk(notes_path=self.path)
        self.desk.resize(1000,700);self.desk.show();self.app.processEvents()

    def tearDown(self):
        self.desk.close();self.app.processEvents();self.tmp.cleanup()

    def test_open_show_hide_never_requests_camera(self):
        with patch("cv2.VideoCapture") as capture:
            self.desk.action("Nesneler");self.desk.hide();self.desk.show();self.app.processEvents()
            capture.assert_not_called()
        self.assertFalse(self.desk.camera.isChecked())
        self.assertTrue(self.desk.canvas.frame.isNull())

    def test_mouse_changes_rendered_object(self):
        canvas=self.desk.canvas
        before=canvas.grab().toImage()
        QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(430,220))
        QTest.mouseMove(canvas,QPoint(490,270));QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(490,270))
        after=canvas.grab().toImage()
        self.assertNotEqual(before,after)

    def test_two_hand_scale_is_bounded_and_loss_does_not_jump(self):
        state=Hands();canvas=self.desk.canvas
        canvas._grip=("menu","Left")
        canvas.consume_hands(state.update([hand(x=.3),hand("Right",x=.6)]))
        before=canvas.scale
        canvas.consume_hands(state.update([hand(x=.25),hand("Right",x=.7)]))
        self.assertGreater(canvas.scale,before)
        self.assertLessEqual(canvas.scale,2.5)
        canvas.consume_hands([]);scale=canvas.scale
        canvas.consume_hands(state.update([hand(x=.1),hand("Right",x=.8)]))
        self.assertEqual(canvas.scale,scale)

    def test_hand_drags_visible_panel_instead_of_model_under_it(self):
        self.desk.action("Nesneler");self.app.processEvents()
        canvas=self.desk.canvas;panel=self.desk._panels["Nesneler"]
        before=panel.pos();yaw=canvas.yaw
        pointer=np.array([(panel.x()+70)/canvas.width(),(panel.y()+18)/canvas.height()])
        h={"id":"Left","pinch":True,"down":True,"pointer":pointer,"palm":pointer,"width":.1,"points":np.zeros((21,3))}
        canvas.consume_hands([h])
        h=dict(h,down=False,pointer=pointer+np.array([.1,.1]))
        canvas.consume_hands([h])
        self.assertNotEqual(panel.pos(),before)
        self.assertEqual(canvas.yaw,yaw)
        canvas.consume_hands([])

    def test_remaining_hand_can_move_after_menu_owner_is_lost(self):
        canvas=self.desk.canvas
        canvas._grip=("menu","Left")
        h=Hands().update([hand("Right",x=.6)])[0]
        h["down"]=False
        before=canvas.yaw
        canvas.consume_hands([h])
        canvas.consume_hands([dict(h,pointer=h["pointer"]+np.array([.08,0]))])
        self.assertNotEqual(canvas.yaw,before)

    def test_radial_controls_stay_inside_viewport_at_camera_edges(self):
        canvas=self.desk.canvas
        portrait=QImage(240,480,QImage.Format.Format_RGB888);portrait.fill(0)
        for frame in (QImage(),portrait):
            canvas.frame=frame
            bounds=canvas.image_rect()
            for palm in ([.01,.01],[.99,.01],[.01,.99],[.99,.99]):
                for _,point in canvas.ring_items({"palm":palm,"width":.12}):
                    self.assertGreaterEqual(point.x(),bounds.left()+21)
                    self.assertLessEqual(point.x(),bounds.right()-21)
                    self.assertGreaterEqual(point.y(),bounds.top()+21)
                    self.assertLessEqual(point.y(),bounds.bottom()-21)

    def test_pause_ignores_stale_frames_and_resume_waits_for_release(self):
        desk=self.desk
        rgb=np.zeros((360,640,3),np.uint8)
        with desk._lock:desk._packet=(rgb,[hand()])
        desk.pause.click()
        desk._tick()
        self.assertEqual(desk.canvas.hands,[])
        self.assertFalse(desk.camera.isChecked())
        desk.pause.click()
        with desk._lock:desk._packet=(rgb,[hand()])
        desk._tick()
        self.assertTrue(desk._await_release)
        self.assertEqual(desk.canvas.hands,[])
        with desk._lock:desk._packet=(rgb,[hand(pinch=False)])
        desk._tick()
        self.assertFalse(desk._await_release)
        self.assertFalse(desk.canvas.hands[0]["pinch"])
        with desk._lock:desk._packet=(rgb,[hand()])
        desk._tick()
        self.assertTrue(desk.canvas.hands[0]["pinch"])

    def test_notes_survive_close_and_invalid_obj_keeps_working_scene(self):
        self.desk.notes.setPlainText("Murat — proje notu")
        self.desk.hide();self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["notes"],"Murat — proje notu")
        other=HoloDesk(notes_path=self.path)
        self.assertEqual(other.notes.toPlainText(),"Murat — proje notu");other.close()
        obj=Path(self.tmp.name)/"bad.obj";obj.write_text("bad")
        vertices=self.desk.canvas.vertices.copy()
        self.desk._load_obj(obj)
        np.testing.assert_equal(self.desk.canvas.vertices,vertices)

    def test_corrupt_note_is_retained_instead_of_overwritten(self):
        bad=Path(self.tmp.name)/"broken.json";bad.write_text("{broken",encoding="utf-8")
        other=HoloDesk(notes_path=bad)
        self.assertTrue(other.notes.isReadOnly())
        other._save_notes();other.close()
        self.assertEqual(bad.read_text(encoding="utf-8"),"{broken")

    def test_camera_is_released_on_hide_with_bounded_mailbox(self):
        camera=Mock();camera.isOpened.return_value=True
        camera.read.return_value=(True,np.zeros((360,640,3),np.uint8))
        with patch("cv2.VideoCapture",return_value=camera),patch("actions.screen_processor._get_camera_index",return_value=0),patch("core.holo_desk.HandTracker",side_effect=RuntimeError("test, tracking unavailable")):
            self.desk.camera.click()
            deadline=time.monotonic()+3
            while not camera.read.called and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(camera.read.called)
            self.desk.hide()
            self.desk._thread.join(3)
            self.assertFalse(self.desk._thread.is_alive())
        camera.release.assert_called_once()
        self.assertIsNone(self.desk._packet)
        self.assertFalse(self.desk.camera.isChecked())
