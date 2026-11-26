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

## Temiz Git kurulumunun kesinti sonrası açılışı

Aşama 1, kısmen tamamlandı. Süreç git merge tamamlanır tamamlanmaz kapanırsa
yeni işlem kaydıyla hedef commit ve yedek dal açılışta doğrulanır. Kişisel
dosyalar ve izlenen yerel değişiklikler korunur. Subprocess birleştirmeden
sonra gerçek os._exit ile durduruldu; yerel değişiklik varken açılış durdu,
temiz içerikle kurtarma çevrimdışı tamamlandı. Linux/Python 3.13 üzerinde
48 güncelleyici/açılış/HUD testi geçti. Stash'li veya kısmen yazılmış Git
çalışma ağacında otomatik yıkıcı onarım uygulanmaz.

#213 için ilk genel Linux koşusunda sağlayıcı öz sınaması 139 çıkış koduyla
sonlandı. Ses kataloğu ön yüklemesi panel kapandıktan sonra tamamlanabiliyordu.
İşçi iş parçacıkları artık yalnız Python olayını işaretler. Panel kendi Qt
zamanlayıcısıyla sonucu alır; panel kapanınca zamanlayıcı da kapanır. NVIDIA
sağlayıcı kurulumu hata verirse düğmeye sonuç dönmesini engelleyen tanımsız
değişken düzeltildi. Yerel Python 3.13'te sağlayıcı kontrolleri üç ayrı
süreçte 101/101 geçti. İlk çökmenin yerel çağrı yığını elde edilemedi.

## Sonraki oturum için kabul durumu

Başlangıçta ana dalın en son commit'ini ve aşağıdaki PR sonuçlarını kontrol edin.
SQLite günlük dosyalarının korunması #209 (32e513b) ile ana daldadır.

| Aşama | Durum | Doğrulanan kapsam ve açık kabul |
| --- | --- | --- |
| 1 — Kararlılık ve güvenlik | Geliştiriliyor | #210 imza denetimi, #213 kesintiden sonra temiz Git kurulumunun kurtarılması ve #211 Windows yerinde geçişi. Gerçek yayıncı parmak izi, Android sertifika geçişi, eklenti izolasyonu ve uzun süreli çalışma açık. |
| 2 — Beyin | Kısmen tamamlandı | #212 ile 1.000 giriş sınıflandırıldı. 895 konuşma yönteminin 23'ü yerel işleme bağlı. 76 davranış ilkesi, 29 uygulama girdisi ve 30 alan envanterde. #214 açık izinli RouteLLM sohbeti ve arka plan görev bağlantısı. Gerçek hesap kotası, sağlayıcı geçişleri ve görev bütçeleri açık. |
| 3 — Ses | Fiziksel cihaz bekliyor | Türkçe mikrofon, araya girme, sürekli dinleme ve ses gecikmesi için gerçek cihaz ölçümü açık. |
| 4 — Hafıza | Kısmen tamamlandı | SQLite bütünlüğü ve güncelleme koruması doğrulandı. Anlamsal geri çağırma, belge kaynağı ve kişisel veri yaşam döngüsünün toplu kabulü açık. |
| 5 — Araçlar ve cihazlar | Geliştiriliyor | Mevcut araç izinleri korunuyor. MCP, görev kurtarma, eklenti sınırları, kişisel hesap ve oda kısıtlarının uçtan uca kabulü açık. |
| 6 — Görseller | Kısmen tamamlandı | Blender otomatik testleri mevcut. Kullanıcının GPU, kamera, Holo Masa ve ikinci ekran kabulü açık. |
| 7 — Performans | Test bekliyor | Blender indirme kaynakları ve Qt kapanışı için hedefli kontroller var. Aynı donanımda bütün performans ölçümlerinin önce/sonra karşılaştırması açık. |
| 8 — Nihai kabul | Kısmen tamamlandı | #211 Windows kaynak paketi temiz kurulum, yeniden kurulum, güncelleme ve geri dönüş testinden geçti. Üretim imzalı dağıtım, saha kabulü ve nihai rapor açık. |

#213 ana dal commit'i 7ae34941bdfe23f5efcc3f047c1be4abe1f367ee.
#211 ana dal commit'i f7ab275633758cd95cb04b917a168d6ef2c4a3ca.
Windows paket kabulünde CRLF/LF farkı bulundu. Yeni karşılaştırma Windows satır
sonlarını tanır. Bağımlılık satırı değiştiğinde dosyalara dokunmadan durur.
[Windows paket kabulü](https://github.com/fatmakahraman304-hash/JARV-S/actions/runs/45873297505)
ve [eski kurulumu taşıma komutları](dependency-audit-2026-11-26.md) kaydedildi.
İmzalı yayın yapılandırılmış profilde gerçek yayıncı imzası gereklidir.

GÜNCELLE panelinde ZIP aktarımı sırasında bilinen içerik boyutuyla yüzde,
boyut bildirilmediğinde alınan KiB gösterilir. Gösterge indirme baytlarına
dayanır. Bildirimler her bağlantı denemesinde en çok iki saniyede bir
üretilir. Yedekleme ve dosya kurulumu kendi aşama mesajını gösterir.
Linux/Python 3.13.5 üzerinde güncelleyici, imza, arayüz, bakım ve ilişkili
regresyon kapsamındaki 76 hedefli test geçti. Kullanıcının Windows kurulumunda
bildirilen takılmanın aynı nedenden kaynaklandığı henüz doğrulanmadı.

## Ana dalda sonraki çalışmalar

Bu kayıt güncellenirken ana dal 4833497e017a4cfca83759e8897701d7e90a8b77
commit'indeydi. #214 ana dala alındı (3b279dc7ca3ad07407e6c1fc73e9392b5ebb5b11).
#215–#225 arasında yardım, kullanıcı eklentilerinin incelenmesi ve onayı,
ses sağlayıcıları ile gerçek zamanlı oturum altyapısında değişiklikler
birleşti. Bu özelliklerin gerçek hesap ve cihaz kabulü ayrıca açıktır.
İndirme göstergesi yeni ana dal üzerinde 76 hedefli testle tekrar doğrulandı.

## Git güncellemesinde eşzamanlı düzenleme koruması

Geliştiriliyor — #233, yerel değişiklikleri önce geçici bir Git çalışma
ağacında dener. Gerçek çalışma ağacına yeni düzenleme gelirse kayıtlı stash
korunur. Gerçek uygulama beklenmedik biçimde yarıda kalırsa işlem kaydı
bırakılır ve otomatik yeniden başlatma durur. Bu durum kullanıcı tarafından
incelenmelidir. Linux ve Python 3.13 ortamında gerçek Git depoları ile
çakışma ve eşzamanlı düzenleme senaryolarını içeren 58 test geçti.
Windows CI sonuçları PR üzerinde izlenir.

## Açık dosya tanıtıcısı araştırması

Test bekliyor — 1.158 testlik Linux koşusu başarılı oldu, beş test atlandı.
Koşudaki iki açık metin dosyası uyarısı testlerdeki main.py okuyucularına
izlendi. Kapanışta görülen açık ikili okuyucu uyarısı, gerçek Blender alt
sürecini kullanan LiveLink testinin tek başına çalıştırılmasında yeniden
üretildi. Test kapatılırken süreç çıktısı artık toplanır ve süreç beklenir.
Üç hedefli test grubu 17 testte ResourceWarning uyarısı vermeden geçti.
Bu bulgu tüm uygulamanın uzun süreli kaynak kullanımını doğrulamaz.

Kodlama ajanında iki süreç akışının açık kaldığı ayrıca gerçek alt süreçle
yeniden üretildi. #236 (88a89f56e313d6b427259c10bb2b6beda11b78ec) bu
akışları kapatır. Kodlama ajanı testleri 36/36 geçti. Blender test matrisi,
bozuk indirmeleri reddedip resmî aynayı da deneyerek sürdürülür.
