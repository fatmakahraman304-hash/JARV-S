"""Second brain controls. Workers return through a Qt signal."""
import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QLineEdit, QListWidget, QListWidgetItem, QTextEdit, QCheckBox)
from gui.theme import C
from gui.style import px_font, btn_css, scroll_css


class _AgentUI:
    def __init__(self, window):
        self.log = window._log_sig
        self.job = window._codejob_sig

    def write_log(self, text):
        self.log.emit(text)

    def show_code_job(self, job):
        self.job.emit(dict(job))


class SecondBrainPanel(QDialog):
    completed = pyqtSignal(str)

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle("MAYK · İkinci Beyin")
        self.resize(860, 620)
        self.setFont(px_font(13))
        self.setStyleSheet(f"background: {C.BG}; color: {C.TEXT};")
        self.agent_ui = _AgentUI(window)
        self.busy = False
        layout = QVBoxLayout(self)
        title = QLabel("İKİNCİ BEYİN")
        title.setFont(px_font(24))
        layout.addWidget(title)
        description = QLabel("MAYK’ın gelişim defteri. Yerel kod işi hatalarını izler, fikirleri saklar ve seçtiğiniz geliştirmeyi ayrı çalışma alanında hazırlar.")
        description.setWordWrap(True)
        layout.addWidget(description)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        self.monitor = QCheckBox("Yerel kod işi hatalarını her dakika izle")
        self.monitor.setChecked(True)
        layout.addWidget(self.monitor)
        self.auto_plan = QCheckBox("Yeni fikirleri arka planda planla · API kullanır")
        layout.addWidget(self.auto_plan)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("MAYK neyi daha iyi yapabilsin?")
        row.addWidget(self.input)
        add = QPushButton("Fikir ekle")
        add.setStyleSheet(btn_css("primary", align="center"))
        add.setMinimumHeight(34)
        add.clicked.connect(self.add)
        self.input.returnPressed.connect(self.add)
        row.addWidget(add)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setStyleSheet(f"QListWidget {{ border: 1px solid {C.PRI_DIM}; padding: 8px; }}"
                                f"QListWidget::item {{ padding: 8px; }}"
                                f"QListWidget::item:selected {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}" + scroll_css())
        self.list.currentItemChanged.connect(self.selected)
        layout.addWidget(self.list, 1)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setStyleSheet(f"QTextEdit {{ border: 1px solid {C.PRI_DIM}; padding: 10px; }}" + scroll_css())
        layout.addWidget(self.detail, 1)
        buttons = QHBoxLayout()
        for title, action in (("Şimdi tara", "scan"), ("Plan oluştur", "analyze"),
                              ("Seçileni geliştir", "develop"), ("Arşivle", "dismiss")):
            button = QPushButton(title)
            button.setStyleSheet(btn_css("primary", align="center"))
            button.setMinimumHeight(36)
            button.clicked.connect(lambda checked=False, action=action: self.run(action))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QLabel("Plan oluştur seçilen fikri yapılandırılmış modele gönderir. Geliştirme sonucunu ve testleri burada takip edin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.completed.connect(self.finished)
        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(self.tick)
        self.monitor.toggled.connect(lambda on: self.timer.start() if on else self.timer.stop())
        self.timer.start()
        self.run("scan")

    def add(self):
        from core import second_brain as brain
        try:
            brain.add(self.input.text())
            self.input.clear()
            self.refresh()
        except Exception as exc:
            self.status.setText(str(exc))

    def refresh(self):
        from core import second_brain as brain
        selected = self.current()
        self.list.clear()
        for entry in brain.items():
            item = QListWidgetItem(f"{brain._LABELS[entry['state']]} · {entry['title']}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list.addItem(item)
            if selected and selected["id"] == entry["id"]:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None and self.list.count():
            self.list.setCurrentRow(0)

    def current(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected(self, *args):
        entry = self.current()
        self.detail.setPlainText((entry["detail"] + "\n\n" + entry["analysis"] + "\n\n" + entry["result"]) if entry else "")

    def tick(self):
        if self.monitor.isChecked():
            self.run("scan")

    def run(self, action):
        from core import second_brain as brain
        if self.busy:
            return
        entry = self.current()
        automatic_plan = self.auto_plan.isChecked()
        if action != "scan" and entry is None:
            self.status.setText("Önce bir geliştirme fikri seçin.")
            return
        self.busy = True
        self.status.setText("İşleniyor…")
        def work():
            try:
                message = "Yerel kayıtlar tarandı."
                if action == "scan":
                    brain.scan()
                    if automatic_plan:
                        pending = next((item for item in brain.items()
                                        if item["state"] == "idea" and not item["analysis"] and not item["result"]), None)
                        if pending:
                            try:
                                brain.analyze(pending["id"])
                                message = "Yeni fikir için plan hazır."
                            except Exception as exc:
                                brain.update(pending["id"], result=str(exc))
                                raise
                elif action == "analyze":
                    brain.analyze(entry["id"])
                    message = "Plan hazır. İnceleyip geliştirmeyi başlatabilirsiniz."
                elif action == "develop":
                    message = brain.develop(entry["id"], self.agent_ui)
                else:
                    if entry["state"] in ("requested", "running"):
                        raise ValueError("Çalışan iş arşivlenemez. Kod ajanının sonucunu bekleyin.")
                    brain.update(entry["id"], state="dismissed")
                    message = "Fikir arşivlendi."
            except Exception as exc:
                message = str(exc)
            self.completed.emit(message)
        threading.Thread(target=work, daemon=True, name="second-brain").start()

    def finished(self, message):
        self.busy = False
        self.status.setText(message)
        self.refresh()
