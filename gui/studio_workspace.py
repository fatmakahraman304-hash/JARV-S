"""Local, user-controlled FRIDAY workspace UI."""
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QFileDialog, QMessageBox, QFormLayout)
from PyQt6.QtCore import Qt
from core.studio_workspace import Workspace, KINDS, STAGES, CONFIDENCE, MAX_BACKUP

LABELS = dict(zip(KINDS, ("Proje", "Fikir", "Karar", "Kaynak", "Geri bildirim", "Şablon", "Not")))


class WorkspaceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FRIDAY · Projeler ve Fikir Arşivi")
        self.resize(900, 720)
        self.store = Workspace()
        self.record_id = None
        root = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Başlık, etiket, proje veya içerik ara")
        self.search.setAccessibleName("Kayıt ara")
        self.filter = QComboBox()
        self.filter.addItem("Tüm kayıt türleri", "")
        for k in KINDS:
            self.filter.addItem(LABELS[k], k)
        self.project_filter = QLineEdit()
        self.project_filter.setPlaceholderText("Proje bağlamı (tam ad)")
        filters.addWidget(self.search)
        filters.addWidget(self.filter)
        filters.addWidget(self.project_filter)
        root.addLayout(filters)
        self.rows = QListWidget()
        self.rows.setAccessibleName("Kayıtlar")
        root.addWidget(self.rows, 2)
        self.kind = QComboBox()
        for k in KINDS:
            self.kind.addItem(LABELS[k], k)
        self.title = QLineEdit()
        self.project = QLineEdit()
        self.tags = QLineEdit()
        self.stage = QComboBox()
        self.stage.addItems(STAGES)
        self.confidence = QComboBox()
        self.confidence.addItems(CONFIDENCE)
        self.body = QPlainTextEdit()
        form = QFormLayout()
        for label, field in (("Tür", self.kind), ("Başlık", self.title),
                             ("Proje bağlamı", self.project), ("Etiketler (virgül)", self.tags),
                             ("Aşama", self.stage), ("Güven etiketi (kullanıcı seçimi)", self.confidence),
                             ("İçerik", self.body)):
            form.addRow(label, field)
            field.setAccessibleName(label)
        root.addLayout(form, 3)
        self.status = QLabel("Sadece sizin kaydettiğiniz içerikler saklanır.")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        for controls in (
            (("Yeni", self.clear), ("Kaydet", self.save), ("Sil", self.delete),
             ("Sürüm geçmişi", self.show_versions), ("Bağlantılar", self.show_links)),
            (("Yedekle", self.backup), ("Yedekten ekle", self.restore),
             ("Seçili kaydı paylaşmak için dışa aktar", self.export_selected), ("Kapat", self.close)),
        ):
            bar = QHBoxLayout()
            for label, callback in controls:
                button = QPushButton(label)
                button.clicked.connect(callback)
                bar.addWidget(button)
            root.addLayout(bar)
        self.search.textChanged.connect(self.refresh)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.project_filter.textChanged.connect(self.refresh)
        self.rows.itemClicked.connect(self.load)
        self.refresh()

    def error(self, exc):
        self.status.setText("İşlem yapılamadı: " + str(exc)[:200])

    def refresh(self, *_):
        try:
            self.rows.clear()
            for r in self.store.list(self.search.text(), self.filter.currentData(), self.project_filter.text()):
                item = QListWidgetItem(f"{LABELS[r['kind']]} · {r['title']} · {r['stage']}")
                item.setData(Qt.ItemDataRole.UserRole, r)
                self.rows.addItem(item)
        except Exception as exc:
            self.error(exc)

    def clear(self):
        self.record_id = None
        self.rows.clearSelection()
        for field in (self.title, self.project, self.tags, self.body):
            field.clear()
        self.stage.setCurrentIndex(0)
        self.confidence.setCurrentIndex(0)

    def load(self, item):
        r = item.data(Qt.ItemDataRole.UserRole)
        self.record_id = r["id"]
        self.kind.setCurrentIndex(self.kind.findData(r["kind"]))
        for field, key in ((self.title,"title"), (self.project,"project"), (self.tags,"tags")):
            field.setText(r[key])
        self.stage.setCurrentText(r["stage"])
        self.confidence.setCurrentText(r["confidence"])
        self.body.setPlainText(r["body"])

    def save(self):
        try:
            self.record_id = self.store.save(kind=self.kind.currentData(), title=self.title.text(),
                body=self.body.toPlainText(), tags=self.tags.text(), project=self.project.text(),
                stage=self.stage.currentText(), confidence=self.confidence.currentText(),
                record_id=self.record_id)
            self.refresh()
            self.status.setText("Yerel kayıt kaydedildi.")
        except Exception as exc:
            self.error(exc)

    def delete(self):
        if not self.record_id:
            return
        yes = QMessageBox.question(self, "Kayıt silme",
            "Seçili kayıt ve yerel sürüm geçmişi silinecek. Dışa aktarılan yedekler etkilenmez. Devam?")
        if yes != QMessageBox.StandardButton.Yes:
            return
        if QMessageBox.question(self, "Son onay", "Bu kaydı kalıcı olarak sil?") != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.store.delete(self.record_id):
                self.clear()
                self.refresh()
                self.status.setText("Seçili yerel kayıt silindi.")
        except Exception as exc:
            self.error(exc)

    def show_text(self, title, value):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(value)
        layout.addWidget(text)
        dialog.exec()

    def show_versions(self):
        if not self.record_id:
            return
        try:
            rows = self.store.versions(self.record_id)
            self.show_text("Önceki sürümler", "\n\n".join(
                f"{r['saved_at']} · {r['title']} · {r['stage']}\n{r['body']}" for r in rows) or "Önceki sürüm yok.")
        except Exception as exc:
            self.error(exc)

    def show_links(self):
        try:
            nodes, edges = self.store.relationships(self.project_filter.text())
            names = {n["id"]: n["title"] for n in nodes}
            self.show_text("Etiket ve proje bağlantıları", "\n".join(
                f"{names[e['from']]} ↔ {names[e['to']]} ({e['reason']})" for e in edges) or "Bağlantı yok.")
        except Exception as exc:
            self.error(exc)

    def backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "FRIDAY yerel arşiv yedeği", "friday-studio.json", "JSON (*.json)")
        if path:
            try:
                Path(path).write_text(self.store.export(), encoding="utf-8")
                self.status.setText("Arşiv yedeği yazıldı. Eski sürümler ve diğer uygulama verileri dahil değildir.")
            except Exception as exc:
                self.error(exc)

    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "FRIDAY yedeği seç", "", "JSON (*.json)")
        if not path:
            return
        if QMessageBox.question(self, "Yedekten ekle", "Yedekteki yeni kayıtlar eklenecek; mevcut kayıtlar değişmeyecek.") != QMessageBox.StandardButton.Yes:
            return
        try:
            if Path(path).stat().st_size > MAX_BACKUP:
                raise ValueError("Yedek çok büyük.")
            count = self.store.import_backup(Path(path).read_text(encoding="utf-8"))
            self.refresh()
            self.status.setText(f"{count} yeni kayıt eklendi.")
        except Exception as exc:
            self.error(exc)

    def export_selected(self):
        if not self.record_id:
            return
        try:
            row = next((r for r in self.store.list() if r["id"] == self.record_id), None)
            if not row:
                return
            path, _ = QFileDialog.getSaveFileName(self, "Seçili kaydı yerel dosyaya aktar",
                                                "friday-kayit.txt", "Metin (*.txt)")
            if path:
                Path(path).write_text(f"{row['title']}\n{row['confidence']}\n\n{row['body']}", encoding="utf-8")
                self.status.setText("Dosya yazıldı. Başka kişiye gönderilmedi.")
        except Exception as exc:
            self.error(exc)
