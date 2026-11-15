package ai.jarvis.geminitv;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.regex.Pattern;

final class MediaLinks {
    private static final Pattern VIDEO_ID = Pattern.compile("[A-Za-z0-9_-]{11}");
    private static final Pattern ESREF_EPISODE_ONE = Pattern.compile(
            "(?:eşref|esref)(?: (?:rüya|ruya))? (?:1|birinci) (?:bölüm|bolum)(?:ü|u)?");

    private MediaLinks() {}

    static String youtubeId(String input) {
        String normalized = DeviceCommand.normalize(input).replaceAll("(?<=\\d)\\.", "");
        if (ESREF_EPISODE_ONE.matcher(normalized).matches()) return "IWZr0PdZfSM";

        // Rebuild links from an ID, never pass parameters or an arbitrary target to Android.
        try {
            URI url = new URI(input);
            if (!"https".equalsIgnoreCase(url.getScheme()) || url.getUserInfo() != null
                    || url.getPort() != -1) return null;
            String host = url.getHost();
            String path = url.getPath();
            if ("youtu.be".equalsIgnoreCase(host)) {
                return path.isEmpty() ? null : checkedId(path.substring(1));
            }
            if (!"youtube.com".equalsIgnoreCase(host) && !"www.youtube.com".equalsIgnoreCase(host)
                    && !"m.youtube.com".equalsIgnoreCase(host)) return null;
            if (path.startsWith("/shorts/")) return checkedId(path.substring("/shorts/".length()));
            if (!"/watch".equals(path) || url.getRawQuery() == null) return null;
            String id = null;
            for (String parameter : url.getRawQuery().split("&")) {
                if (!parameter.startsWith("v=")) continue;
                if (id != null) return null;
                id = parameter.substring(2);
            }
            return id == null ? null : checkedId(id);
        } catch (URISyntaxException invalid) {
            return null;
        }
    }

    private static String checkedId(String id) {
        return VIDEO_ID.matcher(id).matches() ? id : null;
    }

    static String officialFilm(String title) {
        switch (DeviceCommand.normalize(title).replace(":", "")) {
            case "endgame":
            case "end game":
            case "avengers endgame":
            case "avengers end game":
                return "https://www.disneyplus.com/tr-tr/browse/entity-b39aa962-be56-4b09-a536-98617031717f";
            default:
                return null;
        }
    }
}
