package ai.jarvis.geminitv;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

import java.io.InterruptedIOException;
import java.net.HttpURLConnection;
import java.net.URL;
import org.junit.Test;

public class GeminiHttpTest {
    @Test public void cancelledCallRejectsLateConnection() {
        GeminiHttp.Call call = new GeminiHttp.Call();
        assertNull(call.cancel());
        assertFalse(call.attach(null));
    }

    @Test public void cancellationReturnsOnlyItsOwnConnection() throws Exception {
        URL url = new URL("https://example.invalid");
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        GeminiHttp.Call first = new GeminiHttp.Call();
        GeminiHttp.Call next = new GeminiHttp.Call();
        assertTrue(first.attach(connection));
        assertSame(connection, first.cancel());
        first.detach();
        assertNull(first.cancel());
        next.checkActive();
        connection.disconnect();
    }

    @Test(expected = InterruptedIOException.class)
    public void cancelledCallStopsProcessing() throws Exception {
        GeminiHttp.Call call = new GeminiHttp.Call();
        call.cancel();
        call.checkActive();
    }

    @Test public void onlyCredentialOrRequestErrorsOfferKeyReplacement() {
        assertTrue(new GeminiHttp.ApiError(400).canReplaceKey());
        assertTrue(new GeminiHttp.ApiError(401).canReplaceKey());
        assertTrue(new GeminiHttp.ApiError(403).canReplaceKey());
        assertFalse(new GeminiHttp.ApiError(404).canReplaceKey());
        assertFalse(new GeminiHttp.ApiError(429).canReplaceKey());
        assertFalse(new GeminiHttp.ApiError(503).canReplaceKey());
    }
}
