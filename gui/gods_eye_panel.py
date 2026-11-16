"""Run the local God's Eye View app inside JARVIS's center panel."""

import json
import socket
import time
from collections import deque

from PyQt6.QtCore import QProcess, QProcessEnvironment, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkRequest
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core import gods_eye
from gui.theme import C

try:
    from PyQt6.QtWebEngineCore import QWebEnginePage
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEnginePage = QWebEngineView = None


_RUNNER = "window.__godsEyeView?.voiceCommands?.runner"
_DISPATCH = """
(({name, args}) => {
    const run = window.__godsEyeView?.voiceCommands?.runner;
    if (typeof run !== "function") return false;
    const controller = new AbortController();
    const task = {controller, result: null};
    window.__jarvisGevTask = task;
    Promise.resolve().then(() => run(name, args, {
        signal: controller.signal, origin: "programmatic"
    })).then(value => {
        if (value == null) {
            task.result = JSON.stringify({error: "Upstream command returned no result."});
            return;
        }
        const raw = JSON.stringify(value);
        task.result = raw.length <= 10000 ? raw : JSON.stringify({
            ok: value.ok, error: value.error, summary: value.summary,
            note: "Large result; see the map for full details."
        });
    }).catch(error => {
        task.result = JSON.stringify({error: String(error.message || error)});
    });
    return true;
})
"""


if QWebEnginePage is not None:
    class GlobePage(QWebEnginePage):
        port = 0

        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            return not is_main_frame or self.is_globe(url)

        def is_globe(self, url):
            return (url.scheme() == "http" and url.host() == "127.0.0.1"
                    and url.port() == self.port and not url.userInfo())


class GodsEyePanel(QWidget):
    back_requested = pyqtSignal()
    result = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = deque()
        self._active = None
        self._port = 0
        self._startup_deadline = 0
        self._command_deadline = 0
        self._epoch = 0
        self._loaded = False
        self._ready_confirmed = False
        self._navigation_started = False
        self._probe = None
        self._next_probe = 0
        self._stopping = False
        self._pending_js = False
        self._output = b""
        self._network = QNetworkAccessManager(self)
        self._network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self._server = QProcess(self)
        self._server.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._server.readyReadStandardOutput.connect(self._server_output)
        self._server.finished.connect(self._server_stopped)
        self._server.errorOccurred.connect(self._server_error)
        QApplication.instance().aboutToQuit.connect(self._stop)
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._tick)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("God's Eye View"))
        row.addStretch()
        back = QPushButton("CORE’a dön")
        back.clicked.connect(self.back_requested.emit)
        row.addWidget(back)
        layout.addLayout(row)
        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._view = None
        if QWebEngineView is not None:
            self._view = QWebEngineView(self)
            self._view.setPage(GlobePage(self._view))
            self._view.page().setBackgroundColor(QColor(C.BG))
            self._view.loadStarted.connect(self._page_loading)
            self._view.loadFinished.connect(self._page_loaded)
            self._view.page().renderProcessTerminated.connect(self._renderer_stopped)
            layout.addWidget(self._view, 1)

    def submit(self, payload, reply):
        if self._view is None:
            self._finish(reply, "Gömülü harita için PyQt6-WebEngine gerekli.")
            return
        if len(self._queue) >= 12:
            self._finish(reply, "God's Eye View komut sırası dolu.")
            return
        if self._server.state() == QProcess.ProcessState.NotRunning:
            try:
                self._start()
            except (OSError, ValueError) as error:
                self._finish(reply, str(error))
                return
        self._queue.append((payload, reply))
        self._timer.start()

    def _start(self):
        gods_eye.read_catalog()
        node = gods_eye.executable("node")
        vite = gods_eye.ROOT / gods_eye.VITE
        if not node or not vite.is_file():
            raise ValueError(gods_eye.SETUP_HINT)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self._port = probe.getsockname()[1]
        self._loaded = False
        self._ready_confirmed = False
        self._navigation_started = False
        self._next_probe = 0
        self._stopping = False
        self._output = b""
        self._startup_deadline = time.monotonic() + 120
        self._view.page().port = self._port
        self._status.setText("Yerel harita başlatılıyor…")
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("GEV_ALLOWED_HOSTS", "")
        environment.insert("PINOKIO_SHARE_LOCAL", "0")
        environment.insert("PINOKIO_SHARE_CLOUDFLARE", "0")
        environment.insert("PINOKIO_SHARE_VAR", "")
        self._server.setProcessEnvironment(environment)
        self._server.setWorkingDirectory(str(gods_eye.ROOT))
        self._server.start(node, [str(vite), "--host", "127.0.0.1",
                                  "--port", str(self._port), "--strictPort"])

    def _server_output(self):
        self._output = (self._output + bytes(self._server.readAllStandardOutput()))[-6000:]

    def _probe_server(self, now):
        if (self._probe is not None or now < self._next_probe
                or self._server.state() != QProcess.ProcessState.Running):
            return
        self._next_probe = now + .6
        address = QUrl(f"http://127.0.0.1:{self._port}/")
        request = QNetworkRequest(address)
        request.setTransferTimeout(2000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        probe = self._probe = self._network.get(request)
        body = bytearray()

        def read():
            remaining = 32768 - len(body)
            body.extend(bytes(probe.read(remaining)))
            if probe.bytesAvailable():
                probe.abort()

        def finished():
            try:
                if self._probe is not probe:
                    return
                self._probe = None
                if self._stopping or self._server.state() != QProcess.ProcessState.Running:
                    return
                status = probe.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                if (probe.error() == probe.NetworkError.NoError and status == 200
                        and b"<title>God's Eye View</title>" in body
                        and b'/src/main.js' in body):
                    self._navigation_started = True
                    self._status.setText("Yerel servis hazır. Harita sayfası yükleniyor…")
                    self._view.setUrl(address)
            finally:
                probe.deleteLater()

        probe.readyRead.connect(read)
        probe.finished.connect(finished)

    def _stop(self):
        self._stopping = True
        if self._probe is not None:
            probe, self._probe = self._probe, None
            probe.abort()
        if self._server.state() != QProcess.ProcessState.NotRunning:
            self._server.kill()
            self._server.waitForFinished(1500)

    def _server_stopped(self, code, _status):
        if not self._stopping:
            self._fail_all(f"Yerel harita servisi kapandı (kod {code}). {gods_eye.SETUP_HINT}")

    def _server_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._fail_all("Yerel harita servisi başlatılamadı. " + gods_eye.SETUP_HINT)

    def _page_loading(self):
        self._loaded = False
        self._ready_confirmed = False
        self._startup_deadline = time.monotonic() + 120
        self._epoch += 1
        self._pending_js = False
        if self._active:
            _, reply = self._active
            self._active = None
            self._finish(reply, "Harita komutu sırasında sayfa yeniden yüklendi.")

    def _page_loaded(self, success):
        self._loaded = success
        if success:
            self._status.setText("Harita sahnesi yükleniyor…")
        else:
            self._fail_all("Yerel harita sayfası yüklenemedi.")
            self._stop()

    def _renderer_stopped(self, *_args):
        self._fail_all("Harita görüntüleyicisi durdu. WebEngine ve ekran kartı desteğini kontrol et.")
        self._stop()

    def _finish(self, reply, message):
        if reply is not None:
            reply.finish(message)
        self._status.setText(message[:180])
        self.result.emit(message)

    def _fail_all(self, message):
        self._epoch += 1
        self._pending_js = False
        self._loaded = False
        active, self._active = self._active, None
        queued, self._queue = self._queue, deque()
        if active and active[1] is not None:
            active[1].finish(message)
        for _, reply in queued:
            if reply is not None:
                reply.finish(message)
        self._timer.stop()
        self._finish(None, message)

    def _js(self, script, callback):
        epoch = self._epoch
        self._pending_js = True

        def receive(value):
            if epoch == self._epoch:
                self._pending_js = False
                callback(value)

        self._view.page().runJavaScript(script, receive)

    def _tick(self):
        if not self._queue and not self._active:
            self._timer.stop()
            return
        now = time.monotonic()
        if self._active and now >= self._command_deadline:
            _, reply = self._active
            self._active = None
            self._epoch += 1
            self._pending_js = False
            self._view.page().runJavaScript("window.__jarvisGevTask?.controller.abort()")
            self._finish(reply, "God's Eye View komutu zaman aşımına uğradı.")
            return
        if not self._ready_confirmed and now >= self._startup_deadline:
            message = ("Harita sayfası yanıt verdi, 3D sahne zamanında açılmadı. WebGL desteğini kontrol et."
                       if self._navigation_started else "Yerel Node.js servisi harita sayfasına yanıt vermedi.")
            self._fail_all(message)
            self._stop()
            return
        if not self._navigation_started:
            self._probe_server(now)
            return
        if self._pending_js or not self._loaded or not self._view.page().is_globe(self._view.url()):
            return
        if self._active:
            self._js("window.__jarvisGevTask?.result ?? null", self._result)
        else:
            self._js(f'typeof ({_RUNNER}) === "function"', self._ready)

    def _ready(self, ready):
        if not ready:
            return
        self._ready_confirmed = True
        if not self._queue:
            return
        payload, reply = self._queue.popleft()
        if payload.get("kind") == "open":
            self._finish(reply, "God's Eye View hazır.")
            return
        self._active = payload, reply
        self._command_deadline = time.monotonic() + 45
        encoded = json.dumps(json.dumps(payload, allow_nan=False))
        self._js(f"{_DISPATCH}(JSON.parse({encoded}))", self._accepted)

    def _accepted(self, accepted):
        if accepted is not True and self._active:
            _, reply = self._active
            self._active = None
            self._finish(reply, "God's Eye View komut motoru isteği kabul etmedi.")

    def _result(self, raw):
        if not raw or not self._active:
            return
        payload, reply = self._active
        self._active = None
        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            self._finish(reply, "Harita geçerli bir komut sonucu döndürmedi.")
            return
        status = "başarısız" if isinstance(result, dict) and (
            result.get("ok") is False or result.get("error")
        ) else "sonuç"
        self._finish(reply, f"{payload['name']} [{status}] " + json.dumps(result, ensure_ascii=False))
