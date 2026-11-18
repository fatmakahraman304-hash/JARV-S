"""Play chess against the assistant by voice, on the same board as the screen.

The game is core.chess_game (shared with gui/chess_panel.py); the window is
asked to show the board through player.show_chess, which is thread-safe.
After the user's move this waits for the assistant's reply (a few seconds at
most, set by the difficulty) so the answer can say both moves aloud.
"""
import time

from core import outcome

PLUGIN = {
    "name": "chess",
    "description": (
        "Play chess with the user on the on-screen board (Satranç). Use when the user wants "
        "to play chess, says a chess move ('e4', 'at f3', 'atı f3'e oyna', 'vezir h5', "
        "'kısa rok', 'Nf3'), or asks about the game. Actions: 'open' shows the board; "
        "'new' starts a game (color 'white'/'black', level 'kolay'/'orta'/'zor'); 'move' plays "
        "the user's move given in 'move' (SAN like Nf3/exd5/O-O, coordinates like e2e4, or "
        "Turkish piece words) and returns your reply move; 'undo' takes back; 'resign'; "
        "'status' returns the position (FEN), moves so far and whose turn it is, so you can "
        "comment; 'hint' gives the best move for the user; 'teach' (on true/false) turns on teaching: "
        "after every user move you get a 'coach' verdict (good / mistake / blunder) and the better move — "
        "explain why in one or two sentences, and teach openings and tactics as they come up. "
        "Say moves to the user in Turkish (at=N, fil=B, kale=R, vezir=Q, şah=K)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "'open', 'new', 'move', 'undo', 'resign', 'status', 'hint' or 'teach'."},
            "move": {"type": "STRING", "description": "For move: the user's move."},
            "color": {"type": "STRING", "description": "For new: 'white' or 'black' (the user's side)."},
            "level": {"type": "STRING", "description": "For new: 'kolay', 'orta' or 'zor'."},
            "on": {"type": "BOOLEAN", "description": "For teach: true to teach, false to stop."},
        },
        "required": ["action"],
    },
}

_TEACH = {"on": False}


def coach(fen: str, move_text: str) -> dict | None:
    """How good is the user's move in this position, against the best one?
    Every move is searched to the same depth so the comparison is fair.
    {"yours", "best", "loss" (centipawns), "verdict"}; None if not legal."""
    from core.chess_engine import Board, root_scores
    before = Board(fen)
    mv = before.parse(move_text)
    if mv is None:
        return None
    scores = root_scores(before, 2)
    best_score, best = scores[0]
    mine = next(sc for sc, m in scores if m == mv)
    loss = best_score - mine
    if mv == best or loss < 35:
        verdict = "çok iyi hamle"
    elif loss < 90:
        verdict = "fena değil"
    elif loss < 250:
        verdict = "hata"
    else:
        verdict = "büyük hata"
    return {"yours": _spoken(before.san(mv)), "best": _spoken(before.san(best)),
            "loss": int(loss), "verdict": verdict}


_TR = {"N": "at", "B": "fil", "R": "kale", "Q": "vezir", "K": "şah"}


def _spoken(san: str) -> str:
    """'Nf3' → 'at f3', 'O-O' → 'kısa rok' — how to say a move in Turkish."""
    if not san:
        return ""
    if san.startswith("O-O-O"):
        base = "uzun rok"
    elif san.startswith("O-O"):
        base = "kısa rok"
    else:
        base = san
        if san[0] in _TR:
            base = _TR[san[0]] + " " + san[1:]
        base = base.replace("x", " alır ").replace("=", " terfi ").replace("+", "").replace("#", "")
        for k, v in _TR.items():
            base = base.replace(" terfi " + k, " terfi " + v)
    if san.endswith("#"):
        base += ", şah mat"
    elif san.endswith("+"):
        base += ", şah"
    return " ".join(base.split())


def _show(player):
    try:
        if player is not None and hasattr(player, "show_chess"):
            player.show_chess(True)
    except Exception:
        pass


def _state(game) -> dict:
    s = game.snapshot()
    sans = s["sans"]
    pgn = " ".join((f"{i // 2 + 1}. " if i % 2 == 0 else "") + m for i, m in enumerate(sans))
    return {"fen": s["fen"], "moves": pgn or "none", "status": game.status_text(),
            "user_color": "white" if s["user_white"] else "black", "level": s["level"]}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core.chess_game import get_game
        game = get_game()
        p = parameters or {}
        action = str(p.get("action") or "open").strip().lower()
        if action == "open":
            _show(player)
            return outcome.done("chess", **_state(game))
        if action == "new":
            color = str(p.get("color") or "").lower()
            user_white = None if not color else not color.startswith(("b", "s", "black", "siyah"))
            level = str(p.get("level") or "").lower() or None
            game.new_game(user_white=user_white, level=level)
            _show(player)
            reply = ""
            if not game.user_to_move():
                reply = _wait_reply(game)
            st = _state(game)
            return outcome.done("chess", started=True, your_first_move=_spoken(reply) or "-", **st)
        if action == "teach":
            _TEACH["on"] = p.get("on") is not False
            _show(player)
            return outcome.done("chess", teaching=_TEACH["on"], **_state(game))
        if action == "hint":
            from core.chess_engine import Board, search
            b = Board(game.snapshot()["fen"])
            if not game.user_to_move() or not b.legal_moves():
                return outcome.failed("chess", "şu an ipucu yok", **_state(game))
            best, _, _ = search(b, "zor")
            return outcome.done("chess", hint=_spoken(b.san(best)), **_state(game))
        if action == "move":
            _show(player)
            advice = None
            if _TEACH["on"] and game.user_to_move():
                try:
                    advice = coach(game.snapshot()["fen"], str(p.get("move") or ""))
                except Exception:
                    advice = None
            ok, info = game.user_move(str(p.get("move") or ""))
            if not ok:
                return outcome.failed("chess", info, **_state(game))
            reply = _wait_reply(game)
            extra = {"coach": advice} if advice else {}
            return outcome.done("chess", user_move=_spoken(info), your_move=_spoken(reply) or "-",
                                **extra, **_state(game))
        if action == "undo":
            ok, info = game.undo()
            _show(player)
            if not ok:
                return outcome.failed("chess", info, **_state(game))
            return outcome.done("chess", undone=True, **_state(game))
        if action == "resign":
            game.resign()
            _show(player)
            return outcome.done("chess", resigned=True, **_state(game))
        if action == "status":
            return outcome.done("chess", **_state(game))
        return outcome.failed("chess", f"unknown action '{action}'")
    except Exception as exc:                       # a plugin never raises
        return outcome.failed("chess", str(exc)[:200])


def _wait_reply(game, limit: float = 8.0) -> str:
    """Wait for the assistant's move (searched on its own thread)."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        s = game.snapshot()
        if not s["thinking"]:
            return s["last_reply"]
        time.sleep(0.05)
    return ""
