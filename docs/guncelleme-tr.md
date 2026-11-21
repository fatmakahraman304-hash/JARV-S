# MAYK kurulumu ve GÜNCELLE düğmesi

## Windows’ta kaynak kurulumu

PowerShell’de Python 3.13 ve Git ile yeni bir klasöre kurun. Mevcut kurulumunuzdaki kişisel dosyaları bu işlem için taşımanız gerekmez.

```powershell
git clone --branch main https://github.com/fatmakahraman304-hash/JARV-S.git MAYK
cd MAYK
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe setup.py
.\.venv\Scripts\python.exe main.py
```

## Güncelleme

**GÜNCELLE** düğmesi, kaynak kurulumda arka planda çalışır. Etkinlik günlüğünde kontrol, ZIP indirme, yedekleme, uygulama ve dosya veya commit doğrulaması görünür. Doğrulamadan sonra HUD yeniden başlatmayı zamanlar. Yardımcı süreç başlatılamazsa pencere açık kalır ve elle açma bilgisi gösterilir. Yeni süreçte HUD’ı ve gereken ses aygıtını kontrol edin.

- Git kurulumu etkin dalı yalnızca ileri yönde günceller. Önceki commit için `jarvis-backup/` dalı oluşturur. Gerçek yerel düzenlemeleri adlandırılmış stash kaydına alır. Çakışma olursa kayıt saklanır. İzlenmeyen bir kullanıcı dosyası yeni sürümle çakışırsa işlem durur.
- ZIP kurulumu ilk seferinde `update_channel.json` içindeki dalı, daha sonra kayıtlı kanalı izler. Üzerine yazacağı dosyaları `.jarvis-backups/` içine kopyalar. Dosyaları değiştirdikten sonra içerik özetlerini kontrol eder. Başarısız yazmada bu işlemde değişmiş dosyaları geri alır.
- DNS veya bağlantı hatasından sonra bağlantı düzeldiğinde tekrar deneyin. Yeni sürüm ek bağımlılık istiyorsa ayrı bir klasöre yeni kurulum yapın ve orada açılışı sınayın. Çalışan Qt ve ses DLL’leri yerinde değiştirilmez. Paketli EXE için uygun kurulum paketi gerekir.

## Kesintiden sonra

Bu sürümle başlayan bir güncelleme, kontrol veya indirme sırasında kesildiyse **GÜNCELLE** yeniden denenebilir. İşletim sistemi canlı güncelleyicinin kilidini tutar ve süreç kapanınca bırakır.

Bu sürümle başlatılan ZIP güncellemesi dosya yazarken kesilirse tekrar **GÜNCELLE** düğmesine basın. Kurtarma çevrimdışı çalışır. Sürüm kaydı henüz yazılmamışsa önceki sürüm geri yüklenir. Kayıt tamamlanmışsa yeni sürümün dosyaları doğrulanır. Kesintiden sonra sizin düzenlediğiniz bir dosya veya bozuk yedek tespit edilirse kurtarma durur ve yedekler saklanır.

HUD açılmıyorsa MAYK kapalıyken kurulum klasöründe şu komutu çalıştırın. Kurtarma başarılı olursa MAYK’ı normal şekilde açın.

```powershell
.\.venv\Scripts\python.exe -m core.app_updater --recover
```

Git güncellemesinin dosya uygulama aşamasında kesinti, geri almada hata veya önceki sürümden kalan belirsiz bir kilit bildirilirse MAYK’ı kapatın. Kurulum klasörünü, gizli yedekleri ve kullanıcı verilerini ayrı bir konuma kopyalayın. Windows’ta kalıcı hafıza ve devamlılık kayıtları için `%LOCALAPPDATA%\JarvisMurat` klasörünü de koruyun. Güncelleme kilidini tek başına kaldırmak yarım işlemi onarmaz.

- Git için `git status --short`, `git branch --list "jarvis-backup/*"`, `git stash list` ve `git rev-parse HEAD` ile durumu kaydedin. Önceki sürümü denemek için yedek dalı ayrı bir çalışma klasöründe açabilirsiniz.
- ZIP için güncelleme günlüğündeki yedek konumunu ve `.jarvis-update.json` dosyasını saklayın. Yedek klasörü işlem öncesinde var olan dosyaları içerir. Yeni eklenmiş dosyalar veya yarıda kalmış işlem nedeniyle klasörün tek başına eksiksiz bir kurulum olduğu varsayılamaz. Bilinen çalışan sürümü ayrı klasörde açıp kişiselleştirme ve hafızayı doğrulayın.
- Yardımcı süreç günlüğü Windows’ta `%LOCALAPPDATA%\Jarvis\logs\restart.log` yolundadır. Bu günlükteki başlatma kaydı, mikrofonun veya modelin hazır olduğunu tek başına doğrulamaz.


## Dosyalar kurulduktan sonra HUD açılmıyorsa

Normal yeniden başlatmada yardımcı süreç eski MAYK’ın çıkmasını bekler. Yeni pencere görünür olup Qt olay döngüsü çalıştığında açılış onayını `restart.log` dosyasına yazar. Süreç erken kapanırsa çıkış kodunu kaydeder. 90 saniyede onay gelmezse günlükte açılışın doğrulanamadığı belirtilir. Bu durumda Görev Yöneticisi’nde MAYK’ın hâlâ açık olup olmadığını kontrol edin.

Yeni kod kurulmuş ancak çalışmıyorsa, MAYK kapalıyken bu sürümün güncellediği **ZIP kurulumunda** son güncellemeyi çevrimdışı geri almak için kurulum klasöründe çalıştırın.

```powershell
.\.venv\Scripts\python.exe -m core.app_updater --rollback
.\.venv\Scripts\python.exe main.py
```

İkinci komutu yalnızca önceki sürümün geri yüklendiği doğrulandıktan sonra çalıştırın. Geri dönüş dosyaları ve önceki sürüm kaydını denetler. Yerel düzenleme varsa durur. Geri dönüşün kendisi kesilirse `--recover` ile devam edilir. Bu yol, geri dönüş kaydı içeren bir ZIP güncellemesi gerektirir. Git kurulumunda yukarıdaki yedek dal yöntemi geçerlidir.
