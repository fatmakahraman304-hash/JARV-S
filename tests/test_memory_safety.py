"""MAYK never loses what it knows: a broken memory file comes back from the last good copy,
and a full memory archives (not deletes) its oldest facts, which recall still finds."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory import memory_manager as mm


class MemorySafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p = [patch.object(mm, "MEMORY_PATH", d / "long_term.json"),
                  patch.object(mm, "BACKUP_PATH", d / "long_term.json.bak"),
                  patch.object(mm, "ARCHIVE_PATH", d / "long_term_archive.json"),
                  patch.object(mm, "_LEGACY_MEMORY_PATH", d / "none.json")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_desktop_edit_beats_an_older_phone_edit_on_same_day(self):
        from core.sync_hub import merge_memory
        mm.remember("shared", "desktop")
        local = mm.load_memory()
        stamp = local["notes"]["shared"]["updated"]
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        phone = {"notes": {"shared": {"value": "phone", "updated": stamp[:10]}}}
        self.assertEqual(merge_memory(phone, local)["notes"]["shared"]["value"], "desktop")

    def test_invalid_json_shape_cannot_replace_valid_backup(self):
        mm.BACKUP_PATH.write_text('{"notes": {}}')
        mm.MEMORY_PATH.write_text("[]")
        mm.save_memory({"notes": {}})
        self.assertEqual(json.loads(mm.BACKUP_PATH.read_text()), {"notes": {}})

    def test_broken_file_comes_back_from_the_last_good_copy(self):
        mm.update_memory({"identity": {"name": {"value": "Murat"}}})
        mm.update_memory({"preferences": {"drink": {"value": "çay"}}})       # second write: first is now the backup
        mm.MEMORY_PATH.write_text('{"identity": {"name": ', encoding="utf-8")  # power cut mid-write
        data = mm.load_memory()
        self.assertEqual(data["identity"]["name"]["value"], "Murat")
        self.assertTrue(list(Path(self.tmp.name).glob("long_term.corrupt-*.json")))   # the broken file was kept
        mm.update_memory({"notes": {"x": {"value": "y"}}})                   # and the next save keeps Murat
        self.assertEqual(json.loads(mm.MEMORY_PATH.read_text(encoding="utf-8"))["identity"]["name"]["value"], "Murat")

    def test_a_broken_file_never_becomes_the_backup(self):
        mm.update_memory({"identity": {"name": {"value": "Murat"}}})
        mm.update_memory({"identity": {"city": {"value": "Lefkoşa"}}})
        good_backup = mm.BACKUP_PATH.read_text(encoding="utf-8")
        mm.MEMORY_PATH.write_text("garbage", encoding="utf-8")
        mm._write_memory({"identity": {}})
        self.assertEqual(mm.BACKUP_PATH.read_text(encoding="utf-8"), good_backup)

    def test_full_memory_archives_and_recall_still_finds_it(self):
        with patch.object(mm, "MEMORY_MAX_CHARS", 400):
            mm.update_memory({"notes": {"old_car": {"value": "Murat'ın eski arabası mavi bir Fiat Doblo", "updated": "2020-01-01"}}})
            for i in range(8):
                mm.update_memory({"notes": {f"fact{i}": {"value": f"yeni bilgi numarası {i} " * 2, "updated": f"2026-01-0{i + 1}"}}})
        self.assertNotIn("old_car", mm.load_memory()["notes"])
        self.assertIn("old_car", json.loads(mm.ARCHIVE_PATH.read_text(encoding="utf-8"))["notes"])
        self.assertIn("Fiat Doblo", mm.search_memory("araba Fiat"))
        self.assertIn("arşivden", mm.search_memory("Fiat"))


if __name__ == "__main__":
    unittest.main()


class StandingInstructions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.p = [patch.object(mm, "MEMORY_PATH", d / "long_term.json"),
                  patch.object(mm, "BACKUP_PATH", d / "long_term.json.bak"),
                  patch.object(mm, "ARCHIVE_PATH", d / "long_term_archive.json"),
                  patch.object(mm, "_LEGACY_MEMORY_PATH", d / "none.json")]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.tmp.cleanup()

    def test_always_in_the_prompt_first_and_never_trimmed(self):
        mm.update_memory({"instructions": {"no_sir": {"value": "Do not call the user 'sir' (efendim)", "updated": "2020-01-01"}}})
        with patch.object(mm, "MEMORY_MAX_CHARS", 600):
            for i in range(30):
                mm.update_memory({"preferences": {f"like{i}": {"value": f"likes thing number {i} a lot", "updated": f"2026-01-{i % 28 + 1:02d}"}}})
        memory = mm.load_memory()
        self.assertIn("no_sir", memory["instructions"])                     # the oldest entry, still there
        block = mm.format_memory_for_prompt(memory)
        self.assertTrue(block.startswith("[STANDING INSTRUCTIONS FROM THE USER"))
        self.assertIn("Do not call the user 'sir' (efendim)", block)

    def test_taken_back(self):
        mm.update_memory({"instructions": {"short": {"value": "Answer in at most two sentences"}}})
        self.assertIn("Forgotten", mm.forget("short", "instructions"))
        self.assertNotIn("STANDING INSTRUCTIONS", mm.format_memory_for_prompt(mm.load_memory()))
