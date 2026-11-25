# FRIDAY ikincil beyni — özellik denetçisi

Konuşma çubuğundaki **beyin simgesi** denetim panelini orta alanda açar.
CORE etrafındaki hareketler o anda gerçekten kontrol edilen alanı gösterir.
Bir alana dokunarak sonuçlarını süzebilirsiniz. **Yalnız sorunlar** hata ve
“doğrulanmadı” kayıtlarını gösterir; **Raporu kopyala** son kontrollerin
zamanını, kapsamını, sürelerini, hata ayrıntısını ve kaynak konumunu kopyalar.
Yazı/fikir girmeniz gerekmez. FRIDAY’a dön yüz ekranını geri getirir.

## Kendiliğinden ne yapar?

İlk kurulum hazırsa uygulama açılışından 45 saniye sonra, sonra her dakikada
sıradaki alanın **yerel bileşen kontrolünü** çalıştırır. 12 bileşen alanı ve canlı izleme yaklaşık
13 dakikada dolaşılır; kontroller uygulama açıkken tekrar eder. Bir defada
bir kontrol çalışır. Panelin kapalı olması kontrolleri durdurmaz.

İkincil beyin artık modelden geliştirme planı istemez, kod yazmaz, kod ajanı
başlatmaz, commit/PR/yayın veya kendini güncelleme yapmaz. Eski fikir ve kod
işi kayıtları silinmez; yeni kontrol sonuçları ayrı yerel SQLite tablolarına
yazılır. Eski duraklatma tercihi korunur. Diğer, **kullanıcı talebiyle**
çalışan kod ajanı değişmemiştir.

Bileşen kontrolleri kaynak kodun geçici bir kopyasında, ayrı Python sürecinde,
geçici config/veri dizinleriyle yapılır. Kişisel ayar, konuşma ve API anahtarı
dosyaları kopyalanmaz; anahtar/token ortam değişkenleri aktarılmaz. Model
çağrısı veya harici ağ bağlantısı yapılmaz. Gerçek fare/klavye, dosya silme,
mesaj, kamera, ödeme, akıllı ev veya güncelleme işlemi denenmez. Geçici test
verileri işlem sonunda temizlenir. Bu mekanizma zararlı Python kodu için
bir işletim sistemi sandbox'ı değildir; sabit, yerel FRIDAY kontrolleridir.

Her kontrol 20 saniye sınırındadır. **Duraklat** çalışan kontrolü iptal eder
ve yeni kontrolü engeller; **Devam ettir** kayıtlı sırayla sürdürür. Uygulama
kapanırken bekleyen süreç sonlandırılır. Geçmiş en fazla 500 olay, panel son
100 olayı tutar; her alanın son sonucu ayrıca saklanır. Sonuç saati önemlidir:
eski bir geçiş daha yeni sürümün veya canlı hizmetin kabulü sayılmaz. Kaynak
kontrol sırasında değişirse sonuç “doğrulanmadı” olur.

## Hata olursa

Yeni/değişmiş bir hata veya doğrulanamayan kontrol etkinlik günlüğünde
bildirilir. Aynı sorun her turda tekrar bildirilmez; yeniden açılışta da
önceki sonuç dikkate alınır. Daha önce sorunlu kontrol geçince düzeldiği
bildirilir. Bildirim konuşmayı kesip otomatik ses üretmez; panel ve etkinlik
günlüğünden izlenir. Kopyaladığınız raporu düzeltme için paylaşabilirsiniz.
API anahtarı, kullanıcı konuşması ve kişisel hafıza rapora eklenmez.

**Geçti**, yalnız aşağıdaki kontrolün çalışıp beklenen sonucu verdiğidir.
**Hata**, beklenen sonucun alınamaması veya zaman aşımıdır.
**Doğrulanmadı**, bağımlılık/başlatıcı eksikliği, yarım kalmış süreç veya
kaynak değişimi gibi nedenle sonuç alınamamasıdır; başarı sayılmaz.

| Alan | Gerçek çalıştırılan yerel kontrol | Bu sonuçla doğrulanmayan |
| --- | --- | --- |
| Ses | Türkçe döküm birleştirme, PCM kuyruk aktarımı ve kapanış | Fiziksel mikrofon, yankı, canlı ses |
| Hafıza | Geçici hafızaya yazma/arama/unutma, tombstone birleşimi, SQLite arama | Kişisel veri bütünlüğü, gerçek cihaz eşitlemesi |
| Modeller | Araç şemasını sağlayıcı biçimine dönüştürme | Model hesabı, kota, API erişimi |
| Kod ajanı | Bozuk Python kodunu mevcut denetçiyle yakalama | Gerçek kod geliştirme; ajan başlatılmaz |
| Güncelleme | ZIP içeriğini ve tehlikeli yolu doğrulama | Kurulu sürümü güncelleme/yeniden başlatma |
| Güvenlik | Sahte onay tokenını reddetme ve iptal | Gerçek etkili işlem ve kullanıcı onayı |
| Cihazlar | Boş cihaz listesinde ses sahibi seçmeme | Telefon, Home Assistant bağlantısı |
| Arayüz | Gerçek yüz geometrisinin varlığı ve sonlu koordinatlar | GPU, pencere etkileşimi ve görsel kalite |
| Araştırma | Sentetik yanıtla belirsiz kitap indirmesini reddetme | İnternet araştırması |
| Otomasyon | done/unverified/failed sonuçlarını ayırma | Tarayıcı/masaüstü işlemi |
| Eklentiler | Holo Masa OBJ aktarımının tutarlılığı | Blender ve fiziksel kamera |
| Canlı izleme | Mevcut oturumdaki arka plan izleyicilerinin gerçek kalp atışı | Başlamayan izleyiciler, mikrofon/model bağlantısı |
| Uzun işler | Eski araç sonuçlarını kısaltırken görev sırasını koruma | Canlı kullanıcı görevi |

Bu kontroller bütün FRIDAY yeteneklerinin uçtan uca kabulü değildir.
Canlı model, fiziksel donanım ve yüksek etkili işlemler otomatik olarak
“geçti” gösterilmez. Paket ayrı Python alt süreci başlatmayı desteklemiyorsa
kontroller “doğrulanmadı” olur; sahte başarı üretilmez.
