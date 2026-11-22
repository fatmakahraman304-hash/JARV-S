# Otonom İkinci Beyin

Alt konuşma çubuğundaki **beyin simgesi**, MAYK’ın orta alanında gelişim ağını açar. Merkezde CORE, çevresinde ses, hafıza, model zekâsı, kod ajanı, testler, güncelleme, güvenlik, cihazlar, arayüz, araştırma, otomasyon, eklentiler ve uzun işler bulunur. Bir noktaya dokununca o alanın kayıtları süzülür. MAYK’a dön yüz ekranına döner.

## Otomatik çalışma

Normal main.py açılışında, mevcut ilk kurulum tamamlandıktan sonra İkinci Beyin arka planda başlar. Kayıtlı kurulumda ilk tarama 45 saniye sonra yapılır. Sesli oturumu ayrıca başlatmanız gerekmez. Paneli açmanız veya fikir yazmanız gerekmez.

Her 15 dakikada bir sıradaki alanın gerçek kaynak dosyaları ve test envanteri incelenir. Sözdizimi hataları yerelde belirlenir. Model incelemesinde kaynak dosyaları veri olarak gönderilir ve yalnızca sağlanan dosyalara dayanan bir bulgu kabul edilir. Bulgu varsa plan ve kabul testleri hazırlanır, mevcut kod ajanı ayrı geliştirme kopyasında çalıştırılır. Bir kod işi sürerken yenisi başlatılmaz. Aynı kaynak içeriğinde aynı denetim bulgusu yeniden işlenmez.

Ağdaki hareketli noktalar gerçek analiz, planlama, kod yazma ve test durumunu gösterir. Testi geçmeyen veya başlatıldığı doğrulanamayan işler ayrı durumlarla görünür. Sonuçlar yerel SQLite günlüğünde saklanır. Uygulama yeniden açıldığında önceki geliştirme kaydı tekrar izlenir. Yayın, birleştirme ve çalışan uygulamayı güncelleme mevcut kullanıcı onaylı akışları kullanır.

Model çağrıları yapılandırılmış sağlayıcıyı, onun anahtarını ve kotasını kullanır. Kaynak incelemesine kişisel konuşma geçmişi, API anahtarı dosyası veya yerel ayarlar eklenmez. Geliştirme için yerel Git, kurulmuş model sağlayıcısı ve mevcut GitHub geliştirme çalışma alanı kuralları geçerlidir. Sağlayıcı veya geliştirme alanı kullanılamazsa hata ağın kayıtlarında gösterilir.

**Duraklat**, yeni öz denetim ve kod işi başlatılmasını durdurur. Başlamış kod işinin sonucu izlenir. **Devam ettir** izlemeyi yeniden etkinleştirir. Bu seçim ve sıradaki inceleme zamanı yeniden başlatmalarda korunur. Paneli kapatmak otomatik çalışmayı durdurmaz.

## Erkek hologram yüz

Varsayılan yüz, ışık katmanları ve saydam tarama çizgilerinden oluşan erkek projeksiyonudur. Cilt ve saç malzemesi kullanılmaz. Mevcut konuşma sesinin sürdürdüğü çene hareketi, göz kırpma ve bakış davranışı korunur. Çizim QPainter ile yapılır ve OpenGL gerektirmez. Yüzün görseli Gideon tarzındaki holografik projeksiyonlardan esinlenir.
