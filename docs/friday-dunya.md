# FRIDAY ve Dünya

Asistanın görünen adı ve konuşma kimliği FRIDAY. Gemini Live için varsayılan
kadın sesi Aoede; eski Charon/Puck/Fenrir seçimi Aoede olarak okunur. Kore gibi
mevcut kadın sesi korunur. Konuşma tarzı sakin, kısa, doğal Türkçe ve ölçülü
esprilidir. Bu bir film kaydı, oyuncu ses klonu veya resmî Marvel ürünü değildir.
Diğer sağlayıcılar, model öncelikleri ve hesap anahtarları değiştirilmez.
Kendi ElevenLabs/Piper/sistem sesini kullanan bir pipeline aynı sağlayıcıda
kalır; Gemini sesi bu bağımsız motorların sesini değiştirmez. Canlı sesin
hesabınızda kullanılabilirliği ve fiziksel mikrofon/hoparlör kabulü ayrıca gerekir.

Kişiselleştirme girişleri Ayarlar'dan ve kurulum çekmecesinden kaldırıldı.
Mevcut tema, kullanıcının adı, hafıza, hesap ayarları ve veri dizini korunur.
WhatsApp Business/Twilio otomatik yanıt sunucusu ve ayar ekranı kaldırıldı.
Eski yerel yapılandırma ve sırlar silinmez; uygulama bunlarla dinleyici başlatmaz.
Normal WhatsApp mesajlaşmasının kullanıcı onaylı araçları korunur.

## Dünya ekranı

Alt çubuktaki küre simgesine basın veya Ctrl+Shift+O kullanın.

- Holografik: mavi atmosferli 3D küre ve harita çizgileri.
- Doğal / Uydu: Esri World Imagery görüntüleri; görüntü tarihi ve çözünürlüğü
  bölgeye bağlıdır. Canlı dünya görüntüsü veya fotoğraflanmış 3D bina modeli değildir.
- Sokak haritası: Esri World Street Map yol/bina adları, yakın görünüm ve adres arama.
- 2D / 3D: düz harita ile küre arasında geçiş. Tekerlek ve +/− yakınlaştırır;
  sürükleme gezinir. Yakın kamera mesafesi 120 metredir; daha fazla büyütme
  kaynak görüntünün gerçek ayrıntısını artırmaz.
- Sokak panoraması: ekran merkezini Google Maps'in ayrı tarayıcı sayfasında
  açar. Sokak fotoğrafının bulunması bölgenin kapsamasına bağlıdır.
- Normal harita: WebGL, indirme veya GPU sorunu varsa mevcut Qt haritasına geçer.
- CORE’a dön: konuşma ekranına döner; gizli dünya çizim döngüsü durur.

Motor ve harita katmanları yalnızca panel açılınca indirilir. Konum otomatik
alınmaz; arama metni mevcut yer arama servisine, görüntülenen harita alanı ilgili
harita servisine gider. Bu panelde kamera, mikrofon, dosya seçimi, hesabın oturum
çerezleri veya Python komut köprüsü yoktur. Yerel dosya erişimi üç paket dosyasıyla,
uzak erişim üç harita/motor sunucusuyla sınırlıdır. Sağlayıcı atıfları görünürdür.

## Kaynaklar ve kabul

- [CesiumJS 1.123 / Apache-2.0](https://github.com/CesiumGS/cesium/tree/1.123)
- [OpenStreetMap atıf ve kullanım ilkeleri](https://operations.osmfoundation.org/policies/tiles/)
- [Esri World Imagery hizmet bilgisi](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer)
- [Gemini Live ses yapılandırması](https://firebase.google.com/docs/ai-logic/live-api/configuration)

`tools/verify_earth.py` gerçek QtWebEngine/WebGL ve ağ görüntüsü yüklenmesini,
üç katmanı, sokak seviyesine uçuşu, 2D geçişini ve gizleme/göstermeyi denetler.
Windows ve Linux sonuçları PR kabul kaydında tutulur. Bir donanım veya hizmet
denenmediyse doğrulanmış sayılmaz. Bu test panorama hizmetinin tüm sokakları
kapsadığını, fiziksel kullanıcı GPU'sunu veya gerçek ses çıkışını kanıtlamaz.
