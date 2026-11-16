"""core/chess_game.py — the one chess game you play against the assistant.

Both the board on screen (gui/chess_panel.py) and the voice tool
(plugins/chess.py) drive this same object, so a move said aloud and a move
clicked on the board are the same game. It is thread-safe: every change takes
the lock, and the assistant's reply is searched on a worker thread so neither
the Qt thread nor a tool thread ever waits for it.

Listeners (callables taking no arguments) are told after every change. They
may be called from any thread — the board passes a Qt signal's emit, which Qt
delivers on its own thread.
"""
from __future__ import annotations

import threading

from core import chess_engine as ce

LEVEL_NAMES = {"kolay": "Kolay", "orta": "Orta", "zor": "Zor"}


class ChessGame:
    def __init__(self):
        self._lock = threading.RLock()
        self._listeners: list = []
        self._gen = 0
        self.level = "orta"
        self.user_white = True
        self._reset()

    # ── listeners ─────────────────────────────────────────────────────────────
    def add_listener(self, fn) -> None:
        with self._lock:
            if fn not in self._listeners:
                self._listeners.append(fn)

    def remove_listener(self, fn) -> None:
        with self._lock:
            if fn in self._listeners:
                self._listeners.remove(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass

    # ── state ─────────────────────────────────────────────────────────────────
    def _reset(self) -> None:
        self.board = ce.Board()
        self.sans: list[str] = []
        self.last_move = None
        self.thinking = False
        self.resigned = None            # "user" | "assistant" | None
        self.last_reply = ""

    def outcome(self):
        if self.resigned == "user":
            return ("0-1" if self.user_white else "1-0"), "sen terk ettin"
        return self.board.outcome()

    def user_to_move(self) -> bool:
        return self.board.white == self.user_white

    def snapshot(self) -> dict:
        with self._lock:
            b = self.board
            out = self.outcome()
            check = b.king_square(b.white) if b.in_check() else None
            legal = b.legal_moves() if (not out and self.user_to_move() and not self.thinking) else []
            return {
                "squares": b.sq[:], "white_to_move": b.white, "user_white": self.user_white,
                "legal": legal, "last_move": self.last_move, "check": check,
                "sans": self.sans[:], "outcome": out, "thinking": self.thinking,
                "level": self.level, "fen": b.fen(), "last_reply": self.last_reply,
                "captured": self._captured(),
            }

    def _captured(self) -> dict:
        start = {"p": 8, "n": 2, "b": 2, "r": 2, "q": 1}
        out = {"white": [], "black": []}            # pieces each side has lost
        for k, n in start.items():
            have_w = sum(1 for p in self.board.sq if p == k.upper())
            have_b = sum(1 for p in self.board.sq if p == k)
            out["white"] += [k.upper()] * max(0, n - have_w)
            out["black"] += [k] * max(0, n - have_b)
        return out

    def status_text(self) -> str:
        s = self.snapshot()
        if s["outcome"]:
            result, reason = s["outcome"]
            if result == "1/2-1/2":
                return f"Berabere — {reason}"
            user_won = (result == "1-0") == s["user_white"]
            return f"{'Kazandın' if user_won else 'Kaybettin'} — {reason}"
        if s["thinking"]:
            return "Düşünüyorum…"
        turn = "Senin sıran" if s["white_to_move"] == s["user_white"] else "Benim sıram"
        return turn + (" · Şah!" if s["check"] is not None else "")

    # ── actions ───────────────────────────────────────────────────────────────
    def new_game(self, user_white: bool | None = None, level: str | None = None) -> None:
        with self._lock:
            self._gen += 1
            if user_white is not None:
                self.user_white = bool(user_white)
            if level in ce.LEVELS:
                self.level = level
            self._reset()
            start_engine = not self.user_to_move()
        self._notify()
        if start_engine:
            self._start_engine()

    def set_level(self, level: str) -> None:
        if level in ce.LEVELS:
            with self._lock:
                self.level = level
            self._notify()

    def user_move(self, move) -> tuple[bool, str]:
        """Play the user's move — a move tuple or text ('e4', 'Nf3', 'at f3',
        'e2e4'). Returns (ok, SAN or a reason in Turkish)."""
        with self._lock:
            if self.outcome():
                return False, "Oyun bitti; yeni oyun başlatabilirsin."
            if self.thinking:
                return False, "Henüz düşünüyorum, biraz bekle."
            if not self.user_to_move():
                return False, "Şu an benim sıram."
            mv = move if isinstance(move, tuple) else self.board.parse(str(move))
            if mv is None or mv not in self.board.legal_moves():
                return False, f"'{move}' bu konumda geçerli bir hamle değil."
            san = self.board.san(mv)
            self.board.push(mv)
            self.sans.append(san)
            self.last_move = mv
            self.last_reply = ""
            start_engine = not self.board.outcome()
            if start_engine:
                self.thinking = True
        self._notify()
        if start_engine:
            self._start_engine()
        return True, san

    def undo(self) -> tuple[bool, str]:
        """Take back the user's last move, and the reply to it if one was made."""
        with self._lock:
            self._gen += 1                       # drop a reply still being searched
            self.thinking = False
            self.resigned = None
            plies = 0
            if self.board.history:
                if self.user_to_move():          # last ply was the reply
                    self._pop()
                    plies = 1
                if self.board.history:           # the user's own move
                    self._pop()
                    plies += 1
            self.last_move = self.board.history[-1][0] if self.board.history else None
            self.last_reply = ""
            need_engine = not self.user_to_move() and not self.board.outcome()
        self._notify()
        if need_engine:                          # e.g. back at the start playing black
            self._start_engine()
        return (plies > 0), ("Geri alındı." if plies else "Geri alınacak hamle yok.")

    def _pop(self) -> None:
        self.board.pop()
        if self.sans:
            self.sans.pop()

    def resign(self) -> None:
        with self._lock:
            if not self.outcome():
                self._gen += 1
                self.thinking = False
                self.resigned = "user"
        self._notify()

    # ── the assistant's move ──────────────────────────────────────────────────
    def _start_engine(self) -> None:
        with self._lock:
            gen = self._gen
            board = self.board.copy()
            level = self.level
            self.thinking = True
        self._notify()

        def work():
            try:
                mv, _score, _depth = ce.search(board, level, stop=lambda: self._gen != gen)
            except Exception:
                mv = None
            with self._lock:
                if self._gen != gen:
                    return
                self.thinking = False
                if mv is not None and mv in self.board.legal_moves():
                    san = self.board.san(mv)
                    self.board.push(mv)
                    self.sans.append(san)
                    self.last_move = mv
                    self.last_reply = san
            self._notify()
        threading.Thread(target=work, daemon=True, name="chess-engine").start()


_game: ChessGame | None = None
_game_lock = threading.Lock()


def get_game() -> ChessGame:
    global _game
    with _game_lock:
        if _game is None:
            _game = ChessGame()
        return _game
