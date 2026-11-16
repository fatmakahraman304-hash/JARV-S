"""A paged, two-column reading surface inside the HUD."""

from PyQt6.QtCore import QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget

from gui.style import btn_css, px_font
from gui.theme import C


class BookPanel(QWidget):
    back_requested = pyqtSignal()
    gestures_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setFont(px_font(24))
        self.title.setStyleSheet(f"color: {C.PRI};")
        layout.addWidget(self.title)
        spread = QHBoxLayout()
        spread.setSpacing(4)
        self.leaves = []
        self.sources = []
        for side in range(2):
            leaf = QTextEdit(readOnly=True)
            leaf.setFont(px_font(15))
            border = "right" if side == 0 else "left"
            leaf.setStyleSheet(
                f"QTextEdit {{ background: {C.PANEL}; color: {C.TEXT}; padding: 16px;"
                f"border: 1px solid {C.BORDER}; border-{border}: 2px solid {C.PRI}; }}"
            )
            self.leaves.append(leaf)
            page = QVBoxLayout()
            page.addWidget(leaf, 1)
            source = QPushButton("Kaynağı aç")
            source.clicked.connect(lambda checked=False, offset=side: self._open_source(offset))
            source.setStyleSheet(btn_css("dim", align="center"))
            self.sources.append(source)
            page.addWidget(source)
            spread.addLayout(page, 1)
        layout.addLayout(spread, 1)
        bar = QHBoxLayout()
        self.previous = QPushButton("‹ Önceki")
        self.next = QPushButton("Sonraki ›")
        self.count = QLabel()
        self.jump = QSpinBox()
        self.jump.setAccessibleName("Sayfaya git")
        self.jump.setPrefix("Sayfa ")
        self.jump.setSingleStep(2)
        self.jump.setKeyboardTracking(False)
        self.jump.valueChanged.connect(self._jump_to)
        self.gestures = QPushButton("El hareketi")
        self.gestures.setCheckable(True)
        self.gestures.toggled.connect(self.gestures_changed)
        back = QPushButton("Taramaya dön")
        back.clicked.connect(self.back_requested)
        self.previous.clicked.connect(lambda: self.turn(-1))
        self.next.clicked.connect(lambda: self.turn(1))
        for widget in (self.previous, self.jump, self.count, self.next, self.gestures, back):
            if isinstance(widget, QPushButton):
                widget.setStyleSheet(btn_css("dim", align="center"))
            bar.addWidget(widget)
        layout.addLayout(bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.pages = []
        self.index = 0

    def show_pages(self, title, pages):
        self.title.setText(title)
        self.pages, self.index = pages, 0
        self.status.clear()
        self._render()

    def turn(self, direction):
        target = self.index + direction * 2
        if 0 <= target < len(self.pages):
            self.index = target
            self._render()

    def show_spread(self, index):
        if not self.pages:
            return
        index = max(0, min(index, len(self.pages) - 1))
        target = (index // 2) * 2
        if target != self.index:
            self.index = target
            self._render()

    def _jump_to(self, page):
        if 1 <= page <= len(self.pages):
            self.show_spread(page - 1)

    def _open_source(self, offset):
        index = self.index + offset
        if index < len(self.pages):
            url = QUrl(self.pages[index][2])
            if url.scheme() in {"https", "http"} and url.host() and not url.userInfo():
                QDesktopServices.openUrl(url)

    def _render(self):
        for offset, widget in enumerate(self.leaves):
            index = self.index + offset
            self.sources[offset].setVisible(index < len(self.pages))
            if index >= len(self.pages):
                widget.setPlainText("Kaynaklı sonuç bulunamadı." if not self.pages and not offset else "")
                continue
            heading, body, source = self.pages[index]
            widget.setPlainText(f"{heading}\n\n{body}\n\nKaynak\n{source}")
        self.count.setText(
            f"{self.index + 1}–{min(self.index + 2, len(self.pages))} / {len(self.pages)}"
            if self.pages else "0 sayfa"
        )
        self.jump.blockSignals(True)
        self.jump.setRange(1, max(1, len(self.pages)))
        self.jump.setValue(self.index + 1)
        self.jump.setEnabled(bool(self.pages))
        self.jump.blockSignals(False)
        self.previous.setEnabled(self.index > 0)
        self.next.setEnabled(self.index + 2 < len(self.pages))
        self.gestures.setEnabled(len(self.pages) > 2)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.turn(1 if key == Qt.Key.Key_Right else -1)
            event.accept()
        elif key == Qt.Key.Key_PageDown:
            self.turn(1)
            event.accept()
        elif key == Qt.Key.Key_PageUp:
            self.turn(-1)
            event.accept()
        elif key == Qt.Key.Key_Home:
            self.show_spread(0)
            event.accept()
        elif key == Qt.Key.Key_End:
            self.show_spread(len(self.pages) - 1)
            event.accept()
        else:
            super().keyPressEvent(event)
