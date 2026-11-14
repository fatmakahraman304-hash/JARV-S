import importlib.util
import unittest
from unittest.mock import Mock, patch

from core import scan_research


class BookResearchTests(unittest.TestCase):
    def test_ambiguous_titles_are_not_downloaded(self):
        response = Mock()
        response.json.return_value = {"results": [
            {"id": 1, "title": "The Book", "copyright": False},
            {"id": 2, "title": "The Book", "copyright": False},
        ]}
        with patch.object(scan_research.httpx, "get", return_value=response), patch.object(
            scan_research.httpx, "stream"
        ) as stream:
            self.assertEqual(scan_research._gutenberg("The Book", ""), [])
            stream.assert_not_called()

    def test_exact_book_yields_sourced_reading_pages(self):
        response = Mock()
        response.json.return_value = {"results": [
            {"id": 1, "title": "The Book", "copyright": False, "authors": [{"name": "Writer, Jane"}]},
            {"id": 2, "title": "The Book", "copyright": True, "authors": [{"name": "Writer, Jane"}]},
        ]}
        with patch.object(scan_research.httpx, "get", return_value=response), patch.object(
            scan_research.httpx, "stream"
        ) as stream:
            stream.return_value.__enter__.return_value.iter_bytes.return_value = [
                b"*** START OF THE PROJECT GUTENBERG EBOOK THE BOOK ***\n"
                b"A chapter.\n*** END OF THE PROJECT GUTENBERG EBOOK THE BOOK ***\n"
            ]
            pages = scan_research._gutenberg("The Book", "Jane Writer")
        self.assertEqual(pages[0][1:], ("A chapter.", "https://www.gutenberg.org/ebooks/1"))

    def test_objects_use_web_results_without_book_download(self):
        rows = [{"title": "Ceramic lamp", "snippet": "An overview", "url": "https://example.org/lamp"}]
        with patch("actions.web_search._ddg_search", return_value=rows), patch.object(
            scan_research, "_gutenberg"
        ) as download:
            pages = scan_research.research("Ceramic lamp", book=False)
        download.assert_not_called()
        self.assertEqual(pages[0][1:], ("An overview", "https://example.org/lamp"))


@unittest.skipUnless(importlib.util.find_spec("cv2"), "OpenCV is required")
class GestureTests(unittest.TestCase):
    def test_swipe_directions_and_still_frames(self):
        import numpy as np
        from core.page_gesture import PageSwipe

        blank = np.zeros((160, 240, 3), dtype=np.uint8)
        for direction, positions in [(1, range(155, 54, -20)), (-1, range(55, 156, 20))]:
            frames = [blank, blank]
            for x in positions:
                frame = blank.copy()
                frame[55:105, x:x + 35] = 200
                frames.append(frame)
            detector = PageSwipe()
            with patch("core.page_gesture.time.monotonic", side_effect=[i * .08 for i in range(len(frames))]):
                turns = [turn for frame in frames if (turn := detector.feed(frame))]
            self.assertEqual(turns, [direction])
