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
Bu bölüm o oturumun durumudur; üçüncü oturumdaki kalıcı yerel kayıt değişiklikleri aşağıdadır.

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

## Üçüncü oturum: Neural Network için kalıcı yerel eşitleme temeli

Başlangıç `main`: `0211c4929f922ae5baa6d6c819709b8ddb618528`; #252 ve #253 korunur.

### Tamamlanan

- `core/neural_journal.py`: Cihaz eşitleme bekleme kayıtları SQLite işlemi içinde AES-256-GCM ile şifrelenir; komut kimlikleri HMAC özetiyle saklanır. Windows'ta şifreleme anahtarı mevcut kullanıcının DPAPI profiliyle korunur. Tek çalışan süreç kilidi, bozuk kayıt/eksik anahtar durumunda durma ve farklı Gist hesabına bekleyen veriyi yanlışlıkla aktarmama kontrolü eklendi.
- `core/sync_hub.py`: Eşitleme başlatıldıktan sonra bekleyen yanıt, konuşma, cihaz mesajı, resim ve hatırlatıcı kuyrukları yerel kayda yazılır ve yeniden başlatmada yüklenir. Gist yazımı başarıyla döndüğünde yalnızca işlenen anlık görüntü işlemli olarak kuyruktan çıkarılır.
- Gelen bir komutun kimliği ve bekleyen yanıt kaydı aynı SQLite işlemiyle eylemden önce kaydedilir. Eylemin sonucu bilinmeden kesinti olursa yeniden açılışta durum belirsiz olarak bildirilir; komut otomatik tekrarlanmaz. İşlenmiş kimlikler yeniden başlatmalar arasında saklanır.
- Sürecin zorla sonlandırılması, eksik anahtar, bozuk şifreli içerik, farklı Gist hesabı, kilit, diske yazma hatası ve yinelenen komut için testler eklendi. Linux/Python 3.12 ile cihaz ve güncelleyici regresyonlarından 143 test geçti. Windows/Linux Python 3.13 sonuçları GitHub iş akışından ayrıca doğrulanmalıdır.

### Eksik kalan

- Bu sadece masaüstündeki Gist eşitleme kuyruklarını kapsar; bağımsız `core/tasks` görev deposu, konuşma arşiv kuyruğu, diğer istemcilerin yerel verileri ve eski veriler bu şifreli depoya taşınmadı. Eşitleme hiç başlatılmadıysa eski bellek içi davranış sürer.
- Gist hâlâ taşıma katmanıdır; gönderilen içerik bu değişiklikle uçtan uca şifrelenmez, sunucu tarafından atomik çoklu cihaz yazımı veya kimlikli yeni gerçek zamanlı taşıma eklenmedi. Tüm cihazları birbirine bağlayan kayıt, güvenilir kimlik, yetkilendirme ve otomatik tekrar önleme tamamlanmadı.
- Windows DPAPI aynı kullanıcı profilindeki işlemlere açıktır; Linux/macOS için anahtar 0600 izinli yerel dosyada tutulur ve anahtarı da okuyabilen aynı kullanıcı veya yöneticiye karşı koruma sağlamaz. Dosya adı, boyut ve işlem zamanları gizlenmez. Windows kullanıcı profili veya anahtarı kaybolursa veri kurtarma planı henüz yoktur.
- Ağ yazımının sunucuda gerçekleşip yanıtın kaybolduğu ve karşı cihazın iletiyi tükettiği durumlarda tüm sistem için tam olarak bir kez teslim garantisi yoktur. Diğer cihazların Gist komutlarına güven politikası ayrıca incelenmelidir.
- Merkezi zekâ, çoklu model yönlendirme, Windows kontrolü, diğer platformların istemcileri ve Omega'nın diğer bölümleri bu oturumda tamamlanmadı.

### Başarısız veya fiziksel cihaz gerektiren

- Kullanıcının laptopu, telefonları, TV'si, saati ve akıllı ev cihazları üzerinde canlı test yapılmadı; gerçek Gist hesabıyla kesinti, çoklu cihaz yarışı ve kişisel veri taşıma deneyi gerçekleştirilmedi.
- Kullanıcının güncelleme panelinin neden takıldığı ve gerçek imzalı kurulum paketinin yayın durumu hâlâ doğrulanmadı. Bu değişiklik yeni paket bağımlılığı eklemez; `cryptography` önceden `requirements.txt` içinde bulunur.
