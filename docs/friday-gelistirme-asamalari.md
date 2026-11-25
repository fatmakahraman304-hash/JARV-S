# FRIDAY geliştirme aşamaları

Kullanıcının belirlediği sıra geçerlidir. Aynı anda bir aktif aşama yürütülür.
Bir düzeltmenin birleşmesi, bütün aşamanın tamamlandığı anlamına gelmez.

| Aşama | Kapsam | Durum |
| --- | --- | --- |
| 1 — Sistem kararlılığı | Hatalar, güncelleyici, veri güvenliği, dayanıklılık | Otomatik kabul geçti; saha doğrulaması açık |
| 2 — Yapay zekâ beyni | 1.000 yetenek, düşünme, öğrenme, Abacus AI, sohbet | **Aktif** |
| 3 — Ses sistemi | FRIDAY sesi, sürekli dinleme, hızlı konuşma | Bekliyor |
| 4 — Hafıza sistemi | Kalıcı hafıza, projeler, bağlam | Bekliyor |
| 5 — Otomasyon | Bilgisayar, uygulamalar, gerçek araçlar | Bekliyor |
| 6 — Görsel sistem | 3D yüz, holografik arayüz, dünya, görsel analiz | Bekliyor |
| 7 — Performans | Açılış, CPU, RAM, yanıt süresi | Bekliyor |
| 8 — Nihai sistem | Bütünleşik testler, Windows kurulumu, son denetim | Bekliyor |

## Aşama 1 kabul koşulları

- Güncelleme hatası ve kesintisinde önceki kod, kullanıcı verileri ve yedekler korunmalı.
- Yarım kurulumu normal uygulama açılışı çalıştırmamalı; kurtarma yolu açıklanmalı.
- Kurtarma, yeniden başlatma ve kontrollü kapanış testleri Windows/Linux üzerinde geçmeli.
- Veri yazımı, yedekleme ve geri yüklemenin hata senaryoları gözden geçirilmeli.
- Temiz Windows kurulumu ve yeniden kurulum doğrulanmalı; donanım/servis gerektiren açıklar ayrıca kaydedilmeli.

## Aşama 1 otomatik kabul kaydı ve geçiş

Son kabul edilen temel commit: `678f7a69be85ac239231bca077269bc513e3e268` (#189).

| Koşul | Doğrulama | Durum |
| --- | --- | --- |
| Güncelleme hatası/kesintisinde koruma | ZIP işlem günlüğü, hata enjeksiyonu, gerçek süreç kesintisi ve geri alma testleri; #181–182, #187 | Geçti |
| Yarım kurulumda güvenli açılış | Gerçek main.py alt süreci, kesilmiş ZIP ve çevrimdışı kurtarma; #184 | Geçti |
| Kurtarma, yeniden açılış ve kapanış | Gerçek alt süreçte erken kapanma, Qt HUD ve kaynak kapanışı; #189 | Geçti |
| Veri yazımı ve yedekleme hataları | JSON/SQLite, flush/replace hataları, unutma/eşitleme ve çok süreçli kilit; #185–188 | Geçti |
| Windows temiz/yeniden kurulum | Gerçek masaüstü penceresini açıp normal kapatma, tarayıcı motorları, yeniden kurulum ve pip check | Geçti |

[Windows/Linux regresyonu](https://github.com/fatmakahraman304-hash/JARV-S/actions/runs/45576344452):
her sistemde 873 test; 849 başarılı, 24 atlandı; sağlayıcı kontrolleri 99/99.
[Windows kurulum kabulü](https://github.com/fatmakahraman304-hash/JARV-S/actions/runs/45576344388):
kurulu ortamda 63 ilgili test geçti. Bu sonuçlar donanım ve canlı API kabulü değildir.
Fiziksel güç kesintisi, kullanıcı cihazında uzun süreli sesli oturum ve disk/ACL
kontrolleri Aşama 8'de **DOĞRULANMADI** olarak açık kalır. Aşama 2'ye geçiş,
bu açıkların kapandığı veya nihai ürünün hazır olduğu iddiasını taşımaz.

## Aşama 2 kabul koşulları

- Kısa cevaplar ve düzeltmelerde konuşma yönlendirmesi ile yetenek seçimi tutarlı olmalı.
- Konu değişimi, yalnız görsel/boş ileti ve sistem verisi sınırları ayrı ele alınmalı.
- Katalogdaki 1.000 girdi, 1.000 doğrulanmış bağımsız araç gibi sunulmamalı;
  gerçek işlem, açıklama yöntemi ve bağlı olmayan servis durumu ayrılmalı.
- Abacus önceliği/fallback konuşma bağlamını korumalı; kısmi cevap veya araç çağrısı tekrarlanmamalı.
- Yerel yöntemler ve mevcut araçlar istekle eşleşmeli; yönlendirme kullanıcı yetkisi sayılmamalı.
- Model/servis erişimi olmadan canlı zekâ/kalite/öğrenme artışı iddia edilmemeli.
- İlgili ve tam Windows/Linux regresyonları geçmeli; canlı servis ve davranış kabulü açıkça raporlanmalı.

## Aşama 2: kısa yanıt ve bağlam sınırları

Modüler konuşma hattında "Tarifi iki katına çıkar → Kaç kişi için? → 6"
akışı, yetenek tarafında porsiyon hesabını korurken çekirdek yönlendirmede
konuyu kaybediyordu. Görsel/boş kullanıcı iletisi ardından "devam et" ise
çekirdek tarafta eski konuyu yanlış taşıyabiliyordu. İkisi de düzeltmeden
önce testte yeniden üretildi.

`core/conversation_context.py`, kısa sayısal/miktar cevapları ve devam
ifadelerini iki yönlendirme katmanı için tek yerde tanımlar. Yalnız görsel
ve boş kullanıcı iletileri eski yönlendirmeyi sıfırlar. Sistem metadata'sı
yeni konu veya yetki oluşturmaz; sonraki gerçek devam mesajının önceki
isteği bulmasını engellemez. Açık yeni istekler ve acil güvenlik ifadeleri
normal biçimde yeniden yönlendirilir. Araçlar çalıştırılmaz, hafızaya yazılmaz,
servis çağrısı veya yeni yetki verilmez.

## Son çalışma: açılış ve yarım güncelleme

`main.py`, üçüncü taraf modüllerden önce `core/startup_guard.py` kontrolünü çağırır.
Bekleyen yazma/geri dönüş kaydı veya canlı güncelleyici varken normal açılış durur.
Kontrol, uygulama verisi veya yedek silmez; kurtarma çevrimdışı komutla yapılır.
Regresyon testleri gerçek giriş noktasını ayrı süreçte çalıştırır ve uygulama
modüllerine ulaşılmadığını, kişisel dosyaların korunduğunu sınar.

Aşama 1'in aşağıdaki otomatik kabulü tamamlandı. Fiziksel Windows cihazında güç
kesintisi, gerçek mikrofon/hoparlör ve uzun süreli çalışma **DOĞRULANMADI**.
Bunlar Aşama 8 nihai kabulünde açık kontrol olarak korunur; genel ürün hazır
ilan edilmedi. Yeni geliştirme odağı Aşama 2'dir.

## Aşama 1: hafıza dosyalarının güvenli yazımı

`memory/memory_manager.py`, ana JSON, önceki sürüm yedeği ve arşiv için
aynı diskte benzersiz geçici dosya kullanır. Dosya içeriği `flush` ve `fsync`
sonrasında atomik değiştirmeyle yayımlanır. Sabit `.tmp` adlarındaki mevcut
dosyalara dokunulmaz. Bozuk veya yanlış yapılı arşiv, boş arşiv kabul edilmez;
arşivleme ve ana hafızayı küçültme durur, mevcut dosyalar korunur. Arşivleme
başarı mesajı ancak arşiv yazıldıktan sonra verilir.
Son konuşma özetini okumak ana hafızayı veya yedeği yeniden yazmaz; disk yazma
izni bulunmasa da mevcut geçerli özet okunabilir.

Test kapsamı: sabit geçici adlardaki kullanıcı dosyaları; bozuk JSON/kategori
yapısı; ana dosya ve yedek `fsync` hataları; arşiv değiştirme hatası ve geçici
dosya temizliği. 21 Kasım 2026 unutma/eşitleme regresyonları korunur.
Bu koruma, gerçek elektrik kesintisinde disk/işletim sistemi dayanıklılığının
donanım üzerinde doğrulandığı anlamına gelmez. Bu düzeltme Aşama 1 otomatik kabul kapsamındadır.

## Aşama 1: aynı hafızaya birden fazla süreçten yazma

Önceden yalnızca süreç içi `RLock` vardı. İki ayrı süreç aynı eski hafızayı
okuyup farklı tercihleri kaydettiğinde son yazan diğerinin kaydını silebiliyordu.
Bu durum iki gerçek Python sürecinde eşzamanlı okuma/yazmayla yeniden üretildi.

`memory/process_lock.py`, süreç içi yeniden girilebilir kilidi Windows dosya
bölgesi kilidi/POSIX `flock` ile birleştirir. Kilit, okuma-değiştirme-yazma
döngüsünün tamamını kapsar; `core/sync_hub.py` içindeki mevcut `_lock`
bağlamları da aynı korumayı kullanır. On saniyede kilit alınamazsa kayıt
uygulanmaz ve anlaşılır hata verilir. Süreç zorla kapatıldığında kilidi işletim
sistemi bırakır. `.json.lock` dosyasının diskte kalması etkin kilit anlamına
gelmez; kilit dosyasını elle silmeyin. Son oturum özetinin salt okunur yolu
yazılabilir kilit dosyası açmaz.

Kabul testleri: aynı anda iki farklı kayıt, tutan süreci zorla öldürme sonrası
bekleyen yazıcının devamı, zaman aşımında verinin korunması ve yeniden deneme.
Kilit işbirliği yapan yerel FRIDAY süreçleri içindir; harici editörler veya ağ
dosya sistemi kilit davranışı için garanti verilmez. Gerçek fiziksel güç
kesintisi ve uzun süreli kullanıcı cihazı kabulü **DOĞRULANMADI**.

## Aşama 1: kilitli SQLite kaynağından yedekleme

`sqlite3.Connection.backup` kendi yeniden deneme döngüsünü kullandığı için
bağlantı zaman aşımı tek başına yedeklemeyi sınırlandırmıyordu. Gerçek SQLite
özel kilidi altında ayrı bir yedekleme sürecinin beklemede kaldığı yeniden
üretildi. Artık kopyalama aşaması ilerleme geri çağrısında 30 saniyelik bütçeyi
denetler. Bütçe aşılırsa geçici kopya temizlenir; kaynak korunur ve yarım hedef
yayımlanmaz. Kısa süreli kilitlerde işlem bütçe içinde devam edebilir.

Yeni kabul testleri, gerçek ayrı süreç ve gerçek SQLite kilidiyle zaman aşımı,
kilit kalkınca yeniden deneme ve kısa kilit sonrasında tamamlamayı sınar.
Bu bütçe kopyalama/yeniden deneme aşamasına aittir; işletim sisteminde takılan
dosya I/O'su veya sonraki bütünlük denetimi için gerçek zaman garantisi değildir.
Yeni bağımlılık, şema veya kullanıcı verisi değişikliği yoktur. Bu düzeltme Aşama 1 otomatik kabul kapsamındadır.

## Aşama 1: ayar ve API anahtarı dosyalarının bütünlüğü

Geçerli JSON olup kökü liste/null/metin olan ayar dosyası boş kabul ediliyordu;
sonraki ayar yazımı anahtarı kaybedip sağlam yedeği de yanlış yapıyla
değiştirebiliyordu. Sentetik anahtarla yeniden üretildi. Artık bu yapılar
bozuk dosya olarak ele alınır, orijinal korunur ve sağlam yedek kullanılır.
Ana dosya eksikse de okuma ve sonraki ayar değişikliği yedekteki değerleri korur.

Ayarlar ve yedekleri benzersiz, aynı diskte geçici dosya, flush/fsync ve atomik
değiştirmeyle yazılır. Geçici adlar mevcut Git gizlilik kurallarının kapsamındadır.
Sabit `.tmp` adındaki kullanıcı dosyaları korunur; başarısız yazım geçici
dosyaları temizler. Mevcut Windows kısa süreli dosya kilidi yeniden denemesi
korunur. Ayar değişikliği boyunca süreçler arası kilit kullanılır; iki ayrı
FRIDAY sürecinin farklı ayarları birbirini ezmez. Kilit dosyasını elle silmeyin.
Windows kurulu ortam testinde boş kilit dosyasının kilit alınmadan önce
yazılması yüzünden ilk oluşturma yarışı da yakalandı. İlk bayt artık işletim
sistemi kilidi alındıktan sonra yazılır; hafıza ve ayarlar aynı düzeltmeyi kullanır.

Sentetik verilerle bozuk şekil, eksik ana dosya, geçici ad çakışması, ana/yedek
flush hatası, kilitli hedef ve iki süreçten yazma sınanır. Gerçek kullanıcı
anahtarları okunup değiştirilmez; ses, persona ve sağlayıcı seçimi kuralları
değiştirilmez. Fiziksel güç kesintisi ve uzun süreli cihaz kabulü **DOĞRULANMADI**.

## Aşama 1: yeniden açılışta erken kapanmanın doğru raporlanması

Yeniden başlatma aracı, Qt onay dosyası varsa yeni süreç zaten kapanmış olsa
bile başarı bildiriyordu. Onay bırakıp kapanan gerçek alt süreçlerle yeniden
üretildi. Artık önce süreç durumu denetlenir, onaydan sonra en az bir saniyelik
ilk gözlem boyunca süreç açık kalırsa başarı kaydedilir. Erken kapanmada çıkış
kodu ve doğrulanamayan açılış bildirilir; ikinci bir süreç otomatik başlatılmaz.

Testler, onaydan önce kapanma, onay bırakmış ama bitmiş süreç, onaydan hemen
sonra kapanma, onayla birlikte açık kalan süreç ve eski uygulamanın çıkmaması
durumlarını kapsar. Bu gözlem uzun süreli çalışma veya ses/model hazırlığı
garantisi değildir. Bu düzeltme Aşama 1 otomatik kabul kapsamındadır.
