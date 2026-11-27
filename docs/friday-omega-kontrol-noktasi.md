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
- Sürecin zorla sonlandırılması, eksik anahtar, bozuk şifreli içerik, farklı Gist hesabı, kilit, diske yazma hatası ve yinelenen komut için testler eklendi. Linux/Python 3.12 ile cihaz ve güncelleyici regresyonlarından 143 test geçti. GitHub Actions şifreli kayıt ve eşitleme testleri Windows ve Linux/Python 3.13 üzerinde geçti. Genel regresyonların sonucu #254 iş akışında izlenir.

### Eksik kalan

- Bu sadece masaüstündeki Gist eşitleme kuyruklarını kapsar; bağımsız `core/tasks` görev deposu, konuşma arşiv kuyruğu, diğer istemcilerin yerel verileri ve eski veriler bu şifreli depoya taşınmadı. Eşitleme hiç başlatılmadıysa eski bellek içi davranış sürer.
- Gist hâlâ taşıma katmanıdır; gönderilen içerik bu değişiklikle uçtan uca şifrelenmez, sunucu tarafından atomik çoklu cihaz yazımı veya kimlikli yeni gerçek zamanlı taşıma eklenmedi. Tüm cihazları birbirine bağlayan kayıt, güvenilir kimlik, yetkilendirme ve otomatik tekrar önleme tamamlanmadı.
- Windows DPAPI aynı kullanıcı profilindeki işlemlere açıktır; Linux/macOS için anahtar 0600 izinli yerel dosyada tutulur ve anahtarı da okuyabilen aynı kullanıcı veya yöneticiye karşı koruma sağlamaz. Dosya adı, boyut ve işlem zamanları gizlenmez. Windows kullanıcı profili veya anahtarı kaybolursa veri kurtarma planı henüz yoktur.
- Ağ yazımının sunucuda gerçekleşip yanıtın kaybolduğu ve karşı cihazın iletiyi tükettiği durumlarda tüm sistem için tam olarak bir kez teslim garantisi yoktur. Diğer cihazların Gist komutlarına güven politikası ayrıca incelenmelidir.
- Merkezi zekâ, çoklu model yönlendirme, Windows kontrolü, diğer platformların istemcileri ve Omega'nın diğer bölümleri bu oturumda tamamlanmadı.

### Başarısız veya fiziksel cihaz gerektiren

- Kullanıcının laptopu, telefonları, TV'si, saati ve akıllı ev cihazları üzerinde canlı test yapılmadı; gerçek Gist hesabıyla kesinti, çoklu cihaz yarışı ve kişisel veri taşıma deneyi gerçekleştirilmedi.
- Kullanıcının güncelleme panelinin neden takıldığı ve gerçek imzalı kurulum paketinin yayın durumu hâlâ doğrulanmadı. Bu değişiklik yeni paket bağımlılığı eklemez; `cryptography` önceden `requirements.txt` içinde bulunur.

## Dördüncü oturum: merkezi görev planları

Başlangıç `main`: `73514d8c7e0e91375969b47a207a6db42c1e8ef1`; #252, #253 ve #254 korunur.

### Tamamlanan

- `core/tasks/plans.py`, mevcut `TaskEngine` ve `actions/background_tasks.py`: Kullanıcı gerçekten birden fazla adımlı iş istediğinde FRIDAY 1–6 sıralı görevden oluşan plan oluşturabilir; her adım mevcut arka plan ajanı ve araç izinleriyle yürütülür. Önceki adım bitmeden sonraki başlamaz; başarısız adım planı durdurur. Plan durumu listelenebilir, sorgulanabilir ve iptal edilebilir.
- Plan ve önceden belirlenmiş adım kimlikleri diskte saklanır. Adım oluşturulup plan kaydı güncellenmeden süreç kesilirse yeniden açılışta aynı kimlikte ikinci görev oluşturulmaz. İptal isteği kalıcıdır ve yeniden başlatmada tamamlanır; çalışan bir araç anında durmayabilir.
- Önceki sonuç, yalnızca iki adımın web/özel hafıza sınırları aynıysa sınırlı ve güvenilmeyen içerik olarak sonraki adıma verilir. Kayıtlı ajan araçları veya çalışma modu değişmişse yeni adım başlatılmaz. Mevcut arka plan araç kısıtları korunur; komut çalıştırma, dış mesaj ve satın alma yetkisi eklenmez.
- Bir adımın `write_file` aracıyla yazdığı en fazla 16 dosya gerçek içerikle karşılaştırılır, kontrol anı ve SHA-256 kaydedilir; değişmiş veya okunamayan dosya belirtilir. Diğer içeriklerin ve gerçek dünyadaki sonuçların doğruluğu bu kontrolle kanıtlanmaz; plan genel sonucu `finished_unverified` olarak gösterilir.
- Plan adımları için var olan `fast` veya `smart` model katmanı seçilebilir. Araştırma adımları `smart` kullanır; Gemini modelleri bu adımlarda önce ilgili anahtarın model listesiyle karşılaştırılır, listelenmeyen isimler denenmez. Keşif başarısızsa yapılandırılmış diğer sağlayıcı denenir veya görev bekletilir. Kullanıcının sağlayıcı önceliği korunur; boş sağlayıcı yanıtı başarılı sonuç sayılmaz. Yeni model kimliği veya doğrulanmamış kalite iddiası eklenmedi.
- Tamamlanan planın özeti masaüstünde gösterilir ve mevcut cihaz eşitleme bağlantısı uygunsa sesin sahibi cihaza kuyruklanır. Gist yerine yeni bir taşıma protokolü eklenmedi.

### Eksik kalan ve doğrulama sınırları

- Bu, merkezi zekânın görev planlama/yürütme parçasıdır; tüm konuşma, cihaz kontrolü, işletim sistemi, uygulama ve uzman ajanları kapsayan bütünleşik mimari değildir. Adımların içerikleri asistanın isteğinden gelir; ayrı bir planlama modeli çağrısı veya bağımsız anlamsal doğrulayıcı eklenmedi.
- Plan ve `core/tasks` kayıtları mevcut düz metin JSON altyapısında kalır; #254'ün şifreli eşitleme deposuna taşınmadı. Aynı görev dizinini kullanan birden fazla bağımsız FRIDAY süreci için plan adımlarında tam olarak bir kez yürütme garantisi yoktur. Bir adımın içinde kesilen araç çağrısı görev motoru tarafından yeniden denenebilir.
- Model katmanı seçimi erişilebilir en güçlü modeli, maliyeti veya sağlayıcı yeteneklerini otomatik ölçüp garanti etmez. Model listesi API'si Gemini'de modele erişimi listeler; araç çağrısı başarısını garanti etmez. Kullanıcının yapılandırdığı diğer sağlayıcı seçimi ayrıca canlı keşif ile doğrulanmaz. Gerçek sağlayıcı yanıtları, ses gecikmesi ve maliyet bu oturumda ölçülmedi.
- Gist dışı uçtan uca şifreli cihaz iletişimi, telefon/TV/saat istemcileri, tam ortak hafıza, Windows/PowerShell/CMD ve donanım entegrasyonları bu çalışmada tamamlanmadı. Kullanıcının gerçek cihazları ve GÜNCELLE paneli üzerinde canlı kabul testi yapılmadı.

### Testler ve başarısızlıklar

- Linux/Python 3.12 üzerinde merkezi plan, model geri dönüşü, #254 şifreli kayıt, eşitleme ve güncelleyici dâhil 183 ilgili test geçti. Üretim sağlayıcı anahtarı veya gerçek donanım kullanılmadı.
- GitHub Actions merkezi plan testleri Windows ve Linux/Python 3.13 üzerinde geçti; genel regresyonun durumu #255 iş akışında izlenir. Kullanıcının bilgisayarındaki güncelleme panelinin önceki takılma nedeni hâlâ belirlenmedi.


## 2026-11-27 — Yerel sistem teşhisi ve oturum durumu

Başlangıç: `main` a147e81c4a7e8b11542d5eefd977e5bc1b0769f1; #252–#255 korunmuştur.

### Tamamlanan kod

- Salt okunur yerel CPU, bellek, sistem diski, batarya ve ağ bağlantı arayüzü ölçümleri; Windows'ta sabit PowerShell/CIM sorgusuyla işletim sistemi, işlemci, grafik ve BIOS envanteri.
- Etkileşimli araç ve mevcut arka plan görevlerine özel teşhis uzmanı; eksik kaynaklar açıkça belirtilir. Teşhis ve web erişimi aynı arka plan ajanında bir araya getirilmez. Bulut sunucusunun donanımı kullanıcının bilgisayarı olarak sunulmaz.
- Sistem bilgileri kullanıcının yapılandırdığı görev modeli sağlayıcısına işlenmek üzere gönderilebilir. Ağ arayüzünün açık olması internet erişiminin kanıtı değildir.

### Doğrulama ve başarısızlıklar

- Bu değişiklik için Linux ve Windows üzerinde GitHub Actions testleri eklenmiştir; sonuçları ilgili değişiklik isteğinden doğrulanmalıdır.
- Yerel çalışma ortamı, bu oturumdaki diğer kaydedilmemiş çalışmalar tamamlanmadan erişilemez duruma geldi. Daha önceki ara test sonuçları, burada sunulan son kodun geçtiğini kanıtlamaz.

### Eksik kalanlar

- Paralel bağımlılık grafiği, yeniden planlama ve gelişmiş bilişsel motor üzerinde erişilemeyen yerel değişiklikler bu kapsamda birleştirilmemiştir.
- Genel PowerShell/CMD kontrolü, Windows üzerinde işlem yapma, şifreli görev depolaması, doğrulanmış uçtan uca şifreli cihaz ağı ve Omega'nın diğer açık aşamaları tamamlanmamıştır.
- GÜNCELLE paneliyle uçtan uca kurulum ve gerçek sağlayıcılarla kullanım henüz doğrulanmamıştır.

### Fiziksel cihaz gerektirenler

- Kullanıcının kendi Windows bilgisayarında CIM, gerçek donanım/batarya ve GÜNCELLE paneli testleri; telefon, tablet, saat, TV ve akıllı ev cihazlarıyla uçtan uca testler bekliyor.

## 2026-11-27 — NEXUS: kurtarılan bilişsel görev grafiği

Başlangıç `main`: `128209817d6fbf20cf7ea7a7e371d4278614c3bd`; #252–#256 korunur. Önceki yerel çalışma kurtarıldı ve doğrulanmamış hâli ayrı `codex/friday-cognitive-recovered-wip` dalında saklandı.

### Tamamlanan

- Konuşmadaki `background_tasks` aracı üzerinden 1–6 düğümlü, döngüsüz bağımlılık grafiği başlatma, listeleme, durum, iptal ve henüz başlamamış düğümü güncelleme; birbirinden bağımsız düğümler mevcut paralel çalışan sınırına kadar eşzamanlı çalışır.
- Düğüm ve alternatiflerin araç çağrısı, yaklaşık görev süresi ve tur sınırları mevcut görev motoruna bağlanır. Önceden sağlanan alternatifler başarısızlık veya istenen dosya kanıtının yokluğu sonrasında denenebilir; modele otomatik yeni plan hazırlatılmaz. Farklı web/gizli veri sınırları arasında önceki sonuç aktarılmaz.
- Görev ve grafik kaydı yeniden başlatmada korunur; belirlenimci görev kimliği kesintide ikinci görev açılmasını engeller. Dosya ve not yazıları öncesinde kalıcı kayıt tutulur; sonucu belirsiz kalan yazı otomatik tekrarlanmaz ve inceleme bekler. Yalnızca açıkça izin verilen araçlar erişilebilirdir.
- Yazılmış dosya içeriği mevcut bağımsız dosya kontrolüyle karşılaştırılabilir. Görev raporunun veya nihai hedefin doğruluğu bununla kanıtlanmaz; tamamlanan grafik `finished_unverified` kalır.

### Doğrulama ve başarısızlıklar

- Bağımlılık, gerçekten eşzamanlı yürütme, alternatif, kesinti, tekrarı önleme, bütçe, mahremiyet ve #255–#256 regresyon testleri eklendi/çalıştırıldı. Windows ve Linux CI sonuçları ilgili değişiklik isteğinde doğrulanmalıdır.
- Önceki doğrudan `git push` denemesi kimlik bilgisi bulunmadığından başarısız oldu; kurtarma dalı GitHub bağlantısı üzerinden oluşturuldu. Bu, çalışma kodunun doğrulandığı anlamına gelmez.

### Eksik kalanlar

- Ayrı model tabanlı planlayıcı, otomatik dinamik yeniden planlama ve bağımsız anlamsal doğrulayıcı yoktur. Kullanıcının veya konuşma modelinin verdiği grafik ve alternatifler uygulanır. Maliyet ölçümü veya para cinsinden üst sınır yoktur; sağlayıcı gecikmesi/kesintisi süre sınırını aşabilir ve araştırma modunda tur bütçesi kesin bir üst sınır değildir.
- Görev ve grafik verileri şifrelenmemiş mevcut JSON deposundadır, #254 Neural Journal ile birleştirilmemiştir. Birden fazla bağımsız süreç veya cihaz arasında tam olarak bir kez yürütme garantisi yoktur. Denetim mevcut yazma/not araçlarıyla sınırlıdır.
- Gerçek işletim sistemi yönetimi, gizlilik tercihine bağlı yerel donanım analizi, tüm Multi-Brain katmanları, kişisel yaşam araçları ve uçtan uca şifreli cihaz ağı tamamlanmadı. Omega'nın 29 bölümünün tamamı ve tam kaynak denetimi bitmedi.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows cihazında yerel işlem/performans, mikrofon, ses, bağlı cihazlar ve GÜNCELLE paneliyle uçtan uca kabul testleri henüz yapılmadı. Gerçek model sağlayıcılarıyla maliyet, hız ve kalite değerlendirilmedi.
