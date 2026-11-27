# FRIDAY Omega: ilk kontrol noktası

Başlangıç: `main` commit `474e34643aeb4736fec245a30d2dd471b2175bd5`.
Bu kayıt tam kaynak kod denetimi veya Omega aşamalarının tamamlandığı anlamına gelmez.

## Doğrulanan sorunlar ve düzeltmeler

| Alan | Önem | Kök neden ve çözüm | Doğrulama |
| --- | --- | --- | --- |
| `core/tasks/store.py` | Yüksek | Aynı hedefe yazan iş parçacıkları aynı geçici dosyayı paylaşıyordu. Her kayıt artık ayrı bir geçici dosya kullanıyor ve atomik değiştiriyor. | İki eşzamanlı yazıcı, eksiksiz sonuç ve başarısız yazma testi. |
| `core/tasks/store.py` | Yüksek | Görev, dosyaya başarıyla kaydedilmeden bellekte değişiyordu. Kaydetme başarıyla bitince bellek durumu güncelleniyor. | Başarısız oluşturma ve değiştirme sonrası hem bellekteki hem yeniden yüklenen durum kontrolü. |
| `core/app_updater.py` | Orta | Parçalı HTTP indirmesi `IncompleteRead` ile kesildiğinde yeniden deneme uygulanmıyordu. En fazla üç kez baştan indiriliyor. | Kesintili aktarım ve tekrar sınırı testleri. |
| `tests/test_reminder_reliability.py` | Düşük | Linux hatırlatıcısını test ederken Windows yol türü kullanılıyordu; örnek yol platformdan bağımsız POSIX yolu olarak tanımlandı. | Linux hatırlatıcısının boşluk içeren yolları alıntılama kontrolü korunuyor. |

## Doğrulama sınırları ve sonraki işler

- Linux, Python 3.12: görev deposu, güncelleyici, kaynak paket, hazırlanan güncelleme, başlangıç koruması, rutin ve arka plan işi testlerinden 69 test geçti.
- #252 için GitHub Actions üzerinde Windows ve Linux/Python 3.13 kontrolleri, Windows kaynak paketi, güncelleme ve arayüzün yeniden açılması kabul testleri geçti. Bu oturumun yerel ortamında PyQt6 yoktur ve fiziksel donanım ayrıca doğrulanmalıdır.
- GitHub Gist eşitlemesi hâlâ ortak hafıza ve komutlar için kullanılıyor; yeni şifreli cihaz protokolüne geçiş gerçekleştirilmedi. Cihaz kimliği, mesaj tekrarı ve veri silme uçtan uca incelenmeli ve test edilmelidir.
- Tam depo denetimi, model yetenekleri ve maliyet ölçümü, sesli görüşme, akıllı ev, cihaz ve Windows kabul senaryoları henüz tamamlanmadı.
- Güncelleme panelinin kullanıcının bilgisayarında takılmasının gerçek nedeni bu oturumda doğrulanmadı; günlük ve Windows üzerinde yeniden üretim gerekir.
- İmzalı Windows kurulumu veya gerçek yayın imzası üretilmedi. Var olan imza ve geri dönüş mekanizmalarının üretim ortamında kabulü ayrıca doğrulanmalıdır.

## İkinci oturum: cihaz eşitleme güvenilirliği

Başlangıç `main`: `e01a9ac3c1cb0e608da66c120415b7acbe411bdc` (#252 korunur).

### Tamamlanan

- `core/sync_hub.py`: Gist yazımı başarısız olduğunda veya işlem öncesinde hata oluştuğunda yanıt, yerel konuşma, giden cihaz komutu, resim ve hatırlatıcı kuyrukları bellekte korunur. Başarılı yazı sonrası yalnızca o işlemde ele alınan öğeler kuyruktan çıkarılır; işlem sırasında eklenenler kalır.
- Yeniden denemede karşı tarafta hâlâ görülen komut ve yanıt kimlikleri, konuşma kimlikleri, resim ve hatırlatıcı kimlikleri tekrar eklenmez. Yeni giden komutların kimlikleri aynı milisaniyede çakışmaması için UUID kullanır.
- Dolu veya geçersiz uzak gelen kutusu, sıradaki yeni komutu kabul edene kadar korunur; mevcut mesajları yer açmak için silmez. Geçersiz uzak konuşma, yanıt, resim ve hatırlatıcı dosyaları yerel kuyruklarla üzerine yazılmaz.
- Ağ kesintisi, sunucunun yazdığı ancak yanıtın kaybolduğu durum, dolu/bozuk kutu, eşzamanlı yeni öğe ve kimlik çakışması için testler eklendi. Linux/Python 3.12 yerel çalıştırmada cihaz/senkronizasyonla ilişkili 78 test geçti. Python 3.13 Windows/Linux kontrolleri GitHub Actions tarafından ayrıca çalıştırılır.

### Eksik kalan ve güvenlik sınırları

- Bu kuyruklar hâlâ süreç belleğindedir; FRIDAY kapatılır veya çökerse henüz yazılmamış öğeler kaybolabilir. Kalıcı ve şifreli kuyruk uygulanmadı.
- Gist tarafındaki eşzamanlı yazan cihazlar arasında atomik karşılaştırmalı yazım yoktur. Kimlik kontrolü yeniden denemelerin bir kısmında tekrarı önler, ancak bütün ağ/çökme senaryolarında tam olarak bir kez yürütme garantisi sağlamaz. Masaüstünün alınmış komut kimlikleri yeniden başlatmada korunmaz.
- Eşleştirme, şifreli taşıma ve ortak görev/hafıza altyapısı tüm platformlarda yeniden tasarlanmadı. Mevcut Gist tabanlı sistemin gizlilik ve kimlik doğrulama sınırları sürer.
- Omega'nın 29 bölümü üzerinde tam kaynak denetimi, merkezi zekâ, Windows/PowerShell/CMD, donanım ve sağlayıcı entegrasyonları tamamlanmadı. Var olan uygulamaların ve verilerin tümü doğrulanmış değildir.

### Başarısız veya doğrulanamayan

- Kullanıcının gerçek bilgisayarındaki takılan güncelleme yeniden üretilemedi; kök nedeni bilinmiyor. Yayın imzalama anahtarı ve gerçek imzalı kurulum paketi doğrulanmadı.
- Gerçek telefon, TV, diğer cihazlar, mikrofon ve hoparlör bu oturumda bağlanmadı. Kullanıcıya özel hesaplarla gerçek ağ, gecikme ve cihazlar arası ses kabul testleri yapılmadı.
