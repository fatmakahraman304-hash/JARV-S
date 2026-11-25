"""AETHER never loses what it knows: a broken memory file comes back from the last good copy,
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

    def test_forgetting_survives_restart_and_cloud_merge(self):
        from core import sync_hub
        mm.remember("secret", "old detail")
        cloud = mm.load_memory()
        mm.forget("secret")
        local = sync_hub._local_memory_categories()
        merged = sync_hub.merge_memory(local, cloud)
        self.assertNotIn("secret", merged["notes"])
        sync_hub._save_local_categories(merged)
        self.assertIn("notes/secret", mm.load_memory()["_deleted"])
        self.assertFalse(any(r["category"] == "_deleted" for r in mm.all_entries_for_ui()))

    def test_damaged_or_missing_primary_cannot_restore_forgotten_fact(self):
        mm.remember("keep", "retained")
        mm.remember("forgotten", "private")
        mm.forget("forgotten")
        for damage in ("missing", "corrupt"):
            with self.subTest(damage=damage):
                if damage == "missing":
                    mm.MEMORY_PATH.unlink()
                else:
                    mm.MEMORY_PATH.write_text("{")
                restored = mm.load_memory()
                self.assertNotIn("forgotten", restored["notes"])
                self.assertIn("notes/forgotten", restored["_deleted"])
                self.assertEqual(restored["notes"]["keep"]["value"], "retained")

    def test_forgetting_an_archived_fact_hides_it_from_recall(self):
        mm.ARCHIVE_PATH.write_text(json.dumps({"notes": {"old": {"value": "private avocado"}}}))
        mm.forget("old")
        with patch("memory.continuity.search", return_value=""):
            self.assertNotIn("private avocado", mm.search_memory("avocado"))

    def test_second_forget_beats_fast_relearning_on_another_device(self):
        from datetime import datetime, timezone
        from core.sync_hub import merge_memory
        with patch.object(mm, "datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 11, 21, tzinfo=timezone.utc)
            mm.remember("item", "first")
            mm.forget("item")
            mm.remember("item", "second")
            other_device = mm.load_memory()
            mm.forget("item")
        self.assertNotIn("item", merge_memory(mm.load_memory(), other_device)["notes"])

    def test_remembering_again_clears_local_deletion(self):
        mm.remember("item", "first")
        mm.forget("item")
        deleted = mm.load_memory()
        mm.remember("item", "second")
        self.assertNotIn("notes/item", mm.load_memory()["_deleted"])
        from core.sync_hub import merge_memory
        self.assertEqual(merge_memory(deleted, mm.load_memory())["notes"]["item"]["value"], "second")

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

    def test_memory_writes_preserve_existing_temporary_names(self):
        sentinels = [mm.MEMORY_PATH.with_suffix(".json.tmp"),
                     mm.BACKUP_PATH.with_name(mm.BACKUP_PATH.name + ".tmp"),
                     mm.ARCHIVE_PATH.with_suffix(".json.tmp")]
        for path in sentinels:
            path.write_bytes(b"user file")
        mm.remember("one", "first")
        mm.remember("two", "second")
        mm._archive({"notes": {"old": {"value": "saved"}}})
        for path in sentinels:
            self.assertEqual(path.read_bytes(), b"user file")

    def test_corrupt_archive_blocks_trimming_without_losing_primary(self):
        mm.remember("old", "saved fact")
        previous = mm.MEMORY_PATH.read_bytes()
        for invalid in (b"broken json", b"[]", b'{"notes": []}'):
            with self.subTest(invalid=invalid):
                mm.ARCHIVE_PATH.write_bytes(invalid)
                with patch.object(mm, "MEMORY_MAX_CHARS", 50):
                    with self.assertRaises(ValueError):
                        mm.remember("new", "new fact" * 20)
                self.assertEqual(mm.MEMORY_PATH.read_bytes(), previous)
                self.assertEqual(mm.ARCHIVE_PATH.read_bytes(), invalid)

    def test_flush_failure_does_not_publish_or_erase_files(self):
        mm.remember("old", "saved fact")
        before = mm.MEMORY_PATH.read_bytes()
        with patch.object(mm.os, "fsync", side_effect=OSError("disk flush failed")):
            with self.assertRaisesRegex(OSError, "disk flush"):
                mm.remember("new", "must not publish")
        self.assertEqual(mm.MEMORY_PATH.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in Path(self.tmp.name).iterdir()),
                         ["long_term.json", "long_term.json.lock"])

    def test_failed_backup_flush_preserves_primary_and_previous_backup(self):
        mm.remember("one", "first")
        mm.remember("two", "second")
        before = {p: p.read_bytes() for p in (mm.MEMORY_PATH, mm.BACKUP_PATH)}
        with patch.object(mm.os, "fsync", side_effect=[None, OSError("backup flush failed")]):
            with self.assertRaisesRegex(OSError, "backup flush"):
                mm.remember("three", "not committed")
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(list(Path(self.tmp.name).glob(".friday-memory-*.tmp")), [])

    def test_failed_archive_publish_keeps_both_stores_and_reports_no_archive(self):
        mm.remember("old", "saved fact")
        mm._archive({"notes": {"earlier": {"value": "older fact"}}})
        before = {p: p.read_bytes() for p in (mm.MEMORY_PATH, mm.ARCHIVE_PATH)}
        with patch.object(mm, "MEMORY_MAX_CHARS", 50), patch.object(mm, "_log") as log:
            with patch.object(mm.os, "replace", side_effect=OSError("archive locked")):
                with self.assertRaisesRegex(OSError, "archive locked"):
                    mm.remember("new", "new fact" * 20)
            self.assertFalse(any("Archived" in str(call) for call in log.call_args_list))
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(list(Path(self.tmp.name).glob(".friday-memory-*.tmp")), [])

    def test_reading_last_session_never_writes_or_rotates_the_backup(self):
        mm.save_session_summary("Önceki proje")
        mm.save_session_summary("Devam eden proje")
        before = {p: p.read_bytes() for p in (mm.MEMORY_PATH, mm.BACKUP_PATH)}
        with patch.object(mm.os, "replace", side_effect=OSError("read-only disk")) as replace:
            self.assertEqual(mm.pop_last_session()["summary"], "Devam eden proje")
            self.assertEqual(mm.pop_last_session()["summary"], "Devam eden proje")
        replace.assert_not_called()
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

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
