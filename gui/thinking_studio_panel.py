"""Native FRIDAY feature browser. No network calls, secrets or automatic exports."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QFileDialog,
    QMessageBox, QAbstractItemView,
)
from core import thinking_studio as studio


class ThinkingStudioDialog(QDialog):
    def __init__(self, parent, send_command):
        super().__init__(parent)
        self.send_command = send_command
        self._light = False
        self.setWindowTitle("FRIDAY · Düşünce Stüdyosu")
        self.resize(850, 660)
        root = QVBoxLayout(self)
        title = QLabel(f"{len(studio.FEATURES)} özellik · {len(studio.MODES)} çalışma modu")
        root.addWidget(title)
        root.addWidget(QLabel("Ara, kategori seç, bir veya en fazla dört mod seç ve uygula."))
        self.query = QLineEdit()
        self.query.setPlaceholderText("Özellik adı, numarası veya anahtar kelime")
        self.query.setAccessibleName("Özellik ara")
        root.addWidget(self.query)
        self.group = QComboBox()
        self.group.setAccessibleName("Özellik kategorisi")
        self.group.addItem("Tümü", (1, 500))
        for a, b, label in studio.GROUPS:
            self.group.addItem(f"{a}–{b} · {label}", (a, b))
        root.addWidget(self.group)
        self.rows = QListWidget()
        self.rows.setAccessibleName("Özellik listesi")
        self.rows.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        root.addWidget(self.rows, 2)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("Özellik açıklaması ve uygulama durumu")
        root.addWidget(self.detail, 1)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        controls = QHBoxLayout()
        for label, callback in (
            ("Uygula", self.apply_selected), ("Normal mod", lambda: self._send("normal moda dön")),
            ("Sessiz eşlik", lambda: self._send("sessiz eşlik")), ("Kullanım", self.show_usage),
            ("Açık/koyu tema", self.toggle_theme),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        root.addLayout(controls)
        history = QHBoxLayout()
        for label, callback in (
            ("Projeler ve arşiv", self.open_workspace),
            ("Bugünkü kayıtlar", self.show_today),
            ("Son 100 kaydı dışa aktar", self.export_history),
            ("Kapat", self.close),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            history.addWidget(button)
        root.addLayout(history)
        self.query.textChanged.connect(self.refresh)
        self.group.currentIndexChanged.connect(self.refresh)
        self.rows.itemSelectionChanged.connect(self.show_detail)
        self.rows.itemDoubleClicked.connect(lambda _item: self.apply_selected())
        self.refresh()

    def refresh(self, *_):
        a, b = self.group.currentData()
        self.rows.clear()
        for n, title, guide, status in studio.search_features(self.query.text(), a, b):
            item = QListWidgetItem(f"{n:03d} · {title} — {status}")
            item.setData(Qt.ItemDataRole.UserRole, n)
            self.rows.addItem(item)
        self.status.setText(f"{self.rows.count()} sonuç · Etkin: {studio.mode_prompt() or 'Normal'}")

    def show_detail(self):
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.rows.selectedItems()]
        self.detail.setPlainText("\n\n".join(
            f"{n}. {studio.FEATURES[n][0]}\n{studio.guidance_for(n)}\nDurum: {studio.feature_status(n)}"
            for n in ids[:4]))

    def _send(self, command):
        self.close()
        self.send_command(command)

    def apply_selected(self):
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.rows.selectedItems()]
        if len(ids) == 1 and ids[0] in (472, 473, 480, 481, 482, 483, 484, 489, 491, 492, 493, 496, 498):
            self.open_workspace({472:"project",473:"idea",481:"source",483:"decision",489:"template",493:"feedback"}.get(ids[0], ""))
            return
        if ids == [475]:
            self.export_history()
            return
        if ids == [476]:
            self.show_today()
            return
        if ids == [477]:
            self.toggle_theme()
            return
        if ids == [479]:
            self._send("sessiz eşlik")
            return
        if ids == [495]:
            self.show_usage()
            return
        if not ids or len(ids) > 4 or any(n not in studio.MODES for n in ids):
            self.status.setText("Uygulamak için 1–4 çalışma modu seçin. İlkeler ve uygulama maddeleri bilgi amaçlıdır.")
            return
        self._send("mod " + " ve ".join(map(str, ids)))

    def toggle_theme(self):
        self._light = not self._light
        bg, fg, field, border = ("#f2f5f8", "#182533", "#ffffff", "#8b9bab") if self._light else (
            "#17212b", "#edf5fa", "#202e3a", "#58758a")
        self.setStyleSheet(f"QDialog {{background:{bg};color:{fg};}} QLabel {{color:{fg};}} "
                           f"QLineEdit,QPlainTextEdit,QListWidget,QComboBox,QPushButton "
                           f"{{background:{field};color:{fg};border:1px solid {border};padding:5px;}} "
                           "QListWidget::item:selected {background:#14789b;color:white;}")

    def open_workspace(self, kind=""):
        from gui.studio_workspace import WorkspaceDialog
        WorkspaceDialog(self, kind if isinstance(kind, str) else "", self.send_command).exec()


    def show_usage(self):
        counts = studio.usage()
        self.detail.setPlainText("\n".join(
            f"{(studio.MODES if n > 0 else studio.STYLE)[n][0]}: {count}"
            for n, count in sorted(counts.items(), key=lambda kv: -kv[1]))
            or "Bu oturumda henüz mod seçilmedi.")

    def show_today(self):
        from datetime import datetime
        from memory.continuity import recent
        try:
            rows = []
            for stamp, role, text in recent(100):
                date = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone().date()
                if date == datetime.now().date():
                    rows.append(f"{stamp[:16]} · {role}: {text}")
            self.detail.setPlainText("Bugünkü son 100 kayıt içindeki konuşmalar:\n\n" +
                                     ("\n".join(rows) or "Kayıt yok."))
        except Exception as exc:
            self.status.setText(f"Kayıtlar okunamadı: {type(exc).__name__}")

    def export_history(self):
        from pathlib import Path
        from memory.continuity import recent
        path, _ = QFileDialog.getSaveFileName(self, "Konuşma kayıtlarını dışa aktar",
                                             "friday-konusmalar.txt", "Metin (*.txt)")
        if not path:
            return
        try:
            # Explicit destination from the OS dialog; no automatic uploads.
            # The save dialog handles overwrite confirmation.
            rows = recent(100)
            Path(path).write_text("\n".join(f"{stamp} | {role}: {text}" for stamp, role, text in rows),
                                  encoding="utf-8")
            self.status.setText(f"{len(rows)} kayıt seçilen dosyaya yazıldı.")
        except Exception as exc:
            self.status.setText(f"Dışa aktarılamadı: {type(exc).__name__}")
