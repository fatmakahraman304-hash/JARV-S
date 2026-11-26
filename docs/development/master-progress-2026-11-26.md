# FRIDAY ana geliştirme kaydı — 26 Kasım 2026

Yeni ana talep için başlangıç: `6e719a2753462e0c4e7206178ff1c517dab26bbc` (#205).
İzole dal: `friday-dev/stability-audit-20261126`. Eski aşama raporları tarihsel
kanıttır; bu genişletilmiş talebin tamamlandığı anlamına gelmez.

## Kapsam ve korunacak sözleşmeler

Tek FRIDAY kişiliği, mevcut kadın sesi, tasarım, 30 çalışma alanı, kullanıcı
ayarları/hafızası ve izin mekanizmaları korunur. Hesap, model, kamera, mikrofon,
GPU ve gerçek cihaz kullanılmadan bunların çalıştığı iddia edilmez. Güvenli,
geri alınabilir teknik değişiklikler bağımsız geliştirilir. Başarısız kod ana
dala alınmaz. Kritik değişiklik öncesi bu başlangıç commit'i geri dönüş noktasıdır.

| Aşama | Yeni talep için durum | Sonraki somut kapsam |
| --- | --- | --- |
| 1 — Kararlılık/güvenlik | AKTİF; bu değişiklik yalnız aşağıdaki alt kapsamı uygular | Secret store, eklenti izinleri/izolasyon, bağımlılık/CVE, güvenli mod ve güncelleyici imza politikası açık |
| 2 — Beyin | Mevcut işlevler korundu; yeni gereksinimler açık | Sağlayıcı/model doğrulama, 1000 girdinin altı durumlu envanteri, görev/model bütçesi |
| 3 — Ses | Mevcut işlevler korundu; saha kabulü açık | Gerçek Türkçe mikrofon, yankı, barge-in, çevrimdışı ölçüm |
| 4 — Hafıza | Mevcut JSON/SQLite ve unutma kuralları korundu | Kaynaklı öğrenme, RAG/vektör ihtiyacının ölçümü, düzenleme/silme/backup uçtan uca |
| 5 — Araçlar/görevler | Mevcut görev, tarayıcı, Composio ve cihaz altyapısı korundu | MCP SDK/protokol doğrulama, izinli uzman yürütücüler, cihaz/oda sınırları |
| 6 — Görseller | Tasarım değiştirilmedi | Holo Masa/Blender/harita gerçek cihaz kabulü, görsel kalite/ölçüm |
| 7 — Performans | Tarihsel ölçümler yeni hız iddiası sayılmaz | Aynı cihaz/konfigürasyonda açılış, ses, kaynak ve maliyet ölçüm aracı |
| 8 — Nihai kabul | AÇIK | Windows/Linux Python 3.13 CI + fiziksel cihaz/hesap + güvenli dağıtım |

Yeni talepte Abacus AI/RouteLLM ve DeepSeek desteği isteniyor. Başlangıç
kodunda bu sağlayıcılar önceki talep nedeniyle kaldırılmış ve bazı ayar
okuma/yazma yollarında engellenmiş durumda. Bu artık Aşama 2 için açık geri
entegrasyon gereksinimidir. Eski kişisel anahtarlar geri getirildi veya servis
çalışıyor gibi gösterilmez. Resmî uç noktalar/model listeleri doğrulanmadan ve
kaldırma geçişi veri kaybetmeden tasarlanmadan rastgele model adı eklenmez.

## Bu değişikliğin gerçek uygulaması

1. **Açılışta otomatik ZIP kurtarma:** mevcut çevrimdışı, hash doğrulamalı
   kurtarma kullanılır. Bekleyen işlem için canlı güncelleyici kilidi varsa
   açılış durur. Güncel dosya/yedek değişmişse işlem ve yedekler korunur.
   Doğrulanmış kurtarma sonrasında Python süreci yeniden yürütülür; iki
   sürümün belleğe yüklenmiş kodu birlikte çalıştırılmaz. Git veya belirsiz
   işlem kaydı otomatik reset/temizlik yapılmaz.
2. **Anahtar koruması:** ZIP güncelleyici `.jks`, `.keystore`, `.p12`, `.pfx`,
   `.key`, `.pem` dosyalarını getirmez, üzerine yazmaz veya eski manifestten
   silmez. Bunlar `.gitignore` kapsamındadır. Eski bir kurtarma kaydı bu
   tür dosyaları değiştirmeyi içerirse otomatik kurtarma durabilir; kayıt,
   yerel dosya ve yedek korunur, elle inceleme gerekir.
3. **Android:** depodaki eski JKS sürüm kontrolünden çıkarılır; yerel kopya
   silinmez ve geçmiş yeniden yazılmaz. Release artık anahtarsız/unsigned
   adaydır. Debug ayrı uygulama kimliği kullanır; release uygulamasının
   verisini ezmez. Onaylı CI ortamı, depo dışı anahtar ve beklenen yeni
   sertifika ile manuel signed aday üretimi hazırlanır. Eski açık sertifika
   açıkça reddedilir. Otomatik stabil APK yayını kaldırılır.
4. **Kaynak adayı imzası:** mevcut cryptography bağımlılığıyla gerçek Ed25519
   imzalama/doğrulama eklenir. İmza arşivin SHA-256, boyut ve tam commit'ini
   bağlar; güvenilir açık anahtar ayrı sağlanır. Aynı baytlar doğrulanıp
   açılır. Yanlış imza/anahtar/commit, çıkarma başlamadan reddedilir.
   İmzasız aday üretimi mevcut test akışını korur; bu aday yayıncı doğrulaması
   almış sayılmaz.

Bu imza aracı **GÜNCELLE'nin tüm Git/ZIP kanallarında zorunlu yayıncı
imzası doğrulaması yaptığı anlamına gelmez**. Sabit güven kökü, imzalı yayın
kanalı, anahtar devri/iptali ve kullanıcı kurulumuna güvenli ilk dağıtım
ayrı açık çalışmadır. Hiçbir gerçek üretim imza anahtarı oluşturulmadı,
yüklenmedi veya kullanıcı hesabına secret yazılmadı.

## Kanıtlar ve açıklar

İlk statik tarama: 478 izlenen dosya, 387 Python dosyası; Python AST sözdizimi
hatası ve `core/gui/memory/actions/plugins/providers/dashboard` ad alanlarında
bulunamayan mutlak iç modül hedefi yok. Dinamik/opsiyonel import, thread ve
uzun süreli bellek sızıntısı garantisi değildir. 31 proje için kaynak HEAD,
README/lisans ve bakım durumu [ön inceleme kaydındadır](upstream-review-2026-11-26.md).
Bütün projelerin bütün kodu incelendi veya 31 entegrasyon yapıldı sayılmaz.

Yerel ilk hedefli koşu: **79 test geçti**; gerçek Ed25519/tahrifat, APK imza
politikasında sentetik alt süreçler, güncelleyici/anahtar koruma, kesilmiş
süreçten açılış kurtarma ve kimlik koruması dahil. Yerel ortam Python 3.12;
Windows/Linux Python 3.13 CI sonucu PR kaydına eklenecek. Bütün suite
sonucu ayrıca kaydedilir; başarısız testler silinmez veya atlanarak saklanmaz.

Android fiziksel yükseltme, Play hesabı/kurulu sertifika incelemesi, yeni
anahtarın güvenli sahipliği ve güven kökü dağıtımı **DOĞRULANMADI**.
[Android rotasyon adımları](android-signing-rotation.md) tamamlanmadan yeni
signed aday stabil URL'ye yayımlanmaz; eski APK zaten kurulu olabilir.

## Yeni talep ile eski tercih arasındaki fark

Abacus AI/RouteLLM ve DeepSeek daha önce kullanıcı isteğiyle kaldırılmıştı.
Yeni ana talep bunları destek listesine yeniden alıyor; güncel talep geçerlidir.
Bu Aşama 1 değişikliği henüz sağlayıcıları veya mevcut ayar temizleme politikasını
geri getirmedi. Aşama 2'de resmî endpoint/model doğrulaması, izin/maliyet sınırları,
konfigürasyon geçişi ve yeni regresyon sözleşmeleri birlikte uygulanmalıdır.

Yerel geniş koşu gerçek Blender ikilisini bulduğu için Blender model/render
kabulünü de çalıştırdı. Ayrı 150 saniyelik tanılama koşusu Blender render alt
sürecinde süre sınırına ulaştı; başarılı tam regresyon sayılmadı. Hiçbir Blender
testi kaldırılmadı, atlanacak biçimde değiştirilmedi veya gizlenmedi. CI'da
çekirdek regresyon ve mevcut Blender kabul kapsamları ayrı izlenecek.

## Aşama 1 — araç sonucu bütünlüğü

[Boş sonucun başarıya dönüşmesini engelleme](tool-outcomes.md), kayıtlı araçlar,
konuşma/arka plan/bulut ve gerçek onay callback'lerinde ortak sonuç dönüşümü
kullanır. Yerel test ve açık sınırlar ilgili kayıttadır. CI ve birleşme durumu
GitHub PR kaydından doğrulanmalıdır; eski kayıt yeni başarı kanıtı sayılmaz.

## Aşama 1 — isteğe bağlı Windows kimlik bilgisi koruması

Başlangıç güvenilir main: `36970db90ba948bfcf2337a4a6810fce058b22e9`
(PR #207; iki işletim sisteminde Python 3.13 regresyonu ve provider kontrolleri
başarılı). [Kullanım ve geri dönüş](credential-storage.md).

Native Windows DPAPI için açık etkinleştirme/devre dışı bırakma komutu,
primary/backup ayrı değerlerini koruyan geçiş ve merkezi şifre çözücü eklendi.
Eski doğrudan JSON tüketicileri ortak okuyucuya bağlandı; normal ayar yazması
koruma tercihini kaybetmez. Yanlış profil, bozuk ciphertext ve yarım yayın
testleri yeni dosyalardadır. Gerçek kullanıcı verisi/anahtarı okunmadı,
taşınmadı veya otomatik şifrelenmedi; tasarım ve kadın sesi değiştirilmedi.

Yerel ilgili regresyon: Python 3.12'de 63 test, 61 başarılı ve yalnız
2 gerçek Windows DPAPI testi platform nedeniyle atlandı. Açılış/hafıza/onay/
araç sonucu entegrasyonlarında 91 test ve sağlayıcı kontrollerinde 99/99 geçti.
İlk açılış koşusu yeni modül henüz Git indeksine eklenmediğinden izole kaynak
kopyasında bulamadı; dosya izlemeye alındıktan sonra aynı 91 test değişmeden
geçti. Windows/Linux Python 3.13 CI sonucu PR'ye kaydedilecek. Linux/macOS secret
store, cihazdaki profil kurtarma kabulü ve tarihsel açık metin yedeklerinin
kullanıcı denetimi açık. Bu, eklenti izinleri/izolasyon, CVE denetimi,
güvenli mod ve zorunlu yayıncı imzasını tamamlamaz. Aşamalar 1–8 açık kalır.
## Aşama 1 — ZIP güncellemesinde açık SQLite veritabanı

Bu oturumun ana dal başlangıcı ve geri dönüş noktası
`36970db90ba948bfcf2337a4a6810fce058b22e9` (#207).

- ZIP güncelleyicisi .db, .sqlite ve .sqlite3 veritabanlarının günlük ve
  paylaşılan bellek dosyalarını korur. Eski dosya listesinde yer almaları
  bunların kaldırılmasına yol açmaz. Kaynak paketi oluşturulurken .sqlite3
  yan dosyaları da paket dışında kalır.
- Linux/Python 3.13 üzerinde iki regresyon testi düzeltmeden önce başarısız
  oldu. Düzeltmeyle güncelleyici, sesli güncelleme eklentisi ve kaynak paketi
  testlerinin 57'si geçti. Açık WAL bağlantısı sırasında yerel yan dosyaların
  baytları korundu. Yeniden açılan veritabanı bütünlük denetimini geçti ve
  kaydedilmiş satır okundu. Ağ yanıtları bu testte yerel örnektir.
- Ürün sürümü ve Windows paketi yayımlanmadı. Yukarıdaki aşama tablosunda
  açık kalan işler sürüyor. Bu değişiklik için Windows panelinden gerçek
  yükseltme ve yeniden başlatma kabulü bekleniyor.

Ek doğrulamada 392 Python dosyası Python 3.13 ile ayrıştırıldı. Başlangıç
kurtarma, imza, Android imza politikası, araç sonucu ve hafıza kapsamında
40 test, yetenek kataloğu ve düşünce stüdyosunda 26 test geçti. Genel yerel
koşu 180 saniyelik süre sınırında tamamlanmadı. İlk Windows CI koşusunda
sentetik eski manifest requirements.txt dosyasını içermediği için CRLF ile
yazılan dosya haklı olarak çakışma sayıldı. Test artık mevcut dosyanın gerçek
özetini kaydederek kurulu bir sürümü temsil eder. CI sonuçları PR #209'dadır.

### #209 birleşme ve tekrar koşusu

Güncelleyici düzeltmesi [#209](https://github.com/fatmakahraman304-hash/JARV-S/pull/209)
ile ana dala alındı. Birleşen kod `32e513b2eb02d40ee1c422961512e5d6d3dbf420`.
GitHub regresyonunda 1.047 testin Windows'ta 1.023'ü, Ubuntu'da 1.022'si
geçti; sırasıyla 24 ve 25 test atlandı. İki sistemde güvenlik ve kurtarma,
Windows kurulum, yeniden kurulum ve HUD kabulü ile kaynak paket adayı
kontrolleri başarılı. Kaynak paketi adayı üretimi bir stabil sürüm yayını değildir.

Yerel bağımlılık tanılamasında yalın Python'da httpx ve PyQt6 gibi modüller
eksikti. Depodaki requirements.txt izole Python 3.13.5 ortamına kuruldu.
Birleşen kodla ağaç içeriği aynı olan adayda tam koşu 267,380 saniyede bitti.
1.044 test geçti, 3 test atlandı (iki Windows testi ve 250 MB Blender
kılavuzunu indirme). Gerçek Blender modelleme, canlı bağlantı ve render
testleri bu koşuya dahildi. Çıktıda SSL soketleri için ResourceWarning
görüldü; kaynak yaşam döngüsü tanılaması açık kalıyor.
15 izlenen JavaScript dosyası Node sözdizimi denetiminden geçti.

Aynı Linux ortamında depo ölçüm aracıyla üçer ayrı süreçte, dönüşümlü,
Qt offscreen ve render kapalıyken alınan medyanlar aşağıdadır.
Eşzamanlı test yükü vardı. Sayılar HUD hazırlığının örnek ölçümüdür.

| Ölçüm | Önce (#207) | Sonra (#209) |
| --- | ---: | ---: |
| HUD bağımlılıklarının yüklenmesi (ms) | 176,52 | 185,17 |
| HUD bileşeninin oluşturulması (ms) | 39,77 | 49,66 |
| Gizli HUD ile 1 saniyede süreç CPU zamanı (ms) | 19,99 | 11,41 |
| Süreç belleği (MiB RSS) | 68,31 | 67,99 |

Katalog sayımında 76 davranış ilkesi, 29 uygulama girdisi ve 895 konuşma
yöntemi bulundu. Bu son grupta 18 yerel hesaplama/karşılaştırma bağlantısı
var. Altı durumlu işlev ve uçtan uca çalışabilirlik envanteri açık.
Takipte Aşama 1 için [#208](https://github.com/fatmakahraman304-hash/JARV-S/pull/208)
anahtar saklama çalışmasının birleşme durumunu kontrol et. İmzalı kanalın
güven kökü dağıtımı, saha ses/cihaz testleri ve üstteki kabul açıkları sürüyor.

## Aşama 1 devamı — yayıncı güveni, yeniden başlatma ve kaynak ömrü

#208 ana dala alındı (`5abc33f2546a3160140aa4f04c75ad92a1d4656e`).
SQLite düzeltmesi korundu. Windows DPAPI tercihe bağlıdır. #208'in dokuz CI
akışı başarılı. Yeni güven ve güncelleme yolunun kullanım koşulları
[source-signatures.md](source-signatures.md) dosyasındadır.

- Geliştiriliyor — imza kontrolü, profilde seçildikten sonra her iki kurulum
  kanalında zorunlu. Gerçek yayıncı parmak izi ve signed release bekleniyor.
- Geliştiriliyor — arşiv yanıtı parçalar halinde okunur, süre ve boyut
  kontrolü yapılır. Git arka planda kimlik bilgisi istemez. Yardımcı süreç
  açılamadığında kullanıcı yeniden başlatmayı aynı düğmeden yeniden deneyebilir.
- Tamamlandı — Blender kılavuzu HTTP hata gövdesi, geçici dosya tanıtıcısı ve
  yarıda kalan indirme dosyası temizlenir. Eski kodda tracemalloc ile bir SSL
  soketi tahsisi kılavuz indirme iş parçacığına kadar izlendi. Tüm uygulama
  için sızıntısız uzun çalışma kabulü açıktır.
- Kısmen tamamlandı — Python 3.13.5 ortamında ilk lisans envanteri 182 dağıtım
  içerdi. 89'unda araç lisans dosyası toplayamadı. pip-audit izole ortamın
  site-packages kapsamında cryptography 49.0.0 (2), Pillow 12.3.0 (42) ve
  PyPDF2 3.0.1 (1) için bilinen güvenlik kayıtları döndürdü. Bunlar toplam
  45 paket danışma kaydıdır. Platform ve lisans uyumluluğu ayrı doğrulanır.
- Test bekliyor — yerel hedefli 106 testte 104 geçti, 2 Windows testi atlandı.
  Üretim anahtarı, cihaz verileri ve gerçek hesaplar kullanılmadı.
- Fiziksel cihaz bekliyor — Android rotasyonu ve önceki APK üzerinde yükseltme,
  gerçek Windows kullanıcı profilinde anahtar taşıma ve panel takılmasının
  kullanıcının cihazındaki sebebi. Aşama 2–8 için üstteki açık işler sürüyor.
