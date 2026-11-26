package com.aether.alici;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.ComponentName;
import android.database.Cursor;
import android.os.Environment;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.view.accessibility.AccessibilityManager;
import java.util.List;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.ImageView;

import org.json.JSONObject;

/**
 * One screen, easy with a TV remote: status, the setup (one tap from the
 * FRIDAY page on this device, or a pasted setup link), and a button to the
 * accessibility settings.
 */
public class MainActivity extends Activity {
    private TextView status;
    private LocalPairing pairing;
    private long updateDownloadId = -1;
    private boolean updateInstallLaunched = false;
    private static final String APK_URL = "https://github.com/fatmakahraman304-hash/JARV-S/releases/download/alici/aether-alici.apk";
    private final Handler ui = new Handler(Looper.getMainLooper());
    // Keep exactly one status refresh loop. Do not cancel the APK updater's
    // separate checkUpdateDownload callback (regression in older versions).
    private final Runnable refreshTask = this::refresh;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(24), dp(28), dp(24), dp(28));
        root.setBackground(new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{Color.rgb(8, 18, 34), Color.rgb(6, 11, 22)}));

        TextView title = new TextView(this);
        try { title.setText("FRIDAY ALICI · v" + getPackageManager().getPackageInfo(getPackageName(), 0).versionName); }
        catch (Exception ignored) { title.setText("FRIDAY ALICI"); }
        title.setTextColor(Color.rgb(103, 222, 250));
        title.setLetterSpacing(.12f);
        title.setPadding(0, 0, 0, dp(12));
        title.setTextSize(getResources().getConfiguration().smallestScreenWidthDp >= 600 ? 36 : 28);
        root.addView(title);

        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(16);
        status.setPadding(dp(18), dp(16), dp(18), dp(16));
        GradientDrawable statusCard = new GradientDrawable();
        statusCard.setColor(Color.rgb(13, 28, 49));
        statusCard.setCornerRadius(dp(18));
        statusCard.setStroke(dp(1), Color.rgb(37, 61, 87));
        status.setBackground(statusCard);
        TextView subtitle = new TextView(this);
        subtitle.setText("CİHAZ BAĞLANTISI  /  GÜVENLİ KUMANDA");
        subtitle.setTextColor(Color.rgb(147, 170, 197));
        subtitle.setTextSize(12);
        subtitle.setPadding(0, 0, 0, dp(20));
        root.addView(subtitle);
        root.addView(status);

        Button a11y = button("1) Erişilebilirlik iznini aç (kumanda tuşları, yazı, ekran görüntüsü)");
        a11y.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        root.addView(a11y);

        Button appSettings = button("İzin tekrar kapanıyorsa: FRIDAY uygulama kısıtlamaları");
        appSettings.setOnClickListener(v -> startActivity(
                new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:" + getPackageName()))));
        root.addView(appSettings);

        final EditText link = new EditText(this);
        link.setHint("2) Kurulum bağlantısını buraya yapıştır (…#s=…)");
        link.setTextColor(Color.WHITE);
        link.setHintTextColor(Color.GRAY);
        root.addView(link);

        Button save = button("Kaydet ve başlat");
        save.setOnClickListener(v -> setup(link.getText().toString()));
        root.addView(save);

        Button qrButton = button("2) iPhone ile QR kodla bağla (aynı Wi-Fi)");
        root.addView(qrButton);
        qrButton.setOnClickListener(v -> {
            if (pairing != null) pairing.close();
            pairing = new LocalPairing(this::setup);
            try {
                String url = pairing.start(this);
                // A compact dialog keeps the QR visible even on low-resolution projectors.
                LinearLayout panel = new LinearLayout(this);
                panel.setOrientation(LinearLayout.VERTICAL);
                panel.setPadding(12, 8, 12, 8);
                int width = getResources().getDisplayMetrics().widthPixels;
                int height = getResources().getDisplayMetrics().heightPixels;
                int side = Math.max(160, Math.min(340, Math.min(width - 110, height - 150)));
                ImageView image = new ImageView(this);
                image.setImageBitmap(LocalPairing.qr(url));
                image.setScaleType(ImageView.ScaleType.FIT_CENTER);
                panel.addView(image, new LinearLayout.LayoutParams(side, side));
                TextView hint = new TextView(this);
                hint.setTextColor(Color.WHITE);
                hint.setTextSize(15);
                hint.setText("iPhone kamerasıyla QR kodu okut. Açılan sayfaya FRIDAY kurulum bağlantısını yapıştır.");
                panel.addView(hint);
                new AlertDialog.Builder(this)
                        .setTitle("iPhone ile bağla")
                        .setView(panel)
                        .setNegativeButton("Kapat", (dialog, which) -> pairing.close())
                        .show();
            } catch (Exception ex) {
                status.setText("QR eşleştirme açılamadı: " + ex.getMessage());
            }
        });

        Button lan = button("Wi-Fi kumanda bağlantısını göster");
        lan.setOnClickListener(v -> new AlertDialog.Builder(this).setTitle("iPhone için yerel kumanda").setMessage(ReceiverService.lanAddress + "\n\nBu adresi iPhone Safari'de aç. Aynı Wi-Fi ağına bağlı olmalısın.").setPositiveButton("Tamam", null).show());
        root.addView(lan);

        Button web = button("Projeksiyonda FRIDAY'ı aç");
        web.setOnClickListener(v -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(ReceiverService.WEB))));
        root.addView(web);

        Button update = button("↻ FRIDAY Alıcı'yı güncelle");
        update.setOnClickListener(v -> downloadUpdate());
        root.addView(update);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(root);
        setContentView(scroll);
        handle(getIntent());
        a11y.requestFocus();
    }

    @Override protected void onDestroy() {
        if (pairing != null) pairing.close();
        super.onDestroy();
    }

    /** Downloads the published APK and asks Android to install it over this app.
     * Android's package installer requires explicit user confirmation.
     */
    private void downloadUpdate() {
        if (updateDownloadId != -1) {
            new AlertDialog.Builder(this).setMessage("Güncelleme zaten indiriliyor.")
                    .setPositiveButton("Tamam", null).show();
            return;
        }
        try {
            DownloadManager manager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(APK_URL))
                    .setTitle("FRIDAY Alıcı güncellemesi")
                    .setDescription("Yeni sürüm indiriliyor")
                    .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    .setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, "friday-receiver-update.apk");
            updateDownloadId = manager.enqueue(request);
            updateInstallLaunched = false;
            new AlertDialog.Builder(this).setMessage("Güncelleme indiriliyor. İndirme bitince Android kurulum onayı açılacak.")
                    .setPositiveButton("Tamam", null).show();
            ui.postDelayed(this::checkUpdateDownload, 1200);
        } catch (Exception e) {
            updateDownloadId = -1;
            new AlertDialog.Builder(this).setMessage("İndirme başlatılamadı: " + e.getMessage())
                    .setPositiveButton("Tamam", null).show();
        }
    }

    private void checkUpdateDownload() {
        if (updateDownloadId == -1 || isFinishing() || updateInstallLaunched) return;
        DownloadManager manager = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
        try (Cursor cursor = manager.query(new DownloadManager.Query().setFilterById(updateDownloadId))) {
            if (cursor == null || !cursor.moveToFirst()) {
                updateDownloadId = -1;
                return;
            }
            int state = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
            if (state == DownloadManager.STATUS_SUCCESSFUL) {
                Uri apk = manager.getUriForDownloadedFile(updateDownloadId);
                updateDownloadId = -1;
                if (apk == null) throw new IllegalStateException("İndirilen APK bulunamadı");
                updateInstallLaunched = true;
                Intent install = new Intent(Intent.ACTION_VIEW)
                        .setDataAndType(apk, "application/vnd.android.package-archive")
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(install);
                return;
            }
            if (state == DownloadManager.STATUS_FAILED) {
                int reason = cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_REASON));
                updateDownloadId = -1;
                new AlertDialog.Builder(this).setMessage("Güncelleme indirilemedi (kod " + reason + "). İnternet bağlantısını kontrol et.")
                        .setPositiveButton("Tamam", null).show();
                return;
            }
        } catch (Exception e) {
            updateDownloadId = -1;
            new AlertDialog.Builder(this).setMessage("Güncelleme kurulumu açılamadı: " + e.getMessage())
                    .setPositiveButton("Tamam", null).show();
            return;
        }
        ui.postDelayed(this::checkUpdateDownload, 1200);
    }

    private Button button(String text) {
        Button bt = new Button(this);
        bt.setText(text);
        bt.setAllCaps(false);
        bt.setTextSize(getResources().getConfiguration().smallestScreenWidthDp >= 600 ? 20 : 16);
        bt.setTextColor(Color.rgb(232, 242, 255));
        bt.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        bt.setMinHeight(dp(56));
        bt.setPadding(dp(18), dp(12), dp(18), dp(12));
        StateListDrawable states = new StateListDrawable();
        states.addState(new int[]{android.R.attr.state_focused}, buttonSurface(true));
        states.addState(new int[]{android.R.attr.state_pressed}, buttonSurface(true));
        states.addState(new int[]{}, buttonSurface(false));
        bt.setBackground(states);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        params.topMargin = dp(12);
        bt.setLayoutParams(params);
        return bt;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private GradientDrawable buttonSurface(boolean focused) {
        GradientDrawable shape = new GradientDrawable();
        shape.setCornerRadius(dp(14));
        shape.setColor(focused ? Color.rgb(22, 63, 85) : Color.rgb(15, 31, 52));
        shape.setStroke(dp(focused ? 2 : 1), focused ? Color.rgb(103, 222, 250) : Color.rgb(37, 61, 87));
        return shape;
    }

    @Override protected void onNewIntent(Intent i) { super.onNewIntent(i); handle(i); }
    @Override protected void onResume() {
        super.onResume();
        ui.removeCallbacks(refreshTask);
        refresh();
    }
    @Override protected void onPause() {
        ui.removeCallbacks(refreshTask);
        super.onPause();
    }

    private void handle(Intent i) {
        Uri u = i == null ? null : i.getData();
        if (u != null && "aetheralici".equals(u.getScheme())) setup(u.toString());
        else ReceiverService.start(this);
    }

    private void setup(String text) {
        JSONObject j = Gist.parseSetup(text);
        if (j == null) { status.setText("Bu bir FRIDAY kurulum bağlantısı değil."); return; }
        SharedPreferences.Editor e = ReceiverService.prefs(this).edit();
        e.putString("tok", j.optString("t")).putString("gist", j.optString("i"));
        if (!j.optString("d").isEmpty()) e.putString("name", j.optString("d"));
        e.apply();
        stopService(new Intent(this, ReceiverService.class));
        ReceiverService.start(this);
        refresh();
    }

    /** Check Android's saved permission separately from service connectivity.
     * Android TVs sometimes leave the switch ON but kill the bound service;
     * getEnabledAccessibilityServiceList alone can misreport that as OFF.
     * Read only: never change Settings.Secure without the user's approval.
     */
    private boolean accessibilityEnabled() {
        try {
            String enabled = Settings.Secure.getString(getContentResolver(),
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (enabled != null) {
                ComponentName mine = new ComponentName(this, RemoteAccessibility.class);
                for (String name : enabled.split(":")) {
                    ComponentName entry = ComponentName.unflattenFromString(name);
                    if (mine.equals(entry)) return true;
                }
                return false;
            }
        } catch (Exception ignored) { /* Fall back to AccessibilityManager. */ }
        AccessibilityManager manager = (AccessibilityManager) getSystemService(ACCESSIBILITY_SERVICE);
        if (manager == null) return RemoteAccessibility.instance != null;
        List<AccessibilityServiceInfo> services = manager.getEnabledAccessibilityServiceList(
                AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
        for (AccessibilityServiceInfo service : services) {
            if (service.getResolveInfo() != null
                    && getPackageName().equals(service.getResolveInfo().serviceInfo.packageName)
                    && RemoteAccessibility.class.getName().equals(service.getResolveInfo().serviceInfo.name))
                return true;
        }
        return RemoteAccessibility.instance != null;
    }

    private void refresh() {
        SharedPreferences p = ReceiverService.prefs(this);
        boolean linked = !p.getString("gist", "").isEmpty();
        boolean a11yPermission = accessibilityEnabled();
        boolean a11yRunning = RemoteAccessibility.instance != null;
        String a11yStatus = a11yRunning ? "hizmet çalışıyor ✓"
                : a11yPermission ? "izin AÇIK, ancak Android hizmeti durdurmuş"
                : "Android izni KAPALI — Ayarlar → Erişilebilirlik → FRIDAY Alıcı";
        String lastEvent = p.getString(RemoteAccessibility.STATE_KEY, "Henüz bağlantı kaydı yok");
        long lastTime = p.getLong(RemoteAccessibility.TIME_KEY, 0);
        String when = lastTime > 0 ? new java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault())
                .format(new java.util.Date(lastTime)) : "";
        String a11yHelp = a11yRunning ? ""
                : a11yPermission
                    ? "\nAndroid izin anahtarını kapatmamış; hizmet kesilmiş. Uygulama kısıtlamalarını kontrol et."
                    : "\nAndroid izin anahtarını kapatmış. Uygulama bunu kendiliğinden açamaz.";
        status.setText("Bağlantı: " + (linked ? "kurulu" : "kurulmadı — 2. adım") + "\n"
                + "Erişilebilirlik: " + a11yStatus + "\n"
                + "Son hizmet olayı: " + lastEvent + (when.isEmpty() ? "" : " (" + when + ")") + a11yHelp + "\n"
                + "Dinleme: " + ReceiverService.status + "\n"
                + "FRIDAY HTTPS köprüsü: " + RelayRemote.status + "\n"
                + "Wi-Fi kumanda: " + ReceiverService.lanAddress + "\n\n"
                + "Hazır olunca telefondaki FRIDAY'a: \"projeksiyonda YouTube aç\", \"sesi kıs\", \"projeksiyonda ne var?\"");
        ui.removeCallbacks(refreshTask);
        ui.postDelayed(refreshTask, 3000);
    }
}
