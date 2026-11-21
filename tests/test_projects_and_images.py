"""Projects survive restarts (journal, staged builds, resume) and Mayk draws pictures."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class JournalTest(unittest.TestCase):
    def setUp(self):
        from memory import continuity
        self.c = continuity
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(continuity, "data_dir", return_value=Path(self.tmp.name))
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_start_update_recover(self):
        pid = self.c.project_start("build", "site", "/x/site", "bana site yap")
        self.c.project_update(pid, stage=2, stages={"plan": {"stages": [{"title": "a"}, {"title": "b"}, {"title": "c"}]}})
        self.assertEqual(self.c.projects(unfinished_only=True)[0]["status"], "çalışıyor")
        self.c.recover_jobs()                               # Mayk restarted mid-job
        p = self.c.project(pid)
        self.assertEqual(p["status"], "yarıda kaldı")
        self.assertEqual(p["stage"], 2)
        self.assertIn("aşama 2/3", self.c.prompt_context())
        self.c.project_update(pid, status="bitti")
        self.assertEqual(self.c.projects(unfinished_only=True), [])
        self.assertNotIn("UNFINISHED", self.c.prompt_context())


class StagedBuildTest(unittest.TestCase):
    def test_stages_run_in_order_and_resume_skips_done(self):
        from actions import dev_agent
        with tempfile.TemporaryDirectory() as d:
            plan = {"project_name": "site", "summary": "Bir site",
                    "stages": [{"title": "Yapı", "goal": "iskelet", "done": False},
                               {"title": "Sayfalar", "goal": "sayfalar", "done": False}],
                    "present": {"type": "none"}}
            ran, journal = [], []
            with mock.patch.object(dev_agent, "PROJECTS_DIR", Path(d)), \
                 mock.patch.object(dev_agent, "_plan_stages", return_value=json.loads(json.dumps(plan))), \
                 mock.patch.object(dev_agent, "_improve_folder", side_effect=lambda f, instr, pl, open_editor=True: ran.append(instr) or "ok"), \
                 mock.patch.object(dev_agent, "_journal", side_effect=lambda pid, **k: journal.append(k)), \
                 mock.patch.object(dev_agent, "_open_vscode"):
                msg = dev_agent._build_staged("bana site yap", "html", "", None, 7)
                self.assertEqual(len(ran), 2)
                self.assertIn("STAGE 1/2: Yapı", ran[0])
                self.assertIn("STAGE 2/2: Sayfalar", ran[1])
                self.assertTrue((Path(d) / "site" / "README.md").exists())
                self.assertIn("2 stages", msg)
                # resume after stage 1: only stage 2 runs
                ran.clear()
                half = json.loads(json.dumps(plan))
                half["stages"][0]["done"] = True
                dev_agent._build_staged("bana site yap", "html", "", None, 7, plan=half, folder=Path(d) / "site")
                self.assertEqual(len(ran), 1)
                self.assertIn("STAGE 2/2", ran[0])

    def test_resume_picks_interrupted_job(self):
        from actions import dev_agent
        with tempfile.TemporaryDirectory() as d:
            pend = [{"id": 3, "kind": "improve", "title": "app", "folder": d, "instruction": "indirim ekle",
                     "status": "yarıda kaldı", "stage": 0, "stages": []}]
            got = {}
            with mock.patch("memory.continuity.projects", return_value=pend), \
                 mock.patch.object(dev_agent, "_journal"), \
                 mock.patch.object(dev_agent, "_new_job"), \
                 mock.patch.object(dev_agent, "_run_job", side_effect=lambda job, name, who, speak, player, pid=None: got.update(name=name, pid=pid) or "started"):
                self.assertEqual(dev_agent._start_resume(""), "started")
            dev_agent._job_lock.release()
            self.assertEqual(got, {"name": "app", "pid": 3})


class ImageStudioTest(unittest.TestCase):
    def test_falls_back_to_next_model_and_remembers_last(self):
        from core import image_studio
        png = base64.b64encode(b"\x89PNG fake").decode()
        calls = []

        def fake_call(model, key, parts, aspect):
            calls.append((model, parts))
            if model == image_studio.MODELS[0]:
                return None, "", "404 model not found"
            return base64.b64decode(png), "image/png", "işte"
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(image_studio, "out_dir", return_value=Path(d)), \
             mock.patch.object(image_studio, "_STATE", Path(d) / "state.json"), \
             mock.patch.object(image_studio, "_key", return_value="k"), \
             mock.patch.object(image_studio, "_call", side_effect=fake_call):
            path, info = image_studio.make("a red fox")
            self.assertTrue(path.is_file())
            self.assertEqual([c[0] for c in calls], list(image_studio.MODELS[:2]))
            self.assertEqual(image_studio.last_image(), path)
            calls.clear()
            path2, _ = image_studio.make("make it blue", edit_from=image_studio.last_image())
            self.assertIn("inlineData", calls[0][1][0])          # the old picture goes with the edit
            self.assertIn("make it blue", calls[0][1][1]["text"])
            self.assertNotEqual(path, path2)

    def test_refusal_is_not_retried(self):
        from core import image_studio
        calls = []
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(image_studio, "_STATE", Path(d) / "state.json"), \
             mock.patch.object(image_studio, "_key", return_value="k"), \
             mock.patch.object(image_studio, "_call", side_effect=lambda *a: calls.append(1) or (None, "", "blocked: SAFETY")):
            path, msg = image_studio.make("x")
        self.assertIsNone(path)
        self.assertEqual(len(calls), 1)
        self.assertIn("güvenlik", msg)

    def test_no_gemini_quota_uses_free_painter_and_rests_gemini(self):
        from core import image_studio
        gem, free = [], []
        no_quota = "429 You exceeded your current quota ... free_tier_requests, limit: 0"

        def fake_free(en, aspect, seed):
            free.append((en, aspect, seed))
            return b"\xff\xd8 fake jpeg" * 200, "image/jpeg", ""
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(image_studio, "out_dir", return_value=Path(d)), \
             mock.patch.object(image_studio, "_STATE", Path(d) / "state.json"), \
             mock.patch.object(image_studio, "_key", return_value="k"), \
             mock.patch.object(image_studio, "describe", side_effect=lambda p, base="": f"EN[{base}|{p}]"), \
             mock.patch.object(image_studio, "_call", side_effect=lambda *a: gem.append(a[0]) or (None, "", no_quota)), \
             mock.patch.object(image_studio, "_free_call", side_effect=fake_free):
            path, _ = image_studio.make("kırmızı bir tilki", aspect="16:9")
            self.assertTrue(path.is_file())
            self.assertEqual(gem, list(image_studio.MODELS))
            self.assertTrue(image_studio.gemini_resting())
            self.assertEqual(free[0][:2], ("EN[|kırmızı bir tilki]", "16:9"))
            # resting: Gemini is not asked again; the edit keeps the seed and builds on the old description
            gem.clear()
            path2, _ = image_studio.make("mavi yap", edit_from=path)
            self.assertEqual(gem, [])
            self.assertEqual(free[1][0], "EN[EN[|kırmızı bir tilki]|mavi yap]")
            self.assertEqual(free[1][2], free[0][2])
            self.assertNotEqual(path, path2)

    def test_free_painter_failure_is_explained(self):
        from core import image_studio
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(image_studio, "_STATE", Path(d) / "state.json"), \
             mock.patch.object(image_studio, "_key", return_value=""), \
             mock.patch.object(image_studio, "_free_call", return_value=(None, "", "503 busy")):
            path, msg = image_studio.make("a cat")
        self.assertIsNone(path)
        self.assertIn("503", msg)

    def test_size_follows_aspect(self):
        from core import image_studio
        self.assertEqual(image_studio._size("1:1"), (1024, 1024))
        self.assertEqual(image_studio._size("16:9"), (1024, 576))
        self.assertEqual(image_studio._size("9:16"), (576, 1024))
        self.assertEqual(image_studio._size("nonsense"), (1024, 1024))

    def test_plugin_edit_without_picture(self):
        from plugins import generate_image
        with mock.patch("core.image_studio.last_image", return_value=None):
            self.assertIn("resim yok", generate_image.run({"prompt": "mavi yap", "mode": "edit"}))


if __name__ == "__main__":
    unittest.main()
