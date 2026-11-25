# FRIDAY geliştirme aşamaları

Kullanıcının belirlediği sıra geçerlidir. Aynı anda bir aktif aşama yürütülür.
Bir düzeltmenin birleşmesi, bütün aşamanın tamamlandığı anlamına gelmez.

| Aşama | Kapsam | Durum |
| --- | --- | --- |
| 1 — Sistem kararlılığı | Hatalar, güncelleyici, veri güvenliği, dayanıklılık | **Aktif** |
| 2 — Yapay zekâ beyni | 1.000 yetenek, düşünme, öğrenme, Abacus AI, sohbet | Bekliyor |
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

## Son çalışma: açılış ve yarım güncelleme

`main.py`, üçüncü taraf modüllerden önce `core/startup_guard.py` kontrolünü çağırır.
Bekleyen yazma/geri dönüş kaydı veya canlı güncelleyici varken normal açılış durur.
Kontrol, uygulama verisi veya yedek silmez; kurtarma çevrimdışı komutla yapılır.
Regresyon testleri gerçek giriş noktasını ayrı süreçte çalıştırır ve uygulama
modüllerine ulaşılmadığını, kişisel dosyaların korunduğunu sınar.

Bu çalışma Aşama 1'in yalnızca bir parçasıdır. Fiziksel Windows cihazında güç
kesintisi, gerçek mikrofon/hoparlör ve uzun süreli çalışma **DOĞRULANMADI**.
Nihai kabul ve Aşama 2'ye geçiş henüz ilan edilmedi.

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
donanım üzerinde doğrulandığı anlamına gelmez. Aşama 1 **aktif** kalır.

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
Yeni bağımlılık, şema veya kullanıcı verisi değişikliği yoktur. Aşama 1 aktiftir.

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

Sentetik verilerle bozuk şekil, eksik ana dosya, geçici ad çakışması, ana/yedek
flush hatası, kilitli hedef ve iki süreçten yazma sınanır. Gerçek kullanıcı
anahtarları okunup değiştirilmez; ses, persona ve sağlayıcı seçimi kuralları
değiştirilmez. Fiziksel güç kesintisi ve uzun süreli cihaz kabulü **DOĞRULANMADI**.
