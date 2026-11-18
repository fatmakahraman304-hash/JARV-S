import unittest

from core.blender_commands import scene_command


class BlenderCommands(unittest.TestCase):
    def test_reported_command_keeps_all_arguments(self):
        request = "Gazimağusa esintili, 11 binalı ve bir parklı sahil mahallesi oluştur. Projeyi ve renderi aç"
        self.assertEqual(scene_command(request), {"action": "new", "request": request, "result": "both"})

    def test_distinguishes_preview_scene_and_launcher(self):
        self.assertEqual(scene_command("Blender'da bir ev modelle, render al")["result"], "render")
        self.assertEqual(scene_command("/blender Fütüristik lamba, projeyi aç")["result"], "open")
        self.assertEqual(scene_command("Blender'da bir ev tasarla")["result"], "save")
        self.assertEqual(scene_command("Blender’da mevcut projeye bir kanat ekle")["action"], "edit")
        self.assertEqual(scene_command("/blender Son sahnede kanatları büyüt")["action"], "edit")
        for text in ("Blender'ı aç", "Blender'da nasıl ev yapılır?", "Bir mahalle resmi yap",
                     "Blender'da bina oluşturma",
                     "[FILE_UPLOADED] Blender projesi oluştur"):
            self.assertIsNone(scene_command(text), text)
