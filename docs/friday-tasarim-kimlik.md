# FRIDAY — ortak kimlik ve cihaz tasarımı

İnceleme temeli: `0099377c642f9d15186c284e22b02a695b65f3b2`.
Kullanıcının tercihi doğrultusunda **Aether API sağlayıcısı korunur**; bu,
eski asistan kimliği değil, yapılandırılmış üçüncü taraf hizmetin gerçek adıdır.

## Görünür kimlik

Masaüstü başlığı/rozeti, başlangıç, bildirim ve araç metinleri, web/PWA
başlığı/manifesti, giriş ekranı, TV/projeksiyon sayfası, cihaz modülleri ve
Android alıcı metinleri FRIDAY olarak birleştirilir. Girişte HTML etiketleriyle
bölünmüş eski logo da değiştirilir. Ana Python arayüzü ve ses sınıfı artık
`FridayUI` / `FridayLive`; kurulu eski eklentiler için salt okunur sınıf
uyumluluk takma adları kalır. Eski adı geri yazan otomatik yeniden adlandırma
aracı ve kaynakları kendi kendine commit eden iş akışı kaldırılmıştır.

Yeni kurulumlarda veri ve proje dizinleri FRIDAY adını kullanır. Var olan
kullanıcı dizinleri taşınmaz veya silinmez; geçmiş hafıza, proje, log ve Blender
çıktılarının bulunduğu yer seçilir. Kişisel konuşma metinlerinde ve kayıtlı
kullanıcı adında toplu metin değişikliği yapılmaz. Seçili ses/model/API anahtarı
ve özel vurgu rengi korunur. Yeni geliştirme dalları `friday-dev/` ile açılır;
eski geliştirme dalları hâlâ tanınır.

## Tasarım

- Gece laciverti yüzeyler; yüksek karşıtlıklı açık metinler; camgöbeği birincil
  ve mor ikincil vurgu. Qt paleti ve ortak `friday-theme.css` aynı renk ailesini
  kullanır. Web ile dashboard CSS kopyaları bire bir eşit sınanır.
- Telefonda güvenli alan payları, 16 px giriş metni ve küçük ekran düzeni;
  tablette genişleyen yerleşim; TV/projeksiyonda görünür klavye/kumanda odağı;
  saatte kısa FRIDAY işareti ve korunmuş yuvarlak ekran yerleşimi.
- Android'de FRIDAY ikon/banner, koyu tema, bağlantı durum kartı, geniş ve
  odaklanınca belirginleşen kumanda düğmeleri. Uygulama kimliği, eşleştirme
  şeması ve imzalama dosyası korunur; kaynak sürümü 2.3 / kod 13'tür.
- Harici font indirilmez. Mevcut HUD, hologram geometrisi, ses animasyonu,
  cihaz işlevleri ve erişim/onay kontrolleri korunur.

## Neden bazı eski teknik kimlikler bulunur?

Bunlar arayüz markası değildir. Hepsini körlemesine değiştirmek mevcut
kurulumları ve özel verileri bozardı:

| Kimlik | Koruma nedeni |
| --- | --- |
| GitHub depo adresi ve geçmiş commit/PR kayıtları | Depo/hesap veya Git geçmişi bu işte yeniden adlandırılmaz |
| Önceki veri/proje/log klasörleri | Kullanıcı hafızası ve çıktıları yerinde kalır |
| Güncelleyici `.aether-*` işlem kayıtları ve `AETHER/1`, `AETHER/2` biçimleri | Yarım güncelleme ve geri alma kayıtları tanınmaya devam eder |
| Eski çevre değişkenleri, otomatik başlatma kimlikleri ve ikon dosyası | Var olan başlatıcılar ve entegrasyonlar çalışır |
| `aether_*` tarayıcı depolama alanları ve konuşma rolü | Ayar/hafıza/cihaz oturumu silinmez veya yeniden ortaya çıkarılmaz |
| Dashboard şifreleme tuzu ve cihaz keşif etiketi | Eski istemciler yeni sürümle eşleşebilir; şifreli mesaj biçimi değişmez |
| `com.aether.alici`, deep-link şeması ve mevcut APK indirme adresi | Android kurulu uygulama verisi, izinleri ve güncelleme uyumluluğu |
| Aether API ve upstream atıfları/lisans | Gerçek sağlayıcı/üçüncü taraf kimliği yanlış biçimde FRIDAY diye etiketlenmez |

Android imzalama anahtarının daha önce açık olduğu kabul kaydında belgelenmişti.
Anahtarın baytları/sertifikası bu değişiklikte değiştirilmez. CI yeni arayüzü
**friday-receiver-candidate** APK artifact'ı olarak derler. Otomatik push/PR
koşusu bunu nihai sürüm olarak yayımlamaz. Mevcut sertifikayla yayın yalnızca
main dalında açıkça seçilen manuel `publish` girdisiyle yapılabilir; güvenli
anahtar geçişi ve gerçek cihazda veri koruyan yükseltme hâlâ ayrı kabul ister.
Eski stabil APK adresi zaten kurulu istemciler için teknik uyumluluk adresidir.

## Doğrulama ve sınırlar

Kimlik testleri; birleştirilmiş HTML metnini (bölünmüş logolar dahil), Qt
etiketlerini, eski veri okumasını, sınıf uyumluluğunu, sağlayıcıyı, şifreleme
tuzunu/UDP paketlerini, imzalama dosyası özetini ve lisans atfını denetler.
FRIDAY önekli harita/GitHub komutları ayrıca sınanır; mevcut açık eski komut
uyumluluğu korunur. İlk geniş denetimde bu iki önek hatası yeniden üretildi
ve düzeltildi. Normalizasyon testindeki yeni girdi/eski beklenen metin
uyuşmazlığı da yeni kimliğe göre düzeltilip eski girdi ayrıca korunur.

`verify_friday_interfaces.py`, Chromium ve Firefox'ta 390×844, 320×568,
820×1180, 1440×1000, 1920×1080, 1280×800 ve 240×240 görünümlerini, ayrıca
üç dashboard sayfasını açar. JavaScript hatası, yatay taşma, kayıp mikrofon
kontrolü, eski görünür kimlik ve ayar koruması kontrol edilir; ekran görüntüsü
ve JSON kayıtları artifact olur. Qt penceresi de geçici ayarla görüntülenir.
Bu testlerde gerçek hesap, mikrofon, kamera veya kullanıcı oturumu kullanılmaz.

Performans karşılaştırması, ilk optimizasyondan önceki sabit tarihsel commit'e
karşı korunmuş timer/FBO kazancını sınar; her tasarım PR'sinin zaten optimize
HUD'ı bir kez daha hızlandırdığı iddia edilmez. Geometri farkı testi aynı
sabit referans paletinde çalışır; gerçek yeni tasarım ayrı ekran görüntülerinde
görülür. Önceki sıkı timer/FBO/görüntü eşikleri kaldırılmaz.

PR kaydı, son test edilen commit ve bütün CI sonuçlarını içerir. Gerçek
telefon/tablet, iOS Safari, TV/projeksiyon, saat ve Android cihaz kurulumu
**DOĞRULANMADI**; tarayıcıdaki ekran boyutu testi fiziksel cihaz kabulü değildir.
Android kaynak derlemesi tek başına fiziksel kumanda/erişilebilirlik kabulü
sayılmaz. Önceki canlı ses/model/GPU/uzun kullanım açıkları korunur.
