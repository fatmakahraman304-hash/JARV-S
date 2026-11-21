"""MAYK Türkçe komutları: ses, yazı ve GitHub kısa yolları."""

import unittest

from core.intent import kind, should_act
from core.snap_wake import is_sleep_command
from core.voice_commands import is_close_command, normalize_command
from plugins.github_develop import local_command_mode


class TurkishNormalization(unittest.TestCase):
    def test_turkish_case_accents_and_punctuation(self):
        self.assertEqual(normalize_command("MAYK’I KAPAT!"), "mayk i kapat")
        self.assertEqual(normalize_command("Mayk uygulamasından çık."), "mayk uygulamasindan cik")
        self.assertEqual(normalize_command("GITHUB TESTLERİNİ ÇALIŞTIR"), "github testlerini calistir")


class ApplicationClose(unittest.TestCase):
    def test_clear_turkish_commands(self):
        for phrase in (
            "MAYK uygulamasını kapat",
            "MAYK, uygulamasından çık!",
            "MAYK'ı kapat",
            "MAYK’I KAPAT!",
            "MAYK'ı kapatır mısın?",
            "MAYK kendini kapat",
            "MAYK programını kapat",
            "Mayk çıkış yap",
            "lütfen MAYK uygulamasını kapat",
            "close the mayk app",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_close_command(phrase))

    def test_does_not_close_on_questions_or_other_targets(self):
        for phrase in (
            "Bilgisayarı kapat",
            "Spotify uygulamasını kapat",
            "MAYK uygulamasını kapattın mı?",
            "MAYK nasıl kapatılır?",
            "MAYK kamera görüntüsünü kapat",
            "MAYK uygulamasını kapatma",
            "Mayk güncellemeyi kapat",
        ):
            with self.subTest(phrase=phrase):
                self.assertFalse(is_close_command(phrase))


class SleepCommands(unittest.TestCase):
    def test_turkish_sleep_synonyms(self):
        for phrase in (
            "uyu", "MAYK uyu", "MAYK artık uyu",
            "Mayk uykuya geç", "MAYK uyku moduna geç",
            "MAYK uyku modunu aç", "Mayk, dinlemeyi bırak",
            "MAYK DİNLEMEYİ DURDUR",
        ):
            with self.subTest(phrase=phrase):
                self.assertTrue(is_sleep_command(phrase))

    def test_not_an_unrelated_stop(self):
        for phrase in ("müziği durdur", "dosyayı kapat", "MAYK güncellemeyi durdur"):
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
            ("Mayk GitHub testlerini çalıştır", "test"),
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
