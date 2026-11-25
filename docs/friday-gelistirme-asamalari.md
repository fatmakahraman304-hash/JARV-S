# FRIDAY geliştirme aşamaları

Kullanıcının belirlediği sıra geçerlidir. Aynı anda bir aktif aşama yürütülür.
Bir düzeltmenin birleşmesi, bütün aşamanın tamamlandığı anlamına gelmez.

| Aşama | Kapsam | Durum |
| --- | --- | --- |
| 1 — Sistem kararlılığı | Hatalar, güncelleyici, veri güvenliği, dayanıklılık | Otomatik kabul geçti; saha doğrulaması açık |
| 2 — Yapay zekâ beyni | 1.000 yetenek, düşünme, öğrenme, model yönlendirme, sohbet | Otomatik kabul geçti; canlı model kabulü açık |
| 3 — Ses sistemi | FRIDAY sesi, sürekli dinleme, hızlı konuşma | Otomatik kabul geçti; gerçek ses kabulü açık |
| 4 — Hafıza sistemi | Kalıcı hafıza, projeler, bağlam | Otomatik kabul geçti; gerçek cihaz eşitlemesi açık |
| 5 — Otomasyon | Bilgisayar, uygulamalar, gerçek araçlar | Otomatik kabul geçti; kullanıcı masaüstü kabulü açık |
| 6 — Görsel sistem | 3D yüz, holografik arayüz, dünya, görsel analiz | Otomatik render kabulü geçti; kullanıcı GPU/kamera kabulü açık |
| 7 — Performans | Açılış, CPU, RAM, yanıt süresi | Otomatik kabul kapsamı tamamlandı; kullanıcı cihazı ölçümü açık |
| 8 — Nihai sistem | Bütünleşik testler, Windows kurulumu, son denetim | Otomatik kabul kapsamı tamamlandı; saha ve güvenli yayın engelleri açık |

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
- Model yönlendirme/fallback konuşma bağlamını korumalı; kısmi cevap veya araç çağrısı tekrarlanmamalı.
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

## Aşama 2 otomatik kabulü ve Aşama 3'e geçiş

| Koşul | Kanıt ve kapsam |
| --- | --- |
| Kısa yanıt, konu değişimi ve görsel sınırları | #190; çekirdek ve katalog yönlendirmesi ile gerçek pipeline mesaj oluşturma yolu |
| 1.000 girdinin kapsamı | `test_integrated_capabilities` tüm girdileri ve gerçek araç bağlarını denetler; uygulama maddeleri doğrulanmış işlem gibi sunulmaz |
| Model yönlendirme ve bağlam | Sağlayıcı regresyonları, konuşma devamlılığı ve kaldırılmış sağlayıcıların yeniden etkinleşmemesi |
| Tekrar çalıştırmama | Kısmi metin veya araç çağrısı sonrasında fallback yeniden oynatılmaz |
| Hatalı yedeklerin dinlendirilmesi | Kota/kimlik/model hatalarında mevcut uzun, geçici servis hatalarında kısa bekleme; süre bitince yeniden denenir |
| Başarısızlığın açık bildirimi | Tüm modeller beklemedeyse ağ isteği tekrarlanmaz ve hata döner; başarı uydurulmaz |
| Yetki ve yöntem sınırları | Yönlendirme yerel öneridir; gerçek araç ve onay sınırları korunur; katalog bağımsız işlem kanıtı sayılmaz |

Yedek modellerin bekleme kaydı oturum içinde, sunucu/model bazında tutulur;
ayar/anahtar dosyasına yazılmaz ve model sırası değişmez. Süresi bitmiş kayıtlar
temizlenir. Sonuç, bu sürümün ilgili ve tam Windows/Linux regresyonlarıyla
birlikte PR kabul raporunda kaydedilir. Canlı Gemini/NVIDIA ve diğer yapılandırılmış sağlayıcı hesapları,
model kalitesi, gerçek öğrenme kazanımı ve kullanıcı cihazında yanıt gecikmesi
**DOĞRULANMADI** olarak Aşama 8 nihai kabul listesinde açık tutulur.
Bu kabul, 1.000 bağımsız aracın veya bütün katalog yöntemlerinin canlı modelle
ayrı ayrı sınandığı anlamına gelmez. Aşama 2 otomatik kabulü bu kapsamda tamamlandı; güncel aktif aşama tablodadır.

## Aşama 3 kabul koşulları

- Mevcut FRIDAY ses seçimi korunmalı; kullanılan motorun gerçek yetenekleri raporlanmalı.
- Sürekli dinleme ve uyandırma kontrollerinin etkin durumu tutarlı olmalı.
- Ses arabelleği sessizlikte ve kesintisiz konuşma/gürültüde sınırlandırılmalı.
- STT/TTS başarısızlığı, söz kesme, iptal ve kapanış kontrollü çalışmalı.
- Türkçe ses girdileri, sayı/saat ifadeleri ve konuşma bağlamı regresyonları geçmeli.
- Ses/model işlemleri Qt ana thread'ini engellememeli; veri ve izin sınırları korunmalı.
- Windows/Linux otomatik kontrolleri ile gerçek mikrofon/hoparlör kabulü ayrı raporlanmalı.
- Donanım ölçümü olmadan gecikme veya yankı engelleme başarısı ilan edilmemeli.

## Aşama 3: otomatik dinlemede ses tamponu sınırları

Kesintisiz sesin yüksek enerji dalı 30 saniyelik azami tur kontrolünü
atlıyordu. 31 saniyeden uzun sentetik PCM akışında sınırın aşıldığı ve STT'ye
hiç aktarım yapılmadığı yeniden üretildi. Artık otomatik tur algılamada yüksek
ses dalı da aynı sınırda turu kapatır. Normal mikrofon paketlerinde aşım en
fazla son girdi paketinin uzunluğudur. Bu, keyfi büyüklükte tek bir giriş
paketine mutlak bellek sınırı veya donanım gecikme garantisi değildir.

Konuşma başlamadan gelen tek büyük sessizlik paketi de 0,3 saniyelik ön
tampona indirilir; sessizlik gereksiz yere STT'ye gönderilmez. PCM16 paketinin
sonundaki yarım örnek, sonraki paketin örnek hizasını kaydırmadan atılır.
Kapanış, nesnenin bekleyen mikrofon listesini/sayacını ve VAD durumunu temizler;
kapanmış motora yeni ses eklenmez. Manuel bas-konuş açıkça flush edilene kadar
bekleme davranışını korur; otomatik sınır manuel kaydı kendi kendine göndermez.

`test_pipeline_audio_bounds` gerçek pipeline girişinden sentetik PCM ile
kesintisiz ses, büyük sessizlik paketi, PCM hizası, STT hatası ve kapanışı
sınar. Mikrofon, hoparlör, wake-word doğruluğu, yankı ve canlı STT/TTS servis
kabulü **DOĞRULANMADI**. Bu düzeltme Aşama 3 otomatik kabul kapsamındadır; ses/persona seçimi değiştirilmez.

## Aşama 3: tanıma sırası, geç sonuçlar ve iptal

Arka arkaya bas-konuş bırakmalarında iki STT isteği aynı anda çalışabiliyor,
sonuçlar ters sırada gelerek eski komutu yeni mesajın arkasına ekleyebiliyordu.
Ses parçaları beklemeden ayrı yakalanır; tanıma ve konuşmaya ekleme işlemi
motorun asyncio kilidiyle sıralanır. STT hatası sırayı kilitlemez. Motor
kapandıktan sonra geç dönen sonuç yok sayılır; sırada bekleyen tanıma yeni
servis çağrısı yapmaz. Bu, sağlayıcıya zaten gönderilmiş veriyi geri alma
veya native STT hesaplamasını zorla durdurma garantisi değildir.

Söz kesme, çağıran thread yerine üretim görevinin kendi asyncio döngüsünde
iptal edilir. Kontrollü TTS akışında iptal ve sonradan ses yayımlanmaması
sınanır. Otomatik akustik barge-in yeteneği hâlâ destekleniyor gibi sunulmaz.

## Aşama 3 otomatik kabulü ve Aşama 4'e geçiş

| Koşul | Otomatik kanıt ve sınır |
| --- | --- |
| Mevcut FRIDAY ses/personası | Ayar regresyonları; ses veya sağlayıcı seçimi değiştirilmedi |
| Uyandırma ve etkin durum | `test_wake_settings`, `test_typed_wakes`: başarısız algılayıcı etkin gösterilmez, çift kurulum engellenir, reset eski kareyi kullanmaz |
| Sessizlik/kesintisiz ses sınırı | #192 ve `test_pipeline_audio_bounds`; sentetik PCM |
| STT sırası/hata/kapanış | `test_pipeline_speech_lifecycle`: kontrollü async sağlayıcılar ve gerçek motor girişleri |
| İptal/TTS | Farklı thread'den iptal kendi döngüsüne aktarılır; kontrollü TTS iptal sonrası ses üretmez |
| Türkçe ve konuşma bağlamı | `test_turkish_voice_understanding`, kısa cevap ve pipeline bağlam regresyonları; canlı ASR doğruluğu değildir |
| Motor sınırları | Desteklenmeyen otomatik barge-in/resumption yetenekleri açılmaz; widget oluşturulmaz veya worker'dan değiştirilmez |
| Platform kabulü | Tam Windows/Linux regresyonu ve kurulu Windows ses yaşam döngüsü testleri PR kabul raporunda kaydedilir |

Gerçek mikrofon/hoparlör, FRIDAY sesinin işitsel kalitesi, Türkçe canlı ASR,
akustik yankı/yanlış uyandırma oranı, cihaz değiştirme ve gerçek gecikme
**DOĞRULANMADI** olarak Aşama 8 nihai kabulünde açıktır. Otomatik kabul,
bu saha testlerinin tamamlandığı anlamına gelmez. Aşama 3 otomatik kabulü bu kapsamda tamamlandı; güncel aktif aşama tablodadır.

## Aşama 4 kabul koşulları

- Onaylı tercihler, proje ve konuşma bağlamı yeniden başlatmada korunmalı.
- 21 Kasım 2026 unutma/eşitleme kuralları; arşiv ve yedekten silinen bilgiyi geri getirmeme regresyonları geçmeli.
- Proje günlüğü gerçek durumdan devam etmeli; asistanın eski iddiası işlem kanıtı sayılmamalı.
- Eşzamanlı JSON/SQLite erişimi ve yedek/geri yükleme hatalarında veriler korunmalı.
- Hafıza araması ilgili sonuçları sınırlarıyla getirmeli; hassas kayıtlar yetkisiz dışa aktarılmamalı.
- Windows/Linux regresyonları geçmeli; gerçek cihazlar arası eşitleme ve uzun süreli kullanım ayrı raporlanmalı.

## Aşama 4: eski hafızadan yanlış geri getirmeyi engelleme

Güncel ana hafıza yokken yedek bozuksa veya önceki bozuk ana dosya karantinaya
alınmışsa, sonraki okuma eski kurulum hafızasını yeniden içe aktarabiliyordu.
Bu eski kopya silinmiş bilgiler içerebilir. Üç hata senaryosu sentetik kayıtlarla
yeniden üretildi. Artık güncel yedek/karantina kanıtı varsa eski kurulumdan
otomatik ilk taşıma yapılmaz. İlk kurulumdaki gerçek taşıma ve sağlam güncel
yedekten kurtarma korunur. Eski dosyalar silinmez veya otomatik birleştirilmez.

Bozuk ana dosyaların karantina adları benzersizdir; aynı saniyede ikinci
kurtarma birinci bozuk dosyayı ezmez. Kurtarma başarısızlığı, kayıt içeriğini
açığa çıkarmayan Türkçe bildirimle aktarılır; kurtarma başarıyla yapılmış
gibi gösterilmez. Yeni veri şeması veya izin eklenmez. 21 Kasım 2026 unutma/
eşitleme regresyonları korunur. Gerçek cihazlar arası eşitleme ve fiziksel
disk arızası kabulü **DOĞRULANMADI**; Bu düzeltme Aşama 4 otomatik kabul kapsamındadır.

## Aşama 4: hafıza alanlarının yapı doğrulaması

Geçerli JSON içindeki `notes: []`, `preferences: null` veya bozuk `_deleted`
yapısı okunabilir sayılabiliyor; sonraki yazma bunu sağlam yedeğin yerine
koyabiliyordu. Bilinen kategori alanları sözlük, silme kaydı anahtar ve
zamanları metin olarak doğrulanır. Yeni kayıt geçersizse küçültme/arşivleme ve
dosya yazımından önce reddedilir. Bozuk ana dosya yedeğe alınmaz; yalnızca
yapısı geçerli yedek başarıyla geri yüklenmiş sayılır.

Eksik kategori alanları, eski metin kayıtları, gün hassasiyetindeki silme
zamanları ve özel kategoriler korunur. Veri biçimi dönüştürülmez; yeni şema
sürümü veya bağımlılık eklenmez. Geçersiz yapıdaki ana/yedek dosyalar ve
karantina kopyaları korunur. Sentetik dosyalarla bozuk alanlar, geçersiz girdi,
yedek korunması, yanlış kurtarma başarısı ve eski biçim uyumluluğu sınanır.
Aşama 4 aktiftir; gerçek bulut eşitleme/disk arızası kabulü **DOĞRULANMADI**.

## Aşama 4: salt okunur son oturum geri dönüşü

Son oturum özeti, ana dosya yok veya bozukken sağlam yedekten okunmuyordu.
Artık son geçerli kopya salt okunur kullanılır; dosya onarımı, yedek döndürme
veya tüketme yapılmaz. Geçerli ana dosyada özet listesi boşsa bu tercih
geçerlidir; yedekten eski özet getirilmez. Yanlış türde oturum girdisi çağırana
metin gibi dönmez. Bu özet tarihsel bağlamdır; güncel proje/işlem başarısı
olarak kabul edilmez.

## Aşama 4 otomatik kabulü ve Aşama 5'e geçiş

| Koşul | Otomatik kanıt ve kapsam |
| --- | --- |
| Tercihler ve oturum devamlılığı | `test_memory_safety`, `test_continuity`: yeniden okuma, sağlam yedek ve salt okunur oturum özeti |
| Unutma ve eski verinin dönmemesi | 21 Kasım 2026 tombstone/eşitleme; #194 legacy kurtarma ve #195 bozuk alan/yedek regresyonları |
| Gerçek proje durumu | Yarım iş günlüğü tekrar çalıştırılmaz; eski asistan başarı iddiası aktif projeyi tamamlamaz; bitmiş proje korunur |
| Eşzamanlı yazım | Gerçek ayrı süreçlerde JSON kilidi, SQLite thread yazımları ve hata sonrası devam |
| Yedek ve geri yükleme | Committed WAL snapshot, boş hedefe doğrulanmış restore, bozuk kaynak/hedef koruması ve kilit zaman aşımı |
| Arama ve geçmiş | Türkçe farklı ipuçları, sıralama, tam günlük sorgu ve sınırlandırılmış tarihsel konuşma sonuçları |
| Erişim ve dosya koruması | Etkin veri tabanı/yan dosyaları dışa aktarmayla ezilmez; anahtarlar git'e eklenmez; eski konuşma talimat/işlem kanıtı sayılmaz |
| Platform kabulü | Tam Windows/Linux regresyonu ve kurulu Windows hafıza/continuity kabulü ilgili PR sonucunda kaydedilir |

Bu kabul, yapılandırılmış hafıza kayıtları, proje günlüğü ve yerel yedekleme
akışlarına aittir. Bir yapılandırılmış bilgiyi unutmak ham konuşma arşivinin
tamamını silme işlemi değildir; tarihsel kayıtlar mevcut tercih veya işlem
başarısı olarak yeniden yorumlanmamalıdır. Gerçek cihazlar arası bulut
eşitleme, kullanıcı diski/güç kesintisi ve uzun süreli kullanım
**DOĞRULANMADI** olarak Aşama 8'de açık kalır. Aşama 4 otomatik kabulü tamamlandı; güncel aktif aşama tablodadır.

## Aşama 5 kabul koşulları

- Bilgisayar/tarayıcı araçları gerçek sonuçlarını done, unverified veya failed olarak bildirmeli.
- İzin verilen işlemlerde işlem sonrası durum doğrulanmalı; belirsiz sonuç başarı sayılmamalı.
- Dosya silme, ödeme, mesaj gönderimi, hesap/kamera ve yüksek etkili işlemler gerçek kullanıcı yetkisi gerektirmeli.
- Ekran/web içeriği güvenilmeyen veri olmalı; model kendi onayını üretmemeli.
- Uzun işler arka planda, izole çalışma alanında yürümeli; durdurma ve yeniden başlatma gerçek durumu korumalı.
- Kod ajanı test/CI sonucu olmadan başarılı sayılmamalı; güvenli commit/PR/merge sınırları korunmalı.
- Windows/Linux testleri ile gerçek kullanıcı masaüstü/oturum entegrasyonları ayrı raporlanmalı.

## Aşama 1: açılış ve yarım güncelleme

`main.py`, üçüncü taraf modüllerden önce `core/startup_guard.py` kontrolünü çağırır.
Bekleyen yazma/geri dönüş kaydı veya canlı güncelleyici varken normal açılış durur.
Kontrol, uygulama verisi veya yedek silmez; kurtarma çevrimdışı komutla yapılır.
Regresyon testleri gerçek giriş noktasını ayrı süreçte çalıştırır ve uygulama
modüllerine ulaşılmadığını, kişisel dosyaların korunduğunu sınar.

Aşama 1'in aşağıdaki otomatik kabulü tamamlandı. Fiziksel Windows cihazında güç
kesintisi, gerçek mikrofon/hoparlör ve uzun süreli çalışma **DOĞRULANMADI**.
Bunlar Aşama 8 nihai kabulünde açık kontrol olarak korunur; genel ürün hazır
ilan edilmedi. Aşama 1 otomatik kabul kaydı yukarıdadır; güncel aktif aşama tablodadır.

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


## Aşama 5: otomasyon güvenilirliği ve gerçek onay

Tarayıcı komutu için `future.result(timeout)` yalnızca bekleyen çağıranı
bırakıyordu; asıl coroutine çalışmaya devam edebiliyordu. Artık süre aşımında
iptal istenir. Daha önce teslim edilmiş tıklamanın geri alındığı iddia edilmez;
böyle bir sonuç `unverified` döner ve yeniden denemeden önce sayfa kontrolü
istenir. Başlatma hatası bekleyen thread'e aktarılır; kapanış bekleyen işleri
iptal eder, Playwright kaynaklarını ve sahip olunan olay döngüsünü kapatır.
Kapanış doğrulanamıyorsa başarı bildirilmez.

Tıklama ve tuş teslimi uygulamanın amacına ulaşıldığı anlamına gelmez. Normal
metin girişi ancak alanın gerçek değeri tekrar okunup eşleşince `done` olur.
Eklemeli giriş veya okunamayan/dönüştürülen alan `unverified` kalır. Formun
kısmi sonucu ayrı sayılır. Belirsiz tıklama başarısızlığından sonra başka
seçiciye tıklayarak aynı işlemi tekrar etme kaldırıldı. Web sayfası metni ve
URL güvenilmeyen veri sınırında modele aktarılır.

Genel fare/klavye girdisinin ödeme, mesaj gönderimi veya hesap işlemi olup
olmadığı model parametrelerinden güvenilir biçimde anlaşılamaz. Bu yüzden
**genel tarayıcı ve bilgisayar girişleri gerçek, tek kullanımlık HUD onayı**
gerektirir; `confirmed=true` ve benzeri model alanları yetki vermez. Tarayıcı
isteği sayfa nesnesi, adres, DOM ve canlı form değerlerinin özetiyle bağlanır.
Bilgisayar isteği gözlenen pencere, süreç, geometri, öğe konumları ve içerikle
bağlanır; onaydan sonra pencere tekrar odaklanır ve durum yeniden okunur.
Hedef değişmişse, güvenilir okunamıyorsa veya koordinat gözlenen pencerenin
dışındaysa giriş yapılmaz. Onay beklerken istek nesnesini değiştirmek
saklanan işlemi değiştirmez. Bu sıkı genel giriş akışı otomasyonda ek HUD
onayları gerektirir; yalnızca gezinme/okuma gibi işlemler mevcut akışta kalır.
Kamera aracının tek kare isteği de gerçek HUD kararından önce çalışmaz.

Windows pencere başlığı PowerShell kaynak koduna, macOS başlığı AppleScript
kaynak koduna eklenmez; ayrı veri olarak iletilir. Ham araç parametreleri ve
girilen özel metin bilgisayar kontrolünün konsol günlüğüne yazılmaz. Panodan
okunan içerik güvenilmeyen veri olarak işaretlenir; kayıtsız kişisel alan
sahte rastgele kimlikle doldurulmaz.

| Kabul | Kanıt |
| --- | --- |
| Süre aşımı, kapanış, başlangıç ve coroutine temizliği | `test_browser_lifecycle`: gerçek olay döngüsü/thread, gecikmiş etki iptali, kapanış hatası ve boşta coroutine koruması |
| Sonuç dürüstlüğü | Okunmuş alan değeri, kısmi form, tekrar edilmeyen tıklama, `failed`/`unverified` ayrımı |
| Kullanıcı yetkisi | `test_automation_consent`, `test_file_confirm`, `test_message_confirm`, `test_camera_scan`: model alanı, değişen hedef, iptal, HUD yokluğu, tek kullanım ve sabit istek |
| Komut/veri sınırı | `test_computer_command_boundaries`: PowerShell/AppleScript başlık enjeksiyonu ve özel metin günlüğü regresyonu |
| Kod ajanı | `test_agent_coding`, `test_agent_process`, `test_background_job_tracking`, `test_github_develop`: test hatası, güvenli geri alma, gerçek alt süreç iptali, yayın kapsamı, exact-head merge ve geçmiş/aktif iş ayrımı |
| Gerçek tarayıcı | `tools/verify_browser_automation.py`: Chromium/Firefox, geçici profil ve çevrimdışı sentetik sayfa; Türkçe giriş, alan geri okuma, gerçek tıklama, form, sekme, sahte HUD üzerinden gerçek araç işçisi ve kaynak kapanışı |
| Platform | Windows/Linux Python 3.13 tam regresyonu, iki platformdaki gerçek tarayıcı kabulü ve temiz Windows kurulu ortam testleri; sonuçlar ilgili PR'de kaydedilir |

Bu otomatik kabul gerçek kullanıcı hesabında ödeme/mesaj/silme yapıldığı
anlamına gelmez; bu işlemler test için gerçek hesaplarda yapılmaz. Kullanıcının
Windows masaüstünde HUD kararı, pencere odak geri dönüşü, çoklu monitör/DPI,
üçüncü taraf oturumları, fiziksel kamera ve uzun görev saha kabulü
**DOĞRULANMADI** olarak Aşama 8'de açık kalır. DOM/ekran içeriği güvenilmeyen
veridir; bu sınırlar işletim sistemi düzeyinde bir güvenlik sandbox'ı değildir.
Aşama 5 otomatik kabulü tamamlandı; güncel aktif aşama tablodadır.

## Aşama 6 kabul koşulları

- Mevcut FRIDAY kimliği, kadın holografik yüz ve seçili ses korunmalı.
- Qt widget işlemleri yalnızca ana thread'de; sahne üretimi ve ağ işleri arka planda olmalı.
- Hologram, dünya haritası ve görsel analiz gerçek render sonuçlarıyla doğrulanmalı.
- Dünya/normal harita geçişi, yakınlaşma ve dış sokak görünümü veri sağlayıcısının gerçek kapsamına göre raporlanmalı.
- WebGL/GPU/zoom ve Windows QtWebEngine kabulü yalnızca çalıştırılan test kadar başarılı sayılmalı.
- Kamera ve uzaktaki görsel içerik yetki/gizlilik sınırlarını aşmamalı.


## Aşama 6: görünürlük, harita katmanı ve fotoğraf doğrulaması

Dünya panelinde eski bir katmandan geç gelen sonuç, aynı moda geri dönüldüğünde
mevcut katmanın görüntü sayısını ve hata durumunu değiştirebiliyordu. Her katman
artık ayrı nesil numarası taşır; eski görüntü/hata yanıtları yeni katmanın
başarısı veya başarısızlığı gibi gösterilmez. Qt gizleme isteği ile belgenin
visibility durumu birlikte uygulanır. Belge görünürlük olayı gizlenmiş panelin
render döngüsünü yeniden açamaz; sayfa yüklenmesi panel gizlendikten sonra
biterse Qt görünürlüğü tekrar aktarılır.

Yer arama modülünün yüklenememesi artık çalışan işçiyi sessizce düşürüp Ara
düğmesini kapalı bırakmaz. Hata tek sinyal ile ana thread'e aktarılır; panel
silinmişse ikinci kez silinmiş QObject'e sinyal gönderilmez. Geçersiz/eski
arama sonucu mevcut harita hedefine uygulanmaz. Ağ/model işi widget işçisine
taşınmaz; worker yalnızca sinyal yayar.

Fotoğrafın tanımlı 8 MB sınırı artık **dekoder açılmadan önce** uygulanır.
Yanlış giriş türü doğrulama hatasıdır. Piksel sınırı, EXIF yön düzeltmesi ve
metadata kaldırma korunur. Model/hizmet olmadan gerçek fotoğraf baytlarıyla
sınır ve metadata kabulü test edilir. Fiziksel kamera veya canlı görsel model
başarısı buradan türetilmez.

Kadın FRIDAY hologramı, teması ve ses kimliği korunur. Gerçek OpenGL render
kabulü, farklı kafa açılarının yanında **aynı pozda ayrı ağız, göz kırpma ve
bakış** değişikliklerinin framebuffer piksellerini değiştirmesini gerektirir.
İstenen motor yazılım yedeğine düşerse GPU/render kabul testi başarısız kalır;
bu durum başarı sayılmaz. Render çıktıları ve kabul manifesti CI artifact'ına
kaydedilir. CI yazılım OpenGL sonucu kullanıcının fiziksel GPU'su doğrulandı
anlamına gelmez.

| Kabul | Kanıt |
| --- | --- |
| Katman ve görünürlük yarışları | `earth_runtime.cjs`: dağıtılan gerçek JS, kontrollü eski/yeni provider yanıtları ve visibility olayları; Node testleri |
| Qt yaşam döngüsü | `test_earth_panel_lifecycle`: gizli yüklenme, başarısız yükleme sonrası bekleyen hedef, import hatası ve eski arama sonucu |
| Fotoğraf güvenliği | `test_camera_photo`: bayt/piksel sınırı, yanlış tür, gerçek JPEG EXIF yönü ve metadata silme |
| Holografik yüz | Mevcut portre/mesh testleri ve `render_android_preview.py`: gerçek shader, ayrı animasyon pikselleri, 5 poz ve render manifesti |
| Dünya ve yakınlaşma | `verify_earth.py`: gerçek QtWebEngine/WebGL framebuffer, doğal/uydu/sokak modları, hedef/irtifa, 2D geçiş ve gizle/göster |
| Platform | Windows/Linux tam regresyonu ve ayrı gerçek yüz/dünya render workflow'ları; exact-head sonuçları ilgili PR'de |

Otomatik kabul kullanıcı donanımında uzun süreli kullanım, fiziksel GPU/sürücü,
çoklu monitör/DPI, canlı görsel model veya gerçek kamera kabulünü tamamlamaz.
Bu sonuçlar **DOĞRULANMADI** olarak Aşama 8'de açıktır. Harita ve uydu ayrıntısı
sağlayıcı kapsamasına bağlıdır; sokak panoraması ayrı tarayıcıda açılır.
Yakınlaşma testi her bölgede her binanın görüntüsünün bulunduğu iddiası değildir.
Yeni aktif odak Aşama 7'dir.

## Aşama 7 kabul koşulları

- Başlangıç, ilk yanıt ve tekrar eden çizim maliyeti ölçülmeli; CI ölçümü kullanıcı cihazı sonucu gibi sunulmamalı.
- Ağ/model çağrıları ve ağır dosya işleri Qt ana thread'ini engellememeli.
- Görünmeyen paneller ve animasyonlar gereksiz render/CPU tüketmemeli.
- Kaynak tüketimi ve kuyruklar sınırlandırılmalı; hız için hafıza/izin/veri doğrulaması kaldırılmamalı.
- İyileştirmeler ilgili regresyon ve gerçek davranış testleriyle doğrulanmalı.


## Aşama 7: gizli HUD ve OpenGL arabellek maliyeti

Gizli/küçültülmüş HUD, çizim yapmasa da saniyede yaklaşık 60 kez animasyon
hesaplıyordu. Artık gizliyken yalnızca 250 ms aralıkla görünürlük kontrolü
çalışır; avatar/reaktör/viseme hesaplanmaz. Gösterildiğinde 16 ms timer geri
gelir; ses, konuşma durumu ve model oturumu durdurulmaz. Güncel ses zamanlaması
duvar saatinden okunur; süresi dolmuş visemeler geri oynatılmaz. Küçültme/
geri getirme sırasında animasyonun zaman farkı sınırlanır.

Başın fiziksel piksel sınırları her pozda birkaç piksel değiştiğinde dört
örnekli OpenGL framebuffer yeniden oluşturuluyordu. Çizim hedefi artık 32
piksel basamaklarıyla büyütülür; geometrinin piksel ölçeği azaltılmaz, sağ/alt
kenara yalnızca şeffaf pay eklenir. 4096 piksel sınırı korunur. Aynı basamak
aralığındaki küçük hareketler var olan arabelleği kullanır; başın görünüşü ve
sesle animasyonu korunmalıdır.

`tools/measure_hud_performance.py` ayrı süreçlerde HUD import/oluşturma süresi,
gizli timer sayısı, animasyon adımı, süreç CPU zamanı/RSS ve gerçek OpenGL
çizim süresi/FBO oluşturma sayısını kaydeder. Performans workflow'u PR tabanı
ile adayı **aynı runner'da, sırayı değiştirerek üçer kez** çalıştırır. İstenen
render'ın çalışması, gizli animasyonun durması, timer/FBO işinin azalması ve
aynı pozdaki görüntünün ortalama RGB farkının 2/255'i geçmemesi gerekir.
Rapor ve referans kareleri artifact olarak saklanır. Süre ölçümleri gürültü
barındırır; timer sayısındaki azalma aynı oranda CPU tasarrufu iddiası değildir.

Yerel offscreen ilk ölçümünde bir saniyede timer çağrısı 62'den 4'e, gizli
animasyon adımı 62'den 0'a indi. Bu bir kullanıcı cihazı ölçümü değildir.
Gerçek OpenGL, aynı runner önce/sonra kıyası ve regresyon sonuçları ilgili
PR'de kaydedilir. HUD import süresi uygulamanın tam açılış süresi değildir;
bu değişiklik için tam açılış/ilk model yanıtı hızlandı iddiası yoktur.

Aşama 7 aktiftir. Kullanıcının uzun süreli CPU/RAM ölçümü, fiziksel GPU,
tam uygulama ilk açılışı ve canlı ses/model yanıt gecikmesi **DOĞRULANMADI**.
İzin, hafıza doğrulaması veya seçili FRIDAY ses/persona ayarı hız için
kaldırılmaz/değiştirilmez.


## Aşama 7: ilk pencereyi Gemini SDK yüklemesinden ayırma

`main.py`, ilk pencere ve ilk kurulum ekranı görünmeden Gemini SDK'sını
çalıştırıyordu. Artık mevcut `LazyModule` altyapısı ve ertelenmiş tip
anotasyonları kullanılır. İlk gerçek Gemini yapılandırması/yanıt nesnesi/Live
istemcisi aynı SDK'yı yükler; model kimliği, API yükü, sağlayıcı sırası, timeout,
ses/persona ve anahtarlar değişmez. Ses sürücüsü, TLS sertifika doğrulaması ve
kısmi güncelleme başlangıç kontrolü mevcut sırada korunur.

`test_startup_imports` ayrı süreçte SDK import'unu engelleyerek `main` ve gerçek
ilk kurulum penceresinin SDK çalıştırmadan açılabildiğini doğrular. İlk gerçek
`FunctionResponse` erişiminde gerçek SDK yüklenmesi ve yanıt yapısı ayrıca
sınanır. Bu testler model servisine bağlanmaz; canlı hizmet başarısı iddiası
üretmez.

`measure_window_startup.py`, Windows'ta PR tabanı ve adayı aynı kurulu Python
ortamında, sırayı değiştirerek üçer kez çalıştırır. Ölçüm, yalnızca Git'teki
Python kaynakları ve requirements'tan oluşturulmuş temiz ZIP benzeri
kopyalarda yapılır; kullanıcı config/hafızası ve imzalama dosyaları kopyalanmaz.
Çocuk süreç AppData yolları geçici klasöre alınır; sağlayıcı kimlik bilgisi
ortam değişkenleri aktarılmaz. Gerçek görünür FRIDAY penceresi ve üretimdeki restart receipt birlikte
beklenir; pencere `WM_CLOSE` ile normal kapatılır ve çıkış kodu doğrulanır.
Hatalı açılış/kapanış başarılı ölçüm sayılmaz. Rapor ve süreç günlükleri
workflow artifact'ına kaydedilir.

Bu ölçüm **anahtarsız ilk kurulum penceresine** aittir. Yapılandırılmış kullanıcı
profili, fiziksel mikrofon/GPU, ilk model bağlantısı ve ilk sesli yanıt
gecikmesini doğrulamaz. SDK'nın ilk gerçek kullanım maliyeti ortadan
kaldırılmadı; UI'nin önündeki gereksiz zorunluluk kaldırıldı. Aşama 7 aktiftir;
üç tekrarlı Windows sonucu ve regresyonlar ilgili PR'de kaydedilir.


## Kullanıcı isteği: Abacus AI entegrasyonunu kaldırma

Abacus/RouteLLM katalog girdisi, hazır API adresi, özel öncelik yönlendirmesi,
`AbacusPriorityLLM` ve bu özelliğe ait özel cooldown/fallback kodu kaldırıldı.
Bu kaldırılmış özelliğin dokuz eski testi yerine kaldırma ve güvenli ayar
geçişini doğrulayan regresyonlar eklendi; diğer sağlayıcı testleri korunur.
README kurulum talimatları ve aktif yol haritası buna göre güncellendi.

Eski kimlik, katalog veya resmi API adresiyle kaydedilmiş Abacus ayarları
aktif yapılandırmadan ve geçerli son yedekten ayıklanır. Ayar kaydetme ve
salt okunur çözümleme yolları eski kaydı tekrar etkinleştiremez. Registry ve
OpenAI uyumlu sağlayıcı doğrudan eski/custom adresi çalıştırmayı ağ çağrısından
önce reddeder. Kaldırmayı engelleyen/tanıyan migration ve regresyon adları
kaynakta kalır; bunlar kullanılabilir bir Abacus özelliği değildir.

Diğer sağlayıcıların anahtarları, seçili modelleri, STT/TTS ve FRIDAY ses/
kimlik ayarları korunur. Abacus ana konuşma modeliyse yalnızca kayıtlı Gemini
anahtarı bulunduğunda ve `local_only` kapalı olduğunda Gemini Live moduna
geçilir. Aksi halde eski LLM seçimi temizlenir; yeni bir sağlayıcı yapılandırmak
gerekir. Rastgele bir ücretli servise/hesaba geçilmez. Kişisel konuşma ve
proje hafızası silinmez. Bozuk/yapısı okunamayan dosyalar, başka kullanıcı
verilerini kaybetmemek için korunur; geçerli eski yedek yeniden Abacus'a
yönlenemez. Harici Abacus hesabında anahtar iptali veya hesap silme yapılmaz.

Kaldırma testleri; katalog/factory, özel adres/alias, eski ortak katalog,
yerel kullanım sınırı, ayar/yedek temizliği, eski ekranın kaydetmesi, bozuk
ve yalnızca yedek dosya senaryosu ve diğer sağlayıcıları korumayı kapsar.
Aşama 7 aktiftir; kaldırma doğrulaması ilgili PR'de kaydedilir.


## Aşama 7 otomatik kabul ve Aşama 8'e geçiş

Önceki bölümlerdeki “Aşama 7 aktif” ifadeleri ilgili düzeltmenin yapıldığı
anı anlatır; güncel durum üst tablodur. #199, #200 ve #201 temel alınmıştır.

| Kontrol | Önce | Doğrulanan kapsam / sonra |
| --- | --- | --- |
| Gizli HUD | Saniyede 62 timer / 62 animasyon adımı | Aynı runner kıyasında 3 timer / 0 adım; #199 |
| OpenGL FBO | 20 karede 18 yeniden oluşturma | 4; görüntü farkı yaklaşık 1.008/255; #199 |
| Windows ilk kurulum penceresi | Üç tekrar medyanı 1.75 s | 1.04 s; temiz anahtarsız profil, aynı runner; #200 |
| Pipeline çıktı kuyruğu | Sınırsız olay | 128 olay; yavaş okuyucu üreticiyi bekletir, olaylar düşürülmez |
| Oynatma kuyruğu | Sınırsız PCM | 128 × en çok 2400 bayt; doluyken event loop çalışır |
| Mikrofon yükleme taşması | QueueFull callback hatası, telefonda yeni ses düşmesi | En eski parça bırakılır, güncel PCM korunur; kayıp sayacı `_mic_dropped_chunks` |
| Kapanış / söz kesme | Dolu kuyruğu bekleyen üretici için güvence yok | Bekleyen pipeline put iptal edilir; eski oturum/müdahale sonrası PCM geri gelmez |

Yeni gerçek asyncio testleri 10.000 karışık metin/ses/araç/bitiş olayıyla sıra,
kapasite ve geri basıncı; 10.000 mikrofon parçasıyla taşma davranışını sınar.
PCM bölme tam bayt eşitliğiyle doğrulanır. Dolu kuyrukta kapanış, bekleyen
okuyucu, tekrar kapatma/okuma, görev iptali, yeniden bağlantı ve gerçek
`interrupt()` yolu ayrı testlerdir. Windows kurulum kabulüne de eklenmiştir.
Bunlar sentetik yük testleridir; saatlerce gerçek kullanım veya canlı model
gecikmesi ölçümü olarak sunulmaz.

Oynatma ve pipeline kuyrukları ayrı ayrı en fazla 307.200 bayt PCM taşır;
bu sayı tüm süreç RAM sınırı değildir. Sağlayıcının tek yanıtı, metin/araç
payload'ları ve diğer uygulama bileşenleri ayrıca bellek kullanır. TTS'nin
ürettiği büyük tek parça bölünür; sağlayıcının kendi iç arabelleği bu kodun
dışındadır. Yavaş hoparlör ağ tüketicisine geri basınç uygular; ses atlanarak
sahte hız kazanımı yapılmaz. Yerel söz kesme bekleyen eski konuşmayı iptal eder.

## Aşama 8 — aktif nihai kabul

- Windows/Linux Python 3.13 bütünleşik regresyonları ve sağlayıcı kontrolleri.
- Windows temiz kurulum, yeniden kurulum, bağımlılık tutarlılığı, ilk görünür
  pencere ve normal kapanış; güncelleme/geri alma/yeniden açılan HUD kabulü.
- Önceki aşamaların render, tarayıcı, hafıza ve yetkilendirme sonuçlarının
  son sürümle ilişkilendirilmesi; başarısız/atlanmış testlerin açık kaydı.
- **DOĞRULANMADI:** kullanıcının Windows/GPU/WebGL ortamı, fiziksel mikrofon,
  yankı/çift konuşma, FRIDAY sesi, canlı model hesabı/ilk yanıt, gerçek cihaz
  eşitlemesi, gerçek kullanıcı oturumundaki otomasyon ve saatlerce CPU/RAM.
- **DOĞRULANMADI:** nihai dağıtım paketinin kullanıcı cihazında kurulumu ve
  sürüm yükseltmesi; imzalama anahtarı ve lisans denetiminin son sürüm kabulü.

Aşama 7 otomatik kapsamından geçiş, bu açıkları kapatmaz. Aşama 8 sürmektedir;
nihai ürün durumu **KISMEN HAZIR**, tüm sistem için “HAZIR” kabulü verilmemiştir.
Bu değişikliğin Windows/Linux iş ve test sonuçları PR kaydında tutulur.


## Aşama 8 otomatik kapsamının kapanışı

[Güncel nihai kabul raporu](nihai-kabul-2026-11-25.md) kaynak adayı üretimi,
Windows ZIP kurulumu, paket bütünlüğü, kurucu hata sonuçları, tekrar çalıştırılan
görsel/otomasyon testleri ve yayın engellerini bir araya getirir. Önceki “aktif”
ifadeleri ilgili çalışma anıdır; güncel durum üst tablodadır. Bu geçiş yalnızca
aynı PR head'inin bütün CI kontrolleri geçtiğinde kabul edilir. Gerçek cihaz,
canlı hizmet, uzun kullanım ve güvenli dağıtım kabulü açık; genel durum
**KISMEN HAZIR**. Kullanıcının verileri, seçili FRIDAY sesi ve kişiselleştirmesi
bu aşama için sıfırlanmaz.
