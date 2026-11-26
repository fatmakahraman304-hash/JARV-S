# Windows hesabına bağlı isteğe bağlı anahtar koruması

26 Kasım 2026; başlangıç main commit'i `36970db90ba948bfcf2337a4a6810fce058b22e9`.
Aşama 1'in bir alt kapsamıdır; bütün güvenlik kabulü tamamlanmış değildir.

## Kullanım

FRIDAY'i kapatın ve uygulamanın kendi Python ortamıyla depo kökünde çalıştırın:

```powershell
.\.venv\Scripts\python.exe tools/credential_storage.py --status
.\.venv\Scripts\python.exe tools/credential_storage.py --enable
```

Etkinleştirme açık kullanıcı tercihidir; güncelleme bunu otomatik yapmaz.
Windows DPAPI, mevcut Windows kullanıcı profiline bağlı koruma uygular.
Yanına şifre çözme anahtarı yazılmaz, sunucuya bilgi gönderilmez ve yeni
bağımlılık eklenmez. Komutlar anahtar değerlerini göstermez.

`config/api_keys.json` ve mevcut `.bak` dosyasının **kendi ayrı değerleri**
korunarak API key, token, password, secret, credential, authorization ve
cookie adlı alanlar ile nested provider/plugin kimlik bilgileri korunur.
Ses, tasarım ve diğer sıradan tercihler okunabilir JSON olarak kalır.
Hafıza, kişisel dosyalar ve başka uygulamaların secret dosyaları taşınmaz.
İsimle tanınmayan özel alanlar otomatik sır olarak sınıflanmaz.

Merkezi ayar okuyucu çözülmüş değerleri mevcut sağlayıcı/araçlara verir.
Yazma kilidi, fsync ve aynı dizinde atomik değiştirme korunur. Etkinleştirmede
iki dosya önce tamamen şifrelenerek hazırlanır; backup sonra primary
yayımlanır. İki dosyalı yayın tek atomik işlem değildir. Arada kesinti olursa
yeniden `--enable` çalıştırın; normal ayar yazması da korumalı backup'tan
koruma tercihini devralır. Hata sonrası status ve iki dosyayı kontrol edin.
Geçersiz ciphertext, alanlar arası taşıma, bilinmeyen sürüm veya erişilemeyen
profil sessizce boş ayara dönüşmez; yazıcı mevcut dosyaları koruyup hata verir.
Dashboard okunamayan korumalı ayarla HTTP'ye düşerek başlamaz.

## Taşıma ve geri dönüş

Eski uygulama sürümleri bu biçimi okuyamaz. Başka bilgisayara/hesaba taşıma
veya eski sürüme dönmeden **önce**, halen erişebilen Windows profilinde:

```powershell
.\.venv\Scripts\python.exe tools/credential_storage.py --disable
```

Bu açık işlem primary ve backup'ı yeniden taşınabilir **açık metin** yapar.
Sonrasında dosyaların sahipliği ve yedek güvenliğinden kullanıcı sorumludur.
Profil kaybolduktan sonra dosyaları başka bir kullanıcıya kopyalamak şifreyi
çözmez. Windows profilinin güvenli kurtarma/yedekleme düzenini önceden kurun.
Linux/macOS için native secret store henüz uygulanmadı; etkinleştirme reddedilir.
Önceden oluşturulmuş `.broken-*`, harici yedekler ve Git geçmişi temizlenmez;
bu dosyalarda tarihsel açık metin bulunabilir. Kullanıcı dosyaları silinmez.

Bu, disk üzerinde kimlik bilgisi korumasıdır. Aynı kullanıcı olarak çalışan
zararlı kodu izole etmez; bellekte kullanılan sırları veya tüm ayar dosyasını
şifrelemez ve eklenti sandbox'ı yerine geçmez. Sentetik AEAD testleri native
DPAPI kanıtı değildir. Windows Python 3.13 CI ayrıca gerçek DPAPI ile aynı
profilde ikinci süreçten okumayı ve yanlış alan bağlamının reddini çalıştırır.
Gerçek kullanıcı cihazı/profili kurtarma testi ayrıca açık kabul maddesidir.
