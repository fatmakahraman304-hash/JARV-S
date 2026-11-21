"""User-initiated place search for MAYK's native, pannable street map."""
import json
import math
import os
import re
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PLUGIN = {
    'name': 'normal_map',
    'description': 'Control the native Turkish 2D Dünya Haritası within MAYK. Use action=open to open the world overview, action=close to return to CORE, or pass place to show a city, country, street or landmark. Include known location context. For driving directions use map_route.',
    'parameters': {'type': 'OBJECT', 'properties': {
        'action': {'type': 'STRING', 'enum': ['open', 'close'], 'description': 'Only for opening the world overview or closing the map.'},
        'place': {'type': 'STRING', 'description': 'Place or full address, with city or country if known.'},
    }}}
_lock = threading.Lock()
_cache = {}
_CACHE_LIMIT = 128
_CACHE_SECONDS = 900
_last_request = 0.0


def map_command_for_text(text):
    text = " ".join(text.replace("İ", "i").casefold().split()).rstrip(".!?")
    text = re.sub(r"^(?:mayk|friday)[, ]+", "", text)
    match = re.fullmatch(r"(?:dünya haritası(?:nı)?|haritayı|harita) (aç|göster|kapat)", text)
    return match[1] != "kapat" if match else None


def search(place):
    global _last_request
    with _lock:
        key = " ".join(place.strip().casefold().split())
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
            return [dict(item) for item in cached[1]]
        _cache.pop(key, None)
        time.sleep(max(0, 1.1 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        endpoint = os.environ.get('JARVIS_GEOCODER_URL', 'https://nominatim.openstreetmap.org/search')
        request = Request(endpoint + '?' + urlencode({'q':place, 'format':'jsonv2', 'limit':5, 'accept-language':'tr'}),
            headers={'User-Agent':'JarvisPersonalMap/1.0 (https://github.com/fatmakahraman304-hash/JARV-S)'})
        with urlopen(request, timeout=12) as response:
            values = json.loads(response.read(200000))
        if not isinstance(values, list):
            raise ValueError('Yer arama servisi geçersiz yanıt döndürdü.')
        results = []
        for item in values[:5]:
            if not isinstance(item, dict) or not isinstance(item.get('display_name'), str):
                continue
            try:
                lat, lon = float(item['lat']), float(item['lon'])
            except (KeyError, TypeError, ValueError):
                continue
            if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            kind = item.get('addresstype', '')
            zoom = 5 if kind == 'country' else 10 if kind in {'state','province'} else 12 if kind in {'city','town','village'} else 16
            results.append({'name':str(item['display_name']), 'lat':lat, 'lon':lon, 'zoom':zoom})
        if results:
            if len(_cache) >= _CACHE_LIMIT:
                _cache.pop(next(iter(_cache)))
            _cache[key] = (time.monotonic(), results)
        return [dict(item) for item in results]


def run(parameters, player=None, session_memory=None):
    action = parameters.get('action')
    if action in ('open', 'close'):
        show = getattr(player, 'show_world_map', None)
        if not callable(show):
            return 'Dünya Haritası için MAYK arayüzü açık olmalı.'
        show(action == 'open')
        return 'Dünya Haritası açılıyor.' if action == 'open' else 'Harita kapatılıyor.'
    place = str(parameters.get('place', '')).strip()
    if not place or len(place)>500:
        return 'Haritada açılacak yerin adını söyleyin.'
    if player is None or not callable(getattr(player, 'show_map_places', None)):
        return 'Normal harita için MAYK arayüzü açık olmalı.'
    def work():
        try:
            results = search(place)
            if results:
                player.show_map_places(results)
            else:
                player.write_log('HARİTA: Yer bulunamadı. Şehir veya ülkeyi de belirtin.')
        except Exception:
            player.write_log('HARİTA: Yer arama servisine ulaşılamadı. Mevcut harita korundu; tekrar deneyin.')
    threading.Thread(target=work, daemon=True, name='jarvis-map-search').start()
    return 'Yer normal haritada aranıyor; birden fazla eşleşme varsa seçim gösterilecek.'
