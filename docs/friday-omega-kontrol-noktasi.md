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

## 2026-11-27 — Yerel donanım analizi ve model paylaşımı

### Tamamlanan

- Donanım teşhisi artık varsayılan olarak ayrıntıları yalnızca yerel panelde gösterir; tek ölçümde yüksek CPU/RAM/disk kullanımı ve düşük, şarja bağlı olmayan pil için basit yerel eşik değerlendirmesi yapılır. Eşik aşılmaması donanım sağlığının kanıtı değildir.
- Ayarlar > Zekâ ve hafıza bölümündeki açık kullanıcı tercihiyle yerel teşhis aracından modele sınırlı CPU, RAM, sistem diski ve pil yüzdeleri gönderilebilir. Bu araç üzerinden donanım envanteri, arayüz adları ve toplam bayt bilgileri modele aktarılmaz. Arka plan teşhis aracı izin kapalıyken ölçümleri modele sunmaz. Ayar okunamazsa paylaşım kapalı kalır.

### Testler ve başarısızlıklar

- Yerel Linux testleri, paylaşımın varsayılan kapalı olmasını, açıkken veri azaltmayı ve #256 regresyonlarını kapsar. Qt bulunmayan yerel ortamda ayar ekranı açılarak test edilemedi; ilgili kullanıcı arayüzü testi GitHub Actions'ta çalıştırılır. Kullanıcının Windows cihazında fiziksel doğrulama yapılmadı.

### Eksik kalan

- Bu ayar diğer sistem bilgisi yollarını henüz kapsamaz: mevcut `system_status` canlı konuşma aracı ve `SystemMonitor` otomatik uyarıları model sağlayıcısına donanım ölçümleri iletebilir. Bunlar ortak gizlilik yetkilendirmesine taşınana kadar genel cihaz verisi gizliliği sağlanmış sayılmaz.
- Bu yerel eşik analizi bağımsız yerel dil modeli, arıza teşhisi veya onarım değildir; sıcaklık, fan, GPU kullanımı ve disk sağlığı gibi diğer ölçümler bu araca eklenmedi. Paylaşıma izin verildiğinde seçili yüzdeler kullanıcının yapılandırdığı uzak model sağlayıcısına ulaşabilir.
- Genel Windows kontrolü, şifreli görev kayıtları, cihaz ağı, diğer modeller, kişisel yaşam ve Omega'nın kalan aşamaları sürmektedir. Gerçek GÜNCELLE paneli deneyimi doğrulanmadı.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows bilgisayarında ayar ekranı, panel, donanım ve sesli konuşma ile GÜNCELLE panelinin uçtan uca testi bekliyor.

## 2026-11-27 — APEX: donanım durumu ve uyarı gizliliği

Başlangıç `main`: `fe7acc21026c7b0b4979f8f90b69541189a77fc6`; #252–#258 korunur.

### Tamamlanan

- `system_status` tam ölçümleri yerel panelde gösterir. Aynı #258 kullanıcı izni açık değilse ölçümleri modele göndermez; izin açıkken yalnızca sınırlandırılmış CPU/RAM yüzdelerini gönderir. İzin okuma hatasında paylaşım kapanır ve sonuç oluşturulurken izin yeniden kontrol edilir.
- `SystemMonitor` ayrıntılı uyarıları yerel etkinlik günlüğüne yazar. Model paylaşımı açık ve konuşma uygun durumdaysa, ölçüm veya kimlik içermeyen genel bir uyarı modele iletilir. Model izni cihaz eşitlemesine izin sayılmadığından uyarı Gist/uzak cihaz veya yokluk kuyruğuna aktarılmaz.
- Teşhis ve canlı durum için aynı izin okuma işlevi kullanılır. Yerel uyarının gösterilmesi, izin iptali ve gerçek izleme döngüsü dahil testler eklenmiştir.
- Ana ayar dosyası eksik veya bozuksa eski yedekteki açık paylaşım izni geri yüklenmez; politika kapalı kalır. Diğer kullanıcı ayarlarının mevcut yedek kurtarma davranışı korunur.

### Testler ve başarısızlıklar

- Yerel Linux testleri, Windows/Linux GitHub Actions ve kurulum regresyonlarının son durumları ilgili değişiklik isteğinden doğrulanmalıdır. Yerel testlerde Windows'a özel CIM kontrolü atlanır.

### Eksik kalan

- Bu, evrensel gizlilik motoru değildir. Konuşma, hafıza, ekran, dosyalar, diğer araçlar ve cihaz eşitleme yollarının tamamı bu politikaya bağlanmadı veya denetlenmedi; Gist uçtan uca şifreli değildir. Kullanıcının mevcut izinleri bu alanlar için ayrıca gereklidir.
- İzin kapalıyken veya kullanıcı uzaktayken sistem uyarıları artık yalnızca yerel etkinlik günlüğüne düşer; otomatik sesli ve uzak cihaz uyarıları bu koşullarda gönderilmez. Güvenli ve açıkça yetkilendirilmiş uzak bildirim henüz yoktur.
- Model tabanlı planlama/yeniden planlama, bağımsız anlamsal doğrulama, token/para bütçesi, şifreli görev depolaması, Windows yönetimi ve diğer Omega aşamaları henüz tamamlanmadı.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows bilgisayarında gerçek sıcaklık/yük uyarıları, konuşma akışı, mikrofon, GÜNCELLE paneli ve bağlı cihazlarla kabul testi yapılmadı.

## 2026-11-27 — APEX: model tabanlı bilişsel planlama

### Tamamlanan

- Konuşmadaki `background_tasks` aracı üzerinden `cognitive_auto`, mevcut SMART model katmanına kullanıcının hedefini ve mevcut ajanların sınırlı yeteneklerini gönderir; gelen grafiği kodla doğruladıktan sonra mevcut kalıcı görev motorunda başlatır. Hatalı veya boş model yanıtında grafik ve görev oluşturulmaz.
- Model bağımlılıkları, uygun ajanları ve en fazla iki önceden belirlenmiş alternatifi önerebilir. Kod bilinmeyen ajanları, döngüleri, geçersiz düğümleri ve ayrılan toplam süre/araç bütçesini aşan grafikleri reddeder; model ajanlara yeni araç yetkisi veremez. Var olan paralellik, belirsiz yazıların durdurulması ve sonuçların doğrulanmamış olarak işaretlenmesi korunur.
- Üst sınır 6'dan 12 düğüme çıktı; çağrı başına daha düşük düğüm, toplam dakika ve araç çağrısı bütçeleri belirtilebilir. Alternatif girişimleri toplam bütçeye dahildir. Modelin kullanılabilirliği garanti edilmez; yeni model kimliği eklenmedi.

### Testler ve başarısızlıklar

- Sağlayıcı taklit edilerek görev grafiğinin gerçek görev motoruna bağlanması, yedi düğümlü grafik, bütçe, geçersiz grafik, yetki ve sağlayıcı hataları sınandı. Gerçek API anahtarıyla model kalitesi, gecikme ve maliyet ölçülmedi. Windows/Linux CI ve regresyon durumu ilgili değişiklik isteğinden izlenmelidir.

### Eksik kalan

- Model çalışma sırasında kendiliğinden yeniden planlama veya yeni alternatif üretme yapmaz; alternatifleri ilk plan sırasında üretir. Bağımsız anlamsal doğrulayıcı ve otomatik düzeltme yoktur. Dosya doğrulaması tüm hedefin doğruluğunu kanıtlamaz.
- Token ve para cinsinden kullanım ölçümü/üst sınırı yoktur. Dakika bütçesi kesin duvar saati sınırı değildir; araştırma ajanının bazı iç işlemleri ve tur sayısı bütçelerin kesin üst sınırı değildir. Planlayıcı model çağrısı ek sağlayıcı ücreti doğurabilir.
- Grafik ve görev kayıtları düz metin JSON'dur; şifreli Neural Journal'a taşınmadı ve birden fazla bağımsız süreçte tam olarak bir kez yürütme garantisi yoktur. Evrensel gizlilik, Windows yönetimi, cihaz ağı ve 29 Omega bölümünün tamamı bitmedi.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows cihazında, gerçek sağlayıcı hesaplarında ve GÜNCELLE panelinde uçtan uca kullanım doğrulanmadı.

## 2026-11-27 — SOVEREIGN: sınırlı uyarlamalı yeniden planlama

Başlangıç `main`: `21445324de9e5dcec9079814b4896bb88e878a6c`; #252–#260 korunur.

### Tamamlanan

- Modelin oluşturduğu bilişsel grafiklerde başarısız, yazma işlemi yapmamış düğüm için kalan dakika/araç bütçesi varsa model yeni bir yöntem önerebilir. Varsayılan bir, en fazla iki model yeniden planlaması yapılır; mevcut ajan, araçlar, bağımlılıklar ve bütçeler değiştirilmez. Tamamlanmış düğümler yeniden yürütülmez.
- Model çağrısı öncesinde plan durumu ve hak kullanımı diske kaydedilir. Çağrı sırasında çökme veya sonucu belirsiz yazma olursa otomatik tekrar yerine inceleme istenir; iptalden sonra geç gelen öneri çalıştırılmaz. Paralel öneriler ayrılmış bütçeyi iki kez kullanamaz.
- Önceden tanımlı alternatifler de dahil, önceki denemede tamamlanmış yazma/not işlemi varsa başarısız adım otomatik tekrarlanmaz. Bu durum `failed` yerine `needs_review` olarak bildirilir.
- Yazma kaydı eksik veya bozuksa da işlem güvenli varsayılmaz. Yalnızca büyük/küçük harf veya boşlukları değiştiren model önerileri yeni yöntem olarak çalıştırılmaz.

### Testler ve başarısızlıklar

- Yerel testlerde gerçek görev zamanlayıcısı, taklit model yanıtı, önceki yazma, paralel bütçe, yeniden başlatma ve iptal senaryoları kontrol edildi. Sağlayıcı yanıtları taklittir; gerçek sağlayıcı, maliyet ve model kalitesi ölçülmedi. Windows/Linux GitHub testleri ilgili değişiklik isteğinde izlenir.

### Eksik kalan

- Uyarlama aynı ajan ve izinlerle sınırlıdır; dinamik ajan/model değiştirme, genel bağımlılık grafiği yeniden düzenleme ve bağımsız anlamsal sonuç doğrulama henüz yoktur. Model çağrıları için token/para cinsinden kesin üst sınır yoktur. Süre bütçesi kesin duvar saati garantisi değildir.
- Görev/grafik kayıtları hâlâ düz metin JSON'dur; şifreli Neural Journal'a taşınmadı. Aynı veri dizinini kullanan bağımsız süreçler için tam olarak bir kez garantisi yoktur. Konuşma, hafıza ve cihaz ağı için evrensel gizlilik ve diğer Omega aşamaları tamamlanmadı.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows bilgisayarı, gerçek model sağlayıcıları, GÜNCELLE paneli ve cihazlarla uçtan uca kabul testi yapılmadı.

## 2026-11-27 — SOVEREIGN: ayrı sonuç incelemesi

### Tamamlanan

- `cognitive_review`, tamamlanmış bir düğümün görevini ve yanıtını araç kullanamayan ayrı bir model çağrısında eleştirir. Bu işlem için Ayarlar > Zekâ ve hafıza bölümünde ayrı, varsayılan kapalı paylaşım izni gerekir; açıldığında metin ve sonuç yapılandırılmış veya yedek model sağlayıcısına gönderilebilir. Özel hafıza veya donanım aracı kullanan düğümlerin incelemesi henüz desteklenmez.
- Aynı işlem sırasında kaydedilmiş dosyaların mevcut baytları, ilgili başarılı yazma çağrısının içeriğiyle yeniden karşılaştırılır. Model çağrısı sırasında dosya veya görev sonucu değişirse inceleme kaydedilmez. Eksik/değişmiş dosya açıkça belirtilir.
- Model değerlendirmesi ve nesnel dosya kontrolü ayrı tutulur; olumlu model görüşü genel doğruluğun kanıtı sayılmaz ve iş akışının `finished_unverified` durumu değiştirilmez. İnceleme sonucu mevcut görev kaydına yazılır ve durum ekranından görülebilir.

### Testler ve başarısızlıklar

- Dosya değiştirme, çağrı sırasında yarış, varsayılan kapalı izin, özel düğümlerin engellenmesi, izin iptali, yanıltıcı model görüşü, geçersiz veya ulaşılamayan model ve konuşma aracı entegrasyonu taklit sağlayıcı yanıtlarıyla test edildi. Gerçek model sağlayıcısı ile kalite, hız veya maliyet doğrulanmadı; GitHub Windows/Linux sonuçları ilgili değişiklik isteğinde izlenmelidir.

### Eksik kalan

- Eleştiri ayrı bir çağrıdır ancak farklı bir model ya da sağlayıcı garantisi yoktur; dış kaynaklar veya gerçek dünya etkileri bağımsız doğrulanmaz. Henüz otomatik denetim, otomatik düzeltme veya token/para bütçesi yoktur.
- Yalnızca mevcut `write_file` kayıtlarından en fazla 16 dosyanın baytları karşılaştırılır; başka araçların veya kullanıcı bilgisayarındaki sistem değişikliklerinin doğruluğu bu kontrolle kanıtlanmaz. Görev ve inceleme kayıtları şifrelenmemiş JSON'da kalır.
- Evrensel izin yönetimi, Windows yönetimi, kişisel hayat araçları ve uçtan uca şifreli cihaz ağı tamamlanmadı. Orijinal 29 bölümün başlıkları aşağıda ayrı izlenir; incelenmemiş bölümler tamamlanmış sayılmaz.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows cihazı, GÜNCELLE paneli ve gerçek sağlayıcı hesaplarıyla uçtan uca kabul testleri yapılmadı.

## PROJECT FRIDAY OMEGA — 29 bölümün izleme durumu

Başlıklar kullanıcının özgün ana talebindeki sırayı izler. **Kısmi** yalnızca aşağıda anılan kodun varlığını gösterir, bölümün tamamlandığını göstermez. **Henüz doğrulanmadı**, özellik yok demek değildir; kapsam bu kontrol noktasında yeterince incelenmemiştir. Tüm bölümler ve tam kaynak denetimi açıktır.

| No | Özgün bölüm | Mevcut kanıt ve durum |
| --- | --- | --- |
| 1 | ANA GÖREVİN | Kısmi: merkezi görev ve cihaz çalışmaları sürüyor; nihai hedef açık. |
| 2 | BAŞTAN SONA KAYNAK KOD DENETİMİ | Kısmi: önceki oturumlardaki belirli hata düzeltmeleri kaydedildi; bütün kaynak denetlenmedi. |
| 3 | FRIDAY CENTRAL INTELLIGENCE | Kısmi: #255, #257, #260 ve bu oturumdaki görev planlama/yürütme çalışmaları. |
| 4 | MULTI-BRAIN — ÇOKLU MODEL ZEKÂSI | Kısmi: mevcut FAST/SMART yönlendirmesi; FAST/SMART Türkçe değerlendirmesinde sağlayıcının döndürdüğü model sürümü ve token sayıları okunur. Bütün katmanlar ve canlı performans ölçümü eksik. |
| 5 | FRIDAY PERSONAL OPERATING SYSTEM | Kısmi: şifreli kişisel görev, günlük öncelik, zaman çakışması, yeniden zamanlama ve haftalık ilerleme. |
| 6 | FRIDAY WINDOWS NATIVE CONTROL | Kısmi: #256 salt okunur CIM teşhisi ve INFINITY güç planı işlemi; kapsamlı yetkili yönetim tamamlanmadı. |
| 7 | HARDWARE INTELLIGENCE | Kısmi: #256 ve #258 yerel ölçümler ve basit eşikler; tüm sensörler ve fiziksel kabul eksik. |
| 8 | FRIDAY OMNIVISION — EKRANI ANLAMA | Henüz uçtan uca doğrulanmadı. |
| 9 | UNIVERSAL APPLICATION INTELLIGENCE | Henüz uçtan uca doğrulanmadı. |
| 10 | FRIDAY EVERYWHERE — BÜTÜN CİHAZLAR TEK SİSTEM | Kısmi: #253–#254 eşitleme ve yerel kuyruk güvenilirliği; bulut paketindeki görev motoru dosyaları düzeltildi, gerçek sunucu ve uçtan uca şifreli cihaz ağı eksik. |
| 11 | FRIDAY SMART HOME | Henüz uçtan uca doğrulanmadı; varsayılan oda sınırı korunmalı. |
| 12 | FRIDAY VOICE — DOĞAL CANLI KONUŞMA | Henüz fiziksel cihazda ve uçtan uca doğrulanmadı; mevcut kadın sesi korunmalı. |
| 13 | PERSONAL MEMORY — GERÇEK KİŞİSEL HAFIZA | Kısmi: #254 eşitleme günlüğü ve kişisel ajanda dahil sürümlü görev yedeği; canlı birleşik şifreli görev/hafıza geçişi eksik. |
| 14 | FRIDAY EXPERT AGENT NETWORK | Kısmi: mevcut genel ve araştırma ajanları ile sınırlı paralel görevler; tüm uzmanlıklar eksik. |
| 15 | FRIDAY AUTONOMOUS WORK | Kısmi: kalıcı graf ve sınırlı yeniden planlama; genel yetkiler ve kesinti garantileri eksik. |
| 16 | FRIDAY SOFTWARE ENGINEER | Henüz tam kapsamda doğrulanmadı. |
| 17 | SECOND BRAIN — KENDİNİ DENETLEYEN VE GELİŞTİREN SİSTEM | Henüz tam kapsamda doğrulanmadı. |
| 18 | FRIDAY UNIVERSAL KNOWLEDGE | Kısmi: mevcut araştırma ajanı; tüm dosya türleri ve kaynak kabulü doğrulanmadı. |
| 19 | KİŞİSEL HESAP VE SERVİS ENTEGRASYONLARI | Henüz tam kapsamda ve gerçek hesaplarla doğrulanmadı. |
| 20 | FRIDAY HUD — ÖZGÜN SİNEMATİK ARAYÜZ | Henüz tüm cihaz ve panellerde uçtan uca doğrulanmadı. |
| 21 | FRIDAY SECURITY CORE | Kısmi: #258–#259 donanım paylaşımı ve bu oturumdaki inceleme izni; merkezi izin sistemi eksik. |
| 22 | PERFORMANCE ENGINE | Henüz tüm hedefler için ölçülmedi. |
| 23 | FRIDAY UPDATE ENGINE | Kısmi: #252 kurtarma/indirme düzeltmeleri ve CI kabulü; gerçek kullanıcı cihazı ve imzalı yayın doğrulanmadı. |
| 24 | GERÇEK YETENEK KATALOĞU | Henüz tam katalog denetimi doğrulanmadı. |
| 25 | FRIDAY KİŞİLİĞİ | Mevcut kimlik ve ses korunmalı; tam kabul henüz doğrulanmadı. |
| 26 | GERÇEK HAYAT KABUL SENARYOLARI | Henüz tüm senaryolar gerçek cihaz ve hesaplarla doğrulanmadı. |
| 27 | GELİŞTİRME VE KABUL PLANI | Kısmi: aşamalı kod, test ve kontrol noktaları var; 12 aşamanın tamamı bitmedi. |
| 28 | KESİN KURALLAR | Sürekli uygulanıyor; tüm depo için uyum denetimi tamamlanmadı. |
| 29 | NİHAİ TESLİM | Tamamlanmadı; yalnızca doğrulanmış ara işler teslim edildi. |

## 2026-11-27 — INFINITY: Windows güç işlemi ve şifreli işlem kaydı

Başlangıç `main`: `1df5722c258c5d674e155a24408b1a42b1db72c4`; #252–#262 korunur.

### Tamamlanan

- `windows_power` konuşma aracı, yalnızca mevcut yerleşik dengeli, güç tasarrufu veya yüksek performans Windows planını seçebilir. Sistem dizinindeki `powercfg.exe` sabit argümanlarla, kabuksuz ve süre sınırlı çalışır. Önce etkin ve mevcut planlar okunur; değişiklik sonrasında etkin plan yeniden okunarak doğrulanır. Olmayan plan oluşturulmaz, yönetici yetkisi veya güvenlik mekanizması değiştirilmez.
- Önceki plan kayıtlıdır ve mevcut plan son işlemden sonra kullanıcı tarafından değiştirilmediyse geri alınabilir. Uygulamanın mevcut geri alma komutuna bağlandı; yeniden başlatma sonrasında işlem kimliğiyle ayrıca geri alınabilir.
- Windows güç işlemlerinin öncesi/hedefi, durumu ve işlem kimliği, #254 Neural Journal ile aynı AES-GCM ve Windows DPAPI anahtar korumasını kullanan ayrı SQLite kaydında saklanır. İşlem öncesinde `started`, doğrulanınca `done` yazılır. Sonucu belirsiz işlem otomatik tekrarlanmaz ve yenileri durur; çözümleme yalnız gerçek kullanıcı onayından sonra kaydı incelenmiş sayar, işletim sistemini değiştirmez.
- Bilişsel görevler için `windows_power` uzmanı yalnızca güç durumunu okuyabilir; donanım paylaşım iznine bağlıdır, web araçlarıyla bir arada kullanılamaz ve bulut sunucusunun güç durumu kullanıcının laptopu gibi sunulmaz. Değiştirme/geri alma yetkisi arka plan ajanına verilmedi.
- Bulut paketleme listesindeki bilişsel görev motoru ve hafıza bağımlılıkları tamamlandı; izole paketle görev motorunun oluşturulması sınandı. Depoda bulunmayan Telegram eklentileri yeni pakete dahil edilmez; mevcut sunucu dosyaları silinmez ve yeni kurulumda Telegram desteği sağlandığı iddia edilmez.

### Testler ve başarısızlıklar

- Taklit Windows komutlarıyla değiştir/geri al, kullanıcının aradaki değişikliğini koruma, doğrulama hatası, süreç kesintisi, sahte onay, şifreli kayıt, eksik anahtar ve bozulmuş kayıt senaryoları test edildi. İlk eşzamanlı erişim testi kilit yarışını ortaya çıkardı; süreç içi kilitleme düzeltildi ve yeniden sınandı.
- Gerçek `powercfg` okuma ve uygunsa geçici değiştir/geri al testi yalnız izole Windows CI çalıştırıcısında etkinleştirilir; sonuçları ilgili değişiklik isteğinde doğrulanmalıdır. Gerçek kullanıcı cihazı kullanılmadı.

### Eksik kalan

- Şifreli SQLite kaydı **Windows güç işlemleriyle sınırlıdır**; `core/tasks` görevleri, plan grafikleri, konuşmalar, araştırma dosyaları ve kullanıcı çıktıları hâlâ mevcut düz metin depolarındadır. Bunlar Neural Journal'a taşınmadı ve eski dosyalar silinmedi. GÜNCELLE geri alma uyumu ve veri kaybı riskleri çözülmeden genel görev göçü tamamlanmış sayılamaz.
- Şifreli kayıt anahtarı kaybında otomatik kurtarma yoktur. Windows DPAPI aynı kullanıcı profilindeki işlemlere karşı izolasyon sağlamaz; POSIX anahtarı 0600 izinli dosyadır. İşlem kimlikleri ve kayıt zamanına ilişkin dosya meta verisi gizlenmez.
- Geniş PowerShell/CMD yürütmesi, servisler, Registry, UAC gerektiren işlemler, kişisel hayat ve cihaz yönetimi bu değişiklikte uygulanmadı. Yeni bulut kurulumu için eksik Telegram eklentileri ve gerçek sunucuda dağıtım ayrıca çözülmelidir.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows bilgisayarında kullanılabilir güç planları, gerçek değişiklik/geri alma, kullanıcı onay ekranı ve GÜNCELLE paneliyle uçtan uca kabul testi yapılmadı.

## 2026-11-28 — INFINITY: şifreli görev yedeği ve güvenli kurtarma kopyası

### Tamamlanan

- Konuşma görev aracı, istek üzerine görev JSON kayıtlarını, plan ve bilişsel grafikleri, model tur kayıtlarını ve araştırma çalışma notlarını #254 ile aynı AES-GCM/Windows DPAPI anahtar yaklaşımını kullanan ayrı SQLite yedeğine alabilir. Yedek SQLite işlemiyle değiştirilir ve okunurken bütünlük kontrolünden geçirilir. Eski görev dosyaları silinmez veya değiştirilmez.
- Yedekleme çalışan görev iş parçacıkları varken durur; kaynak dosyalar okuma sırasında değişirse işlem iptal edilir. Geçersiz JSON, bozuk şifreli yedek, eksik anahtar/veritabanı veya kayıp tablo tespitinde kayıt korunur ve üzerine yazılmaz. Görev tur kaydı okumaları/yazmaları süreç içi kilitle korunur.
- Kullanıcı gerçek onay verdiğinde yedek, canlı görev dizininden ayrı yeni bir klasöre okunabilir dosyalar olarak çıkarılır. Mevcut görevler üzerine yazılmaz veya otomatik çalıştırılmaz. İşlem, onay ekranında açıkça düz metin kurtarma kopyası olarak tanımlanır.

### Testler ve başarısızlıklar

- Süreç ortasında kesinti, bozuk içerik, eksik anahtar/veritabanı, dosya ve onay sınırları, sahte onay ve canlı görevi değiştirmeyen kurtarma senaryoları yerel testlerle sınandı. Windows/Linux GitHub sonuçları ilgili değişiklik isteğinden doğrulanmalıdır.

### Eksik kalan

- Bu **şifreli yedek kopyasıdır**; canlı görev/plan kayıtları ve kullanıcı çıktıları hâlâ düz metindir. Otomatik ya da kayıpsız canlı depoya geçiş yapılmadı; GÜNCELLE geri alma ve çoklu süreç koordinasyonu çözülmeden mevcut dosyalar silinmemelidir.
- Ekler, görevlerin `files` ve `inputs` dizinleri ile görev deposu dışındaki raporlar yedeğe dahil değildir. Üst sınırlar 5.000 dosya ve 32 MB'dır; aşıldığında önceki yedek korunur. Yalnızca son başarılı şifreli anlık görüntü tutulur; sürüm geçmişi ve anahtar kurtarma henüz yoktur.
- Ayrı kurtarma klasörüne çıkarılan dosyalar **düz metindir**. Çıkartma işleminde ani süreç kesilmesi, yerel kurtarma dizininde kısmi bir klasör bırakabilir. Bu kopya görev motoruna otomatik geri yüklenmez.
- Birden fazla bağımsız süreçte ortak kilitli canlı görev deposu yoktur; dış süreç değişiklikleri yalnız dosya kontrolüyle yakalanmaya çalışılır, tam eşzamanlılık garantisi verilmez. Gerçek model, genel Windows yönetimi, kişisel hayat ve cihaz ağı hâlâ eksiktir.

### Fiziksel cihaz gerektirenler

- Kullanıcının Windows profilinde DPAPI anahtarı, gerçek görev arşiviyle kurtarma ve GÜNCELLE paneli üzerinden uçtan uca kabul testi yapılmadı.

## 2026-11-28 — ABSOLUTE: görev yedek sürüm geçmişi

Başlangıç `main`: `d5a7f7ede37418d3400c7b4f75eeec03a0b488d4`; #252–#264 korunur.

### Tamamlanan

- Mevcut şifreli görev yedeği, yeni yedek yazılırken önceki sürümü aynı SQLite işlemi içinde şifreli geçmişe taşır. Sürüm kimlikleri listelenebilir, seçilen sürüm doğrulanabilir ve gerçek kullanıcı onayıyla canlı görevlerden ayrı düz metin kurtarma klasörüne çıkarılabilir. Eski tek sürümlü depolar uyumlu biçimde açılır.
- Linux yerel testleri önceki sürümün kurtarılmasını, canlı görevin değişmemesini ve bozuk/geçersiz sürümün reddini kapsar. Canlı model kullanılmadı.

### Eksik kalan

- Bu hâlâ istek üzerine alınan yedektir; canlı görevler, planlar, grafikler ve kişisel hafıza şifreli depoya geçirilmedi. Sürüm geçmişi otomatik silinmez ve disk kullanımı büyür. Ekler ve üretilmiş dosyalar hâlâ kapsam dışıdır; anahtar kurtarma ve süreçler arası canlı görev koordinasyonu yoktur.
- Genel Windows işlemleri, kişisel hayat, cihazlar ve 29 Omega bölümünün tamamı bitmedi. Telegram dosyaları yerel Git geçmişinde arandı, belirlenen adlarla geçmiş bulunamadı; tüm eski sürüm ve dağıtım kaynaklarının incelenmesi ve güvenli entegrasyon açık.

### Başarısız veya doğrulanamayan

- Gerçek sağlayıcı testi, gerçek cihazda güncelleme ve anahtar kurtarma testi bu çalışma kapsamında yapılmadı. Windows/Linux CI sonuçları ilgili değişiklik isteğinden izlenmelidir.

### Fiziksel cihaz gerektiren

- Kullanıcının Windows profilinde DPAPI, gerçek arşiv geri yükleme ve GÜNCELLE paneli uçtan uca doğrulanmadı.

## TRANSCENDENCE — Canlı kişisel görevler ve günlük plan

- “Yarınki planıma ders çalışmayı ekle”, “Bugünkü planımı göster” ve “Bu görevi tamamla” işlemleri mevcut konuşma görev aracından kullanılır. Kişisel görevler #264 veritabanında ayrı satırlarda canlı olarak şifrelenir. Günlük panel seçilen tarihteki görevleri ve rutin motorunun o tarihe denk gelen bir sonraki çalıştırmalarını gösterir.
- Kabul testi gerçek SQLite üzerinden ekleme, yeniden açma, tarih süzme ve tamamlama işlemlerini denetler. Model çağrısı veya gerçek kullanıcı hesabı kullanılmadı.
- Eski arka plan görevlerinin JSON kayıtları, planlar, grafikler ve ekler henüz göç etmedi. Kişisel görev tablosu #265 yedek dışa aktarımına henüz dahil değildir. Anahtar kurtarma, harici takvim ve sesle fiziksel cihaz kabulü açıktır.

- Model değerlendirmesi için `python -m tools.evaluate_task_brain --live --tier smart` yapılandırılmış gerçek sağlayıcı yoluna üç sentetik Türkçe görev gönderir. JSON sonucu nesnel beklentiyle karşılaştırır, her isteğin toplam süresini ölçer. FAST da seçilebilir. Yerel puanlama testi taklittir. Model adı, token ve para maliyeti bu ölçümden çıkarılamaz.
- GitHub main geçmişinde bulut dağıtımının beklediği `plugins/telegram_remote.py` yolu sorgulandı ve commit bulunamadı. Eski kurulum ve diğer dallardan kurtarma veya yeni eşleştirilmiş bot uygulaması açık.

- “Başlangıç uygulamalarımı göster” sabit CIM sorgusundan en fazla 100 başlangıç girdisi adını yerel panele getirir. “Odaktaki denetimin türünü göster” Windows UI Automation üzerinden tür ve etkinlik okur. Aynı süre sınırlı PowerShell yürütme yolu üç izinli sorguyu destekler. Etkileşimli masaüstünde odak kabulü, uygulama içi yazma ve yönetici işlemleri açıktır.

## SINGULARITY — Ajanda, sürümlü kurtarma ve süreç belleği

- Kişisel görevlerde öncelik, gün içi başlangıç ve süre saklanır. Günlük görünüm açık işleri önceliğe göre sıralar. Aynı güne kaydedilmiş kişisel görev blokları çakıştığında daha geç bir boş saat varsa önerir. Kullanıcı istediğinde görev kimliğiyle zaman ve öncelik güncellenir. Öneriler harici takvim veya rutinleri boş zaman hesabına katmaz.
- Haftalık panel pazartesi–pazar arasına planlanmış görevlerin kaçının tamamlanmış olduğunu sayar. Eski kayıtlar normal öncelikli ve saatsiz okunur. Hedef ve alışkanlıklar ayrı metrikler olarak henüz izlenmez.
- Şifreli yedeğe canlı kişisel görevler mevcut kilit altında katılır. Onaylı kurtarmada sürümdeki görevler ayrı klasöre JSON olarak çıkarılır. Otomatik canlı içe aktarma, ekler, kurtarma anahtarı ve eski arka plan görevlerinin canlı göçü açık.
- Yavaşlama incelemesi için anlık yerleşik bellek kullanımına göre erişilebilen ilk on işlem yerel panelde gösterilir. Ölçüm tek başına yavaşlığın nedenini kanıtlamaz.
- Testler gerçek SQLite üzerinde çakışma, yeniden zamanlama, tamamlanma sayısı, önceki ve güncel sürümdeki farklı saatlerin kurtarılmasını ve yerel süreç belleği okumayı kapsar. Canlı sağlayıcı, cihaz geçişi, harici takvim ve kullanıcı bilgisayarında kurulum doğrulanmadı. 29 bölümlü izleme tablosunun açık durumları sürüyor.

- Türkçe değerlendirmede sağlayıcı yanıtı olmayan denemelerin gecikmesi boş bırakılır. Token sayıları ve model sürümü yalnız yanıtın metadata alanlarından alınır; fiyat bilgisi doğrulanmadığı için maliyet boş kalır.

- Haftalık uzman değerlendirmesi ayrı bir HUD onayından sonra Cognitive Engine'de tek düğümlü sınırlı görev açar. Kullanıcı hangi iki sayının (toplam ve tamamlanan) normal görev bağlamıyla modele gönderilebileceğini ve düz metin görev geçmişine kaydedileceğini görür. Uzman yalnızca görev notu aracını kullanır. Kabul testi sahte onayın reddini, gerçek onaydan sonra grafiğin oluşturulmasını ve özel görev başlığının grafiğe girmediğini denetler; uzman model yanıtı canlı test edilmedi.
- Kullanıcı, “Görev yedeklerime 256 MiB sınır koy” isteğiyle güncel ve geçmiş sürümlerdeki toplam şifreli veri için kalıcı bir bütçe seçebilir. Sınırı aşacak yeni yedek reddedilir. Mevcut sürümler korunur. Bu sınır SQLite sayfaları, anahtar, canlı ajanda ve ayrı düz metin kurtarma klasörlerinin disk kullanımını kapsamaz. Testte bütçeyi aşan yazıdan sonra eski yedek ve geçmiş yeniden doğrulandı.
