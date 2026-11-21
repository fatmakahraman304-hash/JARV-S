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

Dosya uygulama sırasında kesinti, geri almada hata veya önceki sürümden kalan belirsiz bir kilit bildirilirse MAYK’ı kapatın. Kurulum klasörünü, gizli yedekleri ve kullanıcı verilerini ayrı bir konuma kopyalayın. Windows’ta kalıcı hafıza ve devamlılık kayıtları için `%LOCALAPPDATA%\JarvisMurat` klasörünü de koruyun. Güncelleme kilidini tek başına kaldırmak yarım işlemi onarmaz.

- Git için `git status --short`, `git branch --list "jarvis-backup/*"`, `git stash list` ve `git rev-parse HEAD` ile durumu kaydedin. Önceki sürümü denemek için yedek dalı ayrı bir çalışma klasöründe açabilirsiniz.
- ZIP için güncelleme günlüğündeki yedek konumunu ve `.jarvis-update.json` dosyasını saklayın. Yedek klasörü işlem öncesinde var olan dosyaları içerir. Yeni eklenmiş dosyalar veya yarıda kalmış işlem nedeniyle klasörün tek başına eksiksiz bir kurulum olduğu varsayılamaz. Bilinen çalışan sürümü ayrı klasörde açıp kişiselleştirme ve hafızayı doğrulayın.
- Yardımcı süreç günlüğü Windows’ta `%LOCALAPPDATA%\Jarvis\logs\restart.log` yolundadır. Bu günlükteki başlatma kaydı, mikrofonun veya modelin hazır olduğunu tek başına doğrulamaz.
