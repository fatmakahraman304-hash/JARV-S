# Otonom İkinci Beyin

Alt konuşma çubuğundaki **beyin simgesi**, MAYK’ın orta alanında gelişim ağını açar. Merkezde CORE, çevresinde ses, hafıza, model zekâsı, kod ajanı, testler, güncelleme, güvenlik, cihazlar, arayüz, araştırma, otomasyon, eklentiler ve uzun işler bulunur. Bir noktaya dokununca o alanın kayıtları süzülür. MAYK’a dön yüz ekranına döner.

## Otomatik çalışma

Normal main.py açılışında, mevcut ilk kurulum tamamlandıktan sonra İkinci Beyin arka planda başlar. Kayıtlı kurulumda ilk tarama 45 saniye sonra yapılır. Sesli oturumu ayrıca başlatmanız gerekmez. Paneli açmanız veya fikir yazmanız gerekmez.

Her 15 dakikada bir sıradaki alanın gerçek kaynak dosyaları ve test envanteri incelenir. Sözdizimi hataları yerelde belirlenir. Model incelemesinde kaynak dosyaları veri olarak gönderilir ve yalnızca sağlanan dosyalara dayanan bir bulgu kabul edilir. Bulgu varsa plan ve kabul testleri hazırlanır, mevcut kod ajanı ayrı geliştirme kopyasında çalıştırılır. Bir kod işi sürerken yenisi başlatılmaz. Aynı kaynak içeriğinde aynı denetim bulgusu yeniden işlenmez.

Ağdaki hareketli noktalar gerçek analiz, planlama, kod yazma ve test durumunu gösterir. Testi geçmeyen veya başlatıldığı doğrulanamayan işler ayrı durumlarla görünür. Sonuçlar yerel SQLite günlüğünde saklanır. Uygulama yeniden açıldığında önceki geliştirme kaydı tekrar izlenir. Yayın, birleştirme ve çalışan uygulamayı güncelleme mevcut kullanıcı onaylı akışları kullanır.

Model çağrıları yapılandırılmış sağlayıcıyı, onun anahtarını ve kotasını kullanır. Kaynak incelemesine kişisel konuşma geçmişi, API anahtarı dosyası veya yerel ayarlar eklenmez. Geliştirme için yerel Git, kurulmuş model sağlayıcısı ve mevcut GitHub geliştirme çalışma alanı kuralları geçerlidir. Sağlayıcı veya geliştirme alanı kullanılamazsa hata ağın kayıtlarında gösterilir.

**Duraklat**, yeni öz denetim ve kod işi başlatılmasını durdurur. Başlamış kod işinin sonucu izlenir. **Devam ettir** izlemeyi yeniden etkinleştirir. Bu seçim ve sıradaki inceleme zamanı yeniden başlatmalarda korunur. Paneli kapatmak otomatik çalışmayı durdurmaz.

## Erkek hologram yüz

Varsayılan yüz, pürüzsüz 3D erkek başı, boyun ve omuz geometrisi üzerinde mavi hologram malzemesidir. OpenGL çizicisi gerçek yüzey normallerini, gölgeleri, göz çukurlarını, göz kapaklarını ve ağız içini işler. İnce tarama dokusu ile kenar ışığı malzemenin parçasıdır. Mevcut konuşma sesinin sürdürdüğü çene, göz kırpma ve bakış animasyonu korunur.

Çizici açılamazsa uygulama yedek yüz çizimine geçer ve nedeni günlüğe kaydeder. Bu durumda yüksek kaliteli 3D çizim doğrulanmış sayılmaz. Windows ve Linux render kabul aracı seçilen 3D yol çalışmadığında hata verir.
