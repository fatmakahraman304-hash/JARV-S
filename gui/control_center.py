"""gui/control_center.py — the Control Centre: Jarvis's network and live activity.

Left, the network: the reactor core in the middle, the five capabilities on an
inner ring (voice, chat, web, files, memory) and the apps and tools Jarvis
drives on the outer ring. A node lights up, with a count, once something in
this session has gone through it; its link to the core glows and carries a
pulse towards the node whenever it is used. Click a node to filter the feed to
it; click the core to unmute and talk.

Right, the live activity feed: every action Jarvis takes, as it happens, read
from core.activity. Failures and unconfirmed results are shown as what they
are, never as successes.

Everything is painted with QPainter at the screen's own resolution, colours
come from the C palette, and the widget only animates while it is visible.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPen,
                         QRadialGradient)
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from core import activity
from gui.style import btn_css, px_font, with_alpha
from gui.theme import C, qcol
from gui.widgets import paint_icon

try:
    from gui.reactor import Reactor3D
except Exception:                     # pragma: no cover — never fatal
    Reactor3D = None

_ICON_OF = {k: icon for k, _l, icon, _r in activity.NODES}
_STATUS_COL = {"fail": "RED", "warn": "ACC", "ok": "TEXT", "info": "TEXT"}


def _ago(ts: float) -> str:
    d = max(0, int(time.time() - ts))
    if d < 5:
        return "şimdi"
    if d < 60:
        return f"{d} sn"
    if d < 3600:
        return f"{d // 60} dk"
    return f"{d // 3600} sa"


class NetworkCanvas(QWidget):
    """The network: core, rings of nodes, glowing links and travelling pulses."""

    node_clicked = pyqtSignal(str)     # node key, or "" to clear the filter
    core_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(520, 420)
        self._reactor = Reactor3D() if Reactor3D is not None else None
        self._pos: dict[str, QPointF] = {}
        self._core = QPointF(0, 0)
        self._core_r = 60.0
        self._hover = ""
        self._filter = ""
        self._counts: dict[str, int] = {}
        self._hits: dict[str, float] = {}
        self._caption = ""
        self._t = 0.0

    # ── data ──────────────────────────────────────────────────────────────────
    def set_data(self, counts, hits, caption: str) -> None:
        self._counts, self._hits, self._caption = counts, hits, caption

    def set_filter(self, key: str) -> None:
        self._filter = key
        self.update()

    def advance(self, dt: float, speaking: bool = False, thinking: bool = False,
                muted: bool = False) -> None:
        self._t += dt
        if self._reactor is not None:
            self._reactor.step(dt, speaking, thinking, muted)
        self.update()

    # ── geometry ──────────────────────────────────────────────────────────────
    def _layout(self) -> None:
        W, H = self.width(), self.height()
        cx, cy = W / 2, H * 0.47
        self._core = QPointF(cx, cy)
        m = min(W, H)
        self._core_r = m * 0.11
        inner = [k for k, _l, _i, ring in activity.NODES if ring == 0]
        outer = [k for k, _l, _i, ring in activity.NODES if ring == 1]
        r1x, r1y = m * 0.27, m * 0.25
        r2x, r2y = W * 0.42, H * 0.38
        self._pos = {}
        for i, k in enumerate(inner):
            a = -math.pi / 2 + i * 2 * math.pi / len(inner) + 0.35
            self._pos[k] = QPointF(cx + math.cos(a) * r1x, cy + math.sin(a) * r1y)
        for i, k in enumerate(outer):
            a = -math.pi / 2 + i * 2 * math.pi / len(outer)
            self._pos[k] = QPointF(cx + math.cos(a) * r2x, cy + math.sin(a) * r2y)

    def _node_at(self, pt: QPointF) -> str:
        for k, c in self._pos.items():
            if (pt.x() - c.x()) ** 2 + (pt.y() - c.y()) ** 2 <= 26 ** 2:
                return k
        return ""

    # ── input ─────────────────────────────────────────────────────────────────
    def mouseMoveEvent(self, e):
        k = self._node_at(e.position())
        if k != self._hover:
            self._hover = k
            self.setCursor(Qt.CursorShape.PointingHandCursor if k else Qt.CursorShape.ArrowCursor)
            if k:
                n = self._counts.get(k, 0)
                self.setToolTip(f"{activity.NODE_LABEL[k]} · bu oturumda {n} işlem")
            else:
                self.setToolTip("")

    def mousePressEvent(self, e):
        pt = e.position()
        k = self._node_at(pt)
        if k:
            self.node_clicked.emit("" if k == self._filter else k)
            return
        dx, dy = pt.x() - self._core.x(), pt.y() - self._core.y()
        if dx * dx + dy * dy <= (self._core_r * 1.1) ** 2:
            self.core_clicked.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()

    # ── paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if not self._pos:
            self._layout()
        now = time.time()

        # panel ground with a dot grid
        rect = QRectF(0.5, 0.5, W - 1, H - 1)
        p.setPen(QPen(with_alpha(C.PRI, 0.18), 1))
        p.setBrush(QBrush(with_alpha(C.DARK, 0.92)))
        p.drawRoundedRect(rect, 22, 22)
        p.setPen(Qt.PenStyle.NoPen)
        step = 28.0
        y = 20.0
        while y < H - 10:
            x = 20.0
            while x < W - 10:
                d = math.hypot(x - self._core.x(), y - self._core.y()) / max(W, H)
                p.setBrush(QBrush(with_alpha(C.PRI, max(0.0, 0.14 - d * 0.16))))
                p.drawEllipse(QPointF(x, y), 0.9, 0.9)
                x += step
            y += step

        # header: title, active links
        active = sum(1 for k, *_r in activity.NODES if self._counts.get(k))
        p.setFont(px_font(11, QFont.Weight.DemiBold, spacing=2.4))
        p.setPen(QPen(qcol(C.TEXT_DIM)))
        p.drawText(QRectF(24, 18, 300, 18), Qt.AlignmentFlag.AlignVCenter, "SİNİR AĞI")
        p.setFont(px_font(13))
        p.setPen(QPen(qcol(C.TEXT_MED)))
        p.drawText(QRectF(24, 38, 400, 20), Qt.AlignmentFlag.AlignVCenter,
                   f"{active} / {len(activity.NODES)} bağlantı bu oturumda aktif")

        # mesh: faint links between neighbouring outer nodes
        outer = [k for k, _l, _i, ring in activity.NODES if ring == 1]
        p.setPen(QPen(with_alpha(C.TEXT_DIM, 0.10), 1, Qt.PenStyle.DashLine))
        for i, k in enumerate(outer):
            a, b = self._pos[k], self._pos[outer[(i + 1) % len(outer)]]
            p.drawLine(a, b)

        # links from the core
        core = self._core
        for k, _label, _icon, ring in activity.NODES:
            c = self._pos[k]
            n = self._counts.get(k, 0)
            dim = self._filter and self._filter != k
            if n:
                g = QLinearGradient(core, c)
                g.setColorAt(0.0, with_alpha(C.PRI, 0.10 if dim else 0.55))
                g.setColorAt(1.0, with_alpha(C.ACC, 0.15 if dim else 0.85))
                p.setPen(QPen(QBrush(g), 1.6))
            else:
                p.setPen(QPen(with_alpha(C.TEXT_DIM, 0.12), 1, Qt.PenStyle.DashLine))
            p.drawLine(core, c)
            if n and not dim:
                # a slow steady flow on every active link, and a bright burst
                # travelling outwards for a few seconds after each use
                p.setPen(Qt.PenStyle.NoPen)
                recent = now - self._hits.get(k, 0) < 3.0
                for j in range(3 if recent else 1):
                    u = ((self._t * (0.9 if recent else 0.25)) + j / 3.0 + hash(k) % 97 / 97) % 1.0
                    x = core.x() + (c.x() - core.x()) * u
                    yy = core.y() + (c.y() - core.y()) * u
                    rr = 6.0 if recent else 3.5
                    pg = QRadialGradient(x, yy, rr)
                    pg.setColorAt(0.0, with_alpha(C.WHITE if recent else C.ACC, 0.95))
                    pg.setColorAt(1.0, with_alpha(C.PRI, 0.0))
                    p.setBrush(QBrush(pg))
                    p.drawEllipse(QPointF(x, yy), rr, rr)

        # the core
        if self._reactor is not None:
            self._reactor.paint(p, core.x(), core.y(), self._core_r, qcol(C.PRI), qcol(C.ACC),
                                qcol(C.WHITE), 0.0, False, "")
        else:
            cg = QRadialGradient(core, self._core_r)
            cg.setColorAt(0.0, qcol(C.WHITE))
            cg.setColorAt(0.3, qcol(C.ACC))
            cg.setColorAt(1.0, with_alpha(C.PRI, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(cg))
            p.drawEllipse(core, self._core_r, self._core_r)

        # nodes
        for k, label, icon, ring in activity.NODES:
            c = self._pos[k]
            n = self._counts.get(k, 0)
            hot = k == self._hover or k == self._filter
            dim = bool(self._filter) and self._filter != k
            r = 22.0 if ring == 0 else 20.0
            on = n > 0
            base = qcol(C.PRI) if on else qcol(C.TEXT_DIM)
            alpha = 0.35 if dim else 1.0
            if on and not dim:
                gl = QRadialGradient(c, r * 2.0)
                gl.setColorAt(0.0, with_alpha(C.PRI, 0.30 if hot else 0.18))
                gl.setColorAt(1.0, with_alpha(C.PRI, 0.0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(gl))
                p.drawEllipse(c, r * 2.0, r * 2.0)
            p.setBrush(QBrush(with_alpha(C.PANEL2, 0.95)))
            p.setPen(QPen(with_alpha(base, (0.95 if hot else 0.7 if on else 0.35) * alpha), 1.4))
            p.drawEllipse(c, r, r)
            icol = qcol(C.WHITE) if on else qcol(C.TEXT_DIM)
            icol.setAlphaF(alpha if on else 0.6 * alpha)
            paint_icon(p, icon, QRectF(c.x() - r * 0.5, c.y() - r * 0.5, r, r), icol)
            p.setFont(px_font(11, QFont.Weight.Medium))
            p.setPen(QPen(with_alpha(C.TEXT if on else C.TEXT_DIM, alpha)))
            p.drawText(QRectF(c.x() - 70, c.y() + r + 4, 140, 16), Qt.AlignmentFlag.AlignHCenter, label)
            if n:
                txt = str(n) if n < 100 else "99+"
                p.setFont(px_font(10, QFont.Weight.Bold))
                bw = max(18.0, p.fontMetrics().horizontalAdvance(txt) + 9)
                br = QRectF(c.x() + r * 0.45, c.y() - r - 4, bw, 18)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(with_alpha(C.PRI, alpha)))
                p.drawRoundedRect(br, 9, 9)
                p.setPen(QPen(qcol(C.DARK)))
                p.drawText(br, Qt.AlignmentFlag.AlignCenter, txt)

        # caption: the latest thing Jarvis said, under the network
        if self._caption:
            p.setFont(px_font(14))
            p.setPen(QPen(qcol(C.TEXT_MED)))
            fm = p.fontMetrics()
            text = fm.elidedText(self._caption, Qt.TextElideMode.ElideRight, int(W - 80))
            p.drawText(QRectF(40, H - 52, W - 80, 22), Qt.AlignmentFlag.AlignCenter, text)
        p.setFont(px_font(11))
        p.setPen(QPen(qcol(C.TEXT_DIM)))
        p.drawText(QRectF(40, H - 28, W - 80, 16), Qt.AlignmentFlag.AlignCenter,
                   "Konuşmak için çekirdeğe dokun ya da aşağıya bir görev yaz")
        p.end()


class ActivityFeed(QWidget):
    """Every action Jarvis takes, newest first. Scrolls with the wheel."""

    ROW = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self._events: list = []
        self._filter = ""
        self._scroll = 0.0

    def set_events(self, events) -> None:
        self._events = list(events)
        self.update()

    def set_filter(self, key: str) -> None:
        self._filter = key
        self._scroll = 0.0
        self.update()

    def _shown(self):
        ev = [e for e in reversed(self._events) if not self._filter or e.node == self._filter]
        return ev

    def wheelEvent(self, e):
        rows = len(self._shown())
        room = max(0.0, rows * self.ROW - (self.height() - 84))
        self._scroll = max(0.0, min(room, self._scroll - e.angleDelta().y() / 2))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        p.setPen(QPen(with_alpha(C.PRI, 0.18), 1))
        p.setBrush(QBrush(with_alpha(C.DARK, 0.92)))
        p.drawRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 22, 22)

        title = "Canlı etkinlik"
        if self._filter:
            title += f" · {activity.NODE_LABEL.get(self._filter, '')}"
        p.setFont(px_font(15, QFont.Weight.DemiBold))
        p.setPen(QPen(qcol(C.WHITE)))
        p.drawText(QRectF(22, 16, W - 44, 22), Qt.AlignmentFlag.AlignVCenter, title)
        p.setFont(px_font(11))
        p.setPen(QPen(qcol(C.TEXT_DIM)))
        p.drawText(QRectF(22, 40, W - 44, 18), Qt.AlignmentFlag.AlignVCenter,
                   "Jarvis'in yaptığı her işlem, anında.")
        p.setPen(QPen(with_alpha(C.PRI, 0.18), 1))
        p.drawLine(QPointF(18, 68), QPointF(W - 18, 68))

        shown = self._shown()
        p.save()
        p.setClipRect(QRectF(0, 72, W, H - 80))
        if not shown:
            p.setFont(px_font(12))
            p.setPen(QPen(qcol(C.TEXT_DIM)))
            p.drawText(QRectF(22, 90, W - 44, 60), int(Qt.AlignmentFlag.AlignLeft.value | Qt.TextFlag.TextWordWrap.value),
                       "Henüz bir işlem yok. Jarvis'e bir şey söyle ya da yaz; yaptığı her şey burada görünür.")
        y = 78 - self._scroll
        for e in shown:
            if y > H:
                break
            if y + self.ROW >= 72:
                ic = QRectF(20, y + 8, 30, 30)
                col = qcol(getattr(C, _STATUS_COL.get(e.status, "TEXT")))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(with_alpha(C.PRI, 0.12)))
                p.drawRoundedRect(ic, 9, 9)
                paint_icon(p, _ICON_OF.get(e.node, "grid"), ic.adjusted(8, 8, -8, -8), qcol(C.PRI))
                p.setFont(px_font(12, QFont.Weight.Medium))
                fm = p.fontMetrics()
                node = activity.NODE_LABEL.get(e.node, "")
                ago = _ago(e.ts)
                right = fm.horizontalAdvance(ago) + 16
                text = fm.elidedText(e.text, Qt.TextElideMode.ElideRight, int(W - 66 - right))
                p.setPen(QPen(col))
                p.drawText(QRectF(60, y + 7, W - 66 - right, 18), Qt.AlignmentFlag.AlignVCenter, text)
                p.setFont(px_font(10))
                p.setPen(QPen(qcol(C.TEXT_DIM)))
                p.drawText(QRectF(60, y + 25, W - 80, 14), Qt.AlignmentFlag.AlignVCenter, node)
                p.drawText(QRectF(W - right - 12, y + 7, right, 18),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, ago)
            y += self.ROW
        p.restore()
        p.end()


class ControlCenter(QWidget):
    """The Control Centre page: network on the left, live activity on the right."""

    back_requested = pyqtSignal()
    talk_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        back = QPushButton("‹  CORE")
        back.setStyleSheet(btn_css("dim", align="center"))
        back.setFixedSize(96, 32)
        back.setFont(px_font(11, QFont.Weight.DemiBold, spacing=1.5))
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested.emit)
        bar.addWidget(back)
        bar.addStretch()
        self._live = QPushButton("●  CANLI")
        self._live.setEnabled(False)
        self._live.setFixedSize(96, 32)
        self._live.setFont(px_font(11, QFont.Weight.DemiBold, spacing=1.5))
        self._live.setStyleSheet(
            f"QPushButton {{ color: {C.PRI}; background: {C.PRI_GHO}; "
            f"border: 1px solid {C.BORDER_B}; border-radius: 16px; }}")
        bar.addWidget(self._live)
        self._feed_btn = QPushButton("Etkinliği gizle")
        self._feed_btn.setStyleSheet(btn_css("dim", align="center"))
        self._feed_btn.setFixedSize(132, 32)
        self._feed_btn.setFont(px_font(11, QFont.Weight.DemiBold))
        self._feed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._feed_btn.clicked.connect(self._toggle_feed)
        bar.addWidget(self._feed_btn)
        root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.network = NetworkCanvas()
        self.feed = ActivityFeed()
        self.feed.setFixedWidth(380)
        body.addWidget(self.network, 1)
        body.addWidget(self.feed)
        root.addLayout(body, 1)

        self.network.node_clicked.connect(self._filter)
        self.network.core_clicked.connect(self.talk_requested.emit)

        self._seq = -1
        self._last = time.monotonic()
        self._state = ("", False, False)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)

    # the HUD state, so the core turns like the main one
    def set_state(self, state: str, speaking: bool, muted: bool) -> None:
        self._state = (str(state or ""), bool(speaking), bool(muted))

    def _filter(self, key: str) -> None:
        self.network.set_filter(key)
        self.feed.set_filter(key)

    def _toggle_feed(self) -> None:
        show = not self.feed.isVisible()
        self.feed.setVisible(show)
        self._feed_btn.setText("Etkinliği gizle" if show else "Etkinliği göster")

    def showEvent(self, e):
        super().showEvent(e)
        self._last = time.monotonic()
        self._tmr.start(33)
        self._refresh(force=True)

    def hideEvent(self, e):
        super().hideEvent(e)
        self._tmr.stop()

    def _refresh(self, force: bool = False) -> None:
        seq = activity.last_seq()
        if force or seq != self._seq:
            self._seq = seq
            events = activity.recent(200)
            caption = ""
            for e in reversed(events):
                if e.node == "voice" and "yanıtladı:" in e.text:
                    caption = e.text.split("yanıtladı:", 1)[1].strip()
                    break
            self.network.set_data(activity.counts(), activity.last_hit(), caption)
            self.feed.set_events(events)
        else:
            self.feed.update()      # keeps the "x sn" ages fresh

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = min(0.1, now - self._last), now
        state, speaking, muted = self._state
        self._refresh()
        self.network.advance(dt, speaking, state in ("THINKING", "PROCESSING"), muted)
