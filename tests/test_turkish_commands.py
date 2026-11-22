"""AETHER Türkçe komutları: ses, yazı ve GitHub kısa yolları."""

import unittest

from core.intent import kind, should_act
from core.snap_wake import is_sleep_command
from core.voice_commands import is_close_command, normalize_command
from plugins.github_develop import local_command_mode


class TurkishNormalization(unittest.TestCase):
    def test_turkish_case_accents_and_punctuation(self):
        self.assertEqual(normalize_command("AETHER’I KAPAT!"), "aether i kapat")
        self.assertEqual(normalize_command("Aether uygulamasından çık."), "aether uygulamasindan cik")
        self.assertEqual(normalize_command("GITHUB TESTLERİNİ ÇALIŞTIR"), "github testlerini calistir")


class ApplicationClose(unittest.TestCase):
    def test_clear_turkish_commands(self):
        for phrase in (
            "AETHER uygulamasını kapat",
            "AETHER, uygulamasından çık!",
            "AETHER'ı kapat",
            "AETHER’I KAPAT!",
            "AETHER'ı kapatır mısın?",
            "AETHER kendini kapat",
            "AETHER programını kapat",
            "Aether çıkış yap",
            "lütfen AETHER uygulamasını kapat",
            "close the aether app",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_close_command(phrase))

    def test_does_not_close_on_questions_or_other_targets(self):
        for phrase in (
            "Bilgisayarı kapat",
            "Spotify uygulamasını kapat",
            "AETHER uygulamasını kapattın mı?",
            "AETHER nasıl kapatılır?",
            "AETHER kamera görüntüsünü kapat",
            "AETHER uygulamasını kapatma",
            "Aether güncellemeyi kapat",
        ):
            with self.subTest(phrase=phrase):
                self.assertFalse(is_close_command(phrase))


class SleepCommands(unittest.TestCase):
    def test_turkish_sleep_synonyms(self):
        for phrase in (
            "uyu", "AETHER uyu", "AETHER artık uyu",
            "Aether uykuya geç", "AETHER uyku moduna geç",
            "AETHER uyku modunu aç", "Aether, dinlemeyi bırak",
            "AETHER DİNLEMEYİ DURDUR",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_sleep_command(phrase))

    def test_not_an_unrelated_stop(self):
        for phrase in ("müziği durdur", "dosyayı kapat", "AETHER güncellemeyi durdur"):
            with self.subTest(phrase=phrase):
                self.assertFalse(is_sleep_command(phrase))


class TurkishIntent(unittest.TestCase):
    def test_status_questions_do_not_act(self):
        for phrase in ("Güncelledin mi?", "Test ettin mi?", "Kontrol ettin mi?", "Başlattın mı?"):
            with self.subTest(phrase=phrase):
                self.assertEqual(kind(phrase), "status")
                self.assertFalse(should_act(phrase))

    def test_natural_turkish_requests_are_commands(self):
        for phrase in (
            "İnternette araştır", "Bilgisayardaki dosyayı bul",
            "Bu projeyi güncelle", "GitHub testlerini çalıştır",
            "Telefonuma gönder", "Bunu özetle", "Lütfen ekranı kontrol et",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(kind(phrase), "task")


class GithubCommands(unittest.TestCase):
    def test_turkish_direct_commands(self):
        for phrase, expected in (
            ("/git test", "test"),
            ("GITHUB TESTLERİNİ ÇALIŞTIR!", "test"),
            ("Aether GitHub testlerini çalıştır", "test"),
            ("GitHub geliştirme alanını ana dal ile eşitle", "sync"),
            ("GitHub geliştirme dalını güncelle.", "sync"),
            ("/git sync", "sync"),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(local_command_mode(phrase), expected)

    def test_unrelated_words_do_not_trigger_development(self):
        self.assertIsNone(local_command_mode("github testlerini çalıştırdın mı?"))


if __name__ == "__main__":
    unittest.main()
