package ai.jarvis.geminitv;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import org.junit.Test;

public class DeviceCommandTest {
    @Test public void launchesFromCommonSpokenAndWrittenForms() {
        assertEquals(DeviceCommand.Action.CHROME, DeviceCommand.parse("JARVİS, Chrome’u aç!").action);
        assertEquals(DeviceCommand.Action.CHROME, DeviceCommand.parse("chromu aç").action);
        assertEquals(DeviceCommand.Action.BROWSER, DeviceCommand.parse("Tarayıcıyı aç.").action);
        assertEquals(DeviceCommand.Action.YOUTUBE, DeviceCommand.parse("YouTube'u aç").action);
        assertEquals(DeviceCommand.Action.SETTINGS, DeviceCommand.parse("Android ayarlarını aç").action);
        assertEquals(DeviceCommand.Action.HELP, DeviceCommand.parse("cihaz komutları").action);
    }

    @Test public void keepsSearchTextSeparateFromAction() {
        DeviceCommand command = DeviceCommand.parse("YouTube’da İstanbul & caz ara");
        assertEquals(DeviceCommand.Action.YOUTUBE_SEARCH, command.action);
        assertEquals("İstanbul & caz", command.argument);
        command = DeviceCommand.parse("Google'da ara: C++");
        assertEquals(DeviceCommand.Action.WEB_SEARCH, command.action);
        assertEquals("C++", command.argument);
        assertEquals("", DeviceCommand.parse("webde ara").argument);
    }

    @Test public void appNameIsExplicit() {
        assertEquals("Netflix", DeviceCommand.parse("Netflix uygulamasını aç").argument);
        assertEquals("Disney+", DeviceCommand.parse("uygulamayı aç: Disney+").argument);
    }

    @Test public void parsesVolumeAndMediaControls() {
        assertEquals(DeviceCommand.Action.VOLUME_UP, DeviceCommand.parse("Jarvis, sesi yükselt").action);
        assertEquals(DeviceCommand.Action.VOLUME_DOWN, DeviceCommand.parse("Sesi kıs.").action);
        DeviceCommand volume = DeviceCommand.parse("Sesi yüzde 40’a ayarla");
        assertEquals(DeviceCommand.Action.VOLUME_SET, volume.action);
        assertEquals("40", volume.argument);
        assertEquals(false, volume.leavesJarvis());
        assertEquals(DeviceCommand.Action.MEDIA_PLAY, DeviceCommand.parse("Videoyu oynat").action);
        assertEquals(DeviceCommand.Action.MEDIA_PAUSE, DeviceCommand.parse("Videoyu duraklat").action);
        assertEquals(DeviceCommand.Action.WIFI, DeviceCommand.parse("Wi-Fi ayarlarını aç").action);
        assertEquals(DeviceCommand.Action.BLUETOOTH, DeviceCommand.parse("Bluetooth ayarlarını aç").action);
        assertNull(DeviceCommand.parse("Sesi nasıl yükseltirim?"));
    }

    @Test public void opensOnlyKnownTitlesAndExplicitYoutubeLinks() {
        DeviceCommand episode = DeviceCommand.parse("YouTube’da Eşref 1. bölümü aç");
        assertEquals(DeviceCommand.Action.YOUTUBE_PLAY, episode.action);
        assertEquals("IWZr0PdZfSM", MediaLinks.youtubeId(episode.argument));
        assertEquals("IWZr0PdZfSM", MediaLinks.youtubeId("https://youtu.be/IWZr0PdZfSM?si=example"));
        assertEquals("IWZr0PdZfSM", MediaLinks.youtubeId("https://www.youtube.com/watch?v=IWZr0PdZfSM"));
        assertNull(MediaLinks.youtubeId("https://www.youtube.com/watch?v=IWZr0PdZfSM&v=IWZr0PdZfSM"));
        assertNull(MediaLinks.youtubeId("https://youtu.be"));
        assertNull(MediaLinks.youtubeId("https://youtube.com.example.org/watch?v=IWZr0PdZfSM"));
        assertNull(MediaLinks.youtubeId("https://www.youtube.com@other.example/watch?v=IWZr0PdZfSM"));
        assertNull(MediaLinks.youtubeId("Eşref 10. bölümü"));
        DeviceCommand film = DeviceCommand.parse("Chromuda Endgame filmini aç");
        assertEquals(DeviceCommand.Action.FILM, film.action);
        assertEquals("Endgame", film.argument);
        org.junit.Assert.assertTrue(MediaLinks.officialFilm(film.argument).startsWith("https://www.disneyplus.com/"));
        assertNull(MediaLinks.officialFilm("Başka film"));
    }

    @Test public void doesNotTreatQuestionsOrQuotedInstructionsAsActions() {
        assertNull(DeviceCommand.parse("Chrome’u açabilir misin?"));
        assertNull(DeviceCommand.parse("Chrome’u aç?"));
        assertNull(DeviceCommand.parse("Bana 'Chrome’u aç' demeyi öğret"));
        assertNull(DeviceCommand.parse("javascript:alert(1)"));
        assertNull(DeviceCommand.parse("Uyu"));
    }
}
