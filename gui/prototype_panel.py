"""Offline preview of a generated HTML prototype in a dedicated profile."""

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None


if QWebEngineView is not None:
    class OfflineRequests(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, request):
            request.block(request.requestUrl().scheme() != "data")


    class PreviewPage(QWebEnginePage):
        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            return (
                url.scheme() == "data"
                and navigation_type == QWebEnginePage.NavigationType.NavigationTypeTyped
            )

        def chooseFiles(self, mode, old_files, accepted_types):
            return []


class PrototypePanel(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Çevrimdışı web prototipi"))
        row.addStretch()
        back = QPushButton("CORE’a dön")
        back.clicked.connect(self.back_requested)
        row.addWidget(back)
        layout.addLayout(row)
        self.view = None
        if QWebEngineView is None:
            layout.addWidget(QLabel("Önizleme için PyQt6-WebEngine gerekiyor. HTML dosyası kaydedildi."))
            return
        self.profile = QWebEngineProfile(self)
        self.interceptor = OfflineRequests(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.view = QWebEngineView(self)
        page = PreviewPage(self.profile, self.view)
        options = QWebEngineSettings.WebAttribute
        for attribute in (
            options.LocalContentCanAccessFileUrls, options.LocalContentCanAccessRemoteUrls,
            options.JavascriptCanOpenWindows, options.LocalStorageEnabled,
        ):
            page.settings().setAttribute(attribute, False)
        self.view.setPage(page)
        layout.addWidget(self.view, 1)

    def show_html(self, text):
        if self.view is not None:
            policy = (
                '<meta http-equiv="Content-Security-Policy" content="'
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "img-src data:; media-src data:; font-src data:; form-action 'none'; base-uri 'none'"
                '">'
            )
            self.view.setHtml(policy + text, QUrl())
