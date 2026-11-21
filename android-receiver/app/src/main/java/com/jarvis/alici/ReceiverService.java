package com.jarvis.alici;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.media.AudioManager;
import android.net.Uri;
import android.net.wifi.WifiManager;
import android.net.wifi.WifiNetworkSuggestion;
import android.os.Build;
import android.os.IBinder;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.KeyEvent;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TimeZone;

/**
 * Listens for commands from the phone (or any MAYK device) in the shared
 * gist — inbox-<id>.json — and carries them out on this projector/TV:
 * open apps and pages, search, remote keys, volume, media, typing, Wi-Fi,
 * and a picture of the screen sent back to the device that asked.
 * Answers go to outbox-<id>.json; a heartbeat (device-<id>.json) tells the
 * other devices this receiver is here. Same files as core/sync_hub.py and
 * web/app.js use.
 */
public class ReceiverService extends Service {
    static final String WEB = "https://fatmakahraman304-hash.github.io/JARV-S/";
    static volatile String status = "kapalı";
    private volatile boolean running;
    private final Set<String> done = new LinkedHashSet<>();

    static void start(Context ctx) {
        SharedPreferences p = prefs(ctx);
        if (p.getString("tok", "").isEmpty() || p.getString("gist", "").isEmpty()) return;
        Intent i = new Intent(ctx, ReceiverService.class);
        if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i); else ctx.startService(i);
    }

    static SharedPreferences prefs(Context ctx) { return ctx.getSharedPreferences("alici", MODE_PRIVATE); }

    static String deviceId(Context ctx) {
        SharedPreferences p = prefs(ctx);
        String id = p.getString("id", "");
        if (id.isEmpty()) {
            id = "rx" + Long.toString(System.currentTimeMillis(), 36);
            p.edit().putString("id", id).apply();
        }
        return id;
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm = getSystemService(NotificationManager.class);
            nm.createNotificationChannel(new NotificationChannel("alici", "MAYK Alıcı", NotificationManager.IMPORTANCE_MIN));
            Notification n = new Notification.Builder(this, "alici").setContentTitle("MAYK Alıcı dinliyor")
                    .setSmallIcon(android.R.drawable.ic_menu_view).build();
            startForeground(1, n);
        }
        if (!running) {
            running = true;
            new Thread(this::loop, "alici").start();
        }
        return START_STICKY;
    }

    @Override public void onDestroy() { running = false; status = "kapalı"; super.onDestroy(); }

    private static String now() {
        SimpleDateFormat f = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        f.setTimeZone(TimeZone.getTimeZone("UTC"));
        return f.format(new Date());
    }

    private void loop() {
        SharedPreferences p = prefs(this);
        Gist gist = new Gist(p.getString("tok", ""), p.getString("gist", ""));
        String me = deviceId(this);
        long lastBeat = 0;
        long delayMs = 5000;
        while (running) {
            try {
                Map<String, String> files = gist.files();
                Map<String, String> writes = new HashMap<>();
                JSONArray inbox = new JSONArray(orEmpty(files.get("inbox-" + me + ".json"), "[]"));
                JSONArray outbox = new JSONArray(orEmpty(files.get("outbox-" + me + ".json"), "[]"));
                boolean answered = false;
                for (int i = 0; i < inbox.length(); i++) {
                    JSONObject c = inbox.optJSONObject(i);
                    if (c == null) continue;
                    String id = c.optString("id");
                    if (id.isEmpty() || done.contains(id)) continue;
                    done.add(id);
                    if (done.size() > 300) done.remove(done.iterator().next());
                    String reply = run(c, files, writes);
                    outbox.put(new JSONObject().put("id", id).put("ts", now()).put("reply", reply));
                    answered = true;
                }
                if (inbox.length() > 0) writes.put("inbox-" + me + ".json", "[]");
                if (answered) {
                    JSONArray keep = new JSONArray();
                    for (int i = Math.max(0, outbox.length() - 30); i < outbox.length(); i++) keep.put(outbox.get(i));
                    writes.put("outbox-" + me + ".json", keep.toString());
                }
                if (SystemClock.elapsedRealtime() - lastBeat > 60000) {
                    writes.put("device-" + me + ".json", beat(me).toString());
                }
                if (!writes.isEmpty()) gist.write(writes);
                if (writes.containsKey("device-" + me + ".json")) lastBeat = SystemClock.elapsedRealtime();
                status = "bağlı · cihaz kimliği: " + me;
                delayMs = 5000;
            } catch (Exception e) {
                status = "hata: " + e.getMessage();
                // Back off on API errors; do not hammer GitHub with retries.
                String error = e.getMessage() == null ? "" : e.getMessage();
                delayMs = error.contains("GitHub 403") || error.contains("GitHub 429")
                        ? 60000 : Math.min(30000, delayMs * 2);
            }
            SystemClock.sleep(delayMs);
        }
    }

    private static String orEmpty(String s, String d) { return s == null || s.trim().isEmpty() ? d : s; }

    private JSONObject beat(String me) throws Exception {
        String name = prefs(this).getString("name", "Projeksiyon");
        JSONArray apps = new JSONArray();
        for (String a : appLabels().keySet()) apps.put(a);
        return new JSONObject().put("id", me).put("name", name + " (alıcı)").put("kind", "receiver")
                .put("controls", name).put("seen", now()).put("commands", true).put("active", false)
                .put("model", Build.MANUFACTURER + " " + Build.MODEL).put("android", Build.VERSION.RELEASE)
                .put("a11y", RemoteAccessibility.instance != null).put("apps", apps);
    }

    // ── what the receiver can do ───────────────────────────────────────────
    private String run(JSONObject c, Map<String, String> files, Map<String, String> writes) {
        String op = c.optString("op", c.optString("kind")), arg = c.optString("arg", c.optString("text", ""));
        try {
            switch (op) {
                case "key": return key(arg);
                case "app": return openApp(arg);
                case "url": return openUrl(arg);
                case "search": return search(arg, c.optString("where", "youtube"));
                case "type": {
                    RemoteAccessibility a = RemoteAccessibility.instance;
                    return a == null ? needA11y() : a.type(arg, c.optBoolean("enter", true));
                }
                case "look": return look(c, files, writes);
                case "wifi": return wifi(arg, c.optString("password", ""));
                case "jarvis": return openUrl(WEB);
                case "apps": return "Uygulamalar: " + String.join(", ", appLabels().keySet());
                default: return "Bilinmeyen komut: " + op;
            }
        } catch (Exception e) {
            return "Olmadı: " + e.getMessage();
        }
    }

    private String needA11y() {
        return "Bunun için projeksiyonda Ayarlar → Erişilebilirlik → MAYK Alıcı'yı bir kez açman gerekiyor.";
    }

    private String key(String k) {
        AudioManager am = (AudioManager) getSystemService(AUDIO_SERVICE);
        switch (k) {
            case "volume_up": am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI); return "Ses açıldı.";
            case "volume_down": am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI); return "Ses kısıldı.";
            case "mute": am.adjustStreamVolume(AudioManager.STREAM_MUSIC, AudioManager.ADJUST_TOGGLE_MUTE, AudioManager.FLAG_SHOW_UI); return "Sessiz/sesli.";
            case "play_pause": return media(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, "Oynat/durdur.");
            case "play": return media(KeyEvent.KEYCODE_MEDIA_PLAY, "Oynatılıyor.");
            case "pause": case "stop": return media(KeyEvent.KEYCODE_MEDIA_PAUSE, "Durduruldu.");
            case "next": return media(KeyEvent.KEYCODE_MEDIA_NEXT, "Sonraki.");
            case "previous": return media(KeyEvent.KEYCODE_MEDIA_PREVIOUS, "Önceki.");
            case "fast_forward": return media(KeyEvent.KEYCODE_MEDIA_FAST_FORWARD, "İleri.");
            case "rewind": return media(KeyEvent.KEYCODE_MEDIA_REWIND, "Geri sarıldı.");
            default: break;
        }
        RemoteAccessibility a = RemoteAccessibility.instance;
        return a == null ? needA11y() : a.key(k);
    }

    private String media(int code, String said) {
        AudioManager am = (AudioManager) getSystemService(AUDIO_SERVICE);
        am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, code));
        am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, code));
        return said;
    }

    private Context launcher() {          // starting screens from the background needs the accessibility service
        RemoteAccessibility a = RemoteAccessibility.instance;
        return a != null ? a : this;
    }

    /** label (lower case) → package, for every app that can be opened. */
    private Map<String, String> appLabels() {
        PackageManager pm = getPackageManager();
        Map<String, String> out = new HashMap<>();
        for (String cat : new String[]{Intent.CATEGORY_LEANBACK_LAUNCHER, Intent.CATEGORY_LAUNCHER}) {
            List<ResolveInfo> list = pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(cat), 0);
            for (ResolveInfo r : list) {
                String label = String.valueOf(r.loadLabel(pm)).toLowerCase(new Locale("tr"));
                if (!out.containsKey(label)) out.put(label, r.activityInfo.packageName);
            }
        }
        return out;
    }

    private String openApp(String name) {
        String n = name.toLowerCase(new Locale("tr")).trim();
        Map<String, String> known = new HashMap<>();
        known.put("youtube", "com.google.android.youtube.tv");
        known.put("netflix", "com.netflix.ninja");
        known.put("ayarlar", "com.android.tv.settings");
        known.put("chrome", "com.android.chrome");
        known.put("prime", "com.amazon.amazonvideo.livingroom");
        known.put("disney", "com.disney.disneyplus");
        known.put("spotify", "com.spotify.tv.android");
        Map<String, String> labels = appLabels();
        String pkg = null;
        for (Map.Entry<String, String> e : labels.entrySet()) if (e.getKey().equals(n)) pkg = e.getValue();
        if (pkg == null) for (Map.Entry<String, String> e : labels.entrySet()) if (e.getKey().contains(n) || n.contains(e.getKey())) { pkg = e.getValue(); break; }
        if (pkg == null && known.containsKey(n) && labels.containsValue(known.get(n))) pkg = known.get(n);
        if (pkg == null) return "'" + name + "' bu cihazda yok. Var olanlar: " + String.join(", ", new ArrayList<>(labels.keySet()));
        PackageManager pm = getPackageManager();
        Intent i = pm.getLeanbackLaunchIntentForPackage(pkg);
        if (i == null) i = pm.getLaunchIntentForPackage(pkg);
        if (i == null) return "Açılamadı.";
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        launcher().startActivity(i);
        return name + " açıldı.";
    }

    private String openUrl(String url) {
        if (!url.startsWith("http://") && !url.startsWith("https://")) return "Geçerli bir adres değil.";
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        launcher().startActivity(i);
        return "Açıldı.";
    }

    private String search(String q, String where) throws Exception {
        String enc = java.net.URLEncoder.encode(q, "UTF-8");
        if (where.contains("youtube")) {
            try {
                Intent i = new Intent(Intent.ACTION_SEARCH).setPackage("com.google.android.youtube.tv")
                        .putExtra("query", q).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                launcher().startActivity(i);
                return "YouTube'da '" + q + "' aranıyor.";
            } catch (Exception ignored) {
                return openUrl("https://www.youtube.com/results?search_query=" + enc);
            }
        }
        return openUrl("https://www.google.com/search?q=" + enc);
    }

    private String look(JSONObject c, Map<String, String> files, Map<String, String> writes) throws Exception {
        RemoteAccessibility a = RemoteAccessibility.instance;
        if (a == null) return needA11y();
        String jpg = a.screenshotJpeg();
        if (jpg == null) return "Ekran görüntüsü alınamadı (Android 11 ve üstü gerekir).";
        String to = c.optString("reply_to");
        if (to.isEmpty()) return "Görüntü alındı ama kime gönderileceği bilinmiyor.";
        String name = "inbox-" + to + ".json";
        JSONArray box = new JSONArray(orEmpty(writes.containsKey(name) ? writes.get(name) : files.get(name), "[]"));
        box.put(new JSONObject().put("id", deviceId(this) + "-s" + Long.toString(System.currentTimeMillis(), 36))
                .put("kind", "image").put("data", jpg).put("mime", "image/jpeg").put("see", true)
                .put("question", c.optString("question")).put("from", prefs(this).getString("name", "Projeksiyon"))
                .put("title", prefs(this).getString("name", "Projeksiyon") + " ekranı").put("ts", now()));
        writes.put(name, box.toString());
        return "Ekran görüntüsü gönderildi.";
    }

    private String wifi(String ssid, String pass) {
        if (ssid.isEmpty()) return "Ağ adı lazım.";
        if (Build.VERSION.SDK_INT >= 29) {
            WifiNetworkSuggestion.Builder b = new WifiNetworkSuggestion.Builder().setSsid(ssid);
            if (!pass.isEmpty()) b.setWpa2Passphrase(pass);
            List<WifiNetworkSuggestion> list = new ArrayList<>();
            list.add(b.build());
            WifiManager wm = (WifiManager) getApplicationContext().getSystemService(WIFI_SERVICE);
            int r = wm.addNetworkSuggestions(list);
            Intent i = new Intent(Settings.ACTION_WIFI_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            try { launcher().startActivity(i); } catch (Exception ignored) { }
            return r == WifiManager.STATUS_NETWORK_SUGGESTIONS_SUCCESS
                    ? "'" + ssid + "' ağı eklendi; Android bağlanmak için ekranda onay isteyebilir."
                    : "Ağ eklenemedi (kod " + r + ").";
        }
        return "Bu Android sürümünde uygulama Wi-Fi'ye bağlanamıyor; Wi-Fi ayarlarını açtım.";
    }
}
