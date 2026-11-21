package com.jarvis.alici;

import android.util.Base64;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Field;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;

/** The shared gist every MAYK device uses (desktop: core/sync_hub.py). */
final class Gist {
    private final String token, id;
    private String etag = "";
    private Map<String, String> cache;

    Gist(String token, String id) { this.token = token; this.id = id; }

    private HttpURLConnection open(String method, String path) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL("https://api.github.com" + path).openConnection();
        try {
            c.setRequestMethod(method);
        } catch (java.net.ProtocolException e) {          // very old stacks without PATCH
            Field f = HttpURLConnection.class.getDeclaredField("method");
            f.setAccessible(true);
            f.set(c, method);
        }
        c.setConnectTimeout(15000);
        c.setReadTimeout(30000);
        c.setRequestProperty("Authorization", "Bearer " + token);
        c.setRequestProperty("Accept", "application/vnd.github+json");
        c.setRequestProperty("User-Agent", "JARVIS-Alici");
        return c;
    }

    private static String read(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        return out.toString("UTF-8");
    }

    /** Files of the gist; the cached copy when nothing changed (304). */
    Map<String, String> files() throws Exception {
        HttpURLConnection c = open("GET", "/gists/" + id);
        if (!etag.isEmpty() && cache != null) c.setRequestProperty("If-None-Match", etag);
        int code = c.getResponseCode();
        if (code == 304 && cache != null) { c.disconnect(); return cache; }
        if (code != 200) { c.disconnect(); throw new Exception("GitHub " + code); }
        String nextTag = c.getHeaderField("ETag");
        JSONObject files;
        try (InputStream in = c.getInputStream()) {
            files = new JSONObject(read(in)).getJSONObject("files");
        } finally {
            c.disconnect();
        }
        Map<String, String> out = new HashMap<>();
        for (Iterator<String> it = files.keys(); it.hasNext(); ) {
            String name = it.next();
            JSONObject f = files.getJSONObject(name);
            if (f.optBoolean("truncated")) {
                if (!name.startsWith("inbox-") && !name.startsWith("device-")) continue;   // not needed here
                URL raw = new URL(f.getString("raw_url"));
                if (!"https".equals(raw.getProtocol()) || !"gist.githubusercontent.com".equalsIgnoreCase(raw.getAuthority()))
                    throw new java.io.IOException("Beklenmeyen Gist dosya adresi.");
                HttpURLConnection r = (HttpURLConnection) raw.openConnection();
                r.setInstanceFollowRedirects(false);
                r.setConnectTimeout(15000);
                r.setReadTimeout(30000);
                r.setRequestProperty("Authorization", "Bearer " + token);
                try {
                    if (r.getResponseCode() != 200) throw new java.io.IOException("Gist dosyası alınamadı.");
                    try (InputStream in = r.getInputStream()) { out.put(name, read(in)); }
                } finally {
                    r.disconnect();
                }
            } else {
                out.put(name, f.optString("content", ""));
            }
        }
        etag = nextTag == null ? "" : nextTag;
        cache = out;
        return out;
    }

    void write(Map<String, String> files) throws Exception {
        JSONObject body = new JSONObject(), fs = new JSONObject();
        for (Map.Entry<String, String> e : files.entrySet()) fs.put(e.getKey(), new JSONObject().put("content", e.getValue()));
        body.put("files", fs);
        HttpURLConnection c = open("PATCH", "/gists/" + id);
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type", "application/json");
        try (OutputStream o = c.getOutputStream()) { o.write(body.toString().getBytes(StandardCharsets.UTF_8)); }
        int code = c.getResponseCode();
        if (code >= 300) throw new Exception("GitHub " + code);
        etag = "";
        cache = null;
    }

    /** {g: gemini, t: token, i: gist, n: name} from a MAYK setup link (…#s=…). */
    static JSONObject parseSetup(String text) {
        try {
            String s = text.trim();
            int k = s.indexOf("s=");
            if (k >= 0) s = s.substring(k + 2);
            s = s.replaceAll("[^A-Za-z0-9_\\-]", "");
            byte[] raw = Base64.decode(s, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
            JSONObject j = new JSONObject(new String(raw, StandardCharsets.UTF_8));
            return j.optString("t").isEmpty() || j.optString("i").isEmpty() ? null : j;
        } catch (Exception e) {
            return null;
        }
    }
}
