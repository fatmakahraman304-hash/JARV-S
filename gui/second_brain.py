"""Read-only feature monitor graph; checks run outside the Qt thread."""
import threading
import time

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication
from gui.control_center import NetworkCanvas
from gui.style import btn_css, px_font, scroll_css
from gui.theme import C

NODES = (
    ("voice", "Ses ve konuşma", "pulse", 0),
    ("memory", "Hafıza", "brain", 0),
    ("models", "Model zekâsı", "grid", 0),
    ("coding", "Kod ajanı", "code", 0),
    ("watchers", "Canlı izleme", "pulse", 0),
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
ACTIVE = {'Deneniyor'}


class _MonitorUI:
    def __init__(self, window):
        self.log = window._log_sig

    def write_log(self, text):
        self.log.emit(text)


class SecondBrainPanel(QWidget):
    completed = pyqtSignal(object)
    back_requested = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.timer = QTimer(self)
        self.animation = QTimer(self)
        from core.second_brain_service import Controller
        self.controller = window.__dict__.get("_brain_controller") or Controller(_MonitorUI(window))
        self.busy = False
        self.data = {}
        self.filter = ""
        self.only_errors = False
        self.setFont(px_font(12))
        self.setStyleSheet(f"color: {C.TEXT}; background: {C.BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        header = QHBoxLayout()
        back = QPushButton("‹ FRIDAY’a dön")
        back.setStyleSheet(btn_css("dim", align="center"))
        back.clicked.connect(self.back_requested.emit)
        header.addWidget(back)
        title = QLabel("ÖZELLİK DENETİMİ")
        title.setFont(px_font(18))
        header.addWidget(title, 1)
        self.pause = QPushButton("Duraklat")
        self.pause.setStyleSheet(btn_css("primary", align="center"))
        self.pause.clicked.connect(self.toggle)
        header.addWidget(self.pause)
        layout.addLayout(header)
        self.status = QLabel("FRIDAY açılışından sonra yerel özellik kontrolleri başlar.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.summary = QLabel("İlk kontrol bekleniyor.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        controls = QHBoxLayout()
        self.errors = QPushButton("Yalnız sorunlar")
        self.errors.setCheckable(True)
        self.errors.setStyleSheet(btn_css("dim", align="center"))
        self.errors.toggled.connect(self.filter_errors)
        controls.addWidget(self.errors)
        self.copy = QPushButton("Raporu kopyala")
        self.copy.setStyleSheet(btn_css("primary", align="center"))
        self.copy.clicked.connect(self.copy_report)
        controls.addWidget(self.copy)
        layout.addLayout(controls)
        row = QHBoxLayout()
        self.canvas = NetworkCanvas(self, nodes=NODES)
        self.canvas.setMinimumSize(400, 360)
        self.canvas.heading = "ÖZELLİK DENETİMİ"
        self.canvas.core_label = "CORE"
        self.canvas.footer = "Bir alana dokunarak kontrol ve hata kayıtlarını incele"
        self.canvas.node_clicked.connect(self.select)
        self.canvas.core_clicked.connect(lambda: self.select(""))
        row.addWidget(self.canvas, 3)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMinimumWidth(240)
        self.detail.setStyleSheet(f"QTextEdit {{ border: 1px solid {C.PRI_DIM}; padding: 8px; }}" + scroll_css())
        row.addWidget(self.detail, 2)
        layout.addLayout(row, 1)
        note = QLabel("Dakikada bir sıradaki alan geçici verilerle sınanır. Kod yazılmaz; model API’si, gerçek mesaj, kamera ve cihaz işlemleri kullanılmaz. Geçti sonucu yalnızca belirtilen yerel kontrolü kapsar.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.completed.connect(self.finished)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.animation.setInterval(33)
        self.animation.timeout.connect(self.advance)

    def filter_errors(self, checked):
        self.only_errors = checked
        self.render()

    def copy_report(self):
        from core.second_brain_service import report
        QApplication.clipboard().setText(report(self.data))
        self.copy.setText("Rapor kopyalandı")

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
                    from core.second_brain_service import settings
                    if settings()["enabled"]:
                        self.controller.pause()
                    else:
                        self.controller.resume()
                result = self.controller.snapshot()
            except Exception as exc:
                result = {"error": str(exc)}
            try:
                self.completed.emit(result)
            except RuntimeError:
                pass  # the panel may have been destroyed during shutdown
        threading.Thread(target=work, daemon=True, name="brain-view").start()

    def finished(self, result):
        self.busy = False
        if "error" in result:
            self.status.setText("Durum okunamadı · " + result["error"])
            return
        self.data = result
        self.render()

    def render(self):
        from core.second_brain_service import LABELS as STATES
        from core.second_brain_service import AREAS
        enabled = self.data.get("enabled", True)
        phase = self.data.get("phase", "Başlangıç bekleniyor")
        area = self.data.get("area", "")
        self.pause.setText("Duraklat" if enabled else "Devam ettir")
        self.status.setText((LABELS.get(area, "Öz denetim") + " · " + phase) if enabled
                            else "Özellik denetimi duraklatıldı. Çalışan kontrol durduruluyor.")
        due = self.data.get("next_due", 0)
        if enabled and due > time.time() and phase not in ACTIVE:
            self.status.setText(self.status.text() + " · Sonraki denetim " + time.strftime("%H:%M", time.localtime(due)))
        rows = self.data.get("results", [])
        counts = {state: sum(row['status'] == state for row in rows)
                  for state in ('passed', 'failed', 'unverified', 'running', 'cancelled')}
        self.summary.setText(f"Geçti: {counts['passed']} · Hata: {counts['failed']} · "
                             f"Doğrulanmadı: {counts['unverified']} · Deneniyor: {counts['running']} · "
                             f"Durduruldu: {counts['cancelled']} · Henüz denenmedi: {max(0, len(AREAS) - len(rows))}")
        self.summary.setStyleSheet(f"color: {C.RED if counts['failed'] else C.TEXT};")
        limits = {key: (scope, limit) for key, _, scope, limit in AREAS}
        records = self.data.get("events", [])
        active = bool(enabled and phase in ACTIVE and area in LABELS)
        hits = {area: time.time()} if active else {}
        self.canvas.set_data({area: 1} if active else {}, hits, phase)
        lines = []
        for row in rows:
            if self.filter and row['area'] != self.filter:
                continue
            if self.only_errors and row['status'] not in ('failed', 'unverified'):
                continue
            scope, limit = limits.get(row['area'], ('', ''))
            when = time.strftime('%H:%M:%S', time.localtime(row['updated']))
            lines.append(f"{LABELS.get(row['area'], row['area'])} · {STATES[row['status']]} · {when}\n"
                         f"Kontrol: {scope}\n{row['detail']}\n{row.get('location', '')}\n"
                         f"Süre: {row['duration_ms']:.0f} ms\nSınır: {limit}")
        for event in records:
            if self.filter and event['area'] != self.filter:
                continue
            if self.only_errors and event['status'] not in ('failed', 'unverified'):
                continue
            when = time.strftime('%H:%M:%S', time.localtime(event['time']))
            lines.append(f"{when} · {LABELS.get(event['area'], event['area'])}\n"
                         f"{STATES[event['status']]}\n{event['detail']}")
        text = "\n\n".join(lines) or "Bu görünümde kayıt yok. İlk yerel kontrol açılıştan sonra başlar."
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
