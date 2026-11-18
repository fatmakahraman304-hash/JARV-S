"""gui/holo_panel.py — the hologram table, inside JARVIS's own window.

"Jarvis, can you digitise this and give me a manipulable projection?"
Show an object to the camera → three frames go to Gemini (core/holo_scan) →
the model stands where the core was, rendered on the GPU (gui/holo_gl): a
studio-real render, or the glowing Iron Man hologram. Hands in front of the
camera move it (MediaPipe, if installed):

  pinch + drag            rotate          two-hand pinch   zoom / move
  open palm, hold         explode / back  fist, hold       reset
  point                   name the part   open hand, swipe throw it away

Mouse: drag rotate, right-drag move, wheel zoom, double-click explode.
Spoken commands arrive through plugins/hologram.py → JarvisUI.show_hologram.

Camera and hand tracking run on a worker thread; it only stores the latest
frame and hands. Every widget is touched on the Qt thread (the timer).
"""
from __future__ import annotations

import json
import math
import queue
import threading
import time
from pathlib import Path

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from core import holo_model
from gui.style import btn_css, px_font, with_alpha
from gui.theme import C, qcol

ROOT = Path(__file__).resolve().parent.parent
LIBRARY = ROOT / "memory" / "holo_models.json"
EXPORT_DIR = Path.home() / "Documents" / "JARVIS Modeller"
HAND_TASK = ROOT / "memory" / "hand_landmarker.task"
HAND_TASK_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
BONES = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12), (9, 13),
         (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]
ICON = {"pinch": "🤏", "open": "🖐", "fist": "✊", "point": "☝"}


# ── the library of saved models ───────────────────────────────────────────────

def load_library() -> list:
    try:
        data = json.loads(LIBRARY.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_to_library(model: dict) -> None:
    if not model.get("id"):                                # every saved model needs its own id (gallery, thumbnails)
        import uuid
        model["id"] = uuid.uuid4().hex[:12]
    lib = [m for m in load_library() if m.get("id") != model.get("id")] + [model]
    LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIBRARY.with_suffix(".tmp")
    tmp.write_text(json.dumps(lib[-40:], ensure_ascii=False), encoding="utf-8")
    tmp.replace(LIBRARY)


def delete_from_library(model_id) -> None:
    lib = [m for m in load_library() if m.get("id") != model_id]
    LIBRARY.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIBRARY.with_suffix(".tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LIBRARY)


def sharpest(frames: list[bytes]) -> bytes:
    """The least blurred of the scan frames (variance of the Laplacian)."""
    try:
        import cv2
        best, score = frames[0], -1.0
        for f in frames:
            img = cv2.imdecode(np.frombuffer(f, np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            v = float(cv2.Laplacian(img, cv2.CV_64F).var())
            if v > score:
                best, score = f, v
        return best
    except Exception:
        return frames[len(frames) // 2]


# ── camera + hands on a worker thread ─────────────────────────────────────────

class CameraWorker(threading.Thread):
    def __init__(self, log):
        super().__init__(daemon=True, name="holo-camera")
        self.log = log
        self.lock = threading.Lock()
        self.frame = None                     # latest BGR frame
        self.hands = []                       # [[(x, y) * 21], ...] in image fractions
        self.want_hands = False
        self.hand_note = ""
        self.running = True
        self.failed = ""
        self._tracker = None

    def stop(self):
        self.running = False

    def jpeg(self, quality: int = 90) -> bytes:
        import cv2
        with self.lock:
            f = None if self.frame is None else self.frame.copy()
        if f is None:
            return b""
        ok, buf = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        return buf.tobytes() if ok else b""

    def _make_tracker(self):
        """MediaPipe hands: the classic solution if present, else the Tasks
        API with its model file (downloaded once into memory/)."""
        try:
            import mediapipe as mp
        except Exception:
            self._install_mediapipe()
            return None
        try:
            hands = mp.solutions.hands.Hands(max_num_hands=2, model_complexity=0,
                                             min_detection_confidence=0.6, min_tracking_confidence=0.5)

            def run(rgb):
                res = hands.process(rgb)
                return [[(p.x, p.y) for p in h.landmark] for h in (res.multi_hand_landmarks or [])]
            return run
        except Exception:
            pass
        try:
            from mediapipe.tasks import python as mpt
            from mediapipe.tasks.python import vision
            if not HAND_TASK.exists():
                import urllib.request
                HAND_TASK.parent.mkdir(parents=True, exist_ok=True)
                urllib.request.urlretrieve(HAND_TASK_URL, str(HAND_TASK))
            lm = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=str(HAND_TASK)),
                running_mode=vision.RunningMode.VIDEO, num_hands=2))
            t0 = time.monotonic()

            def run(rgb):
                img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                res = lm.detect_for_video(img, int((time.monotonic() - t0) * 1000))
                return [[(p.x, p.y) for p in h] for h in (res.hand_landmarks or [])]
            return run
        except Exception as exc:
            self.hand_note = f"El takibi başlatılamadı: {type(exc).__name__}"
            self.log(f"[Hologram] hand tracker: {exc}")
            return None

    _installing = False

    def _install_mediapipe(self):
        """El takibi kurulu değil: bir kez arka planda kur, bitince yeniden dene."""
        if CameraWorker._installing:
            return
        CameraWorker._installing = True
        self.hand_note = "El takibi (mediapipe) ilk kez kuruluyor, bir iki dakika… bu sırada fareyle kontrol edebilirsin."

        def go():
            try:
                from core.installer import _pip
                ok = _pip("mediapipe", log=self.log)
            except Exception as exc:
                self.log(f"[Hologram] mediapipe install: {exc}")
                ok = False
            self.hand_note = ("El takibi kuruldu — 🖐 EL'e tekrar bas." if ok else
                              "mediapipe kurulamadı (bu Python sürümü desteklenmiyor olabilir); fareyle kontrol et.")
            CameraWorker._installing = False
        threading.Thread(target=go, daemon=True, name="holo-mediapipe").start()

    def run(self):
        try:
            import cv2
            try:
                from actions.screen_processor import _cv2_backend, _get_camera_index
                cap = cv2.VideoCapture(_get_camera_index(), _cv2_backend())
            except Exception:
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self.failed = "Kamera açılamadı."
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        except Exception as exc:
            self.failed = f"Kamera açılamadı: {exc}"
            return
        try:
            while self.running:
                ok, f = cap.read()
                if not ok:
                    time.sleep(0.03)
                    continue
                hands = []
                if self.want_hands:
                    if self._tracker is None and not self.hand_note:
                        self._tracker = self._make_tracker()
                    if self._tracker is not None:
                        try:
                            hands = self._tracker(cv2.cvtColor(cv2.resize(f, (640, 360)), cv2.COLOR_BGR2RGB))
                        except Exception as exc:
                            self.log(f"[Hologram] hands: {exc}")
                with self.lock:
                    self.frame, self.hands = f, hands
        finally:
            cap.release()


# ── the panel ─────────────────────────────────────────────────────────────────

class HoloPanel(QWidget):
    back_requested = pyqtSignal()
    note = pyqtSignal(str)                    # a line for the activity log

    def __init__(self, parent=None):
        super().__init__(parent)
        from gui.holo_gl import Camera, HoloGL, SoftRenderer
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.cam = Camera()
        self.gl, self.soft = HoloGL(), SoftRenderer()
        self.model: dict | None = None
        self.mesh = None
        self.holo = False
        self.explode, self.explode_to = 0.0, 0.0
        self.sel, self.hover = -1, -1
        self.engine = "real"                  # "real": AI image-to-3D first; "parts": Gemini's parts model
        self.cut = None                       # section view: fraction across the model (0 left … 1 right), None off
        self.measure = False
        self.iso = -1                         # the part shown alone
        self.cursor = None                    # (x, y) widget fractions (pointing finger / mouse)
        self.status, self.status_until = "", 0.0
        self.count = ""
        self.busy = False
        self.worker: CameraWorker | None = None
        self.hands_on = False
        self.gst: dict = {}
        self.last_input = time.monotonic()
        self.throw_t = 0.0
        self.build_t = 0.0
        self.results: queue.Queue = queue.Queue()
        self._img = None
        self._last_key, self._key_since, self._still_img = None, 0.0, None
        self._drag = None
        self._t0 = time.monotonic()
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    # ── layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = QHBoxLayout()
        top.setContentsMargins(18, 14, 18, 0)
        top.setSpacing(8)
        top.addStretch()
        self.btns = {}
        for key, text, kind in (("scan", "📷  TARA", "primary"), ("engine", "🧠  GERÇEK 3B", "choice"), ("detail", "🔎  DETAY", "choice"), ("hands", "🖐  EL", "off"),
                                ("look", "◐  HOLOGRAM", "choice"), ("explode", "💥  PARÇALA", "off"), ("cut", "✂  KESİT", "off"),
                                ("measure", "📏  ÖLÇ", "off"), ("reset", "⟲", "dim"), ("save", "💾", "dim"),
                                ("shot", "📸 4K", "dim"), ("video", "🎬", "dim"), ("stl", "⬇ DIŞA AKTAR", "dim"), ("lib", "📂", "dim"),
                                ("key", "🔑", "dim"), ("close", "✕", "dim")):
            b = QPushButton(text)
            b.setFixedHeight(34)
            b.setMinimumWidth(40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(btn_css(kind, "center"))
            b.setFont(px_font(12, mono=False))
            b.clicked.connect(lambda _=False, k=key: self.command({"action": k}))
            top.addWidget(b)
            self.btns[key] = b
        bottom = QHBoxLayout()
        bottom.setContentsMargins(18, 0, 18, 16)
        bottom.addStretch()
        self.input = QLineEdit()
        self.input.setPlaceholderText("“kanatları kırmızı yap”, “bir Iron Man kaskı modelle”…  (ya da sesle söyle)")
        self.input.setFixedHeight(38)
        self.input.setMinimumWidth(420)
        self.input.setFont(px_font(13))
        self.input.setStyleSheet(f"QLineEdit {{ background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER_B};"
                                 f" border-radius: 19px; padding: 0 16px; }} QLineEdit:focus {{ border-color: {C.PRI}; }}")
        self.input.returnPressed.connect(self._typed)
        bottom.addWidget(self.input, 1)
        bottom.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addStretch()
        lay.addLayout(bottom)

    def _typed(self):
        t = self.input.text().strip()
        self.input.clear()
        if t:
            self.command({"action": "say", "request": t})

    # ── life ──────────────────────────────────────────────────────────────────
    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start(33)
        if self.model is None:
            m = (load_library() or [None])[-1]
            if m:
                self.set_model(holo_model.clean(m), animate=False)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()
        self.stop_camera()

    def stop_camera(self):
        if self.worker:
            self.worker.stop()
            self.worker = None
        self.hands_on = False
        self._mark("hands", False)

    def _ensure_camera(self) -> bool:
        if self.worker is None or not self.worker.is_alive():
            self.worker = CameraWorker(lambda m: print(m))
            self.worker.start()
        return True

    def _mark(self, key, on):
        b = self.btns.get(key)
        if b:
            b.setStyleSheet(btn_css("on" if on else ("dim" if key in ("lib",) else "off"), "center"))

    def flash(self, text: str, seconds: float = 3.5):
        self.status, self.status_until = text, time.monotonic() + seconds
        self.update()

    # ── model ─────────────────────────────────────────────────────────────────
    def set_model(self, m: dict | None, animate: bool = True):
        self.model = m
        self.sel = self.hover = -1
        self.iso = -1
        self.explode = self.explode_to = 0.0
        self._mark("explode", False)
        self.throw_t = 0.0
        if not m or not (m.get("parts") or m.get("glb")):
            self.mesh = None
            self.model = None
            self.update()
            return
        try:
            photo = holo_model.decode_photo(m.get("photo", ""))
            self.mesh = holo_model.build_mesh(m, photo)
        except Exception as exc:
            self.mesh, self.model = None, None
            self.flash(f"Model açılamadı: {exc}", 6)
            return
        self.build_t = time.monotonic() if animate else 0.0
        self.update()

    # ── commands (buttons, typed, spoken) ─────────────────────────────────────
    def command(self, cmd: dict) -> None:
        a = str(cmd.get("action") or "").lower()
        req = str(cmd.get("request") or "").strip()
        self.last_input = time.monotonic()
        if a == "say":
            import re as _re
            m_iso = _re.search(r"sadece (.+?) (göster|kalsın|görünsün)", req.casefold())
            if m_iso and self.model:
                self.command({"action": "isolate", "request": m_iso.group(1)})
                return
            local = holo_model.local_command(req)
            if local:
                a = local
            else:
                a = "edit" if self.model else "make"
        if a == "scan":
            self._scan()
        elif a == "make" or (a == "edit" and not self.model):
            self._job("TASARLANIYOR", lambda: self._make(req or "bir model"))
        elif a == "edit":
            m = self.model
            if m.get("glb"):
                self._job("GÜNCELLENİYOR", lambda: self._edit_real(m, req))
            else:
                self._job("GÜNCELLENİYOR", lambda: __import__("core.holo_scan", fromlist=["x"]).edit(m, req), keep_view=True)
        elif a in ("engine", "real_engine", "parts_engine"):
            self.engine = {"real_engine": "real", "parts_engine": "parts"}.get(a, "parts" if self.engine == "real" else "real")
            self.btns["engine"].setText("🧠  GERÇEK 3B" if self.engine == "real" else "🧩  PARÇA")
            self.flash("Motor: " + ("gerçek 3B (yapay zekâ ile fotoğraftan doku ve şekil)" if self.engine == "real" else "parça modeli (Gemini)"))
        elif a == "upright":
            if self.model and self.model.get("glb"):
                self.model["upright"] = (int(self.model.get("upright") or 0) + 1) % 4
                self.model["parts"] = []
                self.set_model(self.model, animate=False)
                save_to_library(self.model)
        elif a == "detail" and self.model and self.model.get("glb"):
            self.flash("Bu gerçek 3B tarama; ayrıntı turu parça modelleri için. Daha iyi sonuç için ışığı artırıp yeniden tara.")
        elif a == "detail":
            if not self.model:
                self.flash("Önce bir model tara ya da iste")
            else:
                m = self.model
                frames = [self.worker.jpeg()] if self.worker and self.worker.frame is not None and m.get("photo") else []
                self._job("AYRINTILANDIRILIYOR", lambda: __import__("core.holo_scan", fromlist=["x"]).detail(m, [f for f in frames if f], progress=self._progress), keep_view=True)
        elif a == "cut":
            on = cmd.get("on")
            self.cut = (0.5 if self.cut is None else None) if on is None else (0.5 if on else None)
            self._mark("cut", self.cut is not None)
            if self.cut is not None:
                self.flash("✂ Kesit: Shift + tekerlek ile kaydır")
        elif a == "measure":
            self.measure = not self.measure if cmd.get("on") is None else bool(cmd.get("on"))
            self._mark("measure", self.measure)
        elif a == "isolate":
            i = self._find_part(req) if req else (self.sel if self.sel >= 0 else self.hover)
            self.iso = -1 if i is None or i < 0 or i == self.iso else i
            if self.iso >= 0:
                self.flash(f"🔍 {self.model['parts'][self.iso]['name']} — çift tıkla ya da 'hepsini göster' de")
        elif a == "show_all":
            self.iso = -1
        elif a in ("explode", "assemble"):
            self.explode_to = 0.0 if a == "assemble" or self.explode_to > 0.5 else 1.0
            self._mark("explode", self.explode_to > 0.5)
        elif a == "reset":
            self.cam.reset(); self.explode_to = 0.0; self.sel = -1; self._mark("explode", False)
        elif a in ("look", "real", "holo"):
            self.holo = (not self.holo) if a == "look" else a == "holo"
            self.btns["look"].setText("◼  GERÇEKÇİ" if self.holo else "◐  HOLOGRAM")
        elif a == "hands":
            self._toggle_hands(cmd.get("on"))
        elif a == "save":
            if self.model:
                save_to_library(self.model)
                self.flash("💾 Kaydedildi: " + self.model["name"])
        elif a == "stl":
            self._stl()
        elif a in ("shot", "4k", "render"):
            self._shot()
        elif a in ("video", "turntable"):
            self._turntable()
        elif a == "key":
            self._ask_key()
        elif a == "cancel":
            self.cancel()
        elif a == "lib":
            self._toggle_gallery()
        elif a == "throw":
            if self.model:
                save_to_library(self.model)
                self.throw_t = time.monotonic()
        elif a == "close":
            self.back_requested.emit()
        self.update()

    def _job(self, label: str, fn, keep_view: bool = False):
        if self.busy:
            self.flash("Hâlâ çalışıyorum…")
            return
        self.busy = True
        self.status, self.status_until = label + "…", time.monotonic() + 600
        self.job_t0, ticket = time.monotonic(), self._new_ticket()

        def run():
            try:
                m, msg = fn()
            except Exception as exc:
                m, msg = None, f"Hata: {exc}"
            self.results.put((m, msg, keep_view, ticket))
        threading.Thread(target=run, daemon=True, name="holo-gemini").start()

    def _find_part(self, name: str):
        if not self.model:
            return None
        q = name.casefold().strip()
        names = [p["name"].casefold() for p in self.model["parts"]]
        for i, n in enumerate(names):
            if n == q:
                return i
        for i, n in enumerate(names):
            if q and (q in n or n in q):
                return i
        return None

    # ── the real-3D engine (core/holo_ai3d), with the parts model behind it ───
    def _real_from_photo(self, jpeg: bytes, prompt: str = "", source: str = ""):
        from core import holo_ai3d
        if not source:
            holo_ai3d.GLB_DIR.mkdir(parents=True, exist_ok=True)
            source = str(holo_ai3d.GLB_DIR / f"src_{int(time.time() * 1000):x}.jpg")
            Path(source).write_bytes(jpeg)
        self._progress("ÖLÇÜLÜYOR…")
        info = holo_ai3d.measure(prompt, jpeg)
        glb, provider, msg = holo_ai3d.image_to_3d(source, progress=self._progress, log=print)
        if not glb:
            return None, msg
        m = holo_ai3d.build(glb, provider, info, source=source, prompt=prompt)
        return m, f"{m['name']}: gerçek 3B model ({provider})."

    def _make(self, text: str):
        if self.engine == "real":
            from core import holo_ai3d
            self._progress("REFERANS GÖRÜNTÜ ÇİZİLİYOR…")
            ref, note = holo_ai3d.reference_image(text)
            if ref:
                m, msg = self._real_from_photo(Path(ref).read_bytes(), text, ref)
                if m:
                    return m, msg
                note = msg
            from core import holo_scan
            m, msg = holo_scan.create(text, progress=self._progress)
            return m, (f"{msg} (Gerçek 3B olmadı: {note[:120]} — parça modeli yaptım.)" if m and note else msg)
        from core import holo_scan
        return holo_scan.create(text, progress=self._progress)

    def _edit_real(self, m: dict, change: str):
        from core import holo_ai3d
        src = m.get("source_image") or ""
        self._progress("GÖRÜNTÜ DEĞİŞTİRİLİYOR…")
        if src and Path(src).exists():
            ref, note = holo_ai3d.reference_image(change, edit_from=src)
        else:
            ref, note = holo_ai3d.reference_image(f"{m.get('prompt') or m.get('name')}, {change}")
        if not ref:
            return None, note or "Değişikliği çizemedim."
        return self._real_from_photo(Path(ref).read_bytes(), f"{m.get('name')}: {change}", ref)

    def _progress(self, text: str):
        self.status, self.status_until = text, time.monotonic() + 600       # read by paintEvent on the Qt thread

    def _scan(self):
        self._ensure_camera()
        if self.busy:
            return
        self.busy = True
        self.job_t0, ticket = time.monotonic(), self._new_ticket()

        def put(m, msg, keep=False):
            self.results.put((m, msg, keep, ticket))

        def run():
            try:
                for n in ("3", "2", "1"):
                    self.count = n
                    time.sleep(0.65)
                self.count = ""
                self.status, self.status_until = "TARANIYOR — nesneyi yavaşça biraz çevir", time.monotonic() + 600
                frames = []
                for _ in range(5):
                    if self.worker and self.worker.failed:
                        break
                    j = self.worker.jpeg() if self.worker else b""
                    if j:
                        frames.append(j)
                    time.sleep(0.5)
                if not frames:
                    put(None, (self.worker.failed if self.worker else "") or "Kameradan görüntü alınamadı.")
                    return
                self.status = "DİJİTALLEŞTİRİLİYOR…"
                m, msg = (None, "")
                if self.engine == "real":
                    m, msg = self._real_from_photo(sharpest(frames))
                if m is None:
                    from core import holo_scan
                    note = msg
                    m, msg = holo_scan.scan(frames, progress=self._progress)
                    if note and m:
                        msg = f"{msg} (Gerçek 3B olmadı: {note[:120]} — parça modeli yaptım.)"
                put(m, msg)
            except Exception as exc:
                put(None, f"Tarama hatası: {exc}")
        threading.Thread(target=run, daemon=True, name="holo-scan").start()

    _ticket = 0

    def _new_ticket(self) -> int:
        self._ticket += 1
        return self._ticket

    def cancel(self):
        """Stop waiting for the running scan / model (it may finish in the background, unseen)."""
        if self.busy:
            self._new_ticket()
            self.busy, self.count, self.status_until = False, "", 0
            self.flash("İptal edildi")

    def _ask_key(self):
        """A text box for the Hugging Face / Tripo / Meshy key (the real-3D engine's quota)."""
        from PyQt6.QtWidgets import QInputDialog, QLineEdit
        try:
            from memory.config_manager import get_hf_token, load_api_keys
            have = [n for n, ok in (("Hugging Face", get_hf_token()), ("Tripo", load_api_keys().get("tripo_key")),
                                     ("Meshy", load_api_keys().get("meshy_key"))) if ok]
        except Exception:
            have = []
        text, ok = QInputDialog.getText(
            self, "Gerçek 3B anahtarı",
            ("Kayıtlı: " + ", ".join(have) + "\n\n" if have else "") +
            "Ücretsiz Hugging Face anahtarı (hf_…): huggingface.co → Settings → Access Tokens → New token (Read).\n"
            "Ya da Tripo (tsk_…) / Meshy (msy_…) anahtarı:", QLineEdit.EchoMode.Password)
        if ok and text.strip():
            from plugins import hologram
            self.flash(hologram.run({"action": "hf_token", "request": text.strip()}, None), 6)

    def _turntable(self):
        """A 6-second 360° turntable video (1920×1080, MP4) of the model."""
        if not self.mesh:
            self.flash("Videoya alınacak model yok")
            return
        import cv2
        from gui.holo_gl import bloom
        W, H, N = 1920, 1080, 180
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.model["name"]).strip("_") or "model"
        path = EXPORT_DIR / f"{safe}_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
        if not vw.isOpened():
            self.flash("Video dosyası açılamadı")
            return
        acc = qcol(C.PRI)
        yaw0 = self.cam.yaw
        bg = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(bg); self._background(p, W, H); p.end()
        try:
            for i in range(N):
                self.cam.yaw = yaw0 + 360.0 * i / N
                img = self.gl.render(self.mesh, self.cam, W, H, holo=self.holo, accent=(acc.redF(), acc.greenF(), acc.blueF()),
                                     t=i / 30.0, explode=self.explode) or self.soft.render(self.mesh, self.cam, W, H, holo=self.holo,
                                                                                       accent=(acc.redF(), acc.greenF(), acc.blueF()), t=i / 30.0)
                frame = bg.copy()
                p = QPainter(frame); p.drawImage(0, 0, bloom(img, 0.9 if self.holo else 0.45)); p.end()
                frame = frame.convertToFormat(QImage.Format.Format_RGB888)
                ptr = frame.constBits(); ptr.setsize(frame.sizeInBytes())
                arr = np.frombuffer(ptr, np.uint8).reshape(H, frame.bytesPerLine())[:, :W * 3].reshape(H, W, 3)
                vw.write(arr[:, :, ::-1].copy())
        finally:
            vw.release()
            self.cam.yaw = yaw0
        self.flash(f"🎬 Video kaydedildi: {path.name}", 6)
        self.note.emit(f"SYS: 🧊 Dönen video: {path}")

    def _toggle_hands(self, on=None):
        self.hands_on = (not self.hands_on) if on is None else bool(on)
        if self.hands_on:
            self._ensure_camera()
        if self.worker:
            self.worker.want_hands = self.hands_on
        self._mark("hands", self.hands_on)
        if self.hands_on:
            self.flash("🖐 Ellerini kameraya göster: çimdikle döndür, iki elle yakınlaştır")

    def _stl(self):
        """STL (3D printer), OBJ (Blender / CAD) and GLB (textured, everywhere) side by side."""
        if not self.mesh:
            self.flash("İndirilecek model yok")
            return
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.model["name"]).strip("_") or "model"
        done = []
        for ext, make in (("stl", self.mesh.stl), ("obj", lambda: holo_model.export_obj(self.mesh)),
                          ("glb", lambda: holo_model.export_glb(self.mesh, self.model))):
            try:
                (EXPORT_DIR / f"{safe}.{ext}").write_bytes(make())
                done.append(ext.upper())
            except Exception as exc:
                self.note.emit(f"SYS: 🧊 {ext.upper()} kaydedilemedi: {exc}")
        if done:
            self.flash(f"⬇ {' + '.join(done)} → {EXPORT_DIR / safe}", 6)
            self.note.emit(f"SYS: 🧊 Dışa aktarıldı ({', '.join(done)}): {EXPORT_DIR / safe}")
        else:
            self.flash("Dışa aktarılamadı")

    def _shot(self):
        """A 3840×2160 render of what is on the table, saved as PNG."""
        if not self.mesh:
            self.flash("Görüntülenecek model yok")
            return
        from gui.holo_gl import bloom, render_still
        W, H = 3840, 2160
        acc = qcol(C.PRI)
        kw = dict(holo=self.holo, accent=(acc.redF(), acc.greenF(), acc.blueF()), t=time.monotonic() - self._t0,
                  explode=self.explode, sel=-1)
        img = render_still(self.gl, self.mesh, self.cam, W, H, ss=1.5, **kw) or self.soft.render(self.mesh, self.cam, W, H, **kw)
        img = bloom(img, 0.9 if self.holo else 0.45)
        out = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(out)
        self._background(p, W, H)
        p.drawImage(0, 0, img)
        p.end()
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.model["name"]).strip("_") or "model"
        path = EXPORT_DIR / f"{safe}_{time.strftime('%Y%m%d_%H%M%S')}_4K.png"
        if out.save(str(path)):
            self.flash(f"📸 4K kaydedildi: {path.name}")
            self.note.emit(f"SYS: 🧊 4K görüntü: {path}")
        else:
            self.flash("4K görüntü kaydedilemedi")

    def _background(self, p, W, H):
        bg = QRadialGradient(QPointF(W / 2, H * 0.58), max(W, H) * 0.75)
        bg.setColorAt(0, qcol(C.PRI_GHO) if self.holo else QColor(26, 22, 19))
        bg.setColorAt(0.55, qcol(C.BG))
        bg.setColorAt(1, QColor(0, 0, 0))
        p.fillRect(QRectF(0, 0, W, H), bg)

    THUMBS = ROOT / "memory" / "holo_thumbs"

    def _thumb(self, m: dict) -> QImage | None:
        """A small render of a saved model (made once, kept beside the library)."""
        f = self.THUMBS / f"{m.get('id', 'x')}.png"
        if f.exists():
            img = QImage(str(f))
            if not img.isNull():
                return img
        try:
            from gui.holo_gl import Camera
            mesh = holo_model.build_mesh(holo_model.clean(m))
            cam = Camera()
            cam.yaw, cam.pitch = -30, 14
            img = self.gl.render(mesh, cam, 320, 220, holo=False, accent=(1.0, 0.54, 0.11), t=1.0) \
                or self.soft.render(mesh, cam, 320, 220, holo=False, accent=(1.0, 0.54, 0.11), t=1.0)
            out = QImage(320, 220, QImage.Format.Format_ARGB32_Premultiplied)
            p = QPainter(out)
            g = QRadialGradient(QPointF(160, 130), 220)
            g.setColorAt(0, QColor(30, 26, 22)); g.setColorAt(1, QColor(4, 3, 3))
            p.fillRect(0, 0, 320, 220, g); p.drawImage(0, 0, img); p.end()
            self.THUMBS.mkdir(parents=True, exist_ok=True)
            out.save(str(f))
            return out
        except Exception:
            return None

    def _toggle_gallery(self):
        """The saved models as a grid of pictures: click to open, right-click to delete."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QIcon, QPixmap
        from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QListView, QMenu
        g = getattr(self, "gallery", None)
        if g is not None and g.isVisible():
            g.hide()
            self._mark("lib", False)
            return
        lib = load_library()
        if not lib:
            self.flash("Henüz kayıtlı model yok — 💾 ile kaydet")
            return
        if g is None:
            g = self.gallery = QListWidget(self)
            g.setViewMode(QListView.ViewMode.IconMode)
            g.setIconSize(QSize(240, 165))
            g.setGridSize(QSize(262, 205))
            g.setResizeMode(QListView.ResizeMode.Adjust)
            g.setMovement(QListView.Movement.Static)
            g.setWordWrap(True)
            g.setFont(px_font(12))
            g.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            g.setStyleSheet(f"QListWidget {{ background: rgba(6,5,4,235); color: {C.TEXT}; border: 1px solid {C.BORDER_B};"
                            f" border-radius: 14px; padding: 12px; }} QListWidget::item:selected {{ background: {C.PRI_GHO};"
                            f" border: 1px solid {C.PRI}; border-radius: 8px; }}")

            def open_item(it):
                mid = it.data(Qt.ItemDataRole.UserRole)
                for m in load_library():
                    if m.get("id") == mid:
                        self.set_model(holo_model.clean(m))
                        self.cam.reset()
                        self.flash(f"📂 {m.get('name', '')}")
                g.hide()
                self._mark("lib", False)

            def menu(pos):
                it = g.itemAt(pos)
                if it is None:
                    return
                mn = QMenu(g)
                act = mn.addAction("🗑  Sil")
                if mn.exec(g.mapToGlobal(pos)) == act:
                    mid = it.data(Qt.ItemDataRole.UserRole)
                    delete_from_library(mid)
                    (self.THUMBS / f"{mid}.png").unlink(missing_ok=True)
                    g.takeItem(g.row(it))
            g.itemClicked.connect(open_item)
            g.customContextMenuRequested.connect(menu)
        g.clear()
        for m in reversed(lib):
            img = self._thumb(m)
            kind = "🧠" if m.get("glb") else "🧩"
            it = QListWidgetItem(QIcon(QPixmap.fromImage(img)) if img is not None else QIcon(), f"{kind} {m.get('name', 'model')}")
            it.setData(Qt.ItemDataRole.UserRole, m.get("id"))
            g.addItem(it)
        r = self.rect().adjusted(60, 64, -60, -70)
        g.setGeometry(r)
        g.show(); g.raise_()
        self._mark("lib", True)

    def _cycle_library(self):
        lib = load_library()
        if not lib:
            self.flash("Henüz kayıtlı model yok")
            return
        ids = [m.get("id") for m in lib]
        cur = self.model.get("id") if self.model else None
        i = (ids.index(cur) - 1) % len(lib) if cur in ids else len(lib) - 1
        self.set_model(holo_model.clean(lib[i]))
        self.cam.reset()
        self.flash(f"📂 {i + 1}/{len(lib)}: {lib[i].get('name', '')}")

    # ── frame ─────────────────────────────────────────────────────────────────
    def _tick(self):
        now = time.monotonic()
        while not self.results.empty():
            m, msg, keep, ticket = self.results.get()
            if ticket != self._ticket:
                continue                                    # cancelled: the answer came too late
            self.busy = False
            self.status_until = 0
            if m:
                view = (self.cam.yaw, self.cam.pitch, self.cam.zoom) if keep else None
                self.set_model(m, animate=not keep)
                if view:
                    self.cam.yaw, self.cam.pitch, self.cam.zoom = view
                else:
                    self.cam.reset()
                save_to_library(m)
                self.note.emit(f"SYS: 🧊 Hologram: {msg}")
            else:
                self.flash(msg, 6)
                self.note.emit(f"SYS: 🧊 {msg}")
        self.explode += (self.explode_to - self.explode) * 0.14
        if abs(self.explode - self.explode_to) < 0.002:
            self.explode = self.explode_to
        if self.mesh is not None and now - self.last_input > 15 and self._drag is None:
            self.cam.yaw += 0.18
        if self.worker and self.hands_on:
            self._apply_hands(now)
        if self.throw_t and now - self.throw_t > 0.6:
            self.set_model(None)
            self.flash("Model atıldı — 📂 ile geri getirebilirsin")
        self.update()

    def _apply_hands(self, now):
        with self.worker.lock:
            hands = list(self.worker.hands)
        if self.worker.hand_note:
            self.flash(self.worker.hand_note, 5)
            self.worker.hand_note = ""
            self.hands_on = False
            self._mark("hands", False)
            return
        lst = []
        for L in hands:
            k = holo_model.pose([{"x": x, "y": y} for x, y in L])
            x, y = holo_model.anchor([{"x": x, "y": y} for x, y in L], k)
            lst.append((k, (1 - x, y)))                     # mirrored, like the preview
        self._hand_view = hands
        if lst:
            self.last_input = now
        o = holo_model.gesture_step(self.gst, lst, now)
        self.cam.yaw += o["rotate"][0]
        self.cam.pitch = max(-85, min(85, self.cam.pitch + o["rotate"][1]))
        self.cam.zoom = max(0.25, min(6, self.cam.zoom * o["zoom"]))
        self.cam.pan[0] += o["pan"][0] * 0.8
        self.cam.pan[1] += o["pan"][1] * 0.8
        self.cursor = o["cursor"]
        if o["action"]:
            self.command({"action": o["action"]})

    def _pick(self, w, h):
        if self.mesh is None or self.cursor is None:
            return -1
        ids = list(self.mesh.part_center)
        pts = np.array([self.mesh.part_center[i] + (self.mesh.part_center[i] - self.mesh.center) * self.explode * holo_model.EXPLODE for i in ids])
        S = self.cam.project(self.mesh, pts, w, h)
        cx, cy = self.cursor[0] * w, self.cursor[1] * h
        d = np.hypot(S[:, 0] - cx, S[:, 1] - cy)
        d[S[:, 2] <= 0] = 1e9
        i = int(np.argmin(d)) if len(d) else -1
        return ids[i] if i >= 0 and d[i] < 70 * self.devicePixelRatioF() else -1

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        self._background(p, W, H)
        t = time.monotonic() - self._t0
        dpr = self.devicePixelRatioF()
        acc = qcol(C.PRI)
        if self.mesh is not None:
            w, h = int(W * dpr), int(H * dpr)
            self.hover = self._pick(w, h)
            sel = self.sel if self.sel >= 0 else self.hover
            explode = self.explode
            if self.build_t:                                    # parts assemble in from above
                k = min(1.0, (time.monotonic() - self.build_t) / 1.4)
                explode = max(explode, (1 - k) ** 2 * 1.6)
                if k >= 1:
                    self.build_t = 0.0
            cut = 1e9
            if self.cut is not None:
                cut = float(self.mesh.lo[0] + self.cut * self.mesh.size[0] - self.mesh.center[0])
            kw = dict(holo=self.holo, accent=(acc.redF(), acc.greenF(), acc.blueF()), t=t, explode=explode, sel=sel, cut=cut, iso=self.iso)
            # standing still in the real look: one supersampled frame, kept until something moves
            key = (id(self.mesh), round(self.cam.yaw, 2), round(self.cam.pitch, 2), round(self.cam.zoom, 4),
                   round(self.cam.pan[0], 4), round(self.cam.pan[1], 4), round(explode, 3), sel, w, h, round(cut, 3), self.iso,
                   self.gl.ao_ready(self.mesh) if self.gl.ok else True)
            still = not self.holo and not self.build_t and not self.throw_t
            if key != self._last_key:
                self._last_key, self._key_since, self._still_img = key, time.monotonic(), None
            img = None
            if still and self._still_img is not None:
                img = self._still_img
            elif still and time.monotonic() - self._key_since > 0.25 and self.gl.ok is not False:
                from gui.holo_gl import render_still
                img = self._still_img = render_still(self.gl, self.mesh, self.cam, w, h, ss=2.0, **kw)
            if img is None:
                img = self.gl.render(self.mesh, self.cam, w, h, **kw)
            if img is None:
                img = self.soft.render(self.mesh, self.cam, w, h, **kw)
            img.setDevicePixelRatio(dpr)
            if self.throw_t:
                k = min(1.0, (time.monotonic() - self.throw_t) / 0.6)
                p.setOpacity(1 - k)
                p.drawImage(QPointF(W * k * 0.8, -H * k * 0.2), img)
                p.setOpacity(1)
            else:
                p.drawImage(QPointF(0, 0), img)
            self._labels(p, w, h, dpr, sel)
            if self.measure:
                self._dimensions(p, w, h, dpr)
        else:
            self._empty(p, W, H, t)
        self._hud(p, W, H)
        p.end()

    def _empty(self, p, W, H, t):
        cx, cy, R = W / 2, H * 0.6, min(W, H) * 0.3
        for k in range(3):
            p.setPen(QPen(with_alpha(qcol(C.PRI), 0.35 - k * 0.09), 1.2))
            p.drawEllipse(QPointF(cx, cy), R * (1 - k * 0.25), R * 0.3 * (1 - k * 0.25))
        p.setPen(QPen(qcol(C.ACC), 2.2))
        p.drawArc(QRectF(cx - R * 1.04, cy - R * 0.312, R * 2.08, R * 0.624), int(-t * 90 * 16) % 5760, 60 * 16)
        p.setPen(qcol(C.TEXT_MED))
        p.setFont(px_font(15))
        p.drawText(QRectF(0, cy - R * 0.9, W, 40), Qt.AlignmentFlag.AlignCenter,
                   "Bir nesneyi kameraya göster ve TARA'ya bas — ya da ne modelleyeceğimi söyle.")

    def _labels(self, p, w, h, dpr, sel):
        if sel < 0 or sel not in self.mesh.part_center:
            return
        part = self.model["parts"][sel]
        c = self.mesh.part_center[sel] + (self.mesh.part_center[sel] - self.mesh.center) * self.explode * holo_model.EXPLODE
        x, y, z = self.cam.project(self.mesh, [c], w, h)[0]
        if z <= 0:
            return
        x, y = x / dpr, y / dpr
        lo, hi = self.mesh.lo, self.mesh.hi                 # the label sits clear of the model
        corners = [[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])]
        right = float(self.cam.project(self.mesh, corners, w, h)[:, 0].max()) / dpr
        lx = min(max(x + 60, right + 30), self.width() - 230)
        ly = max(70.0, y - 60)
        p.setPen(QPen(qcol(C.ACC2), 1.3))
        p.drawLine(QPointF(x, y), QPointF(lx, ly))
        p.drawLine(QPointF(lx, ly), QPointF(lx + 190, ly))
        p.setBrush(qcol(C.ACC2))
        p.drawEllipse(QPointF(x, y), 3, 3)
        p.setFont(px_font(14, mono=False))
        p.drawText(QPointF(lx + 4, ly - 8), part["name"].upper())
        p.setPen(qcol(C.TEXT_DIM))
        p.setFont(px_font(11))
        p.drawText(QPointF(lx + 4, ly + 16), " × ".join(f"{v:g}" for v in (round(s, 1) for s in part["size"])) + f" cm · {part['shape']}")

    def _dimensions(self, p, w, h, dpr):
        """Width, height and depth drawn on the model's bounding box, in cm."""
        lo, hi = self.mesh.lo, self.mesh.hi
        pts = {k: v for k, v in (("a", (lo[0], lo[1], hi[2])), ("b", (hi[0], lo[1], hi[2])), ("c", (hi[0], lo[1], lo[2])),
                                 ("d", (hi[0], hi[1], hi[2])))}
        S = self.cam.project(self.mesh, list(pts.values()), w, h)
        if (S[:, 2] <= 0).any():
            return
        P = {k: QPointF(S[i, 0] / dpr, S[i, 1] / dpr) for i, k in enumerate(pts)}
        p.setFont(px_font(12))
        for (k1, k2), val in ((("a", "b"), self.mesh.size[0]), (("b", "c"), self.mesh.size[2]), (("b", "d"), self.mesh.size[1])):
            a, b = P[k1], P[k2]
            p.setPen(QPen(qcol(C.ACC2), 1.4, Qt.PenStyle.DashLine))
            p.drawLine(a, b)
            p.setPen(QPen(qcol(C.ACC2), 1.4))
            for q in (a, b):
                p.drawEllipse(q, 2.5, 2.5)
            mid = (a + b) / 2
            text = f"{val:.1f} cm"
            p.fillRect(QRectF(mid.x() - 30, mid.y() - 10, 60, 18), with_alpha(qcol(C.BG), 0.75))
            p.drawText(QRectF(mid.x() - 30, mid.y() - 10, 60, 18), Qt.AlignmentFlag.AlignCenter, text)

    def _hud(self, p, W, H):
        if self.model:
            p.setPen(qcol(C.TEXT))
            p.setFont(px_font(24, mono=False))
            p.drawText(QRectF(22, 62, W * 0.4, 34), Qt.AlignmentFlag.AlignLeft, self.model["name"])
            p.setPen(qcol(C.TEXT_MED))
            p.setFont(px_font(12.5))
            p.drawText(QRectF(22, 98, min(380, W * 0.32), 60), Qt.TextFlag.TextWordWrap, self.model.get("summary", ""))
            if self.mesh is not None:
                p.setPen(qcol(C.ACC))
                p.setFont(px_font(11.5))
                dims = " × ".join(str(round(v)) for v in self.mesh.size)
                p.drawText(QPointF(22, 172), f"{dims} CM  ·  {self.mesh.pieces} PARÇA  ·  {self.mesh.n_vert // 3:,} ÜÇGEN  ·  {'HOLOGRAM' if self.holo else 'GERÇEKÇİ'}".replace(",", "."))
                p.setFont(px_font(11))
                for k, part in enumerate(self.model["parts"][:24]):
                    on = k == (self.sel if self.sel >= 0 else self.hover)
                    p.setPen(qcol(C.ACC2) if on else with_alpha(qcol(C.TEXT_DIM), 0.85))
                    p.drawText(QPointF(30, 198 + k * 17), part["name"])
                    p.fillRect(QRectF(22, 188 + k * 17, 2, 13), qcol(C.PRI) if on else with_alpha(qcol(C.BORDER_B), 0.6))
        # camera preview with the hands drawn on it
        if self.worker and self.worker.frame is not None:
            with self.worker.lock:
                f = self.worker.frame
                hands = list(self.worker.hands)
            fh, fw = f.shape[:2]
            pw = min(300.0, W * 0.22)
            ph = pw * fh / fw
            r = QRectF(W - pw - 20, H - ph - 72, pw, ph)
            rgb = np.ascontiguousarray(f[:, ::-1, ::-1])           # mirrored, BGR → RGB
            qimg = QImage(rgb.data, fw, fh, fw * 3, QImage.Format.Format_RGB888)
            p.drawImage(r, qimg)
            p.setPen(QPen(qcol(C.BORDER_B), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 10, 10)
            for L in hands:
                p.setPen(QPen(qcol(C.ACC), 2))
                for a, b in BONES:
                    p.drawLine(QPointF(r.x() + (1 - L[a][0]) * pw, r.y() + L[a][1] * ph), QPointF(r.x() + (1 - L[b][0]) * pw, r.y() + L[b][1] * ph))
            if self.busy and self.status.startswith("TARANIYOR"):
                y = r.y() + (time.monotonic() * 0.8 % 1) * ph
                p.fillRect(QRectF(r.x(), y, pw, 3), qcol(C.ACC))
            p.setPen(qcol(C.ACC))
            p.setFont(px_font(10))
            label = "EL: " + " ".join(ICON.get(holo_model.pose([{"x": x, "y": y} for x, y in L]), "·") for L in hands) if self.hands_on else "KAMERA"
            p.drawText(QPointF(r.x() + 8, r.y() + 16), label)
        if self.cursor is not None and self.hands_on:
            p.setPen(QPen(qcol(C.ACC2), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(self.cursor[0] * W, self.cursor[1] * H), 13, 13)
        if self.count:
            p.setPen(qcol(C.ACC2))
            p.setFont(px_font(min(W, H) * 0.22, mono=False))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.count)
        if self.status and (time.monotonic() < self.status_until or self.busy):
            p.setPen(qcol(C.ACC))
            p.setFont(px_font(15))
            st = self.status
            if self.busy and getattr(self, "job_t0", 0):
                st += f"  ·  {int(time.monotonic() - self.job_t0)} sn  ·  Esc: iptal"
            p.drawText(QRectF(0, 58, W, 30), Qt.AlignmentFlag.AlignHCenter, st)
        if self.hands_on:
            p.setPen(with_alpha(qcol(C.TEXT_DIM), 0.9))
            p.setFont(px_font(11))
            for i, line in enumerate(("🤏 çimdikle + sürükle: döndür", "🤏🤏 iki elle: yakınlaştır / taşı", "🖐 avuç açık tut: parçala",
                                      "✊ yumruk: sıfırla", "☝ işaret et: parça adı", "👋 hızla savur: at")):
                p.drawText(QPointF(22, H - 150 + i * 17), line)
        if self.gl.ok is False and self.mesh is not None:
            p.setPen(with_alpha(qcol(C.TEXT_DIM), 0.7))
            p.setFont(px_font(10))
            p.drawText(QPointF(22, H - 22), "OpenGL yok — basit çizim: " + self.gl.error[:80])

    # ── mouse ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._drag = (e.position(), e.button(), time.monotonic())
        self.last_input = time.monotonic()

    def mouseMoveEvent(self, e):
        self.last_input = time.monotonic()
        if self._drag is None:
            self.cursor = (e.position().x() / max(1, self.width()), e.position().y() / max(1, self.height())) if not self.hands_on else self.cursor
            return
        pos, btn, _ = self._drag
        d = e.position() - pos
        if btn == Qt.MouseButton.RightButton:
            self.cam.pan[0] -= d.x() / max(1, self.width()) * 0.8
            self.cam.pan[1] -= d.y() / max(1, self.height()) * 0.8
        else:
            self.cam.yaw -= d.x() * 0.4
            self.cam.pitch = max(-85, min(85, self.cam.pitch + d.y() * 0.3))
        self._drag = (e.position(), btn, self._drag[2])

    def mouseReleaseEvent(self, e):
        if self._drag and time.monotonic() - self._drag[2] < 0.25:
            self.sel = self.hover if self.sel != self.hover else -1
        self._drag = None

    def leaveEvent(self, _e):
        if not self.hands_on:
            self.cursor = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        g = getattr(self, "gallery", None)
        if g is not None and g.isVisible():
            g.setGeometry(self.rect().adjusted(60, 64, -60, -70))

    def mouseDoubleClickEvent(self, _e):
        if self.iso >= 0:
            self.command({"action": "show_all"})
        elif self.hover >= 0:
            self.command({"action": "isolate"})
        else:
            self.command({"action": "explode"})

    def wheelEvent(self, e):
        self.last_input = time.monotonic()
        if self.cut is not None and e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            d = e.angleDelta().y() or e.angleDelta().x()
            self.cut = max(0.0, min(1.0, self.cut + (0.03 if d > 0 else -0.03)))
            return
        self.cam.zoom = max(0.25, min(6, self.cam.zoom * (1.1 if e.angleDelta().y() > 0 else 0.9)))

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            if getattr(self, "gallery", None) is not None and self.gallery.isVisible():
                self._toggle_gallery()
            elif self.busy:
                self.cancel()
            else:
                self.back_requested.emit()
        elif k == Qt.Key.Key_Space:
            self.command({"action": "explode"})
        elif k == Qt.Key.Key_R:
            self.command({"action": "reset"})
        elif k == Qt.Key.Key_H:
            self.command({"action": "look"})
        else:
            super().keyPressEvent(e)
