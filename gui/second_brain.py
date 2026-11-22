"""Live autonomous improvement graph. All analysis runs outside the Qt thread."""
import threading
import time

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit
from gui.control_center import NetworkCanvas
from gui.style import btn_css, px_font, scroll_css
from gui.theme import C

NODES = (
    ("voice", "Ses ve konuşma", "pulse", 0),
    ("memory", "Hafıza", "brain", 0),
    ("models", "Model zekâsı", "grid", 0),
    ("coding", "Kod ajanı", "code", 0),
    ("testing", "Testler", "code", 0),
    ("updates", "Güncelleme", "gear", 1),
    ("security", "Güvenlik", "eye", 1),
    ("devices", "Cihazlar", "monitor", 1),
    ("interface", "Arayüz", "grid", 1),
    ("research", "Araştırma", "globe", 1),
    ("automation", "Otomasyon", "monitor", 1),
    ("integrations", "Eklentiler", "gear", 1),
    ("tasks", "Uzun işler", "calendar", 1),
)
LABELS = {key: name for key, name, icon, ring in NODES}
ACTIVE = {"Analiz", "Planlama", "Geliştirme hazırlanıyor", "Kod ajanına aktarıldı",
          "Kaynaklar okunuyor", "Kod yazılıyor", "Kod denetimi", "Test"}


class _AgentUI:
    def __init__(self, window):
        self.log = window._log_sig
        self.job = window._codejob_sig

    def write_log(self, text):
        self.log.emit(text)

    def show_code_job(self, job):
        self.job.emit(dict(job))


class SecondBrainPanel(QWidget):
    completed = pyqtSignal(object)
    back_requested = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.timer = QTimer(self)
        self.animation = QTimer(self)
        from core.second_brain_service import Controller
        self.controller = window.__dict__.get("_brain_controller") or Controller(_AgentUI(window))
        self.busy = False
        self.data = {}
        self.filter = ""
        self.setFont(px_font(12))
        self.setStyleSheet(f"color: {C.TEXT}; background: {C.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        header = QHBoxLayout()
        back = QPushButton("‹ AETHER’a dön")
        back.setStyleSheet(btn_css("dim", align="center"))
        back.clicked.connect(self.back_requested.emit)
        header.addWidget(back)
        title = QLabel("İKİNCİ BEYİN")
        title.setFont(px_font(18))
        header.addWidget(title, 1)
        self.pause = QPushButton("Duraklat")
        self.pause.setStyleSheet(btn_css("primary", align="center"))
        self.pause.clicked.connect(self.toggle)
        header.addWidget(self.pause)
        layout.addLayout(header)
        self.status = QLabel("AETHER açılışından sonra otomatik öz denetim başlar.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.canvas = NetworkCanvas(self, nodes=NODES)
        self.canvas.setMinimumSize(400, 360)
        self.canvas.heading = "OTONOM GELİŞİM"
        self.canvas.core_label = "CORE"
        self.canvas.footer = "Bir gelişim alanına dokunarak kayıtlarını incele"
        self.canvas.node_clicked.connect(self.select)
        self.canvas.core_clicked.connect(lambda: self.select(""))
        row.addWidget(self.canvas, 3)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumWidth(240)
        self.detail.setStyleSheet(f"QTextEdit {{ border: 1px solid {C.PRI_DIM}; padding: 8px; }}" + scroll_css())
        row.addWidget(self.detail, 2)
        layout.addLayout(row, 1)
        note = QLabel("15 dakikada bir kaynak analizi → plan → ayrı alanda kod → test sonucu. Yapılandırılmış model API’si kullanılır. Yayın için mevcut onay akışı geçerlidir.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.completed.connect(self.finished)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.animation.setInterval(33)
        self.animation.timeout.connect(self.advance)

    def select(self, key):
        self.filter = key
        self.canvas.set_filter(key)
        self.render()

    def toggle(self):
        if not self.busy:
            self.refresh(toggle=True)

    def refresh(self, toggle=False):
        if self.busy:
            return
        self.busy = True
        def work():
            try:
                if toggle:
                    from core.second_brain_service import set_enabled, settings
                    set_enabled(not settings()["enabled"])
                result = self.controller.snapshot()
            except Exception as exc:
                result = {"error": str(exc)}
            self.completed.emit(result)
        threading.Thread(target=work, daemon=True, name="brain-view").start()

    def finished(self, result):
        self.busy = False
        if "error" in result:
            self.status.setText("Durum okunamadı · " + result["error"])
            return
        self.data = result
        self.render()

    def render(self):
        from core import second_brain
        enabled = self.data.get("enabled", True)
        phase = self.data.get("phase", "Başlangıç bekleniyor")
        area = self.data.get("area", "")
        self.pause.setText("Duraklat" if enabled else "Devam ettir")
        self.status.setText((LABELS.get(area, "Öz denetim") + " · " + phase) if enabled
                            else "Otomatik geliştirme duraklatıldı. Başlamış kod işinin sonucu izlenir.")
        due = self.data.get("next_due", 0)
        if enabled and due > time.time() and phase not in ACTIVE:
            self.status.setText(self.status.text() + " · Sonraki denetim " + time.strftime("%H:%M", time.localtime(due)))
        records = self.data.get("events", [])
        active = bool(enabled and phase in ACTIVE and area in LABELS)
        hits = {area: time.time()} if active else {}
        self.canvas.set_data({area: 1} if active else {}, hits, phase)
        lines = []
        for event in records:
            if self.filter and event["area"] != self.filter:
                continue
            when = time.strftime("%H:%M:%S", time.localtime(event["time"]))
            lines.append(f"{when} · {LABELS.get(event['area'], event['area'])}\n{event['phase']}\n{event['detail']}")
        if not self.filter:
            for item in self.data.get("items", []):
                lines.append(f"{second_brain._LABELS[item['state']]} · {item['title']}\n"
                             f"{item['analysis']}\n{item['result']}")
        text = "\n\n".join(lines) or "İlk öz denetim kaydı bekleniyor. Kaynak incelemesi açılıştan kısa süre sonra başlar."
        if text != self.detail.toPlainText():
            self.detail.setPlainText(text)
        self.canvas.update()

    def advance(self):
        enabled = self.data.get("enabled", True)
        phase = self.data.get("phase", "")
        self.canvas.advance(.033, thinking=enabled and phase in ACTIVE)

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()
        self.animation.start()
        self.refresh()

    def hideEvent(self, event):
        self.timer.stop()
        self.animation.stop()
        super().hideEvent(event)
