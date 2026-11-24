# FRIDAY Holo Masa

Referans, kullanıcının verdiği 17,233 s ve 9,867 s uzunluğunda iki ekran kaydıdır.
İkisi de 30 kare/s: toplam **813 kare** ayrıştırıldı ve yerel el modelinden
geçirildi. 33 ms'den küçük bir hareketin ayrı karesi bu kayıtlarda yoktur.
Bazı bölümlerde oynatıcı 2× hız gösterir; kayıt süresini asistanın gerçek
gecikmesi gibi değerlendirmiyoruz. Küçük monitör üzerindeki okunamayan metinler
ve kaynak kod videodan birebir çıkarılamaz. Buradaki uygulama görülen etkileşimi
mevcut FRIDAY içinde çalışır hale getirir; video veya sahte bir animasyon oynatmaz.

## Videoda görülen akış ve karşılığı

| Kayıt A zamanı | Görülen davranış | FRIDAY karşılığı |
|---|---|---|
| 0–3,5 s | Alkış/uyandırma ve asistan ekranı | Mevcut yerel uyandırma ve manuel uykudan kısa ses darbesiyle uyanma korunur; FRIDAY uyku komutu düzeltildi |
| 4–7,5 s | Holo Desk'in kamera üzerine açılması | Alt çubuktaki küp simgesi / `Holo Masa’yı aç` aracı; kamera ayrı gerçek düğmeyle açılır |
| 8–10 s | Eller çevresindeki dairesel kontroller | Gerçek 21 işaretli el çıkarımı, avuçla birlikte hareket eden 6 düğme |
| 10–14 s | Yüzen panel ve 3D nesneyle etkileşim | Panel başlığını çimdikle sürükle; tek el döndür/taşı, iki el ölçekle |
| 14–17,233 s | Dosya/işlem paneli ve yazıcıya ilişkin konuşma | Gerçek dosya listesi ve OBJ işlemleri; **yazıcıya gönderme yok** |

Kayıt B aynı akışın farklı çekim ve oynatımını gösterir. Asistanın kullanıcı
bilgisayarındaki sesi, donanımı veya video sahibinin özel uygulaması taklit
edilmiş gibi sunulmaz. FRIDAY adı, mevcut yüz ve seçili konuşma motoru korunur.

## Kullanım

1. Alt çubuktaki **küp** simgesini aç. Ana uygulama, konuşma ve görev motoru sürer.
2. Kamera olmadan sol sürükleme döndürür; sağ sürükleme taşır; tekerlek ölçekler.
3. El ile kullanmak istersen **El takibini kur** düğmesine bas. İsteğe bağlı
   MediaPipe paketi ve Google'ın yaklaşık 7,8 MB modeli arka planda hazırlanır.
   İndirme SHA-256 ile doğrulanır. Kurulum kamerayı kendiliğinden açmaz.
4. **Kamerayı aç** düğmesine kendin bas. Tek el çimdikle tutar. İki elin de
   başparmak ve işaret parmağını birleştirip aralarını açmak büyütür. İki el
   ölçeklemesi menü seçimine göre önceliklidir. Döndür/Taşı seçimi alttadır.
5. Bir elin çimdik işaretini dairesel düğmeye getirerek paneli aç/kapat.
   Panel başlığını tutarak taşı. Takip kaybolursa tutuş bırakılır; geri gelen
   elin eski konumuna göre nesne bir anda sıçratılmaz.

Dosyalar panelinde kendi seçtiğin klasörün en fazla 200 girdisi gösterilir.
Bir OBJ'ye çift tıklamak onu 3D görünümde açar; diğer dosyalar çalıştırılmaz,
yalnızca ad/boyut gösterilir. Nesneler panelinde çekirdek, küp, küre ve piramit
vardır. OBJ aç/kaydet gerçek dosya işlemleridir; materyal, betik ve dış dosyalar
çalıştırılmaz. İçe aktarım 2 MB / 10000 köşe / 10000 üçgen ile sınırlıdır.
Geçersiz dosya mevcut çalışan nesneyi değiştirmez. Kaydedilen OBJ modelin
geometrisidir; görünümdeki geçici kamera dönüşü dosyaya uygulanmaz.

Notlar yerel veri dizinindeki `holo-desk/notes.json` dosyasına atomik yazılır.
Kapanış ve güncellemede korunur. Bozuk veya sınırı aşan eski not dosyasına
yazılmaz. Widget paneli gerçek saat ve CPU/RAM değerlerini gösterir.

Sesli `holo_desk` aracı aç/kapat, görünümü sıfırla, hazır nesne ve gerçek durum
sorgusunu destekler. Kamera açma işlemi araç şemasında yoktur. Karmaşık bir
3D nesne için mevcut `voice_prototype(format=object)` yolu kullanılır: modelden
gelen OBJ doğrulanır, kaydedilir ve Holo Masa'da gösterilir. Model/araç hatası
başarı gibi bildirilmez. Bir UI sonucu zamanında alınmazsa `unverified` döner.

## Gizlilik ve yaşam döngüsü

- Kamera varsayılan kapalıdır. Açma yalnızca gerçek Qt düğmesindedir.
- El görüntüleri yerelde işlenir; LLM'e/servise gönderilmez veya kaydedilmez.
- Tek kamera işçisi ve tek son-kare kutusu vardır; gecikmiş kareler birikmez.
- Panel gizlenince, CORE'a dönünce veya uygulama kapanırken kamera durdurulur.
  Aygıtın bırakılması devam ediyorsa sesli araç bunu doğrulanmış gibi bildirmez.
- Fare/eller yalnızca Holo Masa'nın nesne ve panellerini yönetir. Sistem
  faresini, hesabı, mesajlaşmayı, dosya silmeyi veya yazıcıyı tetiklemez.
- Widget ve resim işlemleri Qt ana thread'indedir; kamera, model ve paket
  indirmesi işçi thread'indedir. Mevcut sağlayıcı ve anahtarlar değiştirilmez.

Model/paket kurulumu için ağ gerekir; kurulduktan sonra el takibi yereldir.
Yeni isteğe bağlı kurulumda OpenCV'nin 4.x aralığı korunur. Windows'ta zaten
yüklü bir OpenCV DLL'i kullanımdaysa paket kurulumu kilitlenebilir; hata
gösterilir. Kamerayı açmadan yeniden başlatıp kurulum denenmelidir.
Linux'ta MediaPipe için `libgles2` / `libegl1` gerekebilir. Kamera meşgulse veya
işletim sistemi izni yoksa hata gösterilir; fareyle kullanım sürer. Başka bir
uygulamayla aynı kameranın eşzamanlı paylaşılabileceği varsayılmaz.

## Doğrulama ve sınırlar

Kaynak kayıtların bütün karelerindeki gerçek MediaPipe çıkarımı (yerel
Python 3.13.5, MediaPipe 0.10.35, CPU):

| Kayıt | Kare | Tek el bulunan | İki el bulunan | Çimdik durumu | Çıkarım medyan / p95 |
|---|---:|---:|---:|---:|---:|
| A | 517 | 380 | 16 | 59 | 15,92 / 22,11 ms |
| B | 296 | 90 | 19 | 23 | 18,17 / 26,79 ms |

Bunlar etiketlenmiş doğruluk oranı değildir: her karede el görünmüyor ve
kayıtlar dışarıdan bir monitörü çekiyor. Gerçek webcam gecikmesi, karanlıkta
güvenilirlik veya kullanıcının donanım başarımı bu sayılardan çıkarılamaz.
Kayıtlar ve el işaretleri GitHub'a yüklenmedi; yalnızca bu toplamlar raporlandı.

Aynı yerel renderer denemesinde 20 kare ortalaması, nokta/fırça tekrar kullanımı
öncesi 37,27 ms, sonrası 20,80 ms idi. Bu koşu canlı kamera/LLM gecikmesi değildir.
Görünürken Qt çizim hedefi yaklaşık 30, kamera işçisi üst sınırı 24 kare/s'dir;
donanımın bunları sağlayacağı vaat edilmez. Büyük OBJ'ler daha yavaş olabilir.

`tests/test_holo_desk.py`: geometri, bozuk/güvensiz OBJ, çimdik, takip kaybı,
iki el ölçekleme, fareyle gerçek çizim değişimi, not kalıcılığı/bozuk dosya ve
kameranın varsayılan kapalı olması/gizlenince bırakılması test edilir.
Kamera yaşam döngüsü testindeki aygıt kontrollü sahte aygıttır; fiziksel test değildir.

`tools/verify_holo_desk.py --tracking` gerçek MediaPipe modeliyle Google'ın
örnek görselinde iki eli ve 21'er işareti bulur; yerel Qt panelini, nesne
dönüşünü, OBJ ve notları doğrular. Windows/Linux son sonuçları PR kabul
kaydındadır. **Fiziksel webcam, mikrofon/alkış ve uzun süreli kullanıcı
ergonomisi DOĞRULANMADI.** Bu çalışma yazıcı entegrasyonu içermez.

Kaynaklar: [Google Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker),
[resmî örnek](https://github.com/google-ai-edge/mediapipe-samples/blob/main/examples/hand_landmarker/python/hand_landmarker.ipynb).
MediaPipe/model kaynaklarının kendi lisansları korunur; model ağırlıkları
depoya eklenmez, kullanıcının açık kurulum isteğiyle resmî kaynaktan indirilir.
