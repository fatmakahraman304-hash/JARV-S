"""core/chess_engine.py — chess rules and a small chess-playing engine.

Pure Python, no dependencies, no Qt. Two parts:

* Board: the full rules — castling, en passant, promotion, check, checkmate,
  stalemate, the fifty-move rule, threefold repetition and insufficient
  material — plus move notation: standard SAN ("Nf3", "exd5", "O-O", "e8=Q+")
  out, and SAN, UCI ("g1f3") or Turkish ("at f3", "Af3", "vezir d1", "kısa
  rok") in.
* search(): alpha-beta with quiescence, iterative deepening, move ordering and
  piece-square evaluation, bounded by time and depth. Difficulty levels map to
  those bounds, the easiest one also plays a less-than-best move now and then.

Squares are 0..63, a1 = 0, h1 = 7, a8 = 56. Pieces are letters: upper case
for white (PNBRQK), lower case for black, "." for empty. A move is a tuple
(from, to, promotion) with promotion "" or one of "qrbn".
"""
from __future__ import annotations

import random
import re
import time

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FILES = "abcdefgh"

KNIGHT = (17, 15, 10, 6, -6, -10, -15, -17)
KING = (1, -1, 8, -8, 9, 7, -7, -9)
ROOK_DIRS = (1, -1, 8, -8)
BISHOP_DIRS = (9, 7, -7, -9)

VALUE = {"p": 100, "n": 320, "b": 330, "r": 500, "q": 900, "k": 0}


def sq_name(s: int) -> str:
    return FILES[s % 8] + str(s // 8 + 1)


def sq_index(name: str) -> int:
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def _step_ok(frm: int, to: int, max_file_jump: int) -> bool:
    return 0 <= to < 64 and abs(to % 8 - frm % 8) <= max_file_jump


class Board:
    def __init__(self, fen: str = START_FEN):
        self.set_fen(fen)

    # ── setup ─────────────────────────────────────────────────────────────────
    def set_fen(self, fen: str) -> None:
        parts = fen.split()
        rows = parts[0].split("/")
        sq = ["."] * 64
        for r, row in enumerate(rows):
            f = 0
            for ch in row:
                if ch.isdigit():
                    f += int(ch)
                else:
                    sq[(7 - r) * 8 + f] = ch
                    f += 1
        self.sq = sq
        self.white = parts[1] == "w"
        self.castling = "" if parts[2] == "-" else parts[2]
        self.ep = None if parts[3] == "-" else sq_index(parts[3])
        self.halfmove = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1
        self.history: list = []
        self.keys: list = [self.key()]

    def fen(self) -> str:
        rows = []
        for r in range(7, -1, -1):
            row, empty = "", 0
            for f in range(8):
                p = self.sq[r * 8 + f]
                if p == ".":
                    empty += 1
                else:
                    row += (str(empty) if empty else "") + p
                    empty = 0
            rows.append(row + (str(empty) if empty else ""))
        return (f"{'/'.join(rows)} {'w' if self.white else 'b'} {self.castling or '-'} "
                f"{sq_name(self.ep) if self.ep is not None else '-'} {self.halfmove} {self.fullmove}")

    def key(self):
        """Position identity for repetition: placement, side, castling, ep."""
        return ("".join(self.sq), self.white, self.castling, self.ep)

    def copy(self) -> "Board":
        b = Board.__new__(Board)
        b.sq = self.sq[:]
        b.white, b.castling, b.ep = self.white, self.castling, self.ep
        b.halfmove, b.fullmove = self.halfmove, self.fullmove
        b.history = []
        b.keys = self.keys[:]
        return b

    # ── attacks ───────────────────────────────────────────────────────────────
    def attacked(self, s: int, by_white: bool) -> bool:
        sq = self.sq
        pawn, knight, king = ("P", "N", "K") if by_white else ("p", "n", "k")
        bishop_q = ("B", "Q") if by_white else ("b", "q")
        rook_q = ("R", "Q") if by_white else ("r", "q")
        for d in ((-7, -9) if by_white else (7, 9)):
            t = s + d
            if _step_ok(s, t, 1) and sq[t] == pawn:
                return True
        for d in KNIGHT:
            t = s + d
            if _step_ok(s, t, 2) and sq[t] == knight:
                return True
        for d in KING:
            t = s + d
            if _step_ok(s, t, 1) and sq[t] == king:
                return True
        for dirs, pieces in ((BISHOP_DIRS, bishop_q), (ROOK_DIRS, rook_q)):
            for d in dirs:
                t = s
                while True:
                    nt = t + d
                    if not _step_ok(t, nt, 1):
                        break
                    t = nt
                    p = sq[t]
                    if p != ".":
                        if p in pieces:
                            return True
                        break
        return False

    def king_square(self, white: bool) -> int:
        return self.sq.index("K" if white else "k")

    def in_check(self, white: bool | None = None) -> bool:
        white = self.white if white is None else white
        return self.attacked(self.king_square(white), not white)

    # ── move generation ───────────────────────────────────────────────────────
    def _pseudo(self, captures_only: bool = False):
        sq, white = self.sq, self.white
        own = str.isupper if white else str.islower
        moves = []
        for s in range(64):
            p = sq[s]
            if p == "." or not own(p):
                continue
            k = p.lower()
            if k == "p":
                fwd = 8 if white else -8
                start_rank, last_rank = (1, 7) if white else (6, 0)
                t = s + fwd
                if not captures_only and 0 <= t < 64 and sq[t] == ".":
                    if t // 8 == last_rank:
                        moves += [(s, t, pr) for pr in "qrbn"]
                    else:
                        moves.append((s, t, ""))
                        t2 = t + fwd
                        if s // 8 == start_rank and sq[t2] == ".":
                            moves.append((s, t2, ""))
                for d in ((7, 9) if white else (-7, -9)):
                    t = s + d
                    if not _step_ok(s, t, 1):
                        continue
                    target = sq[t]
                    if (target != "." and not own(target)) or t == self.ep:
                        if t // 8 == last_rank:
                            moves += [(s, t, pr) for pr in "qrbn"]
                        else:
                            moves.append((s, t, ""))
            elif k in "nk":
                for d in (KNIGHT if k == "n" else KING):
                    t = s + d
                    if _step_ok(s, t, 2 if k == "n" else 1):
                        target = sq[t]
                        if target == ".":
                            if not captures_only:
                                moves.append((s, t, ""))
                        elif not own(target):
                            moves.append((s, t, ""))
            else:
                dirs = (BISHOP_DIRS if k == "b" else ROOK_DIRS if k == "r"
                        else BISHOP_DIRS + ROOK_DIRS)
                for d in dirs:
                    t = s
                    while True:
                        nt = t + d
                        if not _step_ok(t, nt, 1):
                            break
                        t = nt
                        target = sq[t]
                        if target == ".":
                            if not captures_only:
                                moves.append((s, t, ""))
                            continue
                        if not own(target):
                            moves.append((s, t, ""))
                        break
        if not captures_only:
            moves += self._castles()
        return moves

    def _castles(self):
        out = []
        if self.white:
            if ("K" in self.castling and self.sq[4] == "K" and self.sq[7] == "R"
                    and self.sq[5] == self.sq[6] == "."
                    and not any(self.attacked(x, False) for x in (4, 5, 6))):
                out.append((4, 6, ""))
            if ("Q" in self.castling and self.sq[4] == "K" and self.sq[0] == "R"
                    and self.sq[1] == self.sq[2] == self.sq[3] == "."
                    and not any(self.attacked(x, False) for x in (4, 3, 2))):
                out.append((4, 2, ""))
        else:
            if ("k" in self.castling and self.sq[60] == "k" and self.sq[63] == "r"
                    and self.sq[61] == self.sq[62] == "."
                    and not any(self.attacked(x, True) for x in (60, 61, 62))):
                out.append((60, 62, ""))
            if ("q" in self.castling and self.sq[60] == "k" and self.sq[56] == "r"
                    and self.sq[57] == self.sq[58] == self.sq[59] == "."
                    and not any(self.attacked(x, True) for x in (60, 59, 58))):
                out.append((60, 58, ""))
        return out

    def legal_moves(self, captures_only: bool = False):
        out = []
        mover = self.white
        for m in self._pseudo(captures_only):
            self.push(m)
            if not self.attacked(self.king_square(mover), not mover):
                out.append(m)
            self.pop()
        return out

    # ── make / unmake ─────────────────────────────────────────────────────────
    def push(self, m) -> None:
        frm, to, promo = m
        sq = self.sq
        piece, captured = sq[frm], sq[to]
        self.history.append((m, piece, captured, self.castling, self.ep, self.halfmove, self.fullmove))
        ep_capture = piece.lower() == "p" and to == self.ep and captured == "."
        sq[to], sq[frm] = piece, "."
        if ep_capture:
            sq[to - 8 if self.white else to + 8] = "."
        if promo:
            sq[to] = promo.upper() if self.white else promo
        if piece in "Kk" and abs(to - frm) == 2:            # castling: move the rook
            if to % 8 == 6:
                sq[to - 1], sq[to + 1] = sq[to + 1], "."
            else:
                sq[to + 1], sq[to - 2] = sq[to - 2], "."
        rights = self.castling
        if rights:
            for s_ in (frm, to):               # a king or rook moving or being captured
                lose = {4: "KQ", 60: "kq", 0: "Q", 7: "K", 56: "q", 63: "k"}.get(s_, "")
                for ch in lose:
                    rights = rights.replace(ch, "")
            self.castling = rights
        self.ep = (frm + to) // 2 if piece in "Pp" and abs(to - frm) == 16 else None
        self.halfmove = 0 if piece in "Pp" or captured != "." or ep_capture else self.halfmove + 1
        if not self.white:
            self.fullmove += 1
        self.white = not self.white
        self.keys.append(self.key())

    def pop(self):
        m, piece, captured, self.castling, self.ep, self.halfmove, self.fullmove = self.history.pop()
        self.keys.pop()
        self.white = not self.white
        frm, to, promo = m
        sq = self.sq
        sq[frm], sq[to] = piece, captured
        if piece in "Pp" and to == self.ep and captured == ".":
            sq[to - 8 if self.white else to + 8] = "p" if self.white else "P"
        if piece in "Kk" and abs(to - frm) == 2:
            if to % 8 == 6:
                sq[to + 1], sq[to - 1] = sq[to - 1], "."
            else:
                sq[to - 2], sq[to + 1] = sq[to + 1], "."
        return m

    # ── game state ────────────────────────────────────────────────────────────
    def insufficient_material(self) -> bool:
        rest = [p for p in self.sq if p not in ".Kk"]
        if not rest:
            return True
        if len(rest) == 1 and rest[0] in "NBnb":
            return True
        if all(p in "Bb" for p in rest):
            colours = {(s // 8 + s % 8) % 2 for s, p in enumerate(self.sq) if p in "Bb"}
            return len(colours) == 1
        return False

    def outcome(self):
        """None while the game goes on, else (result, reason):
        result '1-0', '0-1' or '1/2-1/2'."""
        if not self.legal_moves():
            if self.in_check():
                return ("0-1" if self.white else "1-0"), "şah mat"
            return "1/2-1/2", "pat"
        if self.halfmove >= 100:
            return "1/2-1/2", "50 hamle kuralı"
        if self.keys.count(self.keys[-1]) >= 3:
            return "1/2-1/2", "üç kez tekrar"
        if self.insufficient_material():
            return "1/2-1/2", "yetersiz taş"
        return None

    # ── notation ──────────────────────────────────────────────────────────────
    def san(self, m) -> str:
        frm, to, promo = m
        piece = self.sq[frm]
        k = piece.upper()
        if k == "K" and abs(to - frm) == 2:
            s = "O-O" if to % 8 == 6 else "O-O-O"
        else:
            capture = self.sq[to] != "." or (k == "P" and to == self.ep)
            if k == "P":
                s = (FILES[frm % 8] + "x" if capture else "") + sq_name(to)
                if promo:
                    s += "=" + promo.upper()
            else:
                others = [o for o in self.legal_moves()
                          if o[1] == to and o[0] != frm and self.sq[o[0]] == piece]
                dis = ""
                if others:
                    if all(o[0] % 8 != frm % 8 for o in others):
                        dis = FILES[frm % 8]
                    elif all(o[0] // 8 != frm // 8 for o in others):
                        dis = str(frm // 8 + 1)
                    else:
                        dis = sq_name(frm)
                s = k + dis + ("x" if capture else "") + sq_name(to)
        self.push(m)
        if self.in_check():
            s += "#" if not self.legal_moves() else "+"
        self.pop()
        return s

    def uci(self, m) -> str:
        return sq_name(m[0]) + sq_name(m[1]) + m[2]

    # Turkish piece letters and words → English SAN letters
    _TR_WORDS = (("şah", "K"), ("sah", "K"), ("vezir", "Q"), ("kale", "R"), ("fil", "B"),
                 ("at", "N"), ("piyon", ""), ("king", "K"), ("queen", "Q"), ("rook", "R"),
                 ("bishop", "B"), ("knight", "N"), ("pawn", ""))
    _TR_LETTERS = {"Ş": "K", "V": "Q", "K": "R", "F": "B", "A": "N"}

    def parse(self, text: str):
        """A legal move from SAN, UCI or Turkish notation, or None."""
        raw = str(text or "").strip()
        low = raw.lower().replace("ı", "i").replace("’", "'")
        legal = self.legal_moves()
        if not legal:
            return None
        if any(w in low for w in ("kısa rok", "kisa rok", "short castle", "küçük rok")):
            raw = "O-O"
        elif any(w in low for w in ("uzun rok", "long castle", "büyük rok", "buyuk rok")):
            raw = "O-O-O"
        compact = re.sub(r"[\s\-]", "", low)
        m = re.fullmatch(r"([a-h][1-8])([a-h][1-8])([qrbn])?", compact)
        if m:
            frm, to = sq_index(m[1]), sq_index(m[2])
            promo = m[3] or ""
            for mv in legal:
                if mv[0] == frm and mv[1] == to and (mv[2] == promo or (not promo and mv[2] == "q")):
                    return mv
            return None
        # Turkish words ("atı f3'e", "vezir d1") → a SAN letter in front
        letter = None
        words = re.findall(r"[a-zçğışöü]+", low)
        for w in words:
            for tr, en in self._TR_WORDS:
                if w == tr or (len(tr) > 2 and w.startswith(tr)) or (tr == "at" and w in ("ati", "atı")):
                    letter = en
                    break
            if letter is not None:
                break
        san = raw.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
        if letter is not None:
            squares = re.findall(r"[a-h][1-8]", low)
            if squares:
                san = letter + ("x" if "x" in low or "al" in words else "") + squares[-1]
        elif san[:1] in self._TR_LETTERS and len(san) >= 3 and re.match(r"[a-h1-8x]", san[1:2] or ""):
            san = self._TR_LETTERS[san[0]] + san[1:]
        want = re.sub(r"[+#!?\s]", "", san).replace("=", "")
        want_loose = want.replace("x", "")
        matches = []
        for mv in legal:
            s = re.sub(r"[+#]", "", self.san(mv)).replace("=", "")
            if s == want or s.replace("x", "") == want_loose:
                matches.append(mv)
        if len(matches) == 1:
            return matches[0]
        # "Nf3" when two knights can go there, or a pawn move typed without its piece
        if not matches:
            target = re.findall(r"[a-h][1-8]", want)
            letter = want[0] if want[:1] in "NBRQK" else ""
            if target:
                t = sq_index(target[-1])
                cands = [mv for mv in legal if mv[1] == t
                         and self.sq[mv[0]].upper() == (letter or "P")
                         and (not mv[2] or mv[2] == "q")]
                if len(cands) == 1:
                    return cands[0]
        return None


# ── evaluation ────────────────────────────────────────────────────────────────
# Piece-square tables from white's side, a8 first (rank 8 → rank 1), as is usual.
_PST_TXT = {
    "p": """ 0  0  0  0  0  0  0  0
            50 50 50 50 50 50 50 50
            10 10 20 30 30 20 10 10
             5  5 10 25 25 10  5  5
             0  0  0 20 20  0  0  0
             5 -5-10  0  0-10 -5  5
             5 10 10-20-20 10 10  5
             0  0  0  0  0  0  0  0""",
    "n": """-50-40-30-30-30-30-40-50
            -40-20  0  0  0  0-20-40
            -30  0 10 15 15 10  0-30
            -30  5 15 20 20 15  5-30
            -30  0 15 20 20 15  0-30
            -30  5 10 15 15 10  5-30
            -40-20  0  5  5  0-20-40
            -50-40-30-30-30-30-40-50""",
    "b": """-20-10-10-10-10-10-10-20
            -10  0  0  0  0  0  0-10
            -10  0  5 10 10  5  0-10
            -10  5  5 10 10  5  5-10
            -10  0 10 10 10 10  0-10
            -10 10 10 10 10 10 10-10
            -10  5  0  0  0  0  5-10
            -20-10-10-10-10-10-10-20""",
    "r": """ 0  0  0  0  0  0  0  0
             5 10 10 10 10 10 10  5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
            -5  0  0  0  0  0  0 -5
             0  0  0  5  5  0  0  0""",
    "q": """-20-10-10 -5 -5-10-10-20
            -10  0  0  0  0  0  0-10
            -10  0  5  5  5  5  0-10
             -5  0  5  5  5  5  0 -5
              0  0  5  5  5  5  0 -5
            -10  5  5  5  5  5  0-10
            -10  0  5  0  0  0  0-10
            -20-10-10 -5 -5-10-10-20""",
    "k": """-30-40-40-50-50-40-40-30
            -30-40-40-50-50-40-40-30
            -30-40-40-50-50-40-40-30
            -30-40-40-50-50-40-40-30
            -20-30-30-40-40-30-30-20
            -10-20-20-20-20-20-20-10
             20 20  0  0  0  0 20 20
             20 30 10  0  0 10 30 20""",
    "k_end": """-50-40-30-20-20-30-40-50
            -30-20-10  0  0-10-20-30
            -30-10 20 30 30 20-10-30
            -30-10 30 40 40 30-10-30
            -30-10 30 40 40 30-10-30
            -30-10 20 30 30 20-10-30
            -30-30  0  0  0  0-30-30
            -50-30-30-30-30-30-30-50""",
}


def _table(txt):
    nums = [int(x) for x in re.findall(r"-?\d+", txt)]
    rows = [nums[i * 8:(i + 1) * 8] for i in range(8)]
    out = [0] * 64
    for r, row in enumerate(rows):          # r = 0 is rank 8
        for f, v in enumerate(row):
            out[(7 - r) * 8 + f] = v
    return out


PST = {k: _table(v) for k, v in _PST_TXT.items()}


def evaluate(b: Board) -> int:
    """Score in centipawns from the side to move's point of view."""
    sq = b.sq
    queens = sum(1 for p in sq if p in "Qq")
    minors = sum(1 for p in sq if p in "NBRnbr")
    endgame = queens == 0 or (queens <= 2 and minors <= 2)
    score = 0
    for s, p in enumerate(sq):
        if p == ".":
            continue
        k = p.lower()
        table = PST["k_end"] if (k == "k" and endgame) else PST[k]
        if p.isupper():
            score += VALUE[k] + table[s]
        else:
            score -= VALUE[k] + table[(7 - s // 8) * 8 + s % 8]
    return score if b.white else -score


# ── search ────────────────────────────────────────────────────────────────────
MATE = 100000

LEVELS = {
    # name: (max depth, seconds, chance of a weaker move)
    "kolay": (2, 0.5, 0.30),
    "orta": (3, 1.2, 0.0),
    "zor": (5, 3.0, 0.0),
}


class _Timeout(Exception):
    pass


def _order(b: Board, moves, best=None):
    def score(m):
        if m == best:
            return 10 ** 6
        victim = b.sq[m[1]]
        s = 0
        if victim != ".":
            s += 10 * VALUE[victim.lower()] - VALUE[b.sq[m[0]].lower()] // 10 + 1000
        if m[2]:
            s += VALUE[m[2]]
        return s
    return sorted(moves, key=score, reverse=True)


def search(board: Board, level: str = "orta", stop=None, rng=None):
    """Best move for the side to move. `stop()` returning True ends early.
    Returns (move, score, depth) or (None, 0, 0) when there is no move."""
    rng = rng or random.Random()
    max_depth, seconds, weak = LEVELS.get(level, LEVELS["orta"])
    b = board.copy()
    root = b.legal_moves()
    if not root:
        return None, 0, 0
    if len(root) == 1:
        return root[0], 0, 0
    deadline = time.monotonic() + seconds
    nodes = [0]

    def check_time():
        nodes[0] += 1
        if nodes[0] & 255 == 0 and (time.monotonic() > deadline or (stop and stop())):
            raise _Timeout()

    def quiesce(alpha, beta, depth=0):
        check_time()
        stand = evaluate(b)
        if stand >= beta:
            return beta
        alpha = max(alpha, stand)
        if depth > 6:
            return alpha
        for m in _order(b, b.legal_moves(captures_only=True)):
            b.push(m)
            score = -quiesce(-beta, -alpha, depth + 1)
            b.pop()
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    def negamax(depth, alpha, beta, ply):
        check_time()
        if ply and b.keys.count(b.keys[-1]) >= 2:
            return 0
        moves = b.legal_moves()
        if not moves:
            return -MATE + ply if b.in_check() else 0
        if depth <= 0:
            return quiesce(alpha, beta)
        for m in _order(b, moves):
            b.push(m)
            score = -negamax(depth - 1, -beta, -alpha, ply + 1)
            b.pop()
            if score >= beta:
                return beta
            alpha = max(alpha, score)
        return alpha

    best, best_score, reached = _order(b, root)[0], 0, 0
    scored = []
    for depth in range(1, max_depth + 1):
        try:
            alpha, current, cur_score, results = -MATE - 1, None, -MATE - 1, []
            for m in _order(b, root, best):
                b.push(m)
                # With a weaker-move chance every root move needs its real score,
                # not an alpha-beta bound, so it searches with the full window.
                window = MATE + 1 if weak else -alpha
                score = -negamax(depth - 1, -MATE - 1, window, 1)
                b.pop()
                results.append((score, m))
                if score > cur_score:
                    cur_score, current = score, m
                alpha = max(alpha, score)
            best, best_score, reached, scored = current, cur_score, depth, results
            if abs(best_score) > MATE - 100:
                break
        except _Timeout:
            while len(b.history):
                b.pop()
            break
    if weak and scored and rng.random() < weak:
        # a plausible but weaker move: among the top few, never a blunder of mate
        ranked = sorted(scored, key=lambda x: -x[0])
        pool = [m for s, m in ranked[1:4] if s > best_score - 250 and s > -MATE + 100]
        if pool and best_score < MATE - 100:            # never pass up a mate
            best = rng.choice(pool)
    return best, best_score, reached
