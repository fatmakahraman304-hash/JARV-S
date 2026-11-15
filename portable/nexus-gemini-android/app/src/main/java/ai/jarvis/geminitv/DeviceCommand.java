package ai.jarvis.geminitv;

import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class DeviceCommand {
    enum Action {
        CHROME, BROWSER, WEB_SEARCH, YOUTUBE, YOUTUBE_SEARCH, YOUTUBE_PLAY, FILM, APP,
        SETTINGS, WIFI, BLUETOOTH, DISPLAY, VOLUME_UP, VOLUME_DOWN, VOLUME_SET,
        MEDIA_PLAY, MEDIA_PAUSE, MEDIA_NEXT, MEDIA_PREVIOUS, HELP
    }

    private static final int MAX_ARGUMENT_LENGTH = 200;
    private static final int FLAGS = Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE;
    private static final Pattern WAKE_PREFIX = Pattern.compile("^jarv[iı]s(?:[, :]+|$)", FLAGS);
    private static final Pattern SEARCH_AFTER = Pattern.compile(
            "^(google|web|youtube)(?:'?(?:da|de|ta|te))? (.+) ara$", FLAGS);
    private static final Pattern SEARCH_BEFORE = Pattern.compile(
            "^(google|web|youtube)(?:'?(?:da|de|ta|te))? ara(?:[: ]+(.+))?$", FLAGS);
    private static final Pattern YOUTUBE_PLAY = Pattern.compile(
            "^youtube'?(?:da|de)? (.+) (?:aç|oynat|başlat)$", FLAGS);
    private static final Pattern FILM = Pattern.compile(
            "^(?:chrom(?:e|u)?'?(?:da|de) )?(.+?) filmi(?:ni)? (?:aç|oynat|başlat)$", FLAGS);
    private static final Pattern VOLUME = Pattern.compile(
            "^ses(?:i| seviyesini)? %? *(?:yüzde )?([0-9]{1,3}) *(?:ye |e |a )?(?:ayarla|yap)$");
    private static final Pattern APP = Pattern.compile(
            "^(?:uygulamayı aç(?:[: ]+(.+))?|(.+?) uygulamasını aç)$", FLAGS);

    final Action action;
    final String argument;

    private DeviceCommand(Action action, String argument) {
        this.action = action;
        this.argument = argument;
    }

    static DeviceCommand parse(String input) {
        if (input == null || input.length() > 2000) return null;
        String text = Normalizer.normalize(input, Normalizer.Form.NFC)
                .replace('’', '\'').replaceAll("\\s+", " ").trim();
        text = WAKE_PREFIX.matcher(text).replaceFirst("").trim();
        String plain = text.replaceAll("[.!]+$", "").trim();
        switch (normalize(plain).replace("'", "")) {
            case "chrome aç":
            case "chromu aç":
            case "chromeu aç":
                return new DeviceCommand(Action.CHROME, "");
            case "tarayici aç":
            case "tarayiciyi aç":
            case "tarayiciyi başlat":
                return new DeviceCommand(Action.BROWSER, "");
            case "youtube aç":
            case "youtubeu aç":
                return new DeviceCommand(Action.YOUTUBE, "");
            case "ayarlari aç":
            case "android ayarlarini aç":
                return new DeviceCommand(Action.SETTINGS, "");
            case "wi-fi ayarlarini aç":
            case "wifi ayarlarini aç":
            case "kablosuz ağ ayarlarini aç":
                return new DeviceCommand(Action.WIFI, "");
            case "bluetooth ayarlarini aç":
                return new DeviceCommand(Action.BLUETOOTH, "");
            case "ekran ayarlarini aç":
                return new DeviceCommand(Action.DISPLAY, "");
            case "sesi yükselt":
            case "ses yükselt":
            case "sesi artir":
            case "sesi arttir":
            case "sesi aç":
                return new DeviceCommand(Action.VOLUME_UP, "");
            case "sesi azalt":
            case "ses azalt":
            case "sesi düşür":
            case "sesi kis":
                return new DeviceCommand(Action.VOLUME_DOWN, "");
            case "medyayi oynat":
            case "videoyu devam ettir":
            case "videoyu oynat":
                return new DeviceCommand(Action.MEDIA_PLAY, "");
            case "medyayi duraklat":
            case "videoyu duraklat":
                return new DeviceCommand(Action.MEDIA_PAUSE, "");
            case "sonraki video":
                return new DeviceCommand(Action.MEDIA_NEXT, "");
            case "önceki video":
                return new DeviceCommand(Action.MEDIA_PREVIOUS, "");
            case "cihaz komutlari":
                return new DeviceCommand(Action.HELP, "");
            default:
                break;
        }
        // A question about a command must not launch an app.
        if (plain.endsWith("?")) return null;
        Matcher volume = VOLUME.matcher(normalize(plain).replace("'", " "));
        if (volume.matches()) return new DeviceCommand(Action.VOLUME_SET, volume.group(1));
        Matcher playback = YOUTUBE_PLAY.matcher(plain);
        if (playback.matches()) return new DeviceCommand(Action.YOUTUBE_PLAY, argument(playback.group(1)));
        Matcher film = FILM.matcher(plain);
        if (film.matches()) return new DeviceCommand(Action.FILM, argument(film.group(1)));
        Matcher search = SEARCH_AFTER.matcher(plain);
        if (!search.matches()) search = SEARCH_BEFORE.matcher(plain);
        if (search.matches()) {
            Action action = search.group(1).equalsIgnoreCase("youtube")
                    ? Action.YOUTUBE_SEARCH : Action.WEB_SEARCH;
            return new DeviceCommand(action, argument(search.group(2)));
        }
        Matcher app = APP.matcher(plain);
        if (app.matches()) {
            String name = app.group(1) == null ? app.group(2) : app.group(1);
            return new DeviceCommand(Action.APP, argument(name));
        }
        return null;
    }

    boolean leavesJarvis() {
        switch (action) {
            case HELP:
            case VOLUME_UP:
            case VOLUME_DOWN:
            case VOLUME_SET:
            case MEDIA_PLAY:
            case MEDIA_PAUSE:
            case MEDIA_NEXT:
            case MEDIA_PREVIOUS:
                return false;
            default:
                return true;
        }
    }

    static String normalize(String label) {
        return Normalizer.normalize(label.trim(), Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT).replace("\u0307", "").replace('ı', 'i')
                .replaceAll("\\s+", " ");
    }

    private static String argument(String value) {
        if (value == null) return "";
        String text = value.trim();
        return text.length() <= MAX_ARGUMENT_LENGTH ? text : "";
    }
}
