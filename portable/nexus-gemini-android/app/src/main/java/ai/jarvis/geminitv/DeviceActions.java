package ai.jarvis.geminitv;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.media.AudioManager;
import android.net.Uri;
import android.provider.Settings;
import android.view.KeyEvent;
import java.util.LinkedHashMap;
import java.util.Map;

final class DeviceActions {
    private static final String CHROME = "com.android.chrome";
    private static final String YOUTUBE_TV = "com.google.android.youtube.tv";
    private static final String YOUTUBE = "com.google.android.youtube";

    private DeviceActions() {}

    static String execute(Activity activity, DeviceCommand command) {
        switch (command.action) {
            case SETTINGS:
                return openSettings(activity, Settings.ACTION_SETTINGS, "Android ayarları");
            case WIFI:
                return openSettings(activity, Settings.ACTION_WIFI_SETTINGS, "Wi-Fi ayarları");
            case BLUETOOTH:
                return openSettings(activity, Settings.ACTION_BLUETOOTH_SETTINGS, "Bluetooth ayarları");
            case DISPLAY:
                return openSettings(activity, Settings.ACTION_DISPLAY_SETTINGS, "Ekran ayarları");
            case VOLUME_UP:
            case VOLUME_DOWN:
            case VOLUME_SET:
                return changeVolume(activity, command);
            case MEDIA_PLAY:
                return mediaKey(activity, KeyEvent.KEYCODE_MEDIA_PLAY);
            case MEDIA_PAUSE:
                return mediaKey(activity, KeyEvent.KEYCODE_MEDIA_PAUSE);
            case MEDIA_NEXT:
                return mediaKey(activity, KeyEvent.KEYCODE_MEDIA_NEXT);
            case MEDIA_PREVIOUS:
                return mediaKey(activity, KeyEvent.KEYCODE_MEDIA_PREVIOUS);
            case CHROME:
                if (launchPackage(activity, CHROME)) return "Chrome açılıyor.";
                return openWeb(activity, Uri.parse("https://www.google.com/"),
                        "Chrome açılamadı. Varsayılan tarayıcı açılıyor.");
            case BROWSER:
                return openWeb(activity, Uri.parse("https://www.google.com/"), "Tarayıcı açılıyor.");
            case WEB_SEARCH:
                if (command.argument.isEmpty()) return "Aranacak metni 1–200 karakterle söyle veya yaz.";
                return openWeb(activity, Uri.parse("https://www.google.com/search").buildUpon()
                        .appendQueryParameter("q", command.argument).build(), "Web araması açılıyor.");
            case YOUTUBE:
                if (launchPackage(activity, YOUTUBE_TV) || launchPackage(activity, YOUTUBE)) {
                    return "YouTube açılıyor.";
                }
                return openWeb(activity, Uri.parse("https://www.youtube.com/"), "YouTube tarayıcıda açılıyor.");
            case YOUTUBE_PLAY:
                if (command.argument.isEmpty()) return "Video adını veya YouTube bağlantısını söyle ya da yaz.";
                String video = MediaLinks.youtubeId(command.argument);
                if (video != null) {
                    Uri watch = Uri.parse("https://www.youtube.com/watch").buildUpon()
                            .appendQueryParameter("v", video).build();
                    return openYouTube(activity, watch, "YouTube videosu açılıyor.");
                }
                return searchYouTube(activity, command.argument,
                        "Başlık için YouTube sonuçları açılıyor. Videoyu sonuçlardan seç.");
            case YOUTUBE_SEARCH:
                if (command.argument.isEmpty()) return "Aranacak metni 1–200 karakterle söyle veya yaz.";
                return searchYouTube(activity, command.argument, "YouTube araması açılıyor.");
            case FILM:
                if (command.argument.isEmpty()) return "Film adını 1–200 karakterle söyle veya yaz.";
                String official = MediaLinks.officialFilm(command.argument);
                if (official != null) {
                    return openInChrome(activity, Uri.parse(official),
                            "Disney+ film sayfası açılıyor. Oynatmak için hesabınla devam et.");
                }
                Uri results = Uri.parse("https://www.google.com/search").buildUpon()
                        .appendQueryParameter("q", command.argument + " resmi izleme platformu").build();
                return openInChrome(activity, results, "Filmin izleme seçenekleri aranıyor.");
            case APP:
                return openNamedApp(activity, command.argument);
            case HELP:
                return "Chrome’u aç · YouTube’u aç · YouTube’da caz ara · Web’de hava durumu ara "
                        + "· Sesi yükselt · Sesi yüzde 40 yap · Videoyu duraklat "
                        + "· YouTube’da Eşref 1. bölümü aç · Endgame filmini aç "
                        + "· Wi-Fi ayarlarını aç · Netflix uygulamasını aç";
            default:
                return "Cihaz komutu kullanılamıyor.";
        }
    }

    private static String openSettings(Activity activity, String action, String label) {
        return launch(activity, new Intent(action)) ? label + " açılıyor." : label + " açılamadı.";
    }

    private static String changeVolume(Activity activity, DeviceCommand command) {
        AudioManager audio = activity.getSystemService(AudioManager.class);
        if (audio == null || audio.isVolumeFixed()) return "Bu cihazda ses seviyesi kumandadan ayarlanıyor.";
        int stream = AudioManager.STREAM_MUSIC;
        int max = audio.getStreamMaxVolume(stream);
        if (max <= 0) return "Bu cihaz medya ses seviyesini bildirmiyor.";
        if (command.action == DeviceCommand.Action.VOLUME_SET) {
            int percentage = Integer.parseInt(command.argument);
            if (percentage > 100) return "Ses yüzdesi 0 ile 100 arasında olmalı.";
            audio.setStreamVolume(stream, Math.round(max * percentage / 100f), AudioManager.FLAG_SHOW_UI);
        } else {
            int direction = command.action == DeviceCommand.Action.VOLUME_UP
                    ? AudioManager.ADJUST_RAISE : AudioManager.ADJUST_LOWER;
            audio.adjustStreamVolume(stream, direction, AudioManager.FLAG_SHOW_UI);
        }
        return "Medya sesi ayarlandı.";
    }

    private static String mediaKey(Activity activity, int key) {
        AudioManager audio = activity.getSystemService(AudioManager.class);
        if (audio == null) return "Android medya kontrolü kullanılamıyor.";
        audio.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, key));
        audio.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, key));
        return "Medya komutu Android’e gönderildi.";
    }

    private static String searchYouTube(Activity activity, String query, String success) {
        Uri results = Uri.parse("https://www.youtube.com/results").buildUpon()
                .appendQueryParameter("search_query", query).build();
        return openYouTube(activity, results, success);
    }

    private static String openYouTube(Activity activity, Uri uri, String success) {
        if (launch(activity, webIntent(uri).setPackage(YOUTUBE_TV))
                || launch(activity, webIntent(uri).setPackage(YOUTUBE))) return success;
        return openWeb(activity, uri, success);
    }

    private static String openInChrome(Activity activity, Uri uri, String success) {
        return launch(activity, webIntent(uri).setPackage(CHROME))
                ? success : openWeb(activity, uri, success);
    }

    private static String openNamedApp(Activity activity, String label) {
        if (label.isEmpty()) return "Cihazdaki uygulamanın adını söyle veya yaz.";
        PackageManager pm = activity.getPackageManager();
        Map<String, ComponentName> matches = new LinkedHashMap<>();
        for (String category : new String[]{Intent.CATEGORY_LEANBACK_LAUNCHER, Intent.CATEGORY_LAUNCHER}) {
            Intent launcher = new Intent(Intent.ACTION_MAIN).addCategory(category);
            for (ResolveInfo entry : pm.queryIntentActivities(launcher, 0)) {
                if (entry.activityInfo == null) continue;
                String packageName = entry.activityInfo.packageName;
                if (activity.getPackageName().equals(packageName)) continue;
                if (DeviceCommand.normalize(entry.loadLabel(pm).toString()).equals(DeviceCommand.normalize(label))) {
                    matches.putIfAbsent(packageName, new ComponentName(packageName, entry.activityInfo.name));
                }
            }
        }
        if (matches.isEmpty()) return "Bu adla açılabilecek uygulama bulunamadı. Uygulamalar listesindeki adı kullan.";
        if (matches.size() > 1) return "Aynı adda birden fazla uygulama var. Android menüsünden seç.";
        ComponentName target = matches.values().iterator().next();
        return launch(activity, Intent.makeMainActivity(target))
                ? label + " açılıyor." : "Android bu uygulamayı açamadı.";
    }

    private static boolean launchPackage(Activity activity, String name) {
        PackageManager pm = activity.getPackageManager();
        return launch(activity, pm.getLeanbackLaunchIntentForPackage(name))
                || launch(activity, pm.getLaunchIntentForPackage(name));
    }

    private static String openWeb(Activity activity, Uri uri, String success) {
        return launch(activity, webIntent(uri)) ? success : "Bu bağlantıyı açabilecek uygulama bulunamadı.";
    }

    private static Intent webIntent(Uri uri) {
        return new Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE);
    }

    private static boolean launch(Activity activity, Intent intent) {
        if (intent == null) return false;
        try {
            activity.startActivity(intent);
            return true;
        } catch (ActivityNotFoundException | SecurityException unavailable) {
            return false;
        }
    }
}
