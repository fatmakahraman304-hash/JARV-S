"""Explicit, user-operated platform connection dialog."""

import shlex
import threading

from PyQt6.QtCore import QProcess, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from core.platform_authorization import (
    AuthorizationError, GITHUB_LOGIN, MODEL_PLATFORMS, github_access, verify_model,
)
from core.social_sites import SITES
from gui.style import btn_css
from memory import config_manager as cfg


class AuthorizationDialog(QDialog):
    verified = pyqtSignal(bool, str)

    def __init__(self, site, parent):
        super().__init__(parent)
        self.site = site
        self.setWindowTitle(SITES[site][0] + " · JARVIS yetkisi")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        self.layout_box = layout
        self.process = None
        self._device_output = ""
        self.pending = None
        if site == "github":
            self._github()
        else:
            self._model()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.check = self._button(
            "Yetkiyi kontrol et" if site == "github" else "Doğrula ve kaydet", self._check
        )
        self.verified.connect(self._verified)

    def _description(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        self.layout_box.addWidget(label)

    def _button(self, text, action):
        button = QPushButton(text)
        button.setStyleSheet(btn_css("dim", align="center"))
        button.clicked.connect(action)
        self.layout_box.addWidget(button)
        return button

    def _github(self):
        self._description("GitHub CLI üzerinden tarayıcıda izin ver. JARVIS, proje deposuna yazma yetkisini kontrol eder.")
        self._button("GitHub’da giriş yap", self._login_github)
        self._button("Terminal komutunu kopyala",
                     lambda: QApplication.clipboard().setText(shlex.join(GITHUB_LOGIN)))
        self.device = QLabel()
        self.device.setTextFormat(Qt.TextFormat.PlainText)
        self.device.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.device.setWordWrap(True)
        self.layout_box.addWidget(self.device)
        self._button("GitHub cihaz onay sayfası",
                     lambda: QDesktopServices.openUrl(QUrl("https://github.com/login/device")))

    def _model(self):
        self.provider, _, key_url = MODEL_PLATFORMS[self.site]
        saved = cfg.get_provider_config(self.provider)
        self._description("Resmi API anahtarını ve hesabında kullanabildiğin model kimliğini gir. Doğrulama kısa bir model isteği gönderir.")
        self._button("API anahtarı sayfası", lambda: QDesktopServices.openUrl(QUrl(key_url)))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("API anahtarı")
        self.key.setAccessibleName("API anahtarı")
        self.layout_box.addWidget(self.key)
        self.model = QLineEdit(str(saved.get("model") or ""))
        self.model.setAccessibleName("Model kimliği")
        self.model.setPlaceholderText("Model kimliği")
        self.layout_box.addWidget(self.model)
        self.coding = QCheckBox("Kod geliştirmede kullan")
        self.background = QCheckBox("Arka plan isteklerinde öncelikli kullan")
        self.coding.setChecked(cfg.get_coding_provider() == self.provider)
        self.background.setChecked(cfg.get_sidecar_provider() == self.provider)
        self.layout_box.addWidget(self.coding)
        self.layout_box.addWidget(self.background)
        if self._saved_key():
            self._description("Bu sağlayıcının anahtarı kayıtlı. Yenilemek istemiyorsan anahtar alanını boş bırak.")

    def _saved_key(self):
        saved = cfg.get_provider_config(self.provider)
        base = str(saved.get("base_url") or "").rstrip("/")
        return saved.get("api_key", "") if base == MODEL_PLATFORMS[self.site][1] else ""

    def _login_github(self):
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.device.clear()
        self._device_output = ""
        if self.process is not None:
            self.process.deleteLater()
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_device_code)
        self.process.finished.connect(self._login_finished)
        self.process.errorOccurred.connect(
            lambda _: self.status.setText("GitHub CLI başlatılamadı. gh kurulumunu kontrol et.")
        )
        self.status.setText("Tarayıcıdaki GitHub onayını tamamla.")
        self.process.start(GITHUB_LOGIN[0], list(GITHUB_LOGIN[1:]))

    def _read_device_code(self):
        import re

        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        self._device_output = (self._device_output + output)[-4096:]
        if codes := re.findall(r"\b[A-Z0-9]{4}-[A-Z0-9]{4}\b", self._device_output):
            self.device.setText("GitHub cihaz kodu  " + codes[-1])

    def _login_finished(self, code, _status):
        self.device.clear()
        if code == 0:
            self._check()
        else:
            self.status.setText("Giriş tamamlanamadı. Terminal komutuyla tekrar deneyebilirsin.")

    def _check(self):
        if not self.check.isEnabled():
            return
        if self.site != "github":
            key = self.key.text().strip() or self._saved_key()
            model = self.model.text().strip()
            if not key or not model or "\n" in key or "\r" in key:
                self.status.setText("API anahtarı ve model kimliği gerekli.")
                return
            self.pending = (key, model, self.coding.isChecked(), self.background.isChecked())
        pending = self.pending
        self.check.setEnabled(False)
        self.status.setText("Yetki doğrulanıyor…")

        def worker():
            try:
                if self.site == "github":
                    github_access()
                else:
                    verify_model(self.site, pending[0], pending[1])
                self.verified.emit(True, "")
            except AuthorizationError as exc:
                self.verified.emit(False, str(exc))
            except Exception:
                self.verified.emit(False, "Bağlantı doğrulanamadı. İnterneti ve sağlayıcı ayarlarını kontrol et.")

        try:
            threading.Thread(target=worker, daemon=True, name="jarvis-platform-auth").start()
        except RuntimeError:
            self._verified(False, "Doğrulama başlatılamadı.")

    def _verified(self, ok, message):
        self.check.setEnabled(True)
        pending, self.pending = self.pending, None
        if not ok:
            self.status.setText(message)
            return
        if self.site == "github":
            self.status.setText("GitHub erişimi ve JARVIS deposuna yazma yetkisi doğrulandı.")
            return
        if pending is None:
            return
        key, model, coding, background = pending
        try:
            cfg.save_authorized_model(
                self.provider, key, model, MODEL_PLATFORMS[self.site][1],
                coding=coding, background=background,
            )
        except OSError:
            self.status.setText("Bağlantı doğrulandı fakat yerel ayarlar kaydedilemedi.")
            return
        self.key.clear()
        self.status.setText("Model erişimi doğrulandı ve kaydedildi.")
