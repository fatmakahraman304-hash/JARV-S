package ai.jarvis.geminitv;

import static org.junit.Assert.assertEquals;
import org.junit.Test;

public class VoiceControlTest {
    @Test public void muteCommandsDoNotRequireButtons() {
        assertEquals(VoiceControl.Command.MUTE, VoiceControl.classify("Sus"));
        assertEquals(VoiceControl.Command.MUTE, VoiceControl.classify("JARVIS, SUS!"));
        assertEquals(VoiceControl.Command.MUTE, VoiceControl.classify("sessiz ol"));
        assertEquals(VoiceControl.Command.MUTE, VoiceControl.classify("sesini kapat"));
    }
    @Test public void resumeSpeechWhenMuted() {
        assertEquals(VoiceControl.Command.UNMUTE, VoiceControl.classify("konuş"));
        assertEquals(VoiceControl.Command.UNMUTE, VoiceControl.classify("Jarvis konuş"));
        assertEquals(VoiceControl.Command.UNMUTE, VoiceControl.classify("Konuşmaya başla."));
        assertEquals(VoiceControl.Command.UNMUTE, VoiceControl.classify("sesini aç"));
    }
    @Test public void sleepAndWakeAreSeparateFromMute() {
        assertEquals(VoiceControl.Command.SLEEP, VoiceControl.classify("Uyu"));
        assertEquals(VoiceControl.Command.SLEEP, VoiceControl.classify("JARVİS, UYU!"));
        assertEquals(VoiceControl.Command.SLEEP, VoiceControl.classify("Jarvis uyku modu"));
        assertEquals(VoiceControl.Command.WAKE, VoiceControl.classify("JARVIS uyan."));
        assertEquals(VoiceControl.Command.WAKE, VoiceControl.classify("Uyan"));
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify("Uyu ne demek?"));
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify("Jarvis uyanınca ne olur?"));
    }
    @Test public void doNotMistakeQuestionsForCommands() {
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify("Sus ne demek?"));
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify("Herkes sus dediğinde ne olur?"));
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify("Ne zaman konuşalım?"));
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify("Merhaba JARVIS, beni duyuyor musun?"));
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify(""));
        assertEquals(VoiceControl.Command.NONE, VoiceControl.classify(null));
    }
}
