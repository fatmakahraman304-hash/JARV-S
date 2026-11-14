"""On-demand views of the official websites, inside the central HUD."""

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from core.social_sites import CHAT_HOSTS, SITES
from gui.chat_composer import composer_script
from gui.style import btn_css
from gui.theme import C

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None


def permitted_url(url, site):
    return (
        url.scheme() == "https"
        and url.host().lower() in SITES[site][2]
        and url.port(443) == 443
        and not url.userInfo()
    )


def open_in_browser(site):
    return QDesktopServices.openUrl(QUrl(SITES[site][1]))


if QWebEngineView is not None:
    class SocialPage(QWebEnginePage):
        blocked = pyqtSignal()

        def __init__(self, profile, view, site):
            super().__init__(profile, view)
            self.site = site
            self.newWindowRequested.connect(self._open_here)

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            if not is_main_frame:
                return True
            if permitted_url(url, self.site):
                return True
            self.blocked.emit()
            return False

        def _open_here(self, request):
            url = request.requestedUrl()
            if not request.isUserInitiated():
                return
            if permitted_url(url, self.site):
                self.setUrl(url)
            else:
                self.blocked.emit()


class SocialPanel(QWidget):
    back_requested = pyqtSignal()
    site_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._views = {}
        QApplication.instance().aboutToQuit.connect(self._release_profiles)
        self._site = ""
        self._draft_request = None
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self._selector = QComboBox()
        self._selector.setAccessibleName("Platform seç")
        self._selector.setMinimumHeight(32)
        self._selector.setMinimumWidth(125)
        self._selector.setStyleSheet(
            f"QComboBox {{ color: {C.TEXT}; background: {C.PANEL2}; "
            f"border: 1px solid {C.BORDER}; border-radius: 8px; padding-left: 10px; }} "
            f"QAbstractItemView {{ color: {C.TEXT}; background: {C.PANEL2}; "
            f"selection-background-color: {C.BORDER}; }}"
        )
        for key, (label, _, _) in SITES.items():
            self._selector.addItem(label, key)
        self._selector.activated.connect(self._select_site)
        row.addWidget(self._selector)
        row.addStretch()
        row.addWidget(self._button("Tarayıcıda aç", self._open_external))
        self._retry = self._button("Yenile", self._reload)
        row.addWidget(self._retry)
        row.addWidget(self._button("CORE’a dön", self.back_requested.emit))
        layout.addLayout(row)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self._status)
        self._draft_notice = QLabel()
        self._draft_notice.setTextFormat(Qt.TextFormat.PlainText)
        self._draft_notice.setWordWrap(True)
        self._draft_notice.hide()
        layout.addWidget(self._draft_notice)
        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

    @staticmethod
    def _button(text, action):
        button = QPushButton(text)
        button.setMinimumHeight(32)
        button.setStyleSheet(btn_css("dim", align="center"))
        button.clicked.connect(action)
        return button

    def _select_site(self, index):
        site = self._selector.itemData(index)
        self._selector.setCurrentIndex(self._selector.findData(self._site))
        self.site_requested.emit(site)

    def open_site(self, site):
        if site != self._site:
            self._draft_request = None
            self._draft_notice.hide()
        _, address, _ = SITES[site]
        self._site = site
        self._selector.setCurrentIndex(self._selector.findData(site))
        self._retry.setEnabled(QWebEngineView is not None)
        if QWebEngineView is None:
            self._status.setText("Gömülü web görünümü eksik. Tarayıcıda açabilirsin.")
            self._status.show()
            return
        if site not in self._views:
            view = QWebEngineView(self._stack)
            # Keep the existing storage name so previous sign-ins still work.
            profile = QWebEngineProfile("jarvis-social-" + site, QApplication.instance())
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            page = SocialPage(profile, view, site)
            view.setPage(page)
            self._stack.addWidget(view)
            self._views[site] = [view, "Yükleniyor…"]
            view.loadStarted.connect(lambda: self._set_status(site, "Yükleniyor…"))
            view.loadFinished.connect(lambda ok: self._loaded(site, ok))
            page.blocked.connect(lambda: self._set_status(
                site, "Bu bağlantı gömülü görünümde açılamıyor. Giriş için tarayıcıyı kullanabilirsin."
            ))
            view.setUrl(QUrl(address))
        self._stack.setCurrentWidget(self._views[site][0])
        self._refresh_status()

    def write_chat_draft(self, draft):
        site = self._site
        if site not in CHAT_HOSTS:
            return False
        entry = self._views.get(site)
        if entry is None:
            self._show_draft_notice("Sohbet kutusu için gömülü web görünümü gerekli.")
            return False
        request = object()
        self._draft_request = request
        self._show_draft_notice("Sohbet kutusu bekleniyor…")
        self._try_draft(request, site, draft, remaining=20)
        return True

    def _show_draft_notice(self, text):
        self._draft_notice.setText(text)
        self._draft_notice.show()

    def _try_draft(self, request, site, draft, remaining):
        if request is not self._draft_request or not self.isVisible():
            return
        view = self._views[site][0]

        def retry():
            if remaining:
                QTimer.singleShot(350, lambda: self._try_draft(request, site, draft, remaining - 1))
            else:
                self._draft_request = None
                self._show_draft_notice(
                    "Sohbet kutusu bulunamadı. Giriş yapıp sohbeti açtıktan sonra tekrar dene."
                )

        url = view.url()
        if not (permitted_url(url, site) and url.host().lower() in CHAT_HOSTS[site]):
            retry()
            return

        def finished(result):
            if request is not self._draft_request or not self.isVisible():
                return
            if result == "inserted":
                self._draft_request = None
                self._show_draft_notice("Taslak sohbet kutusuna yazıldı. Göndermek için sohbet düğmesini kullan.")
            elif result in ("no-composer", "wrong-page"):
                retry()
            else:
                self._draft_request = None
                self._show_draft_notice("Sohbet kutusuna yazı aktarılamadı.")

        view.page().runJavaScript(
            composer_script(site, draft), QWebEngineScript.ScriptWorldId.ApplicationWorld.value, finished
        )

    def hideEvent(self, event):
        self._draft_request = None
        self._draft_notice.hide()
        super().hideEvent(event)

    def _set_status(self, site, message):
        self._views[site][1] = message
        if site == self._site:
            self._refresh_status()

    def _refresh_status(self):
        _, message = self._views[self._site]
        self._status.setText(message)
        self._status.setVisible(bool(message))

    def _loaded(self, site, ok):
        message = "" if ok else "Site yüklenemedi. Yenile veya tarayıcıda aç."
        self._set_status(site, message)

    def _reload(self):
        entry = self._views.get(self._site)
        if entry:
            view = entry[0]
            if permitted_url(view.url(), self._site):
                view.reload()
            else:
                view.setUrl(QUrl(SITES[self._site][1]))

    def _release_profiles(self):
        # main.py exits with os._exit after the Qt loop. Destroy disk profiles
        # while Qt is still alive so Chromium can flush their data.
        self._draft_request = None
        for view, _ in self._views.values():
            profile = view.page().profile()
            sip.delete(view)
            sip.delete(profile)
        self._views.clear()

    def _open_external(self):
        if self._site and not open_in_browser(self._site):
            self._status.setText("Varsayılan tarayıcı açılamadı.")
            self._status.show()
