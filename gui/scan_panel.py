"""Show a scan and its observations in the center HUD."""

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from gui.style import btn_css, px_font
from gui.theme import C


class ScanPreview(QLabel):
    def paintEvent(self, event):
        super().paintEvent(event)
        image = self.pixmap()
        if image is None or image.isNull():
            return
        left = (self.width() - image.width()) // 2 + 6
        top = (self.height() - image.height()) // 2 + 6
        right = self.width() - left
        bottom = self.height() - top
        if right - left < 44 or bottom - top < 44:
            return
        painter = QPainter(self)
        pen = QPen(QColor(C.PRI), 2)
        painter.setPen(pen)
        for x, y, dx, dy in ((left, top, 1, 1), (right, top, -1, 1),
                             (left, bottom, 1, -1), (right, bottom, -1, -1)):
            corner = QPoint(x, y)
            painter.drawLine(corner, QPoint(x + 20 * dx, y))
            painter.drawLine(corner, QPoint(x, y + 20 * dy))
        guide = QColor(C.PRI)
        guide.setAlpha(80)
        painter.setPen(guide)
        middle = (top + bottom) // 2
        painter.drawLine(left, middle, right, middle)


class ScanPanel(QWidget):
    back_requested = pyqtSignal()
    research_requested = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 16)
        header = QHBoxLayout()
        title = QLabel("KAMERA TARAMASI")
        title.setFont(px_font(16, spacing=2))
        title.setStyleSheet(f"color: {C.PRI};")
        header.addWidget(title)
        header.addStretch()
        back = QPushButton("CORE’a dön")
        back.setStyleSheet(btn_css("dim", align="center"))
        back.clicked.connect(self.back_requested)
        header.addWidget(back)
        layout.addLayout(header)
        self.source = QLabel()
        self.source.setStyleSheet(f"color: {C.TEXT_DIM};")
        layout.addWidget(self.source)
        self.photo = ScanPreview()
        self.photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.photo.setStyleSheet(
            f"background: {C.BG}; border: 1px solid {C.PRI}; border-radius: 10px;"
        )
        layout.addWidget(self.photo)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setFont(px_font(15))
        self.details.setStyleSheet(
            f"background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER};"
            "border-radius: 10px; padding: 12px;"
        )
        layout.addWidget(self.details, 1)
        selection = QHBoxLayout()
        self.books = QComboBox()
        self.books.setEditable(True)
        self.books.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.books.setAccessibleName("Kitap başlığı")
        self.books.lineEdit().setPlaceholderText("Kitap başlığı")
        self.books.lineEdit().setMaxLength(180)
        book_button = QPushButton("Kitabı araştır")
        book_button.clicked.connect(lambda: self.research_requested.emit("", True))
        selection.addWidget(self.books, 1)
        selection.addWidget(book_button)
        layout.addLayout(selection)
        selection = QHBoxLayout()
        self.subject = QLineEdit()
        self.subject.setMaxLength(180)
        self.subject.setPlaceholderText("Araştırılacak başka nesne veya yazı")
        item_button = QPushButton("Web’de araştır")
        item_button.clicked.connect(lambda: self.research_requested.emit(self.subject.text(), False))
        self.subject.returnPressed.connect(item_button.click)
        selection.addWidget(self.subject, 1)
        selection.addWidget(item_button)
        layout.addLayout(selection)
        self.research_status = QLabel()
        self.research_status.setWordWrap(True)
        layout.addWidget(self.research_status)
        self._pixmap = QPixmap()

    def show_scan(self, jpeg, report):
        self.source.setText(report["source"])
        self.books.clear()
        self.subject.clear()
        self.research_status.clear()
        for book in report.get("books", ()):
            self.books.addItem(book["title"], book["author"])
        self._pixmap = QPixmap()
        if jpeg:
            self._pixmap.loadFromData(jpeg)
        self.photo.setVisible(not self._pixmap.isNull())
        sections = [report.get("summary", "")]
        sections.extend(f"• {detail}" for detail in report.get("details", ()))
        if codes := report.get("qr"):
            sections.append("OKUNAN QR\n" + "\n".join(codes))
        sections.append(report.get("notice", ""))
        self.details.setPlainText("\n\n".join(section for section in sections if section))
        self._scale_photo()

    def _scale_photo(self):
        if not self._pixmap.isNull():
            self.photo.setPixmap(self._pixmap.scaled(
                max(1, self.width() - 48), max(80, min(310, self.height() // 2)),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale_photo()
