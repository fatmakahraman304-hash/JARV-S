"""Offline checks: run with python -m unittest discover -s tests -p test_book_panel.py."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from gui.book_panel import BookPanel


class BookPanelKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The test runner is its own process and never imports ui.py, so the
        # app's QApplication does not exist here. Qt aborts if a widget is
        # built without one. This reuses an instance already in this process,
        # for example one made by another test module, and creates one only
        # when there is none. It never makes a second instance. This is the
        # same pattern as tests/test_location_map.py.
        cls.app = QApplication.instance() or QApplication(['jarvis-book-test'])

    def make_panel(self, count):
        panel = BookPanel()
        self.addCleanup(panel.close)
        panel.show_pages('Test', [(f'H{i}', f'Body {i}', 'https://example.org/') for i in range(count)])
        return panel

    def test_page_keys_turn_spreads(self):
        panel = self.make_panel(6)
        QTest.keyClick(panel, Qt.Key.Key_PageDown)
        self.assertEqual(panel.index, 2)
        self.assertEqual(panel.jump.value(), 3)
        QTest.keyClick(panel, Qt.Key.Key_PageDown)
        self.assertEqual(panel.index, 4)
        QTest.keyClick(panel, Qt.Key.Key_PageDown)
        self.assertEqual(panel.index, 4)
        QTest.keyClick(panel, Qt.Key.Key_PageUp)
        self.assertEqual(panel.index, 2)

    def test_home_and_end_jump_to_first_and_last_spread(self):
        panel = self.make_panel(7)
        QTest.keyClick(panel, Qt.Key.Key_End)
        self.assertEqual(panel.index, 6)
        self.assertFalse(panel.next.isEnabled())
        self.assertEqual(panel.count.text(), '7–7 / 7')
        QTest.keyClick(panel, Qt.Key.Key_Home)
        self.assertEqual(panel.index, 0)
        self.assertFalse(panel.previous.isEnabled())

    def test_keys_on_empty_book_do_nothing(self):
        panel = BookPanel()
        self.addCleanup(panel.close)
        panel.show_pages('Empty', [])
        for key in (Qt.Key.Key_End, Qt.Key.Key_Home, Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            QTest.keyClick(panel, key)
        self.assertEqual(panel.index, 0)
        self.assertEqual(panel.count.text(), '0 sayfa')


if __name__ == '__main__':
    unittest.main()
