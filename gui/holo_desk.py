"""Native Holo Desk: camera stays local, gestures affect this workspace only."""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

import numpy as np
import psutil
from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer, QSaveFile, QIODevice, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF, QBrush
from PyQt6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QComboBox, QPlainTextEdit, QFileDialog, QListWidget)

from core.holo_desk import Hands, mesh, parse_obj, obj_text, project
from gui.theme import C
from gui.style import px_font, btn_css


class FloatingPanel(QFrame):
    def __init__(self, title, parent):
        super().__init__(parent)
        self.setObjectName("holoFloating")
        self.setStyleSheet(f"QFrame#holoFloating {{background:{C.PANEL};border:1px solid {C.PRI_DIM};border-radius:9px;}}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10,7,10,10)
        row = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setFont(px_font(12))
        self.title.setStyleSheet(f"color:{C.PRI};")
        self.title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(self.title)
        close = QPushButton("×")
        close.setFixedSize(25,25)
        close.clicked.connect(self.hide)
        row.addWidget(close)
        layout.addLayout(row)
        self.body = layout
        self.resize(265,240)
        self._drag = None

    def mousePressEvent(self, event):
        if event.button()==Qt.MouseButton.LeftButton and event.position().y()<37:
            self._drag=event.globalPosition().toPoint()-self.pos()
            self.raise_()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.place(event.globalPosition().toPoint()-self._drag)

    def mouseReleaseEvent(self,event):
        self._drag=None

    def place(self, point):
        parent=self.parentWidget()
        self.move(max(0,min(parent.width()-self.width(),int(point.x()))),
                  max(0,min(parent.height()-self.height(),int(point.y()))))


class SpatialCanvas(QWidget):
    action = pyqtSignal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumSize(360,280)
        self.setMouseTracking(True)
        self.frame=QImage()
        self.hands=[]
        self.panels=[]
        self.yaw=.45;self.pitch=-.3;self.scale=1.0
        self.offset=np.zeros(2)
        self.mode="Döndür"
        self.vertices,self.faces=mesh()
        self._mouse=None;self._grip=None;self._panel_grip=None
        self.auto_rotate=False

    def reset_view(self):
        self.yaw=.45;self.pitch=-.3;self.scale=1.0
        self.offset=np.zeros(2);self._grip=None;self._panel_grip=None
        self.update()

    def image_rect(self):
        if self.frame.isNull():
            return QRectF(self.rect())
        ratio=min(self.width()/self.frame.width(),self.height()/self.frame.height())
        w,h=self.frame.width()*ratio,self.frame.height()*ratio
        return QRectF((self.width()-w)/2,(self.height()-h)/2,w,h)

    def screen(self, xy):
        r=self.image_rect()
        return QPointF(r.x()+xy[0]*r.width(),r.y()+xy[1]*r.height())

    def ring_items(self, hand):
        centre=self.screen(hand["palm"])
        radius=max(48,min(78,hand["width"]*self.image_rect().width()*1.05))
        margin=radius+23
        visible=self.image_rect()
        centre=QPointF(max(visible.left()+margin,min(visible.right()-margin,centre.x())),
                       max(visible.top()+margin,min(visible.bottom()-margin,centre.y())))
        keys=("Dosyalar","Nesneler","Notlar","Widget","Taşı/Döndür","Sıfırla")
        return [(key,QPointF(centre.x()+math.cos(-math.pi/2+i*math.tau/6)*radius,
                            centre.y()+math.sin(-math.pi/2+i*math.tau/6)*radius)) for i,key in enumerate(keys)]

    def consume_hands(self, hands):
        self.hands=hands
        held=[h for h in hands if h["pinch"]]
        if not held:
            self._grip=None;self._panel_grip=None
            return
        # A pinch selects a ring button or panel header once, never an OS action.
        for hand in held if len(held)==1 else []:
            if not hand["down"]:
                continue
            pointer=self.screen(hand["pointer"])
            # Native widgets take priority over rings painted behind them.
            # A pinch inside a note/file panel must not rotate the model or
            # select an invisible control underneath that panel.
            target=self.childAt(pointer.toPoint())
            while target is not None and target is not self and not isinstance(target,FloatingPanel):
                target=target.parentWidget()
            if isinstance(target,FloatingPanel):
                if pointer.y()<target.y()+37:
                    self._panel_grip=(hand["id"],target,pointer-QPointF(target.pos()))
                    target.raise_()
                else:self._grip=("menu",hand["id"])
                return
            for anchor in hands:
                for key,point in self.ring_items(anchor):
                    if (point-pointer).manhattanLength()<24:
                        self.action.emit(key)
                        self._grip=("menu",hand["id"])
                        return
        if self._panel_grip:
            ident,panel,offset=self._panel_grip
            for hand in held:
                if hand["id"]==ident:
                    panel.place((self.screen(hand["pointer"])-offset).toPoint())
                    return
            self._panel_grip=None
        if self._grip and self._grip[0]=="menu":
            if len(held)==1 and any(h["id"]==self._grip[1] for h in held):
                return
            self._grip=None
        if len(held)==2:
            distance=float(np.linalg.norm(held[0]["pointer"]-held[1]["pointer"]))
            ids=tuple(sorted(h["id"] for h in held))
            if distance<.045:
                self._grip=None;return
            if not self._grip or self._grip[0:2]!=("scale",ids):
                self._grip=("scale",ids,distance,self.scale)
            self.scale=max(.25,min(2.5,self._grip[3]*distance/self._grip[2]))
        else:
            hand=held[0]
            pointer=np.array(hand["pointer"])
            if not self._grip or self._grip[0:2]!=("single",hand["id"]):
                self._grip=("single",hand["id"],pointer,self.yaw,self.pitch,self.offset.copy())
            delta=pointer-self._grip[2]
            if self.mode=="Taşı":
                self.offset=np.clip(self._grip[5]+delta,-.35,.35)
            else:
                self.yaw=self._grip[3]+delta[0]*5
                self.pitch=max(-1.4,min(1.4,self._grip[4]+delta[1]*4))
        self.update()

    def mousePressEvent(self,event):
        if event.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):
            self._mouse=(event.position(),self.yaw,self.pitch,self.offset.copy(),event.button())

    def mouseMoveEvent(self,event):
        if self._mouse:
            start,yaw,pitch,offset,button=self._mouse
            delta=event.position()-start
            if button==Qt.MouseButton.RightButton or self.mode=="Taşı":
                self.offset=np.clip(offset+[delta.x()/self.width(),delta.y()/self.height()],-.35,.35)
            else:
                self.yaw=yaw+delta.x()*.009
                self.pitch=max(-1.4,min(1.4,pitch+delta.y()*.009))
            self.update()

    def mouseReleaseEvent(self,event):
        self._mouse=None

    def wheelEvent(self,event):
        self.scale=max(.25,min(2.5,self.scale*math.exp(event.angleDelta().y()*.001)))
        self.update();event.accept()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor(C.BG))
        if not self.frame.isNull():
            p.drawImage(self.image_rect(),self.frame)
            p.fillRect(self.rect(),QColor(0,8,18,44))
        else:
            grid=QColor(C.BORDER);grid.setAlpha(75)
            p.setPen(QPen(grid,1))
            for x in range(0,self.width(),36):p.drawLine(x,0,x,self.height())
            for y in range(0,self.height(),36):p.drawLine(0,y,self.width(),y)
            p.setFont(px_font(12));p.setPen(QColor(C.TEXT_DIM))
            p.drawText(QRectF(15,15,self.width()-30,30),"Kamera kapalı · Fareyle de kullanabilirsin")
        posed,xy=project(self.vertices,self.yaw,self.pitch,self.scale)
        size=min(self.width(),self.height())*.19
        centre=np.array([self.width()*(.5+self.offset[0]),self.height()*(.50+self.offset[1])])
        pixels=xy*np.array([size,-size])+centre
        tri=posed[self.faces]
        normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        lengths=np.linalg.norm(normals,axis=1)
        normals/=np.maximum(lengths[:,None],1e-8)
        light=np.clip(np.abs(normals@np.array([-.4,.5,.77])),0,1)
        accent=QColor(C.PRI)
        points=[QPointF(*v) for v in pixels]
        shades=[QBrush(QColor.fromRgbF(accent.redF()*(.28+.72*i/31),
            accent.greenF()*(.28+.72*i/31),accent.blueF()*(.28+.72*i/31),.48)) for i in range(32)]
        p.setPen(QPen(QColor(C.PRI_DIM),.65))
        for i in np.argsort(tri[:,:,2].mean(axis=1)):
            if lengths[i]<1e-10:continue
            p.setBrush(shades[int(light[i]*31)])
            p.drawPolygon(QPolygonF([points[j] for j in self.faces[i]]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(C.PRI_DIM),1))
        p.drawEllipse(QRectF(centre[0]-size*1.7,centre[1]+size*1.3,size*3.4,size*.30))
        connections=[(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(0,17),(17,18),(18,19),(19,20)]
        for hand in self.hands:
            p.setPen(QPen(QColor(C.PRI),1.2))
            for a,b in connections:p.drawLine(self.screen(hand["points"][a,:2]),self.screen(hand["points"][b,:2]))
            for key,point in self.ring_items(hand):
                p.setBrush(QColor(C.PANEL));p.setPen(QPen(QColor(C.PRI),1.5))
                p.drawEllipse(point,21,21)
                p.setFont(px_font(8));p.setPen(QColor(C.WHITE))
                short={"Dosyalar":"DOSYA","Nesneler":"3D","Notlar":"NOT","Widget":"CPU","Taşı/Döndür":"TAŞI","Sıfırla":"SIFIR"}[key]
                p.drawText(QRectF(point.x()-23,point.y()-12,46,24),Qt.AlignmentFlag.AlignCenter,short)
            point=self.screen(hand["pointer"])
            p.setBrush(QColor(C.GREEN if hand["pinch"] else C.PRI))
            p.drawEllipse(point,6,6)
        p.end()


class HoloDesk(QWidget):
    back_requested=pyqtSignal()
    _status=pyqtSignal(str)
    _setup_done=pyqtSignal(str)

    def __init__(self,parent=None,*,notes_path=None):
        super().__init__(parent)
        self.setFont(px_font(12))
        self.setStyleSheet(f"""
            QWidget {{background:{C.BG};color:{C.TEXT};}}
            QLabel {{background:transparent;color:{C.TEXT};}}
            QPushButton {{background:{C.PANEL2};color:{C.PRI};border:1px solid {C.BORDER};border-radius:6px;padding:7px 10px;}}
            QPushButton:hover, QPushButton:checked {{border-color:{C.PRI};background:{C.PANEL};}}
            QComboBox, QPlainTextEdit, QListWidget {{background:{C.PANEL2};color:{C.WHITE};border:1px solid {C.BORDER};padding:6px;}}
        """)
        self._stop=threading.Event();self._thread=None
        self._lock=threading.Lock();self._packet=None;self._generation=0
        self._hands=Hands();self._setup_thread=None
        self._control_paused=False
        self._await_release=False
        self._notes_path=notes_path
        root=QVBoxLayout(self)
        row=QHBoxLayout()
        title=QLabel("FRIDAY / HOLO MASA");title.setFont(px_font(15));row.addWidget(title)
        row.addStretch()
        self.camera=QPushButton("Kamerayı aç");self.camera.setCheckable(True)
        self.camera.toggled.connect(self._camera_changed);row.addWidget(self.camera)
        self.setup=QPushButton("El takibini kur");self.setup.clicked.connect(self._install);row.addWidget(self.setup)
        back=QPushButton("CORE’a dön");back.clicked.connect(self.back_requested);row.addWidget(back)
        root.addLayout(row)
        self.canvas=SpatialCanvas();root.addWidget(self.canvas,1)
        self.status=QLabel("Kamera yalnızca bu düğmeyle açılır. Görüntü kaydedilmez veya modele gönderilmez.")
        self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setFont(px_font(11));root.addWidget(self.status)
        self._status.connect(self.status.setText)
        self._setup_done.connect(self._installed)
        dock=QHBoxLayout()
        for name in ("Dosyalar","Nesneler","Notlar","Widget","Sıfırla"):
            b=QPushButton(name);b.setStyleSheet(btn_css("dim"));b.clicked.connect(lambda checked=False,name=name:self.action(name));dock.addWidget(b)
        self.mode=QComboBox();self.mode.addItems(["Döndür","Taşı"])
        self.mode.currentTextChanged.connect(self._mode);dock.addWidget(self.mode)
        self.pause=QPushButton("El kontrolünü duraklat")
        self.pause.setCheckable(True)
        self.pause.toggled.connect(self._pause_hand_control)
        dock.addWidget(self.pause)
        root.addLayout(dock)
        self.canvas.action.connect(self.action)
        self._panels={}
        self._build_panels()
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self._tick)
        self.note_timer=QTimer(self);self.note_timer.setSingleShot(True);self.note_timer.setInterval(600)
        self.note_timer.timeout.connect(self._save_notes)
        self.notes.textChanged.connect(lambda:self.note_timer.start())
        self._last_stats=0
        self._last_packet=0
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().aboutToQuit.connect(self.stop_camera)

    def _build_panels(self):
        def panel(name,x,y):
            item=FloatingPanel(name,self.canvas);item.move(x,y);item.hide()
            self._panels[name]=item;self.canvas.panels.append(item);return item.body
        body=panel("Nesneler",12,55)
        shapes=QComboBox();shapes.addItems(["Çekirdek","Küp","Küre","Piramit"])
        shapes.currentTextChanged.connect(self.set_shape);body.addWidget(shapes)
        for title,callback in [("OBJ aç",self.open_obj),("OBJ kaydet",self.save_obj)]:
            button=QPushButton(title);button.clicked.connect(callback);body.addWidget(button)
        self.auto=QPushButton("Otomatik döndür");self.auto.setCheckable(True)
        self.auto.toggled.connect(lambda on:setattr(self.canvas,"auto_rotate",on));body.addWidget(self.auto)
        body.addWidget(QLabel("Tek çimdik: döndür/taşı\nİki çimdik: ölçekle\nPanel başlığını tut: sürükle"))
        body=panel("Notlar",300,65)
        self.notes=QPlainTextEdit();self.notes.setPlaceholderText("Yerel notların…");body.addWidget(self.notes)
        from memory.continuity import data_dir
        self.note_path=Path(self._notes_path) if self._notes_path else data_dir()/"holo-desk"/"notes.json"
        try:
            if self.note_path.exists():
                if self.note_path.stat().st_size>=200000:raise ValueError("Not dosyası boyut sınırını aşıyor.")
                data=json.loads(self.note_path.read_text(encoding="utf-8"))
                if not isinstance(data,dict) or not isinstance(data.get("notes"),str):raise ValueError("Not dosyası biçimi geçersiz.")
                self.notes.setPlainText(data["notes"])
        except (OSError,ValueError,AttributeError):
            self.notes.setReadOnly(True)
            self.status.setText("Not dosyası okunamadı; üzerine yazılmayacak. Dosyayı yedekleyip kontrol edin.")
        body=panel("Widget",300,310)
        self.telemetry=QLabel();self.telemetry.setFont(px_font(15));body.addWidget(self.telemetry)
        body.addWidget(QLabel("Canlı sistem değerleri\nHolo Masa içindeki işlemler yereldir."))
        body=panel("Dosyalar",12,310)
        folder=QPushButton("Klasör seç");folder.clicked.connect(self.open_folder);body.addWidget(folder)
        self.files=QListWidget();self.files.itemDoubleClicked.connect(self.preview_file);body.addWidget(self.files)
        self.file_note=QLabel("OBJ dosyasına çift tıkla. Dosya çalıştırılmaz.");self.file_note.setWordWrap(True);body.addWidget(self.file_note)
        self._folder=None

    def _mode(self,name):
        self.canvas.mode=name;self.canvas._grip=None

    def _pause_hand_control(self,paused):
        self._control_paused=bool(paused)
        self._await_release=not paused
        self._hands=Hands()
        self.canvas.consume_hands([]);self.canvas.update()
        self.pause.setText("El kontrolünü sürdür" if paused else "El kontrolünü duraklat")
        self.status.setText("El kontrolü duraklatıldı. Kamera durumu değişmedi; fareyle kullanabilirsin." if paused
            else "El kontrolü açık. Önce parmaklarını ayır, ardından çimdikle tut.")

    def action(self,name):
        if name=="Sıfırla":self.canvas.reset_view()
        elif name=="Taşı/Döndür":self.mode.setCurrentIndex(1-self.mode.currentIndex())
        elif name in self._panels:
            item=self._panels[name];item.setVisible(not item.isVisible());item.place(item.pos());item.raise_()

    def set_shape(self,name):
        if name not in ("Çekirdek","Küp","Küre","Piramit"):
            raise ValueError("Bilinmeyen nesne")
        self.canvas.vertices,self.canvas.faces=mesh(name)
        self.canvas.reset_view()

    def open_obj(self):
        path,_=QFileDialog.getOpenFileName(self,"3D nesne aç","","Wavefront OBJ (*.obj)")
        if path:self._load_obj(Path(path))

    def _load_obj(self,path):
        try:
            if path.stat().st_size>2000000:raise ValueError("OBJ en fazla 2 MB olabilir.")
            vertices,faces=parse_obj(path.read_text(encoding="utf-8"))
            self.canvas.vertices,self.canvas.faces=vertices,faces
            self.canvas.reset_view();self.status.setText(f"OBJ açıldı: {path.name} · {len(faces)} üçgen")
        except (OSError,ValueError,UnicodeError) as exc:self.status.setText(f"OBJ açılamadı: {exc}")

    def save_obj(self):
        path,_=QFileDialog.getSaveFileName(self,"3D nesneyi kaydet","friday-nesne.obj","Wavefront OBJ (*.obj)")
        if not path:return
        try:
            self._atomic(Path(path),obj_text(self.canvas.vertices,self.canvas.faces).encode("utf-8"))
            self.status.setText("OBJ kaydedildi. Yazıcı işlemi yapılmadı.")
        except OSError as exc:self.status.setText(f"OBJ kaydedilemedi: {exc}")

    @staticmethod
    def _atomic(path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        output=QSaveFile(str(path))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly) or output.write(data)!=len(data) or not output.commit():
            raise OSError("Dosya güvenli biçimde yazılamadı; önceki içerik korundu.")

    def _save_notes(self):
        if self.notes.isReadOnly():return
        data=json.dumps({"notes":self.notes.toPlainText()},ensure_ascii=False).encode("utf-8")
        if len(data)>200000:
            self.status.setText("Notlar 200 KB sınırını aştı; son kaydedilen içerik korunuyor.");return
        try:self._atomic(self.note_path,data)
        except OSError as exc:self.status.setText(str(exc))

    def open_folder(self):
        path=QFileDialog.getExistingDirectory(self,"Holo Masa klasörü")
        if not path:return
        self._folder=Path(path);self.files.clear()
        try:
            entries=sorted(self._folder.iterdir(),key=lambda p:p.name.casefold())[:200]
            self.files.addItems([p.name for p in entries if p.is_file()])
        except OSError as exc:self.file_note.setText(str(exc))

    def preview_file(self,item):
        if self._folder is None:return
        path=self._folder/item.text()
        if path.suffix.lower()==".obj":self._load_obj(path)
        else:
            try:self.file_note.setText(f"{path.name} · {path.stat().st_size:,} bayt. Dosya çalıştırılmadı.")
            except OSError as exc:self.file_note.setText(str(exc))

    def _install(self):
        if self._setup_thread and self._setup_thread.is_alive():return
        self.setup.setEnabled(False);self.status.setText("El takibi hazırlanıyor; kamera açılmayacak…")
        def work():
            try:
                from core.holo_desk import install_tracking
                install_tracking(self._status.emit)
                self._setup_done.emit("El modeli doğrulandı. Kamerayı açarak kullanabilirsin.")
            except Exception as exc:self._setup_done.emit(f"El takibi hazırlanamadı: {exc}")
        self._setup_thread=threading.Thread(target=work,daemon=True,name="friday-holo-setup");self._setup_thread.start()

    def _installed(self,message):
        if self.camera.isChecked():self.stop_camera()
        self.setup.setEnabled(True);self.status.setText(message)

    def _camera_changed(self,on):
        if not on:self.stop_camera();return
        if self._thread and self._thread.is_alive():
            self.camera.blockSignals(True);self.camera.setChecked(False);self.camera.blockSignals(False)
            self.status.setText("Önceki kamera oturumu kapanıyor; bir an sonra tekrar dene.");return
        self._generation+=1;generation=self._generation
        self._stop=threading.Event()
        self.status.setText("Kamera ve varsa yerel el modeli hazırlanıyor…")
        self._thread=threading.Thread(target=self._camera_loop,args=(self._stop,generation),daemon=True,name="friday-holo-camera")
        self._thread.start();self.camera.setText("Kamerayı kapat")

    def stop_camera(self):
        self._stop.set();self._generation+=1
        self.camera.blockSignals(True);self.camera.setChecked(False);self.camera.setText("Kamerayı aç");self.camera.blockSignals(False)
        with self._lock:self._packet=None
        self.canvas.frame=QImage();self.canvas.consume_hands([]);self._hands=Hands();self.canvas.update()

    def _camera_loop(self,stop,generation):
        camera=None;tracker=None
        try:
            import cv2
            from actions.screen_processor import _cv2_backend,_get_camera_index
            try:
                from core.holo_desk import HandTracker
                tracker=HandTracker()
            except Exception as exc:self._status.emit(f"Kamera yerel önizleme · El takibi hazır değil: {exc}")
            if stop.is_set() or generation!=self._generation:return
            camera=cv2.VideoCapture(_get_camera_index(),_cv2_backend())
            camera.set(cv2.CAP_PROP_FRAME_WIDTH,640);camera.set(cv2.CAP_PROP_FRAME_HEIGHT,360)
            if not camera.isOpened():raise RuntimeError("Kamera açılamadı; başka uygulamanın kullanmadığından emin ol.")
            if tracker:self._status.emit("Kamera açık · El görüntüleri yerelde işleniyor. Çimdik: tut · İki el: ölçekle")
            while not stop.is_set():
                started=time.monotonic()
                ok,frame=camera.read()
                if not ok:raise RuntimeError("Kameradan kare alınamadı.")
                rgb=cv2.cvtColor(cv2.flip(cv2.resize(frame,(640,360)),1),cv2.COLOR_BGR2RGB)
                hands=tracker.detect(rgb,int(time.monotonic()*1000)) if tracker and not self._control_paused else []
                with self._lock:
                    if generation==self._generation and not stop.is_set():self._packet=(rgb,hands)
                stop.wait(max(0,1/24-(time.monotonic()-started)))
        except Exception as exc:self._status.emit(str(exc))
        finally:
            if camera is not None:camera.release()
            if tracker is not None:tracker.close()
            if generation==self._generation:
                with self._lock:self._packet=(None,[])

    def _tick(self):
        with self._lock:packet,self._packet=self._packet,None
        if packet is not None:
            rgb,values=packet
            if rgb is None:self.stop_camera()
            else:
                self._last_packet=time.monotonic()
                h,w,_=rgb.shape
                self.canvas.frame=QImage(rgb.data,w,h,w*3,QImage.Format.Format_RGB888).copy()
                filtered=[] if self._control_paused else self._hands.update(values,aspect=w/h)
                if self._await_release:
                    if any(h["pinch"] for h in filtered):
                        filtered=[]
                    elif filtered:
                        self._await_release=False
                self.canvas.consume_hands(filtered);self.canvas.update()
        if self.canvas.auto_rotate:
            self.canvas.yaw+=.012;self.canvas.update()
        now=time.monotonic()
        if self.canvas.hands and now-self._last_packet>.45:
            self.canvas.consume_hands([]);self.canvas.update()
        if now-self._last_stats>1:
            self._last_stats=now
            self.telemetry.setText(time.strftime("%H:%M:%S")+f"\nCPU %{psutil.cpu_percent():.0f}\nRAM %{psutil.virtual_memory().percent:.0f}")

    def showEvent(self,event):
        super().showEvent(event);self.timer.start()

    def hideEvent(self,event):
        self.stop_camera();self.timer.stop()
        if self.note_timer.isActive():self.note_timer.stop();self._save_notes()
        super().hideEvent(event)

    def closeEvent(self,event):
        self.stop_camera();self.timer.stop()
        if self.note_timer.isActive():self.note_timer.stop();self._save_notes()
        super().closeEvent(event)
