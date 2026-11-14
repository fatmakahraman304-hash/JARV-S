"""One-time entry for the local coding API keys."""

from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from gui.style import btn_css, px_font
from gui.theme import C
from memory.config_manager import save_deepseek_coding_keys


class DeepSeekSetup(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("DeepSeek · Kodlama")
        self.setMinimumWidth(420)
        self.setStyleSheet(
            f"QDialog {{ background: {C.BG}; }} QLabel {{ color: {C.TEXT}; }}"
            f"QLineEdit {{ background: {C.PANEL}; color: {C.TEXT}; padding: 8px;"
            f" border: 1px solid {C.BORDER}; border-radius: 6px; }}"
        )
        layout = QVBoxLayout(self)
        title = QLabel("DeepSeek V4.1 Flash")
        title.setFont(px_font(20))
        layout.addWidget(title)
        note = QLabel("Kod değişiklikleri için üç farklı API anahtarı gir.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.fields = []
        for index in range(1, 4):
            field = QLineEdit()
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setPlaceholderText(f"API anahtarı {index}")
            field.setAccessibleName(f"DeepSeek API anahtarı {index}")
            field.setMaxLength(512)
            self.fields.append(field)
            layout.addWidget(field)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        later = QPushButton("Daha sonra")
        later.setStyleSheet(btn_css("dim", align="center"))
        later.clicked.connect(self.reject)
        save = QPushButton("Kaydet")
        save.setStyleSheet(btn_css("primary", align="center"))
        save.clicked.connect(self._save)
        row.addStretch()
        row.addWidget(later)
        row.addWidget(save)
        layout.addLayout(row)
        self.finished.connect(self._clear)

    def _clear(self):
        for field in self.fields:
            field.clear()
        self.status.clear()

    def _save(self):
        try:
            save_deepseek_coding_keys([field.text() for field in self.fields])
        except ValueError as exc:
            self.status.setText(str(exc))
        except OSError:
            self.status.setText("Anahtarlar kaydedilemedi. JARVIS klasörünün yazma iznini kontrol et.")
        else:
            self.accept()
