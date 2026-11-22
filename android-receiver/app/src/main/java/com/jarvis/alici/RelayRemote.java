package com.jarvis.alici;

import android.content.Context;
import android.util.Base64;
import android.util.Log;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * Encrypted HTTPS bridge for the HTTPS MAYK web UI.
 *
 * ntfy.sh only relays opaque AES-256-GCM messages under unguessable topics.
 * The receiver's existing private LAN capability token is never uploaded.
 * This is separate from (and does not modify) the working local Wi-Fi remote.
 */
final class RelayRemote {
    interface Handler { String command(JSONObject request); }

    static volatile String status = "kapalı";
    private static final String ROOT = "https://ntfy.sh/";
    private final Context context;
    private final Handler handler;
    private final Set<String> seen = new LinkedHashSet<>();
    private volatile boolean running;
    private Thread worker;
    private volatile HttpURLConnection current;
    private String secret;
    private String inboundTopic;
    private String outboundTopic;
    private String lastEventId = "";
    private int backoff = 2500;

    RelayRemote(Context context, Handler handler) {
        this.context = context.getApplicationContext();
        this.handler = handler;
    }

    static String digestHex(String value) throws Exception {
        byte[] hash = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder out = new StringBuilder();
        for (byte b : hash) out.append(String.format(java.util.Locale.US, "%02x", b & 255));
        return out.toString();
    }

    private SecretKeySpec key() throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(("mayk-v1-key:" + secret).getBytes(StandardCharsets.UTF_8));
        return new SecretKeySpec(digest, "AES");
    }

    private JSONObject decrypt(String encoded) throws Exception {
        byte[] b = Base64.decode(encoded, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
        if (b.length < 29 || b.length > 6000) throw new IllegalArgumentException("Geçersiz paket");
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Arrays.copyOfRange(b, 0, 12)));
        byte[] plain = c.doFinal(Arrays.copyOfRange(b, 12, b.length));
        return new JSONObject(new String(plain, StandardCharsets.UTF_8));
    }

    private String encrypt(JSONObject message) throws Exception {
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, key(), new GCMParameterSpec(128, nonce));
        byte[] encrypted = c.doFinal(message.toString().getBytes(StandardCharsets.UTF_8));
        byte[] packed = new byte[nonce.length + encrypted.length];
        System.arraycopy(nonce, 0, packed, 0, nonce.length);
        System.arraycopy(encrypted, 0, packed, nonce.length, encrypted.length);
        return Base64.encodeToString(packed, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    void start() {
        if (running) return;
        secret = ReceiverService.prefs(context).getString("lan_secret", "");
        if (!secret.matches("(?i)[a-f0-9]{32,64}")) {
            status = "yerel eşleştirme anahtarı bulunamadı";
            return;
        }
        try {
            inboundTopic = "mayk-" + digestHex("mayk-v1-cmd:" + secret).substring(0, 40);
            outboundTopic = "mayk-" + digestHex("mayk-v1-res:" + secret).substring(0, 40);
        } catch (Exception e) {
            status = "kriptografi hatası";
            return;
        }
        running = true;
        worker = new Thread(this::loop, "mayk-https-relay");
        worker.start();
    }

    void stop() {
        running = false;
        HttpURLConnection con = current;
        if (con != null) con.disconnect();
        if (worker != null) worker.interrupt();
        status = "kapalı";
    }

    private void loop() {
        while (running) {
            try {
                status = "HTTPS bağlanıyor";
                String since = lastEventId.isEmpty()
                        ? String.valueOf(System.currentTimeMillis() / 1000L - 12L)
                        : java.net.URLEncoder.encode(lastEventId, "UTF-8");
                URL url = new URL(ROOT + inboundTopic + "/json?since=" + since);
                HttpURLConnection con = (HttpURLConnection) url.openConnection();
                current = con;
                con.setConnectTimeout(12000);
                con.setReadTimeout(90000);
                con.setRequestProperty("Accept", "application/x-ndjson");
                int code = con.getResponseCode();
                if (code != 200) throw new java.io.IOException("HTTPS " + code);
                backoff = 2500;
                status = "HTTPS bağlı";
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(con.getInputStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while (running && (line = reader.readLine()) != null) {
                        if (line.length() < 3 || line.length() > 12000) continue;
                        JSONObject event;
                        try { event = new JSONObject(line); } catch (Exception ignored) { continue; }
                        if (!"message".equals(event.optString("event"))) continue;
                        String eventId = event.optString("id", "");
                        if (!eventId.isEmpty()) lastEventId = eventId;
                        try { process(event.optString("message", "")); }
                        catch (Exception bad) { Log.w("MAYK-Relay", "Rejected invalid relay event", bad); }
                    }
                } finally { con.disconnect(); current = null; }
            } catch (Exception error) {
                if (!running) break;
                status = "HTTPS bağlantı hatası: " + String.valueOf(error.getMessage());
                Log.w("MAYK-Relay", "Reconnecting", error);
                backoff = Math.min(backoff * 2, 60000);
            }
            if (!running) break;
            try { Thread.sleep(backoff); } catch (InterruptedException ignored) { break; }
        }
    }

    private void process(String opaque) throws Exception {
        JSONObject message = decrypt(opaque);
        if (message.optInt("v") != 1) return;
        String id = message.optString("id", "");
        long ts = message.optLong("ts", 0);
        if (!id.matches("[a-zA-Z0-9_-]{12,80}")
                || Math.abs(System.currentTimeMillis() - ts) > 120000L) return;
        if (!seen.add(id)) return;
        while (seen.size() > 120) seen.remove(seen.iterator().next());
        String op = message.optString("op", "");
        String arg = message.optString("arg", "");
        if (arg.length() > 1000 || !("key".equals(op) || "app".equals(op)
                || "search".equals(op) || "url".equals(op) || "type".equals(op))) return;
        // Only commands authenticated and decrypted with the private local key
        // reach the existing receiver action handler.
        String reply = handler.command(message);
        JSONObject out = new JSONObject().put("v", 1).put("id", id)
                .put("ts", System.currentTimeMillis()).put("reply", reply);
        publish(outboundTopic, encrypt(out));
    }

    private void publish(String topic, String content) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(ROOT + topic).openConnection();
        try {
            byte[] body = content.getBytes(StandardCharsets.UTF_8);
            con.setRequestMethod("POST");
            con.setConnectTimeout(10000);
            con.setReadTimeout(10000);
            con.setDoOutput(true);
            con.setRequestProperty("Content-Type", "text/plain; charset=utf-8");
            con.setFixedLengthStreamingMode(body.length);
            try (OutputStream out = con.getOutputStream()) { out.write(body); }
            int code = con.getResponseCode();
            if (code < 200 || code >= 300) throw new java.io.IOException("HTTPS relay publish " + code);
            try (InputStream ignored = con.getInputStream()) { }
        } finally { con.disconnect(); }
    }
}
