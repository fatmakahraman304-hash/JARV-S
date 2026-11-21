"""Regression checks for the iPhone web chess layout and piece rendering."""
import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


class ChessWebUiTests(unittest.TestCase):
    def test_board_has_exactly_eight_equal_rows_and_columns(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(8, minmax(0, 1fr))", html)
        self.assertIn("grid-template-rows: repeat(8, minmax(0, 1fr))", html)
        self.assertIn("aspect-ratio: 1 / 1", html)
        self.assertIn("min-width: 0; min-height: 0", html)
        self.assertIn(".board > .ch-square", html)
        self.assertIn(".board .ch-piece { display: block; width: 80%; height: 80%", html)

    def test_pieces_are_svg_not_platform_emoji(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")
        for kind in "pnbrqk":
            self.assertRegex(app, rf"(?m)^    {kind}: '<")
        self.assertIn('viewBox="0 0 45 45"', app)
        self.assertIn("function pieceSvg(piece)", app)
        self.assertIn("p !== '.' ? pieceSvg(p) : ''", app)
        self.assertNotIn("const GLYPH", app)

    def test_squares_are_buttons_with_coordinate_and_accessible_label(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn('<button type="button" class="ch-square', app)
        self.assertIn('aria-label="${label} ${CH.sqName(s)}"', app)
        self.assertIn('aria-pressed="${chess.sel === s}"', app)
        self.assertIn("querySelectorAll('[data-s]')", app)


if __name__ == "__main__":
    unittest.main()
