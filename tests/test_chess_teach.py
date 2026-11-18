import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


class CoachTest(unittest.TestCase):
    def test_fair_verdicts(self):
        from plugins import chess
        from core.chess_engine import START_FEN
        self.assertEqual(chess.coach(START_FEN, "e4")["verdict"], "çok iyi hamle")
        bad = chess.coach("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "Ng5")
        self.assertEqual(bad["verdict"], "büyük hata")             # the queen takes the knight
        missed = chess.coach("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "h3")
        self.assertEqual(missed["best"], "kale a8, şah mat")
        self.assertIsNone(chess.coach(START_FEN, "e5"))            # not legal for white

    def test_teach_and_hint_actions(self):
        from plugins import chess
        from core.chess_game import get_game
        game = get_game()
        game.new_game(user_white=True, level="kolay")
        self.assertIn("teaching=true", chess.run({"action": "teach", "on": True}))
        out = chess.run({"action": "hint"})
        self.assertIn("hint", out)
        moved = chess.run({"action": "move", "move": "e4"})
        self.assertIn("coach", moved)
        chess.run({"action": "teach", "on": False})

    def test_root_scores_sorted(self):
        from core.chess_engine import Board, root_scores
        sc = root_scores(Board("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"), 2)
        self.assertGreater(sc[0][0], 90000)                        # the mate comes first

    def test_web_has_the_same_engine_and_coach(self):
        js = (ROOT / "web" / "chess.js").read_text(encoding="utf-8")
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        for name in ("function rootScores", "function search", "parse(text)", "kolay: [2, 500, 0.30]"):
            self.assertIn(name, js)
        self.assertIn("case 'chess': return chessTool(a);", app)
        self.assertIn("loss < 35 ? 'çok iyi hamle'", app)
        self.assertIn("coffee_fortune", app)
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="chess.js"></script>', html)


if __name__ == "__main__":
    unittest.main()
