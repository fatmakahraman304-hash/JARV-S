import random
import time
import unittest

from core import chess_engine as ce
from core.chess_game import ChessGame


def perft(b, depth):
    if depth == 0:
        return 1
    n = 0
    for m in b.legal_moves():
        b.push(m)
        n += perft(b, depth - 1)
        b.pop()
    return n


class RulesTests(unittest.TestCase):
    # Reference move counts (chessprogramming.org "Perft Results").
    CASES = [
        (ce.START_FEN, [20, 400, 8902]),
        ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039]),
        ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
        ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264, 9467]),
        ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486]),
    ]

    def test_perft_matches_reference_counts(self):
        for fen, expected in self.CASES:
            b = ce.Board(fen)
            self.assertEqual([perft(b, d + 1) for d in range(len(expected))], expected, fen)
            self.assertEqual(b.fen(), fen)          # make/unmake leaves no trace

    def test_endings(self):
        b = ce.Board()
        for t in ("e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6"):
            b.push(b.parse(t))
        m = b.parse("Qxf7")
        self.assertEqual(b.san(m), "Qxf7#")
        b.push(m)
        self.assertEqual(b.outcome(), ("1-0", "şah mat"))
        self.assertEqual(ce.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1").outcome(), ("1/2-1/2", "pat"))
        self.assertEqual(ce.Board("8/8/8/4k3/8/8/2KB4/8 w - - 0 1").outcome()[1], "yetersiz taş")
        self.assertEqual(ce.Board("8/8/8/4k3/8/8/2KQ4/8 w - - 100 80").outcome()[1], "50 hamle kuralı")
        b = ce.Board()
        for _ in range(2):
            for t in ("Nf3", "Nf6", "Ng1", "Ng8"):
                b.push(b.parse(t))
        self.assertEqual(b.outcome()[1], "üç kez tekrar")

    def test_notation_in_and_out(self):
        b = ce.Board()
        for text, san in (("e2e4", "e4"), ("at f6", "Nf6"), ("Af3", "Nf3"), ("e6", "e6"),
                          ("Fc4", "Bc4"), ("fil c5", "Bc5"), ("kısa rok", "O-O")):
            m = b.parse(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(b.san(m), san)
            b.push(m)
        self.assertIsNone(b.parse("vezir"))
        self.assertIsNone(b.parse("Ke7"))              # not a legal move for black here
        b = ce.Board("8/4P3/8/8/8/8/k7/4K3 w - - 0 1")
        self.assertEqual(b.san(b.parse("e8=Q")), "e8=Q")
        self.assertEqual(b.san(b.parse("e7e8n")), "e8=N")
        b = ce.Board("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
        m = b.parse("exd6")
        b.push(m)
        self.assertEqual(b.sq[ce.sq_index("d5")], ".")  # en passant took the pawn
        # disambiguation
        b = ce.Board("4k3/8/8/8/8/8/4K3/R6R w - - 0 1")
        self.assertEqual(b.san(b.parse("Rad1")), "Rad1")
        self.assertEqual(b.san(b.parse("Rhd1")), "Rhd1")
        self.assertIsNone(b.parse("Rd1"))              # ambiguous: which rook?


class EngineTests(unittest.TestCase):
    def test_finds_mate_in_one_at_every_level(self):
        for level in ce.LEVELS:
            for seed in range(5):
                b = ce.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
                m, _s, _d = ce.search(b, level, rng=random.Random(seed))
                self.assertEqual(b.san(m), "Rd8#", level)

    def test_takes_a_free_queen_and_respects_time(self):
        b = ce.Board("4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1")
        start = time.monotonic()
        m, _s, _d = ce.search(b, "orta")
        self.assertEqual(b.san(m), "Rxd5")
        self.assertLess(time.monotonic() - start, ce.LEVELS["orta"][1] + 1.0)

    def test_stop_ends_search_early(self):
        start = time.monotonic()
        m, _s, _d = ce.search(ce.Board(), "zor", stop=lambda: True)
        self.assertIn(m, ce.Board().legal_moves())
        self.assertLess(time.monotonic() - start, 1.0)


class GameTests(unittest.TestCase):
    def wait(self, g):
        for _ in range(200):
            if not g.snapshot()["thinking"]:
                return
            time.sleep(0.02)

    def test_play_undo_black_resign(self):
        g = ChessGame()
        g.level = "kolay"
        seen = []
        g.add_listener(lambda: seen.append(1))
        self.assertEqual(g.user_move("e4"), (True, "e4"))
        self.wait(g)
        self.assertEqual(len(g.sans), 2)
        self.assertFalse(g.user_move("e4")[0])
        self.assertTrue(g.undo()[0])
        self.assertEqual(g.sans, [])
        g.new_game(user_white=False)
        self.wait(g)
        self.assertEqual(len(g.sans), 1)                # the assistant opened
        self.assertEqual(g.status_text(), "Senin sıran")
        g.resign()
        self.assertTrue(g.status_text().startswith("Kaybettin"))
        self.assertGreater(len(seen), 3)

    def test_stale_reply_is_dropped_after_new_game(self):
        g = ChessGame()
        g.level = "zor"
        g.user_move("e4")
        g.new_game(user_white=True)                     # while the reply is being searched
        self.wait(g)
        time.sleep(0.2)
        self.assertEqual(g.sans, [])


class PluginTests(unittest.TestCase):
    def test_voice_moves(self):
        from plugins import chess
        from core import chess_game
        chess_game._game = None
        shown = []

        class P:
            def show_chess(self, opened=True):
                shown.append(opened)

        out = chess.run({"action": "new", "color": "white", "level": "kolay"}, P())
        self.assertTrue(out.startswith("status=done"))
        out = chess.run({"action": "move", "move": "atı f3'e"}, P())
        self.assertIn('user_move="at f3"', out)
        self.assertNotIn("your_move=-", out)
        self.assertTrue(chess.run({"action": "move", "move": "Ke2e9"}, P()).startswith("status=failed"))
        self.assertEqual(chess._spoken("exd5+"), "e alır d5, şah")
        self.assertEqual(chess._spoken("O-O-O"), "uzun rok")
        self.assertTrue(shown)


if __name__ == "__main__":
    unittest.main()
