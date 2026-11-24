"""Native FRIDAY feature browser. No network calls, secrets or automatic exports."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QFileDialog,
    QMessageBox, QAbstractItemView, QInputDialog,
)
from core import thinking_studio as studio
from core import core_modes as core
from core import integrated_capabilities as integrated
from core.voice_commands import normalize_command


class ThinkingStudioDialog(QDialog):
    def __init__(self, parent, send_command):
        super().__init__(parent)
        self.send_command = send_command
        self._light = False
        self.setWindowTitle("FRIDAY · Yerleşik Yetenekler ve Arşiv")
        self.resize(850, 660)
        root = QVBoxLayout(self)
        title = QLabel(f"{len(studio.FEATURES)} yerleşik özellik · Otomatik sohbet")
        root.addWidget(title)
        root.addWidget(QLabel("Tüm özellikler normal konuşmada otomatik kullanılır. Bu panel bilgi ve arşiv içindir."))
        self.query = QLineEdit()
        self.query.setPlaceholderText("Özellik adı, numarası veya anahtar kelime")
        self.query.setAccessibleName("Özellik ara")
        root.addWidget(self.query)
        self.group = QComboBox()
        self.group.setAccessibleName("Özellik kategorisi")
        self.group.addItem("30 çalışma alanı (otomatik)", (0, 0))
        self.group.addItem("Tüm yerleşik özellikler", (1, studio.MAX_FEATURE))
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
            ("İncele / arşivi aç", self.apply_selected),
            ("Sessiz eşlik", lambda: self._send("sessiz eşlik")), ("Kullanım", self.show_usage),
            ("Açık/koyu tema", self.toggle_theme),
            ("Yönlendirme önizle", self.preview_route),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        root.addLayout(controls)
        history = QHBoxLayout()
        for label, callback in (
            ("Projeler ve arşiv", self.open_workspace),
            ("Görevler", lambda: self.open_workspace("task")),
            ("Kayıt şablonu", self.open_template),
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
        if a == 0:
            q = normalize_command(self.query.text())
            for n, mode in core.MODES.items():
                searchable = normalize_command(f"{n} {mode.name} {mode.purpose}")
                if q and q not in searchable:
                    continue
                item = QListWidgetItem(f"{n:02d} · {mode.name} — otomatik")
                item.setData(Qt.ItemDataRole.UserRole, -n)
                self.rows.addItem(item)
            self.status.setText(f"{self.rows.count()} çalışma alanı · normal sohbet içinde otomatik")
            return
        for n, title, guide, status in studio.search_features(self.query.text(), a, b):
            item = QListWidgetItem(f"{n:03d} · {title} — {status}")
            item.setData(Qt.ItemDataRole.UserRole, n)
            self.rows.addItem(item)
        self.status.setText(f"{self.rows.count()} sonuç · Normal sohbet içinde kullanılabilir")

    def show_detail(self):
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.rows.selectedItems()]
        if ids and all(n < 0 for n in ids):
            self.detail.setPlainText(core.turn_hint(tuple(-n for n in ids[:3])))
            return
        self.detail.setPlainText("\n\n".join(
            f"{n}. {studio.FEATURES[n][0]}\n{studio.workflow_for(n)}\nDurum: {studio.feature_status(n)}"
            for n in ids[:4]))

    def _send(self, command):
        self.close()
        self.send_command(command)

    def apply_selected(self):
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.rows.selectedItems()]
        if ids and all(n < 0 for n in ids):
            self.status.setText("Çalışma alanları normal sohbet içinde otomatik kullanılır.")
            return
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
            self.status.setText("Özellik açıklaması için kayıt seçin.")
            return
        self.show_detail()
        self.status.setText("Bu yöntemler FRIDAY sohbetinde otomatik kullanılır; etkinleştirme gerekmez.")

    def preview_route(self):
        request, accepted = QInputDialog.getText(self, "Otomatik yönlendirme", "Örnek isteği yazın (çalıştırılmaz):")
        if accepted:
            decision = core.decide(request)
            self.detail.setPlainText(core.explain(decision) + "\n\n" + (integrated.guidance(integrated.resolve(request, decision.ids)) or "Ek katalog yöntemi eşleşmedi."))

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


    def open_template(self):
        from core.studio_templates import FIELDS, draft
        from gui.studio_workspace import WorkspaceDialog
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.rows.selectedItems()]
        if len(ids) != 1 or ids[0] not in FIELDS:
            self.status.setText("Şablon için desteklenen bir günlük, tarif, fatura veya kayıt modu seçin.")
            return
        WorkspaceDialog(self, "note", self.send_command, template=draft(ids[0])).exec()

    def show_usage(self):
        counts = studio.usage()
        self.detail.setPlainText("\n".join(
            f"{(studio.MODES if n > 0 else studio.STYLE)[n][0]}: {count}"
            for n, count in sorted(counts.items(), key=lambda kv: -kv[1]))
            or "Bu oturumda henüz açık üslup/etkileşim ayarı kullanılmadı.")

    def show_today(self):
        from datetime import datetime
        from memory.continuity import day_history
        try:
            snapshot=day_history()
            rows=[]
            for stamp,role,body in snapshot["rows"]:
                local=datetime.fromisoformat(stamp).astimezone().strftime("%H:%M")
                rows.append(f"{local} · {role}: {body}")
            notice=f"{snapshot['day']} · {len(rows)} / {snapshot['total']} kayıt"
            if snapshot["omitted"]:
                notice+=f" · Görüntü sınırı nedeniyle {snapshot['omitted']} eski kayıt gösterilmiyor."
            self.detail.setPlainText(notice+"\n\n"+("\n".join(rows) or "Gösterilecek kayıt yok."))
            self.status.setText("Yerel konuşma kayıtları; otomatik yapay zekâ özeti değildir.")
        except Exception as exc:
            self.status.setText(f"Kayıtlar okunamadı: {type(exc).__name__}")

    def export_history(self):
        from memory.continuity import export_recent_text
        path, _ = QFileDialog.getSaveFileName(self, "Konuşma kayıtlarını dışa aktar",
                                             "friday-konusmalar.txt", "Metin (*.txt)")
        if not path:
            return
        try:
            count=export_recent_text(path)
            self.status.setText(f"{count} kayıt seçilen dosyaya yazıldı.")
        except Exception as exc:
            self.status.setText(f"Dışa aktarılamadı: {type(exc).__name__} · {str(exc)[:150]}")
