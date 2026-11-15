package ai.jarvis.geminitv;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.provider.Settings;
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
                return launch(activity, new Intent(Settings.ACTION_SETTINGS))
                        ? "Android ayarları açılıyor." : "Android ayarları açılamadı.";
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
            case YOUTUBE_SEARCH:
                if (command.argument.isEmpty()) return "Aranacak metni 1–200 karakterle söyle veya yaz.";
                Uri search = Uri.parse("https://www.youtube.com/results").buildUpon()
                        .appendQueryParameter("search_query", command.argument).build();
                return openWeb(activity, search, "YouTube araması açılıyor.");
            case APP:
                return openNamedApp(activity, command.argument);
            case HELP:
                return "Chrome’u aç · YouTube’u aç · YouTube’da caz ara · Web’de hava durumu ara "
                        + "· Ayarları aç · Netflix uygulamasını aç";
            default:
                return "Cihaz komutu kullanılamıyor.";
        }
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
        return launch(activity, new Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE))
                ? success : "Bu bağlantıyı açabilecek tarayıcı bulunamadı.";
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
