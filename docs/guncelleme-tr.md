# FRIDAY kurulumu ve GÜNCELLE düğmesi

## Windows’ta kaynak kurulumu

PowerShell’de Python 3.13 ve Git ile yeni bir klasöre kurun. Mevcut kurulumunuzdaki kişisel dosyaları bu işlem için taşımanız gerekmez.

```powershell
git clone --branch main https://github.com/fatmakahraman304-hash/JARV-S.git FRIDAY
cd FRIDAY
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe setup.py
.\.venv\Scripts\python.exe main.py
```

## Güncelleme

**GÜNCELLE** düğmesi, kaynak kurulumda arka planda çalışır. Etkinlik günlüğünde kontrol, ZIP indirme, yedekleme, uygulama ve dosya veya commit doğrulaması görünür. Doğrulamadan sonra HUD yeniden başlatmayı zamanlar. Yardımcı süreç başlatılamazsa pencere açık kalır ve elle açma bilgisi gösterilir. Yeni süreçte HUD’ı ve gereken ses aygıtını kontrol edin.

- Git kurulumu etkin dalı yalnızca ileri yönde günceller. Önceki commit için `aether-backup/` dalı oluşturur. Gerçek yerel düzenlemeleri adlandırılmış stash kaydına alır. Çakışma olursa kayıt saklanır. İzlenmeyen bir kullanıcı dosyası yeni sürümle çakışırsa işlem durur.
- ZIP kurulumu ilk seferinde `update_channel.json` içindeki dalı, daha sonra kayıtlı kanalı izler. Üzerine yazacağı dosyaları `.aether-backups/` içine kopyalar. Dosyaları değiştirdikten sonra içerik özetlerini kontrol eder. Başarısız yazmada bu işlemde değişmiş dosyaları geri alır.
- DNS veya bağlantı hatasından sonra bağlantı düzeldiğinde tekrar deneyin. Yeni sürüm ek bağımlılık istiyorsa ayrı bir klasöre yeni kurulum yapın ve orada açılışı sınayın. Çalışan Qt ve ses DLL’leri yerinde değiştirilmez. Paketli EXE için uygun kurulum paketi gerekir.

## Kesintiden sonra

Bu sürümle başlayan bir güncelleme, kontrol veya indirme sırasında kesildiyse **GÜNCELLE** yeniden denenebilir. İşletim sistemi canlı güncelleyicinin kilidini tutar ve süreç kapanınca bırakır.

Bu sürümle başlatılan ZIP güncellemesi dosya yazarken kesilirse tekrar **GÜNCELLE** düğmesine basın. Kurtarma çevrimdışı çalışır. Sürüm kaydı henüz yazılmamışsa önceki sürüm geri yüklenir. Kayıt tamamlanmışsa yeni sürümün dosyaları doğrulanır. Kesintiden sonra sizin düzenlediğiniz bir dosya veya bozuk yedek tespit edilirse kurtarma durur ve yedekler saklanır.

Normal açılış, bekleyen ZIP uygulama/geri dönüş kaydını Qt, ses, ayarlar ve hafıza yüklenmeden çevrimdışı kurtarmayı dener. Bütün dosya/yedek özetleri eşleşirse işlem tamamlanır ve Python temiz süreçte yeniden açılır. Doğrulanmamış yerel değişiklik, bozuk yedek, korunan anahtar dosyası, belirsiz işlem veya canlı güncelleyici varsa açılış durur; kayıt ve yedekler korunur. Kontrol aşamasında kesilmiş işlem tek başına açılışı engellemez. `pythonw` ile konsolsuz Windows açılışında hata yerel ileti kutusunda gösterilir.

Bekleyen ZIP işlemi nedeniyle açılış durduysa FRIDAY kapalıyken kurulum klasöründe şu komutu çalıştırın. Kurtarma başarılı olursa FRIDAY’ı normal şekilde açın.

```powershell
.\.venv\Scripts\python.exe -m core.app_updater --recover
```

Git güncellemesinin dosya uygulama aşamasında kesinti, geri almada hata veya önceki sürümden kalan belirsiz bir kilit bildirilirse FRIDAY’ı kapatın. Kurulum klasörünü, gizli yedekleri ve kullanıcı verilerini ayrı bir konuma kopyalayın. Windows’ta kalıcı hafıza ve devamlılık kayıtları için `%LOCALAPPDATA%\AetherMurat` klasörünü de koruyun. Güncelleme kilidini tek başına kaldırmak yarım işlemi onarmaz.

- Git için `git status --short`, `git branch --list "aether-backup/*"`, `git stash list` ve `git rev-parse HEAD` ile durumu kaydedin. Önceki sürümü denemek için yedek dalı ayrı bir çalışma klasöründe açabilirsiniz.
- ZIP için güncelleme günlüğündeki yedek konumunu ve `.aether-update.json` dosyasını saklayın. Yedek klasörü işlem öncesinde var olan dosyaları içerir. Yeni eklenmiş dosyalar veya yarıda kalmış işlem nedeniyle klasörün tek başına eksiksiz bir kurulum olduğu varsayılamaz. Bilinen çalışan sürümü ayrı klasörde açıp kişiselleştirme ve hafızayı doğrulayın.
- Yardımcı süreç günlüğü Windows’ta `%LOCALAPPDATA%\Friday\logs\restart.log` yolundadır. Bu günlükteki başlatma kaydı, mikrofonun veya modelin hazır olduğunu tek başına doğrulamaz.


## Dosyalar kurulduktan sonra HUD açılmıyorsa

Normal yeniden başlatmada yardımcı süreç eski FRIDAY’ın çıkmasını bekler. Yeni pencere görünür olup Qt olay döngüsü çalıştığında açılış onayı üretir. Yardımcı araç, her kontrolde önce yeni sürecin hâlâ açık olduğunu denetler; onaydan sonra en az bir saniyelik ilk gözlem boyunca da süreç açık kalırsa sonucu `restart.log` dosyasına yazar. Böylece onay bırakıp hemen kapanan süreç başarılı sayılmaz. Bu kısa gözlem, mikrofon/model hazırlığını veya uzun süreli kararlılığı doğrulamaz. Süreç erken kapanırsa çıkış kodunu kaydeder. 90 saniyede doğrulama bitmezse günlükte açılışın doğrulanamadığı belirtilir. Bu durumda Görev Yöneticisi’nde FRIDAY’ın hâlâ açık olup olmadığını kontrol edin.

Yeni kod kurulmuş ancak çalışmıyorsa, FRIDAY kapalıyken bu sürümün güncellediği **ZIP kurulumunda** son güncellemeyi çevrimdışı geri almak için kurulum klasöründe çalıştırın.

```powershell
.\.venv\Scripts\python.exe -m core.app_updater --rollback
.\.venv\Scripts\python.exe main.py
```

İkinci komutu yalnızca önceki sürümün geri yüklendiği doğrulandıktan sonra çalıştırın. Geri dönüş dosyaları ve önceki sürüm kaydını denetler. Yerel düzenleme varsa durur. Geri dönüşün kendisi kesilirse `--recover` ile devam edilir. Bu yol, geri dönüş kaydı içeren bir ZIP güncellemesi gerektirir. Git kurulumunda yukarıdaki yedek dal yöntemi geçerlidir.

## Konuşma ve görev geçmişini yedekleme

FRIDAY çalışırken, kendi hesabınıza özel yerel bir NTFS klasöründe yeni bir yedek oluşturabilirsiniz. Her yedek için yeni bir dosya adı seçin.

```powershell
.\.venv\Scripts\python.exe -m memory.continuity --backup "$env:LOCALAPPDATA\FRIDAY-Yedek\gecmis-01.sqlite3"
```

Yedek, SQLite’a kaydedilmiş konuşmaları, görevleri ve uygulama kayıtlarını içerir. Kişisel metinler içerdiği için erişimini sınırlayın. API anahtarları, persona ayarları ve diğer hafıza dosyaları ayrıca korunmalıdır.

Yeni bir Windows kurulumu veya boş bir veri klasöründe, FRIDAY kapalıyken geri yükleyin. Komut mevcut geçmişi korur ve aynı adlı dosyanın üzerine yazmaz.

```powershell
.\.venv\Scripts\python.exe -m memory.continuity --restore "$env:LOCALAPPDATA\FRIDAY-Yedek\gecmis-01.sqlite3"
```


## Doğrulanabilir kaynak ZIP adayı

Aşama 8'deki kaynak adayının commit/SHA-256 doğrulaması, temiz Windows kurulumu
ve mevcut kurulumun üzerine yazmadan test adımları için
[nihai kabul raporuna](nihai-kabul-2026-11-25.md) bakın. Bu aday imzalı EXE
değildir; gerçek cihaz ve güvenli yayın kabulündeki açıklar raporda listelenir.

## Git güncellemesi birleştirme sonunda kesilirse

Güncelleme temiz çalışma ağacında başladıysa FRIDAY dalı, önceki ve yeni commit'i
ve önceki commit'e işaret eden yedek dalı kaydeder. Sonraki açılış veya
`python -m core.app_updater --recover` bunları çevrimdışı doğrular. HEAD hedefe
ulaştıysa, izlenen dosyalar temizse ve devam eden Git işlemi görünmüyorsa
kayıt kaldırılır. Açılış temiz süreçte devam eder. Yerel değişiklik, eksik
yedek veya tamamlanmamış birleştirmede kayıt yerinde bırakılır. Stash
gerektiren işlemler ve eski belirsiz kilitler için mevcut elle inceleme geçerlidir.
