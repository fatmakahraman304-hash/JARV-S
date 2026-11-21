package com.jarvis.alici;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.LinkAddress;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Locale;

/** Same-Wi-Fi HTTP remote. Binds all interfaces and advertises the active Wi-Fi address. */
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

    private String activeWifiIpv4() throws IOException {
        ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm != null) {
            Network active = cm.getActiveNetwork();
            NetworkCapabilities caps = active == null ? null : cm.getNetworkCapabilities(active);
            if (active != null && caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                LinkProperties links = cm.getLinkProperties(active);
                if (links != null) {
                    for (LinkAddress link : links.getLinkAddresses()) {
                        InetAddress ip = link.getAddress();
                        if (ip instanceof Inet4Address && !ip.isLoopbackAddress() && !ip.isLinkLocalAddress()) {
                            return ip.getHostAddress();
                        }
                    }
                }
            }
        }
        throw new IOException("Etkin Wi-Fi IPv4 adresi bulunamadı. Projeksiyonun Android erişim noktasına bağlı olduğunu kontrol et.");
    }

    void start() throws Exception {
        SharedPreferences p = ReceiverService.prefs(context);
        secret = p.getString("lan_secret", "");
        if (secret.length() < 32) {
            byte[] b = new byte[24]; new SecureRandom().nextBytes(b);
            StringBuilder hex = new StringBuilder();
            for (byte v : b) hex.append(String.format(Locale.US, "%02x", v & 255));
            secret = hex.toString();
            p.edit().putString("lan_secret", secret).apply();
        }

        // Do not bind to WifiManager.getConnectionInfo(): on TV boxes it can
        // return a stale/secondary interface address. Listen on all interfaces,
        // but publish only the current Wi-Fi network's IPv4 address.
        String ip = activeWifiIpv4();
        server = new ServerSocket(18765, 16, InetAddress.getByName("0.0.0.0"));
        server.setReuseAddress(true);
        address = "http://" + ip + ":18765/" + secret;
        running = true;
        new Thread(() -> {
            while (running) {
                try {
                    Socket socket = server.accept();
                    new Thread(() -> handle(socket), "lan-client").start();
                } catch (Exception e) {
                    if (running) android.util.Log.w("MAYK-LAN", "accept", e);
                }
            }
        }, "mayk-lan").start();
    }

    void stop() {
        running = false;
        try { if (server != null) server.close(); } catch (Exception ignored) {}
        address = "";
    }

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
            int len = -1;
            for (String line : lines) {
                String low = line.toLowerCase(Locale.US);
                if (low.startsWith("content-length:")) len = Integer.parseInt(line.substring(line.indexOf(':') + 1).trim());
            }
            if (len < 1 || len > 2048) { respond(s, 400, "Geçersiz istek"); return; }
            byte[] body = new byte[len]; int pos = 0;
            while (pos < len) { int n = in.read(body, pos, len-pos); if (n < 0) return; pos += n; }
            String op = "", arg = "", csrf = "";
            for (String pair : new String(body, StandardCharsets.UTF_8).split("&")) {
                int eq = pair.indexOf('='); if (eq < 0) continue;
                String k = URLDecoder.decode(pair.substring(0,eq), "UTF-8");
                String v = URLDecoder.decode(pair.substring(eq+1), "UTF-8");
                if ("op".equals(k)) op = v;
                if ("arg".equals(k)) arg = v;
                if ("csrf".equals(k)) csrf = v;
            }
            // Safari/iOS may send Origin: null from a local HTTP page. The
            // unguessable token must appear in both the URL and form body;
            // do not reject an otherwise valid local command by Origin alone.
            if (!secret.equals(csrf)) { respond(s, 403, "Gecersiz kumanda anahtari"); return; }
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
        h.append("<h3>YouTube ara</h3><form method='post' action='/").append(secret).append("/cmd'><input type='hidden' name='csrf' value='").append(secret).append("'><input type='hidden' name='op' value='search'><input name='arg' placeholder='Aranacak video'><button>Ara</button></form>");
        h.append("<p id='result' role='status' aria-live='polite'></p>");
        // Fetch sends the same authenticated POST without iOS's unsafe-form
        // navigation warning. Forms still work if JavaScript is disabled.
        h.append("<script>document.addEventListener('submit',async function(e){"
                + "const f=e.target;if(!f.matches('form'))return;e.preventDefault();"
                + "const out=document.getElementById('result');out.textContent='Gönderiliyor…';"
                + "try{const r=await fetch(f.action,{method:'POST',body:new URLSearchParams(new FormData(f))});"
                + "const t=await r.text();const d=new DOMParser().parseFromString(t,'text/html');"
                + "out.textContent=(r.ok?'':'Hata: ')+(d.body?d.body.textContent.trim():t);}"
                + "catch(err){out.textContent='Bağlantı hatası: '+err.message;}"
                + "});</script>");
        h.append("</html>"); return h.toString();
    }

    private String form(String op, String arg, String title) {
        return "<form style='display:inline-block' method='post' action='/" + secret + "/cmd'><input type='hidden' name='csrf' value='" + secret + "'><input type='hidden' name='op' value='" + op + "'><input type='hidden' name='arg' value='" + arg + "'><button>" + title + "</button></form>";
    }
    private static String escape(String s) { return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"); }
    private void respond(Socket s, int code, String html) throws IOException {
        byte[] b = html.getBytes(StandardCharsets.UTF_8);
        String reason = code == 200 ? "OK" : code == 400 ? "Bad Request" : code == 403 ? "Forbidden" : code == 404 ? "Not Found" : "Method Not Allowed";
        String head = "HTTP/1.1 " + code + " " + reason + "\r\n"
                + "Content-Type: text/html; charset=utf-8\r\n"
                + "Content-Length: " + b.length + "\r\n"
                + "Cache-Control: no-store\r\n"
                + "X-Content-Type-Options: nosniff\r\n"
                + "Referrer-Policy: no-referrer\r\n"
                + "Connection: close\r\n\r\n";
        s.getOutputStream().write(head.getBytes(StandardCharsets.US_ASCII));
        s.getOutputStream().write(b);
        s.getOutputStream().flush();
    }
}
