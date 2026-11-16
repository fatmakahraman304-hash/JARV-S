# JARVIS ile God's Eye View

JARVIS, [God's Eye View](https://github.com/bilawalsidhu/gods-eye-view) uygulamasını
CORE alanında açar. Orijinal haritanın düğmeleri, katmanları ve panelleri
kullanılabilir. Normal 2D harita ayrı olarak kullanılabilir.

## Windows’ta ilk kurulum

Git ve [Node.js](https://nodejs.org/) gerekli. Bu sürüm Node.js 24.14.0 veya
sonraki bir 24.x sürümünü ya da 26.x sürümünü kullanır.

JARVIS’i güncelledikten sonra JARVIS klasöründe PowerShell aç:

```powershell
python tools/setup_gods_eye.py
```

Araç, haritanın sabitlenmiş sürümünü
`%USERPROFILE%\JarvisIntegrations\gods-eye-view` klasörüne kurar. JARVIS,
haritayı ilk açışında yerel servisi başlatır. Servis yalnızca 127.0.0.1’den
erişilebilir. JARVIS kapanınca servis de kapanır.

## Kullanım

- **Ayarlar → Bağlantılar → God's Eye View**, **Ctrl+Shift+O** veya
  **“God's Eye View’u aç”** ile haritayı aç.
- **“God's Eye View’da Gazimağusa’ya git”**, **“deprem katmanını aç”** veya
  **“küre görünümüne dön”** gibi işleri JARVIS’e söyle.
- **“God's Eye View’da hangi komutları kullanabilirsin?”** dersen JARVIS
  kurulu sürümün komut kataloğunu kullanır. Sonuçlar günlüğe de yazılır.
- **CORE’a dön** düğmesi haritayı kapatıp ana görünüme döner.

3D görünüm için WebGL gerekir. Bazı harita kaynakları ve canlı veri katmanları
kendi sağlayıcı anahtarlarını gerektirir. Bu anahtarlar, ilgili kaynak
kullanılacağında God's Eye View’un kendi sağlayıcı ayarlarından girilir.

Kaynak kodunun ve veri sağlayıcılarının lisansları için
[upstream lisansını](https://github.com/bilawalsidhu/gods-eye-view/blob/main/LICENSE)
incele.
