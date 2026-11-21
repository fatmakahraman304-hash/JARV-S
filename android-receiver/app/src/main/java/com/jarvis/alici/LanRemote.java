package com.jarvis.alici;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.wifi.WifiManager;
import android.text.format.Formatter;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;

/** Same-Wi-Fi HTTP remote. Runs independently of GitHub and never exposes GitHub credentials. */
final class LanRemote {
    interface Handler { String command(String op, String arg); }
    private final Context context;
    private final Handler handler;
    private ServerSocket server;
    private volatile boolean running;
    private String secret;
    private String address = "";

    LanRemote(Context context, Handler handler) { this.context = context; this.handler = handler; }

    String address() { return address; }

    void start() throws Exception {
        SharedPreferences p = ReceiverService.prefs(context);
        secret = p.getString("lan_secret", "");
        if (secret.length() < 32) {
            byte[] b = new byte[24]; new SecureRandom().nextBytes(b);
            StringBuilder hex = new StringBuilder();
            for (byte v : b) hex.append(String.format(java.util.Locale.US, "%02x", v & 255));
            secret = hex.toString();
            p.edit().putString("lan_secret", secret).apply();
        }
        WifiManager wifi = (WifiManager) context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        String ip = wifi == null ? "" : Formatter.formatIpAddress(wifi.getConnectionInfo().getIpAddress());
        if (ip.isEmpty() || "0.0.0.0".equals(ip)) throw new IOException("Wi-Fi IP bulunamadı");
        server = new ServerSocket(18765, 8, InetAddress.getByName(ip));
        address = "http://" + ip + ":18765/" + secret;
        running = true;
        new Thread(() -> {
            while (running) {
                try { Socket socket = server.accept(); new Thread(() -> handle(socket), "lan-client").start(); }
                catch (Exception e) { if (running) android.util.Log.w("MAYK-LAN", "accept", e); }
            }
        }, "mayk-lan").start();
    }

    void stop() { running = false; try { if (server != null) server.close(); } catch (Exception ignored) {} }

    private void handle(Socket socket) {
        try (Socket s = socket) {
            s.setSoTimeout(5000);
            InputStream in = new BufferedInputStream(s.getInputStream());
            ByteArrayOutputStream headers = new ByteArrayOutputStream();
            int b;
            while ((b = in.read()) != -1 && headers.size() < 8192) {
                headers.write(b);
                byte[] bytes = headers.toByteArray(); int n = bytes.length;
                if (n >= 4 && bytes[n-4] == 13 && bytes[n-3] == 10 && bytes[n-2] == 13 && bytes[n-1] == 10) break;
            }
            String[] lines = headers.toString("UTF-8").split("\\r\\n");
            if (lines.length == 0) return;
            String[] first = lines[0].split(" ");
            if (first.length < 2) return;
            String method = first[0], path = first[1];
            if (!path.equals("/" + secret) && !path.equals("/" + secret + "/cmd")) { respond(s, 404, "Bulunamadı"); return; }
            if ("GET".equals(method) && path.equals("/" + secret)) { respond(s, 200, page()); return; }
            if (!"POST".equals(method) || !path.endsWith("/cmd")) { respond(s, 405, "İzin verilmiyor"); return; }
            int len = -1; String origin = "", host = "";
            for (String line : lines) {
                String low = line.toLowerCase(java.util.Locale.US);
                if (low.startsWith("content-length:")) len = Integer.parseInt(line.substring(line.indexOf(':') + 1).trim());
                if (low.startsWith("origin:")) origin = line.substring(line.indexOf(':') + 1).trim();
                if (low.startsWith("host:")) host = line.substring(line.indexOf(':') + 1).trim();
            }
            if (!origin.isEmpty() && !origin.equals("http://" + host)) { respond(s, 403, "Kaynak reddedildi"); return; }
            if (len < 1 || len > 2048) { respond(s, 400, "Geçersiz istek"); return; }
            byte[] body = new byte[len]; int pos = 0;
            while (pos < len) { int n = in.read(body, pos, len-pos); if (n < 0) return; pos += n; }
            String op = "", arg = "";
            for (String pair : new String(body, StandardCharsets.UTF_8).split("&")) {
                int eq = pair.indexOf('='); if (eq < 0) continue;
                String k = URLDecoder.decode(pair.substring(0,eq), "UTF-8");
                String v = URLDecoder.decode(pair.substring(eq+1), "UTF-8");
                if ("op".equals(k)) op = v; if ("arg".equals(k)) arg = v;
            }
            if (!("key".equals(op) || "app".equals(op) || "url".equals(op) || "search".equals(op))) { respond(s, 400, "Komut desteklenmiyor"); return; }
            String reply = handler.command(op, arg);
            respond(s, 200, "<meta charset='utf-8'><meta name='viewport' content='width=device-width'><body style='background:#111;color:white;font:20px sans-serif;padding:20px'><p>" + escape(reply) + "</p><a style='color:orange' href='/" + secret + "'>Kumandaya dön</a></body>");
        } catch (Exception e) { android.util.Log.w("MAYK-LAN", "request", e); }
    }

    private String page() {
        StringBuilder h = new StringBuilder("<!doctype html><html lang='tr'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MAYK Yerel Kumanda</title><style>body{background:#100d0a;color:#fff;font:18px sans-serif;padding:15px}button{background:#29221b;color:#fff;border:1px solid #ae783f;border-radius:12px;padding:16px;margin:5px;font-size:19px}input{padding:14px;font-size:18px;max-width:85%}h2{color:#ffa64b}</style><h2>MAYK · Wi-Fi Kumanda</h2><p>GitHub olmadan doğrudan projeksiyonu kontrol et.</p>");
        String[][] keys = {{"Ses +","volume_up"},{"Ses −","volume_down"},{"Sessiz","mute"},{"Ana ekran","home"},{"Geri","back"},{"Yukarı","up"},{"Aşağı","down"},{"Sol","left"},{"Sağ","right"},{"OK","enter"},{"Oynat / durdur","play_pause"}};
        for (String[] k : keys) h.append(form("key", k[1], k[0]));
        h.append("<h3>Uygulamalar</h3>").append(form("app","youtube","YouTube")).append(form("app","netflix","Netflix")).append(form("app","settings","Ayarlar"));
        h.append("<h3>YouTube ara</h3><form method='post' action='/").append(secret).append("/cmd'><input type='hidden' name='op' value='search'><input name='arg' placeholder='Aranacak video'><button>Ara</button></form>");
        h.append("</html>"); return h.toString();
    }
    private String form(String op, String arg, String title) {
        return "<form style='display:inline-block' method='post' action='/" + secret + "/cmd'><input type='hidden' name='op' value='" + op + "'><input type='hidden' name='arg' value='" + arg + "'><button>" + title + "</button></form>";
    }
    private static String escape(String s) { return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"); }
    private void respond(Socket s, int code, String html) throws IOException {
        byte[] b = html.getBytes(StandardCharsets.UTF_8);
        s.getOutputStream().write(("HTTP/1.1 " + code + " OK\\r\\nContent-Type: text/html; charset=utf-8\\r\\nContent-Length: " + b.length + "\\r\\nCache-Control: no-store\\r\\nX-Content-Type-Options: nosniff\\r\\nReferrer-Policy: no-referrer\\r\\nConnection: close\\r\\n\\r\\n").replace("\\r","\r").replace("\\n","\n").getBytes(StandardCharsets.UTF_8));
        s.getOutputStream().write(b); s.getOutputStream().flush();
    }
}
