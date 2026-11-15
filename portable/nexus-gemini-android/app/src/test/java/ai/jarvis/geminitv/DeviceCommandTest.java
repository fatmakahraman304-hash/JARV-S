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

    @Test public void doesNotTreatQuestionsOrQuotedInstructionsAsActions() {
        assertNull(DeviceCommand.parse("Chrome’u açabilir misin?"));
        assertNull(DeviceCommand.parse("Chrome’u aç?"));
        assertNull(DeviceCommand.parse("Bana 'Chrome’u aç' demeyi öğret"));
        assertNull(DeviceCommand.parse("javascript:alert(1)"));
        assertNull(DeviceCommand.parse("Uyu"));
    }
}
