"""On-demand views of the official websites, inside the central HUD."""

import os
import sys

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from core.social_sites import CHAT_HOSTS, SITES
from gui.chat_composer import composer_script
from gui.style import btn_css
from gui.theme import C

try:
    from PyQt6.QtWebEngineCore import QWebEngineLoadingInfo, QWebEnginePage, QWebEngineProfile, QWebEngineScript
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


def open_in_browser(site, *, edge=False, login=False):
    address = "https://chatgpt.com/auth/login" if login and site == "chatgpt" else SITES[site][1]
    if not edge and QDesktopServices.openUrl(QUrl(address)):
        return True
    if sys.platform != "win32":
        return False
    try:
        os.startfile("microsoft-edge:" + address)
    except OSError:
        return False
    return True



if QWebEngineView is not None:
    class SocialPage(QWebEnginePage):
        blocked = pyqtSignal(str)

        def __init__(self, profile, view, site):
            super().__init__(profile, view)
            self.site = site
            self.newWindowRequested.connect(self._open_here)

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            if not is_main_frame:
                return True
            if permitted_url(url, self.site):
                return True
            self.blocked.emit(bytes(QUrl.toAce(url.host())).decode("ascii")[:253])
            return False

        def _open_here(self, request):
            url = request.requestedUrl()
            if not request.isUserInitiated():
                return
            if permitted_url(url, self.site):
                self.setUrl(url)
            else:
                self.blocked.emit(bytes(QUrl.toAce(url.host())).decode("ascii")[:253])


class SocialPanel(QWidget):
    back_requested = pyqtSignal()
    site_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._views = {}
        QApplication.instance().aboutToQuit.connect(self._release_profiles)
        self._site = ""
        self._blocked = set()
        self._chatgpt_google_blocked = False
        self._failed = set()
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
        row.addWidget(self._button("Tarayıcıda aç", lambda: self._open_external()))
        if sys.platform == "win32":
            row.addWidget(self._button("Edge’de aç", lambda: self._open_external(edge=True)))
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
        help_row = QHBoxLayout()
        self._link = QLabel()
        self._link.setTextFormat(Qt.TextFormat.PlainText)
        self._link.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        help_row.addWidget(self._link, 1)
        self._chatgpt_login = self._button("ChatGPT girişini aç", self._open_chatgpt_login)
        self._chatgpt_login.hide()
        help_row.addWidget(self._chatgpt_login)
        self._google_login = self._button(
            "Google girişini tarayıcıda aç", lambda: self._open_external(login=True)
        )
        self._google_login.hide()
        help_row.addWidget(self._google_login)
        help_row.addWidget(self._button("Adresi kopyala", self._copy_address))
        layout.addLayout(help_row)
        self._fallback = QLabel("Siteyi yeniden yükleyebilir veya adresi tarayıcıya yapıştırabilirsin.")
        self._fallback.setWordWrap(True)
        self._fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback.setStyleSheet(
            f"background: {C.PANEL}; color: {C.TEXT}; border: 1px solid {C.BORDER}; padding: 18px;"
        )
        self._stack.addWidget(self._fallback)

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
        self._link.setText(address)
        self._selector.setCurrentIndex(self._selector.findData(site))
        self._retry.setEnabled(QWebEngineView is not None)
        self._chatgpt_login.setVisible(site == "chatgpt" and QWebEngineView is not None
                                       and not self._chatgpt_google_blocked)
        self._google_login.setVisible(site == "chatgpt" and self._chatgpt_google_blocked)
        if QWebEngineView is None:
            self._status.setText("Gömülü web görünümü eksik. Tarayıcıda açabilirsin.")
            self._status.show()
            self._stack.setCurrentWidget(self._fallback)
            return
        if site not in self._views:
            view = QWebEngineView(self._stack)
            # Keep the existing storage name so previous sign-ins still work.
            profile = QWebEngineProfile("jarvis-social-" + site, QApplication.instance())
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            page = SocialPage(profile, view, site)
            page.setBackgroundColor(QColor(C.BG))
            view.setPage(page)
            self._stack.addWidget(view)
            self._views[site] = [view, "Yükleniyor…"]
            page.loadingChanged.connect(lambda info: self._loading_changed(site, info))
            page.blocked.connect(lambda host: self._navigation_blocked(site, host))
            view.setUrl(QUrl(address))
        self._refresh_status()

    def write_chat_draft(self, draft):
        site = self._site
        if site not in CHAT_HOSTS:
            return False
        if site == "chatgpt" and self._chatgpt_google_blocked:
            self._show_draft_notice("CORE’da açık sohbet yok. Google girişini tarayıcıda tamamla.")
            return True
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
        view, message = self._views[self._site]
        self._stack.setCurrentWidget(self._fallback if self._site in self._failed else view)
        self._status.setText(message)
        self._status.setVisible(bool(message))
        google_blocked = self._site == "chatgpt" and self._chatgpt_google_blocked
        self._google_login.setVisible(google_blocked)
        self._chatgpt_login.setVisible(self._site == "chatgpt" and not google_blocked)

    def _navigation_blocked(self, site, host):
        self._blocked.add(site)
        if site == "chatgpt" and host == "accounts.google.com":
            self._chatgpt_google_blocked = True
            self._draft_request = None
            self._draft_notice.hide()
            self._set_status(site, "Google girişi ayrı tarayıcıda tamamlanır. "
                                   "Tarayıcıdaki oturum CORE’a aktarılmaz.")
            return
        destination = f" ({host})" if host else ""
        self._set_status(site, f"Yönlendirme CORE içinde açılamadı{destination}. "
                               "Hesap girişini tarayıcıda deneyebilirsin.")

    def _open_chatgpt_login(self):
        if self._site == "chatgpt" and (entry := self._views.get("chatgpt")):
            self._draft_request = None
            self._draft_notice.hide()
            entry[0].setUrl(QUrl("https://chatgpt.com/auth/login"))

    def _loading_changed(self, site, info):
        status = info.status()
        state = QWebEngineLoadingInfo.LoadStatus
        if status == state.LoadStartedStatus:
            if site == "chatgpt":
                self._chatgpt_google_blocked = False
            self._failed.discard(site)
            self._blocked.discard(site)
            self._set_status(site, "Yükleniyor…")
        elif status == state.LoadSucceededStatus:
            self._failed.discard(site)
            if site not in self._blocked:
                self._set_status(site, "")
        elif status == state.LoadFailedStatus:
            self._failed.add(site)
            if site in self._blocked:
                self._set_status(site, self._views[site][1])
                return
            domain = info.errorDomain().name
            messages = {
                "DnsErrorDomain": "Site adresi çözümlenemedi. İnternet ve DNS bağlantısını kontrol et.",
                "ConnectionErrorDomain": "Siteye bağlantı kurulamadı. Aynı adresi tarayıcıda dene.",
                "CertificateErrorDomain": "Sitenin güvenli bağlantısı doğrulanamadı.",
                "HttpErrorDomain": "Site web isteğini tamamlayamadı.",
                "HttpStatusCodeDomain": "Site web isteğini tamamlayamadı.",
            }
            message = messages.get(domain, "Site CORE içinde yüklenemedi.")
            self._set_status(site, f"{message} Kod: {info.errorCode()}")

    def _reload(self):
        entry = self._views.get(self._site)
        if entry:
            view = entry[0]
            if self._site in self._failed or self._site in self._blocked or not permitted_url(view.url(), self._site):
                view.setUrl(QUrl(SITES[self._site][1]))
            else:
                view.reload()

    def _copy_address(self):
        if self._site:
            QApplication.clipboard().setText(SITES[self._site][1])
            self._show_draft_notice("Adres kopyalandı. Tarayıcının adres çubuğuna yapıştır.")

    def _release_profiles(self):
        # main.py exits with os._exit after the Qt loop. Destroy disk profiles
        # while Qt is still alive so Chromium can flush their data.
        self._draft_request = None
        for view, _ in self._views.values():
            profile = view.page().profile()
            sip.delete(view)
            sip.delete(profile)
        self._views.clear()

    def _open_external(self, *, edge=False, login=False):
        if not self._site:
            return
        if open_in_browser(self._site, edge=edge, login=login):
            self._show_draft_notice("Adres tarayıcıya iletildi. Açılmazsa adresi kopyalayıp tarayıcıya yapıştır.")
        else:
            self._show_draft_notice("Tarayıcı başlatılamadı. Adresi kopyalayıp tarayıcıya yapıştır.")
