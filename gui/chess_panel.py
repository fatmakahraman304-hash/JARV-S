"""gui/chess_panel.py — play chess against the assistant.

The board is painted with QPainter at the screen's own resolution: warm wood
squares, coordinates, the last move and a king in check lit in the theme's
orange, dots on the squares the selected piece can reach, and a short slide
when a piece moves. Pieces are the Unicode chess glyphs turned into outlined
paths, so they look the same in any font size.

Click a piece, then a square (a promotion asks which piece). The game itself
lives in core.chess_game, shared with the voice tool; this panel listens to
it through a Qt signal, so updates from the assistant's thinking thread or a
spoken move arrive on the Qt thread.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen,
                         QRadialGradient)
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

from core.chess_game import LEVEL_NAMES, get_game
from gui.style import btn_css, px_font, with_alpha
from gui.theme import C, qcol

GLYPH = {"k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}
PIECE_FONTS = ["Segoe UI Symbol", "DejaVu Sans", "Noto Sans Symbols2", "Arial Unicode MS"]
LIGHT = "#cfae7f"
DARK = "#7a4c2a"
PROMO_NAMES = (("q", "Vezir"), ("r", "Kale"), ("b", "Fil"), ("n", "At"))
SLIDE = 0.18                               # seconds a moving piece takes


class BoardWidget(QWidget):
    move_chosen = pyqtSignal(object)       # (from, to, promo)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)
        self.snap: dict = {}
        self.flipped = False
        self.selected: int | None = None
        self.hover: int | None = None
        self._paths: dict = {}
        self._anim = None                  # (piece, from, to, start)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._anim_tick)

    # ── data ──────────────────────────────────────────────────────────────────
    def set_snapshot(self, snap: dict) -> None:
        old_last = self.snap.get("last_move")
        self.snap = snap
        if self.selected is not None and not any(m[0] == self.selected for m in snap.get("legal", [])):
            self.selected = None
        lm = snap.get("last_move")
        if lm and lm != old_last:
            piece = snap["squares"][lm[1]]
            self._anim = (piece, lm[0], lm[1], time.monotonic())
            self._timer.start(16)
        self.update()

    def _anim_tick(self) -> None:
        if not self._anim or time.monotonic() - self._anim[3] > SLIDE:
            self._anim = None
            self._timer.stop()
        self.update()

    # ── geometry ──────────────────────────────────────────────────────────────
    def _board_rect(self) -> QRectF:
        side = min(self.width(), self.height()) - 36
        return QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)

    def _square_rect(self, s: int) -> QRectF:
        r = self._board_rect()
        cell = r.width() / 8
        f, rank = s % 8, s // 8
        col, row = (7 - f, rank) if self.flipped else (f, 7 - rank)
        return QRectF(r.x() + col * cell, r.y() + row * cell, cell, cell)

    def _square_at(self, pt: QPointF):
        r = self._board_rect()
        if not r.contains(pt):
            return None
        cell = r.width() / 8
        col, row = int((pt.x() - r.x()) // cell), int((pt.y() - r.y()) // cell)
        col, row = min(7, max(0, col)), min(7, max(0, row))
        return (row * 8 + 7 - col) if self.flipped else ((7 - row) * 8 + col)

    # ── input ─────────────────────────────────────────────────────────────────
    def mouseMoveEvent(self, e):
        s = self._square_at(e.position())
        legal = self.snap.get("legal", [])
        clickable = s is not None and (any(m[0] == s for m in legal) or
                                       (self.selected is not None and any(m[0] == self.selected and m[1] == s for m in legal)))
        self.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        if s != self.hover:
            self.hover = s
            self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        s = self._square_at(e.position())
        if s is None:
            return
        legal = self.snap.get("legal", [])
        if self.selected is not None:
            options = [m for m in legal if m[0] == self.selected and m[1] == s]
            if options:
                mv = options[0]
                if len(options) > 1:                       # a promotion: ask which piece
                    mv = self._ask_promotion(options, e)
                    if mv is None:
                        return
                self.selected = None
                self.move_chosen.emit(mv)
                self.update()
                return
        self.selected = s if any(m[0] == s for m in legal) and s != self.selected else None
        self.update()

    def _ask_promotion(self, options, e):
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: {C.PANEL2}; color: {C.TEXT}; border: 1px solid {C.BORDER_B}; }}"
                           f"QMenu::item:selected {{ background: {C.PRI_GHO}; color: {C.WHITE}; }}")
        chosen = {}
        for code, name in PROMO_NAMES:
            act = menu.addAction(f"{GLYPH[code]}  {name}")
            chosen[act] = code
        act = menu.exec(self.mapToGlobal(e.position().toPoint()))
        if act is None:
            return None
        code = chosen[act]
        return next((m for m in options if m[2] == code), options[0])

    # ── paint ─────────────────────────────────────────────────────────────────
    def _glyph_path(self, kind: str, size: float) -> QPainterPath:
        key = (kind, round(size))
        if key not in self._paths:
            f = QFont()
            f.setFamilies(PIECE_FONTS)
            f.setPixelSize(max(8, int(size)))
            path = QPainterPath()
            path.addText(0, 0, f, GLYPH[kind])
            br = path.boundingRect()
            path.translate(-br.center().x(), -br.center().y())
            self._paths[key] = path
        return self._paths[key]

    def _draw_piece(self, p: QPainter, piece: str, rect: QRectF, alpha: float = 1.0) -> None:
        path = self._glyph_path(piece.lower(), rect.height() * 0.80)
        p.save()
        p.translate(rect.center())
        white = piece.isupper()
        # soft shadow
        p.translate(0, rect.height() * 0.03)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, int(90 * alpha))))
        p.drawPath(path)
        p.translate(0, -rect.height() * 0.03)
        g = QLinearGradient(0, -rect.height() / 2, 0, rect.height() / 2)
        if white:
            g.setColorAt(0, QColor(255, 251, 242, int(255 * alpha)))
            g.setColorAt(1, QColor(226, 214, 196, int(255 * alpha)))
            outline = QColor(40, 26, 14, int(255 * alpha))
        else:
            g.setColorAt(0, QColor(58, 46, 38, int(255 * alpha)))
            g.setColorAt(1, QColor(16, 12, 10, int(255 * alpha)))
            outline = QColor(255, 236, 210, int(150 * alpha))
        p.setBrush(QBrush(g))
        p.setPen(QPen(outline, max(1.0, rect.height() * 0.022)))
        p.drawPath(path)
        p.restore()

    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        snap = self.snap
        if not snap:
            p.end()
            return
        br = self._board_rect()
        cell = br.width() / 8

        # frame with a warm glow
        glow = QRadialGradient(br.center(), br.width() * 0.75)
        glow.setColorAt(0.0, with_alpha(C.PRI, 0.10))
        glow.setColorAt(1.0, with_alpha(C.PRI, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawRect(QRectF(0, 0, self.width(), self.height()))
        frame = br.adjusted(-10, -10, 10, 10)
        p.setBrush(QBrush(qcol(C.PANEL2)))
        p.setPen(QPen(with_alpha(C.PRI, 0.45), 1.2))
        p.drawRoundedRect(frame, 10, 10)

        squares = snap["squares"]
        last = snap.get("last_move")
        legal = snap.get("legal", [])
        targets = {m[1] for m in legal if m[0] == self.selected} if self.selected is not None else set()
        light, dark = QColor(LIGHT), QColor(DARK)
        for s in range(64):
            r = self._square_rect(s)
            base = light if (s // 8 + s % 8) % 2 else dark
            p.fillRect(r, base)
            if last and s in (last[0], last[1]):
                p.fillRect(r, with_alpha(C.ACC, 0.38))
            if s == self.selected:
                p.fillRect(r, with_alpha(C.PRI, 0.55))
            elif s == self.hover and (any(m[0] == s for m in legal) or s in targets):
                p.fillRect(r, with_alpha(C.WHITE, 0.12))
        if snap.get("check") is not None:
            r = self._square_rect(snap["check"])
            g = QRadialGradient(r.center(), r.width() * 0.62)
            g.setColorAt(0.0, QColor(255, 60, 40, 230))
            g.setColorAt(1.0, QColor(255, 60, 40, 0))
            p.fillRect(r, QBrush(g))

        # coordinates in the corner of the edge squares
        p.setFont(px_font(max(9, int(cell * 0.16)), QFont.Weight.DemiBold))
        for s in range(64):
            r = self._square_rect(s)
            col_on_left = r.x() - br.x() < 1
            row_on_bottom = br.bottom() - r.bottom() < 1
            on_light = (s // 8 + s % 8) % 2
            p.setPen(QPen(dark if on_light else light))
            if row_on_bottom:
                p.drawText(r.adjusted(0, 0, -3, -1), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                           "abcdefgh"[s % 8])
            if col_on_left:
                p.drawText(r.adjusted(3, 1, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                           str(s // 8 + 1))

        # pieces (the moving one is drawn on its way)
        anim = self._anim
        progress = 1.0
        if anim:
            progress = min(1.0, (time.monotonic() - anim[3]) / SLIDE)
            progress = 1 - (1 - progress) ** 3
        for s, piece in enumerate(squares):
            if piece == "." or (anim and s == anim[2]):
                continue
            self._draw_piece(p, piece, self._square_rect(s))
        if anim:
            a, b = self._square_rect(anim[1]), self._square_rect(anim[2])
            r = QRectF(a.x() + (b.x() - a.x()) * progress, a.y() + (b.y() - a.y()) * progress, a.width(), a.height())
            self._draw_piece(p, anim[0], r)

        # where the selected piece can go
        for t in targets:
            r = self._square_rect(t)
            p.setPen(Qt.PenStyle.NoPen)
            if squares[t] != ".":
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(with_alpha(C.PRI, 0.85), max(2.0, cell * 0.06)))
                p.drawEllipse(r.center(), cell * 0.44, cell * 0.44)
            else:
                p.setBrush(QBrush(with_alpha(C.PRI, 0.75)))
                p.drawEllipse(r.center(), cell * 0.14, cell * 0.14)
        p.end()


class ChessPanel(QWidget):
    """The chess page: board on the left, the game card on the right."""

    back_requested = pyqtSignal()
    assistant_moved = pyqtSignal(str)
    _changed = pyqtSignal()

    def __init__(self, assistant_name: str = "JARVIS", parent=None):
        super().__init__(parent)
        self.game = get_game()
        self.name = assistant_name
        self._last_reply_seen = ""
        self.setStyleSheet("background: transparent;")
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(10)

        bar = QHBoxLayout()
        back = QPushButton("‹  CORE")
        back.setStyleSheet(btn_css("dim", align="center"))
        back.setFixedSize(96, 32)
        back.setFont(px_font(11, QFont.Weight.DemiBold, spacing=1.5))
        back.clicked.connect(self.back_requested.emit)
        bar.addWidget(back)
        title = QLabel("SATRANÇ")
        title.setFont(px_font(13, QFont.Weight.DemiBold, spacing=4))
        title.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; padding-left: 12px;")
        bar.addWidget(title)
        bar.addStretch()
        flip = QPushButton("Tahtayı çevir")
        flip.setStyleSheet(btn_css("dim", align="center"))
        flip.setFixedSize(124, 32)
        flip.clicked.connect(self._flip)
        bar.addWidget(flip)
        root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(16)
        self.board = BoardWidget()
        self.board.move_chosen.connect(self._on_move)
        body.addWidget(self.board, 1)
        body.addWidget(self._build_card())
        root.addLayout(body, 1)

        self._changed.connect(self.refresh)
        self.game.add_listener(self._changed.emit)
        self.board.flipped = not self.game.user_white
        self.refresh()

    # ── the game card ─────────────────────────────────────────────────────────
    def _build_card(self) -> QWidget:
        from gui.widgets import HoloPanel
        card = HoloPanel("OYUN", "", pad=16)
        card.setFixedWidth(320)
        lay = card.body
        lay.setSpacing(10)

        self.status = QLabel()
        self.status.setFont(px_font(20, QFont.Weight.Light))
        self.status.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.sub = QLabel()
        self.sub.setFont(px_font(11))
        self.sub.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        lay.addWidget(self.sub)

        self.captured = QLabel()
        self.captured.setFont(QFont(PIECE_FONTS[0], 16))
        self.captured.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self.captured.setWordWrap(True)
        lay.addWidget(self.captured)

        self.moves = QLabel()
        self.moves.setFont(px_font(12, mono=True))
        self.moves.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self.moves.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.moves.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.moves)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setMinimumHeight(140)
        self._moves_scroll = scroll
        lay.addWidget(scroll, 1)

        def pill(text, kind="dim"):
            b = QPushButton(text)
            b.setStyleSheet(btn_css(kind, align="center"))
            b.setFixedHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            return b

        lay.addWidget(self._section("ZORLUK"))
        row = QHBoxLayout()
        self.level_btns = {}
        for key, name in LEVEL_NAMES.items():
            b = pill(name)
            b.clicked.connect(lambda _=False, k=key: self.game.set_level(k))
            self.level_btns[key] = b
            row.addWidget(b)
        lay.addLayout(row)

        lay.addWidget(self._section("YENİ OYUN"))
        row = QHBoxLayout()
        as_white = pill("♔  Beyaz", "primary")
        as_white.clicked.connect(lambda: self._new(True))
        as_black = pill("♚  Siyah", "primary")
        as_black.clicked.connect(lambda: self._new(False))
        row.addWidget(as_white)
        row.addWidget(as_black)
        lay.addLayout(row)

        row = QHBoxLayout()
        undo = pill("Geri al")
        undo.clicked.connect(lambda: self.game.undo())
        resign = pill("Terk et")
        resign.clicked.connect(lambda: self.game.resign())
        row.addWidget(undo)
        row.addWidget(resign)
        lay.addLayout(row)
        return card

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(px_font(10, QFont.Weight.DemiBold, spacing=2))
        lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; padding-top: 6px;")
        return lbl

    # ── actions ───────────────────────────────────────────────────────────────
    def _new(self, user_white: bool) -> None:
        self.board.flipped = not user_white
        self.board.selected = None
        self.game.new_game(user_white=user_white)

    def _flip(self) -> None:
        self.board.flipped = not self.board.flipped
        self.board.update()

    def _on_move(self, mv) -> None:
        self.game.user_move(mv)

    def refresh(self) -> None:
        snap = self.game.snapshot()
        self.board.set_snapshot(snap)
        self.status.setText(self.game.status_text())
        side = "Beyaz" if snap["user_white"] else "Siyah"
        self.sub.setText(f"Sen: {side}  ·  {self.name}: {'Siyah' if snap['user_white'] else 'Beyaz'}"
                         f"  ·  {LEVEL_NAMES.get(snap['level'], snap['level'])}")
        for key, b in self.level_btns.items():
            b.setStyleSheet(btn_css("choice" if key == snap["level"] else "dim", align="center"))
        cap = snap["captured"]
        lost_by_assistant = cap["black"] if snap["user_white"] else cap["white"]
        lost_by_user = cap["white"] if snap["user_white"] else cap["black"]
        order = "qrbnp"

        def fmt(ps):
            return " ".join(GLYPH[p.lower()] for p in sorted(ps, key=lambda x: order.index(x.lower())))
        self.captured.setText((f"Aldıkların: {fmt(lost_by_assistant)}" if lost_by_assistant else "")
                              + ("\n" if lost_by_assistant and lost_by_user else "")
                              + (f"Kaybettiklerin: {fmt(lost_by_user)}" if lost_by_user else ""))
        sans = snap["sans"]
        lines = []
        for i in range(0, len(sans), 2):
            pair = sans[i:i + 2]
            lines.append(f"{i // 2 + 1:>3}. {pair[0]:<8}{pair[1] if len(pair) > 1 else ''}")
        self.moves.setText("\n".join(lines) or "Henüz hamle yok.")
        QTimer.singleShot(0, lambda: self._moves_scroll.verticalScrollBar().setValue(
            self._moves_scroll.verticalScrollBar().maximum()))
        if snap["last_reply"] and snap["last_reply"] != self._last_reply_seen:
            self._last_reply_seen = snap["last_reply"]
            self.assistant_moved.emit(snap["last_reply"])
        elif not snap["last_reply"]:
            self._last_reply_seen = ""

    def closeEvent(self, e):
        self.game.remove_listener(self._changed.emit)
        super().closeEvent(e)
