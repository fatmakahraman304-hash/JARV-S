package com.jarvis.alici;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.wifi.WifiManager;
import android.text.format.Formatter;
import android.os.Handler;
import android.os.Looper;

import com.google.zxing.BarcodeFormat;
import com.google.zxing.MultiFormatWriter;
import com.google.zxing.common.BitMatrix;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Temporary one-time LAN pairing endpoint. Never exposes the GitHub token in a QR code. */
final class LocalPairing {
    interface Callback { void onSetup(String setup); }
    private final ExecutorService workers = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final String nonce;
    private final Callback callback;
    private ServerSocket server;
    private volatile boolean used;

    LocalPairing(Callback callback) {
        this.callback = callback;
        byte[] random = new byte[18];
        new SecureRandom().nextBytes(random);
        StringBuilder b = new StringBuilder();
        for (byte v : random) b.append(String.format(java.util.Locale.US, "%02x", v & 255));
        nonce = b.toString();
    }

    String start(Context context) throws Exception {
        WifiManager wifi = (WifiManager) context.getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        if (wifi == null || wifi.getConnectionInfo() == null) throw new Exception("Wi-Fi bulunamadı");
        String ip = Formatter.formatIpAddress(wifi.getConnectionInfo().getIpAddress());
        if ("0.0.0.0".equals(ip)) throw new Exception("Projeksiyonu Wi-Fi ağına bağla");
        server = new ServerSocket(0, 4);
        String url = "http://" + ip + ":" + server.getLocalPort() + "/" + nonce;
        workers.execute(() -> {
            while (!server.isClosed() && !used) {
                try {
                    Socket s = server.accept();
                    s.setSoTimeout(10000);
                    handle(s);
                } catch (Exception ignored) { /* closed or malformed request */ }
            }
        });
        return url;
    }

    private void handle(Socket socket) {
        try (Socket s = socket) {
            InputStream in = new BufferedInputStream(s.getInputStream());
            ByteArrayOutputStream headerBytes = new ByteArrayOutputStream();
            int c;
            while ((c = in.read()) != -1 && headerBytes.size() < 8192) {
                headerBytes.write(c);
                byte[] h = headerBytes.toByteArray();
                int n = h.length;
                if (n >= 4 && h[n-4] == 13 && h[n-3] == 10 && h[n-2] == 13 && h[n-1] == 10) break;
            }
            String headers = headerBytes.toString("UTF-8");
            String[] lines = headers.split("\\r\\n");
            if (lines.length == 0) return;
            String[] request = lines[0].split(" ");
            if (request.length < 2 || !request[1].equals("/" + nonce)) { respond(s, 404, "Bulunamadı"); return; }
            if ("GET".equals(request[0])) {
                respond(s, 200, "<!doctype html><html lang='tr'><meta name='viewport' content='width=device-width,initial-scale=1'><meta charset='utf-8'><title>MAYK Alıcı</title><body style='font:18px sans-serif;padding:24px'><h2>MAYK Alıcı eşleştirme</h2><p>Telefonda MAYK ayarlarından Alıcıyı bağla ile kopyaladığın bağlantıyı aşağıya yapıştır.</p><form method='POST'><textarea name='setup' rows='5' style='width:100%' required></textarea><p><button style='font-size:20px'>Projeksiyona bağla</button></p></form><p>Yalnızca kendi Wi-Fi ağında kullan.</p></body></html>");
                return;
            }
            if (!"POST".equals(request[0]) || used) { respond(s, 405, "İşlem kullanılamıyor"); return; }
            int length = -1;
            for (String line : lines) if (line.toLowerCase(java.util.Locale.US).startsWith("content-length:")) {
                try { length = Integer.parseInt(line.substring(line.indexOf(':') + 1).trim()); } catch (Exception ignored) {}
            }
            if (length < 1 || length > 8192) { respond(s, 413, "Geçersiz uzunluk"); return; }
            byte[] body = new byte[length];
            int pos = 0;
            while (pos < length) { int n = in.read(body, pos, length - pos); if (n < 0) return; pos += n; }
            String encoded = new String(body, StandardCharsets.UTF_8);
            String value = null;
            for (String pair : encoded.split("&")) {
                if (pair.startsWith("setup=")) { value = java.net.URLDecoder.decode(pair.substring(6), "UTF-8"); break; }
            }
            if (value == null || Gist.parseSetup(value) == null) { respond(s, 400, "Geçersiz MAYK bağlantısı"); return; }
            used = true;
            respond(s, 200, "<!doctype html><html lang='tr'><meta charset='utf-8'><body><h2>Bağlantı projeksiyona gönderildi.</h2><p>MAYK Alıcı ekranını kontrol et.</p></body></html>");
            final String setup = value;
            main.post(() -> callback.onSetup(setup));
            close();
        } catch (Exception ignored) { /* malformed or disconnected client */ }
    }

    private void respond(Socket s, int code, String html) throws Exception {
        byte[] bytes = html.getBytes(StandardCharsets.UTF_8);
        OutputStream out = s.getOutputStream();
        out.write(("HTTP/1.1 " + code + " OK\\r\\nContent-Type: text/html; charset=utf-8\\r\\nContent-Length: " + bytes.length + "\\r\\nCache-Control: no-store\\r\\nConnection: close\\r\\nX-Content-Type-Options: nosniff\\r\\n\\r\\n").getBytes(StandardCharsets.UTF_8));
        out.write(bytes);
        out.flush();
    }

    static Bitmap qr(String text) throws Exception {
        BitMatrix bits = new MultiFormatWriter().encode(text, BarcodeFormat.QR_CODE, 440, 440);
        Bitmap bmp = Bitmap.createBitmap(440, 440, Bitmap.Config.ARGB_8888);
        for (int y = 0; y < 440; y++) for (int x = 0; x < 440; x++) bmp.setPixel(x, y, bits.get(x, y) ? Color.BLACK : Color.WHITE);
        return bmp;
    }

    void close() {
        try { if (server != null) server.close(); } catch (Exception ignored) {}
    }
}
