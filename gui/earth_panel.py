"""Lazy, isolated 3D Earth. No Python bridge, credentials or camera permission."""
from __future__ import annotations

import json
import math
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit

EARTH_ROOT = Path(__file__).resolve().parent.parent / "web" / "earth"
REMOTE_HOSTS = frozenset({"cesium.com", "services.arcgisonline.com", "tile.openstreetmap.org"})


def allowed_resource(url: QUrl) -> bool:
    if url.scheme() in ("data", "blob", "qrc"):
        return True
    if url.scheme() == "https":
        return url.host() in REMOTE_HOSTS and url.port(443) == 443 and not url.userInfo()
    if url.isLocalFile():
        return Path(url.toLocalFile()).resolve() in {
            EARTH_ROOT / name for name in ("index.html", "earth.js", "earth.css")
        }
    return False


def destination(lat, lon, zoom=12):
    lat, lon, zoom = float(lat), float(lon), float(zoom)
    if not all(math.isfinite(v) for v in (lat, lon, zoom)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Geçersiz harita koordinatı")
    return {"lat": lat, "lon": lon, "height": max(120.0, min(24000000.0, 40075000 / 2 ** max(0, min(20, zoom))))}


class EarthPanel(QWidget):
    back_requested = pyqtSignal()
    normal_map_requested = pyqtSignal()
    _search_done = pyqtSignal(int, list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = None
        self._loaded = False
        self._pending = None
        self._search_generation = 0
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("FRIDAY / DÜNYA"))
        self.query = QLineEdit()
        self.query.setPlaceholderText("Şehir, sokak veya adres ara")
        self.query.setAccessibleName("Dünya üzerinde yer ara")
        self.query.setMaxLength(500)
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)
        self.search_button = QPushButton("Ara")
        self.search_button.clicked.connect(self.search)
        row.addWidget(self.search_button)
        normal = QPushButton("Normal harita")
        normal.clicked.connect(self.normal_map_requested)
        row.addWidget(normal)
        panorama = QPushButton("Sokak panoraması ↗")
        panorama.setToolTip("Google Maps’i ayrı tarayıcıda açar; görüntü kapsaması bölgeye bağlıdır.")
        panorama.clicked.connect(self.open_panorama)
        row.addWidget(panorama)
        back = QPushButton("CORE’a dön")
        back.clicked.connect(self.back_requested)
        row.addWidget(back)
        layout.addLayout(row)
        self.status = QLabel("Döndür: sürükle · Yakınlaş: tekerlek · Eğ: sağ tuşla sürükle")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self._search_done.connect(self._finish_search)
        try:
            from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            class Resources(QWebEngineUrlRequestInterceptor):
                def interceptRequest(self, request):
                    request.block(not allowed_resource(request.requestUrl()))

            class Page(QWebEnginePage):
                def acceptNavigationRequest(self, url, kind, main_frame):
                    return main_frame and url.isLocalFile() and Path(url.toLocalFile()).resolve() == EARTH_ROOT / "index.html"

                def chooseFiles(self, mode, old_files, accepted_types):
                    return []

                def createWindow(self, kind):
                    return None

            self.profile = QWebEngineProfile(self)  # off the record, no login cookies
            self.interceptor = Resources(self.profile)
            self.profile.setUrlRequestInterceptor(self.interceptor)
            self.view = QWebEngineView(self)
            page = Page(self.profile, self.view)
            options = QWebEngineSettings.WebAttribute
            page.settings().setAttribute(options.LocalContentCanAccessRemoteUrls, True)
            # Only the three bundled files pass the request interceptor.
            page.settings().setAttribute(options.LocalContentCanAccessFileUrls, True)
            for option in (options.JavascriptCanOpenWindows,
                           options.LocalStorageEnabled, options.ScreenCaptureEnabled):
                page.settings().setAttribute(option, False)
            page.featurePermissionRequested.connect(lambda origin, feature: page.setFeaturePermission(
                origin, feature, QWebEnginePage.PermissionPolicy.PermissionDeniedByUser))
            self.view.setPage(page)
            self.view.loadFinished.connect(self._ready)
            layout.addWidget(self.view, 1)
            self.view.load(QUrl.fromLocalFile(str(EARTH_ROOT / "index.html")))
        except ImportError:
            self.status.setText("3D dünya için PyQt6-WebEngine gerekiyor. Normal harita çalışmaya devam eder.")

    def open_panorama(self):
        if not self.view or not self._loaded:
            return
        def open_point(point):
            if not isinstance(point, dict):
                self.status.setText("Önce haritada bir yere yakınlaşın.")
                return
            try:
                p = destination(point["lat"], point["lon"])
            except (KeyError, TypeError, ValueError):
                return
            from PyQt6.QtGui import QDesktopServices
            url = QUrl("https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=" + str(p["lat"]) + "," + str(p["lon"]))
            if not QDesktopServices.openUrl(url):
                self.status.setText("Sokak panoraması tarayıcıda açılamadı.")
        self.view.page().runJavaScript("window.fridayEarth?.centre()", open_point)

    def _ready(self, ok):
        self._loaded = ok
        if ok and self._pending is not None:
            self.go_to(**self._pending)
        elif not ok:
            self.status.setText("Dünya ekranı yüklenemedi. Normal haritayı kullanabilirsiniz.")

    def go_to(self, lat, lon, zoom=12):
        point = destination(lat, lon, zoom)
        self._pending = dict(lat=lat, lon=lon, zoom=zoom)
        if self._loaded and self.view:
            self.view.page().runJavaScript("window.fridayEarth?.goTo(" + json.dumps(point) + ")")

    def search(self):
        query = self.query.text().strip()
        if not query or not self.search_button.isEnabled():
            return
        self._search_generation += 1
        generation = self._search_generation
        self.search_button.setEnabled(False)
        self.status.setText("Yer aranıyor…")

        def work():
            from plugins.normal_map import search
            try:
                self._search_done.emit(generation, search(query), "")
            except Exception:
                self._search_done.emit(generation, [], "Yer arama servisine ulaşılamadı; mevcut görünüm korundu.")
        threading.Thread(target=work, daemon=True, name="friday-earth-search").start()

    def _finish_search(self, generation, places, error):
        if generation != self._search_generation:
            return
        self.search_button.setEnabled(True)
        if len(places) == 1:
            p = places[0]
            self.go_to(p["lat"], p["lon"], p.get("zoom", 12))
            self.status.setText(p["name"])
        elif places:
            from PyQt6.QtWidgets import QInputDialog
            names = [str(p["name"]) for p in places]
            name, ok = QInputDialog.getItem(self, "Yer seç", "Eşleşen yerler", names, 0, False)
            if ok:
                p = places[names.index(name)]
                self.go_to(p["lat"], p["lon"], p.get("zoom", 12))
                self.status.setText(name)
            else:
                self.status.setText("Yer seçimi iptal edildi.")
        else:
            self.status.setText(error or "Yer bulunamadı; şehir veya ülkeyi de belirtin.")

    def showEvent(self, event):
        super().showEvent(event)
        if self.view:
            self.view.page().runJavaScript("window.fridayEarth?.setActive(true)")

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.view:
            self.view.page().runJavaScript("window.fridayEarth?.setActive(false)")
