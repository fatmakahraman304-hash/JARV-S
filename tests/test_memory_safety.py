"""FRIDAY never loses what it knows: a broken memory file comes back from the last good copy,
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

    def test_invalid_known_fields_recover_from_valid_backup(self):
        good = {"notes": {"keep": {"value": "retained"}}}
        for damaged in ({"notes": []}, {"preferences": None}, {"_deleted": []},
                        {"_deleted": {"notes/item": {"value": "bad timestamp"}}}):
            with self.subTest(damaged=damaged):
                mm.BACKUP_PATH.write_text(json.dumps(good))
                mm.MEMORY_PATH.write_text(json.dumps(damaged))
                restored = mm.load_memory()
                self.assertEqual(restored["notes"]["keep"]["value"], "retained")
                self.assertEqual(json.loads(mm.BACKUP_PATH.read_text()), good)

    def test_structurally_damaged_primary_never_becomes_the_backup(self):
        good = {"notes": {"keep": "retained"}}
        mm.BACKUP_PATH.write_text(json.dumps(good))
        mm.MEMORY_PATH.write_text('{"notes":[]}')
        mm.save_memory({"notes": {"new": "new fact"}})
        self.assertEqual(json.loads(mm.BACKUP_PATH.read_text()), good)
        self.assertEqual(mm.load_memory()["notes"]["new"], "new fact")

    def test_invalid_incoming_fields_are_rejected_before_file_changes(self):
        mm.remember("first", "one")
        mm.remember("second", "two")
        before = {path: path.read_bytes() for path in mm.MEMORY_PATH.parent.iterdir()}
        for incoming in ({"notes": []}, {"preferences": None}, {"_deleted": []},
                         {"_deleted": {"notes/item": 42}}):
            with self.subTest(incoming=incoming):
                with self.assertRaises(ValueError):
                    mm.save_memory(incoming)
                self.assertEqual({path: path.read_bytes() for path in mm.MEMORY_PATH.parent.iterdir()}, before)

    def test_invalid_backup_shape_is_not_published_as_successful_recovery(self):
        mm.MEMORY_PATH.write_text("{broken primary")
        mm.BACKUP_PATH.write_text('{"notes":[]}')
        notices = []
        with patch.object(mm, "_trim_notifier", notices.append):
            restored = mm.load_memory()
        self.assertIsInstance(restored["notes"], dict)
        self.assertFalse(mm.MEMORY_PATH.exists())
        self.assertEqual(mm.BACKUP_PATH.read_text(), '{"notes":[]}')
        self.assertTrue(any("kurtarılamadı" in text for text in notices))
        self.assertFalse(any("geri yüklendi" in text for text in notices))

    def test_legacy_string_entries_and_custom_categories_remain_compatible(self):
        original = {"notes": {"simple": "legacy fact"}, "custom": {"label": "extra"},
                    "_deleted": {"notes/removed": "2026-11-21"}, "sessions": []}
        mm.save_memory(original)
        restored = mm.load_memory()
        for field, value in original.items():
            self.assertEqual(restored[field], value)

    def test_broken_file_comes_back_from_the_last_good_copy(self):
        mm.update_memory({"identity": {"name": {"value": "Murat"}}})
        mm.update_memory({"preferences": {"drink": {"value": "çay"}}})       # second write: first is now the backup
        mm.MEMORY_PATH.write_text('{"identity": {"name": ', encoding="utf-8")  # power cut mid-write
        data = mm.load_memory()
        self.assertEqual(data["identity"]["name"]["value"], "Murat")
        self.assertTrue(list(Path(self.tmp.name).glob("long_term.corrupt-*.json")))   # the broken file was kept
        mm.update_memory({"notes": {"x": {"value": "y"}}})                   # and the next save keeps Murat
        self.assertEqual(json.loads(mm.MEMORY_PATH.read_text(encoding="utf-8"))["identity"]["name"]["value"], "Murat")

    def test_damaged_current_backup_cannot_reimport_stale_legacy_facts(self):
        legacy = Path(self.tmp.name) / "legacy.json"
        legacy.write_text(json.dumps({"notes": {"forgotten": {"value": "synthetic old detail"}}}))
        mm.BACKUP_PATH.write_text("{broken backup")
        with patch.object(mm, "_LEGACY_MEMORY_PATH", legacy):
            for _ in range(2):
                self.assertNotIn("forgotten", mm.load_memory()["notes"])
        self.assertFalse(mm.MEMORY_PATH.exists())
        self.assertEqual(mm.BACKUP_PATH.read_text(), "{broken backup")
        self.assertTrue(legacy.exists())

    def test_quarantined_primary_blocks_legacy_reimport_on_later_reads(self):
        legacy = Path(self.tmp.name) / "legacy.json"
        legacy.write_text(json.dumps({"notes": {"forgotten": {"value": "synthetic old detail"}}}))
        mm.MEMORY_PATH.write_text("{damaged current")
        with patch.object(mm, "_LEGACY_MEMORY_PATH", legacy):
            self.assertNotIn("forgotten", mm.load_memory()["notes"])
            self.assertNotIn("forgotten", mm.load_memory()["notes"])
        self.assertFalse(mm.MEMORY_PATH.exists())
        self.assertEqual(len(list(mm.MEMORY_PATH.parent.glob("long_term.corrupt-*"))), 1)

    def test_repeated_recovery_never_overwrites_earlier_damaged_files(self):
        mm.BACKUP_PATH.write_text('{"notes":{}}')
        with patch("time.time", return_value=100):
            for broken in ("{first damaged", "{second damaged"):
                mm.MEMORY_PATH.write_text(broken)
                mm.load_memory()
        preserved = list(mm.MEMORY_PATH.parent.glob("long_term.corrupt-*"))
        self.assertEqual({path.read_text() for path in preserved}, {"{first damaged", "{second damaged"})

    def test_unrecoverable_memory_reports_failure_without_exposing_fact_contents(self):
        mm.MEMORY_PATH.write_text("{synthetic-private-content")
        messages = []
        with patch.object(mm, "_trim_notifier", messages.append):
            mm.load_memory()
        self.assertTrue(any("kurtarılamadı" in message for message in messages))
        self.assertFalse(any("synthetic-private-content" in message for message in messages))

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

    def test_missing_primary_last_session_reads_good_backup_without_writing(self):
        session = {"date": "2026-11-25", "summary": "Sentetik proje devam ediyor"}
        mm.BACKUP_PATH.write_text(json.dumps({"sessions": [session]}))
        before = {p: p.read_bytes() for p in mm.MEMORY_PATH.parent.iterdir()}
        with patch.object(mm.os, "replace", side_effect=OSError("read only")) as replace:
            self.assertEqual(mm.pop_last_session(), session)
            self.assertEqual(mm.pop_last_session(), session)
        replace.assert_not_called()
        self.assertEqual({p: p.read_bytes() for p in mm.MEMORY_PATH.parent.iterdir()}, before)

    def test_corrupt_primary_last_session_falls_back_without_recovery_writes(self):
        session = {"date": "2026-11-24", "summary": "Son sağlam oturum"}
        mm.MEMORY_PATH.write_text("{broken")
        mm.BACKUP_PATH.write_text(json.dumps({"sessions": [session]}))
        before = {p: p.read_bytes() for p in mm.MEMORY_PATH.parent.iterdir()}
        with patch.object(mm.os, "replace", side_effect=OSError("read only")) as replace:
            self.assertEqual(mm.pop_last_session(), session)
        replace.assert_not_called()
        self.assertEqual({p: p.read_bytes() for p in mm.MEMORY_PATH.parent.iterdir()}, before)

    def test_intentionally_empty_session_list_does_not_revive_backup_session(self):
        mm.MEMORY_PATH.write_text('{"sessions":[]}')
        mm.BACKUP_PATH.write_text('{"sessions":[{"summary":"old private session"}]}')
        self.assertIsNone(mm.pop_last_session())

    def test_invalid_backup_fields_cannot_supply_a_session(self):
        mm.BACKUP_PATH.write_text('{"notes":[],"sessions":[{"summary":"invalid backup"}]}')
        self.assertIsNone(mm.pop_last_session())

    def test_malformed_last_session_cannot_escape_as_a_string(self):
        mm.MEMORY_PATH.write_text('{"sessions":["bad session"]}')
        self.assertIsNone(mm.pop_last_session())

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
