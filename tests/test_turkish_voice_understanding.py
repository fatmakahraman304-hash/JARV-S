"""Gemini Live Türkçe konuşma dökümünü birleştirme ve yanlış anlama testleri."""
import unittest
from pathlib import Path

from core.intent import kind, should_act
from core.live_transcript import combined_text, merge_input_chunk


class InputTranscriptTests(unittest.TestCase):
    def test_independent_segments_keep_utterance_in_order(self):
        parts = []
        for new in ("MAYK", "bilgisayarın sesini", "kıs"):
            parts = merge_input_chunk(parts, new)
        self.assertEqual(combined_text(parts), "MAYK bilgisayarın sesini kıs")

    def test_cumulative_audio_transcription_does_not_duplicate(self):
        parts = []
        for new in ("MAYK ışığı", "MAYK ışığı aç", "MAYK ışığı aç"):
            parts = merge_input_chunk(parts, new)
        self.assertEqual(combined_text(parts), "MAYK ışığı aç")

    def test_word_boundary_overlap_only_once(self):
        parts = []
        for new in ("MAYK Spotify'ı aç", "Spotify'ı aç sonra sesi kıs"):
            parts = merge_input_chunk(parts, new)
        self.assertEqual(combined_text(parts), "MAYK Spotify'ı aç sonra sesi kıs")

    def test_legitimate_single_word_repetition_is_kept(self):
        self.assertEqual(combined_text(merge_input_chunk(["evet"], "evet")), "evet evet")

    def test_similar_words_are_not_cut(self):
        parts = merge_input_chunk(["ev"], "evet")
        self.assertEqual(combined_text(parts), "ev evet")

    def test_corrections_and_punctuation_are_not_dropped(self):
        parts = merge_input_chunk(["Mayk bilgisayarı"], "Mayk bilgisayarı kapatma")
        self.assertEqual(combined_text(parts), "Mayk bilgisayarı kapatma")

    def test_empty_chunks_not_added_or_mutated(self):
        previous = ["MAYK kamera aç"]
        self.assertEqual(merge_input_chunk(previous, "  "), previous)
        self.assertEqual(previous, ["MAYK kamera aç"])


class MisunderstandingFeedbackTests(unittest.TestCase):
    def test_user_corrections_are_feedback(self):
        for phrase in ("Beni yanlış anladın", "Öyle demedim", "Yanlış duydun",
                       "Beni anlamıyorsun", "MAYK yanlış anlıyorsun"):
            with self.subTest(phrase=phrase):
                self.assertEqual(kind(phrase), "feedback")
                self.assertTrue(should_act(phrase))

    def test_correction_followed_by_instruction_stays_a_task(self):
        self.assertEqual(kind("Yanlış anladın, müziği kapat"), "task")


class LiveIntegrationTests(unittest.TestCase):
    def test_live_path_uses_safe_input_merger(self):
        src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn("in_buf = merge_input_chunk(in_buf, txt)", src)
        self.assertIn("self._last_user_text = combined_text(in_buf)", src)
        self.assertIn("[TURKISH SPEECH UNDERSTANDING]", src)
        self.assertIn("Do not invent words, commands", src)


if __name__ == "__main__":
    unittest.main()
