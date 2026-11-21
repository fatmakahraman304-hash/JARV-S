package com.jarvis.alici;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

/**
 * One screen, easy with a TV remote: status, the setup (one tap from the
 * Mayk page on this device, or a pasted setup link), and a button to the
 * accessibility settings.
 */
public class MainActivity extends Activity {
    private TextView status;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(60, 50, 60, 50);
        root.setBackgroundColor(Color.rgb(12, 8, 5));

        TextView title = new TextView(this);
        title.setText("Mayk ALICI");
        title.setTextColor(Color.rgb(255, 160, 60));
        title.setTextSize(30);
        root.addView(title);

        status = new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(18);
        status.setPadding(0, 20, 0, 20);
        root.addView(status);

        Button a11y = button("1) Erişilebilirlik iznini aç (kumanda tuşları, yazı, ekran görüntüsü)");
        a11y.setOnClickListener(v -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        root.addView(a11y);

        final EditText link = new EditText(this);
        link.setHint("2) Kurulum bağlantısını buraya yapıştır (…#s=…)");
        link.setTextColor(Color.WHITE);
        link.setHintTextColor(Color.GRAY);
        root.addView(link);

        Button save = button("Kaydet ve başlat");
        save.setOnClickListener(v -> setup(link.getText().toString()));
        root.addView(save);

        Button web = button("Projeksiyonda Mayk'ı aç");
        web.setOnClickListener(v -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(ReceiverService.WEB))));
        root.addView(web);

        setContentView(root);
        handle(getIntent());
        a11y.requestFocus();
    }

    private Button button(String text) {
        Button bt = new Button(this);
        bt.setText(text);
        bt.setAllCaps(false);
        bt.setTextSize(17);
        bt.setGravity(Gravity.START | Gravity.CENTER_VERTICAL);
        return bt;
    }

    @Override protected void onNewIntent(Intent i) { super.onNewIntent(i); handle(i); }
    @Override protected void onResume() { super.onResume(); refresh(); }

    private void handle(Intent i) {
        Uri u = i == null ? null : i.getData();
        if (u != null && "jarvisalici".equals(u.getScheme())) setup(u.toString());
        else ReceiverService.start(this);
    }

    private void setup(String text) {
        JSONObject j = Gist.parseSetup(text);
        if (j == null) { status.setText("Bu bir Mayk kurulum bağlantısı değil."); return; }
        SharedPreferences.Editor e = ReceiverService.prefs(this).edit();
        e.putString("tok", j.optString("t")).putString("gist", j.optString("i"));
        if (!j.optString("d").isEmpty()) e.putString("name", j.optString("d"));
        e.apply();
        stopService(new Intent(this, ReceiverService.class));
        ReceiverService.start(this);
        refresh();
    }

    private void refresh() {
        SharedPreferences p = ReceiverService.prefs(this);
        boolean linked = !p.getString("gist", "").isEmpty();
        boolean a11y = RemoteAccessibility.instance != null;
        status.setText("Bağlantı: " + (linked ? "kurulu" : "kurulmadı — 2. adım") + "\n"
                + "Erişilebilirlik: " + (a11y ? "açık ✓" : "kapalı — 1. adım (Ayarlar → Erişilebilirlik → Mayk Alıcı)") + "\n"
                + "Dinleme: " + ReceiverService.status + "\n\n"
                + "Hazır olunca telefondaki Mayk'a: \"projeksiyonda YouTube aç\", \"sesi kıs\", \"projeksiyonda ne var?\"");
        ui.removeCallbacksAndMessages(null);
        ui.postDelayed(this::refresh, 3000);
    }
}
