package com.jarvis.alici;

import android.accessibilityservice.AccessibilityService;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.Bundle;
import android.util.Base64;
import android.view.Display;
import android.view.View;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.io.ByteArrayOutputStream;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * What only an accessibility service may do on Android: press the remote's
 * keys for the user, write into the box that has focus (Turkish letters too)
 * and take a picture of the screen. Turned on once by the user in Settings →
 * Accessibility → Mayk Alıcı.
 */
public class RemoteAccessibility extends AccessibilityService {
    static volatile RemoteAccessibility instance;

    @Override protected void onServiceConnected() { instance = this; ReceiverService.start(this); }
    @Override public void onAccessibilityEvent(AccessibilityEvent event) { }
    @Override public void onInterrupt() { }
    @Override public void onDestroy() { if (instance == this) instance = null; super.onDestroy(); }

    private AccessibilityNodeInfo focused() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return null;
        AccessibilityNodeInfo f = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (f == null) f = root.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY);
        return f;
    }

    /** back, home, up, down, left, right, ok, recents, power … */
    String key(String k) {
        switch (k) {
            case "back": return performGlobalAction(GLOBAL_ACTION_BACK) ? "Geri." : "Olmadı.";
            case "home": return performGlobalAction(GLOBAL_ACTION_HOME) ? "Ana ekran." : "Olmadı.";
            case "recents": case "apps": return performGlobalAction(GLOBAL_ACTION_RECENTS) ? "Son uygulamalar." : "Olmadı.";
            case "notifications": return performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS) ? "Bildirimler." : "Olmadı.";
            case "power": case "sleep":
                if (Build.VERSION.SDK_INT >= 28) return performGlobalAction(GLOBAL_ACTION_LOCK_SCREEN) ? "Ekran kapatıldı." : "Olmadı.";
                return "Bu Android sürümünde yapılamıyor.";
            default: break;
        }
        int dir;
        int global;
        switch (k) {
            case "up": dir = View.FOCUS_UP; global = 16; break;
            case "down": dir = View.FOCUS_DOWN; global = 17; break;
            case "left": dir = View.FOCUS_LEFT; global = 18; break;
            case "right": dir = View.FOCUS_RIGHT; global = 19; break;
            case "ok": case "enter": dir = 0; global = 20; break;
            default: return "Bilinmeyen tuş: " + k;
        }
        if (Build.VERSION.SDK_INT >= 33 && performGlobalAction(global)) return "Tamam.";
        AccessibilityNodeInfo f = focused();
        if (f == null) return "Ekranda seçili bir şey yok.";
        if (dir == 0) {
            AccessibilityNodeInfo n = f;
            while (n != null && !n.isClickable()) n = n.getParent();
            return n != null && n.performAction(AccessibilityNodeInfo.ACTION_CLICK) ? "Seçildi." : "Seçilemedi.";
        }
        AccessibilityNodeInfo next = f.focusSearch(dir);
        if (next == null) return "O yönde başka bir şey yok.";
        boolean ok = next.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
                || next.performAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS);
        return ok ? "Tamam." : "Odak taşınamadı.";
    }

    /** Write into the focused box (or the first box on screen). */
    String type(String text, boolean enter) {
        AccessibilityNodeInfo f = focused();
        if (f == null || !f.isEditable()) f = firstEditable(getRootInActiveWindow());
        if (f == null) return "Ekranda yazı yazılacak bir kutu yok; önce arama kutusunu aç.";
        Bundle b = new Bundle();
        b.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        boolean ok = f.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, b);
        if (ok && enter && Build.VERSION.SDK_INT >= 30) {
            f.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.getId());
        }
        return ok ? "Yazıldı: " + text : "Yazılamadı.";
    }

    private AccessibilityNodeInfo firstEditable(AccessibilityNodeInfo n) {
        if (n == null) return null;
        if (n.isEditable()) return n;
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo r = firstEditable(n.getChild(i));
            if (r != null) return r;
        }
        return null;
    }

    /** JPEG of the screen, base64; null when it could not be taken. */
    String screenshotJpeg() {
        if (Build.VERSION.SDK_INT < 30) return null;
        final String[] out = {null};
        final CountDownLatch done = new CountDownLatch(1);
        takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
            @Override public void onSuccess(ScreenshotResult r) {
                try {
                    HardwareBuffer hb = r.getHardwareBuffer();
                    ColorSpace cs = r.getColorSpace();
                    Bitmap hw = Bitmap.wrapHardwareBuffer(hb, cs);
                    Bitmap bm = hw.copy(Bitmap.Config.ARGB_8888, false);
                    hb.close();
                    float sc = Math.min(1f, 1280f / Math.max(bm.getWidth(), bm.getHeight()));
                    if (sc < 1f) bm = Bitmap.createScaledBitmap(bm, Math.round(bm.getWidth() * sc), Math.round(bm.getHeight() * sc), true);
                    ByteArrayOutputStream o = new ByteArrayOutputStream();
                    bm.compress(Bitmap.CompressFormat.JPEG, 72, o);
                    out[0] = Base64.encodeToString(o.toByteArray(), Base64.NO_WRAP);
                } catch (Exception ignored) { }
                done.countDown();
            }
            @Override public void onFailure(int code) { done.countDown(); }
        });
        try { done.await(10, TimeUnit.SECONDS); } catch (InterruptedException ignored) { }
        return out[0];
    }
}
