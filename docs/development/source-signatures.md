# Kaynak adayı imzalama ve doğrulama

SHA-256 bütünlüğü tek başına yayıncı kimliği değildir. Ed25519 imza; arşiv
baytlarını, boyutunu ve tam kaynak commit'ini bağlar. Güvenilir açık anahtarı
arşivden veya imzanın kendisinden otomatik kabul etmeyin.

Mevcut kaynak adayını oluşturup, depo dışındaki sahip olduğunuz Ed25519 PEM
anahtarıyla imzalayın. Bu işlem hiçbir anahtar üretmez veya yayımlamaz.
Şifreli PEM için parolayı güvenli oturumunuzda `FRIDAY_RELEASE_KEY_PASSWORD`
çevre değişkeninde sağlayıp `--password-env FRIDAY_RELEASE_KEY_PASSWORD` ekleyin;
parola değerini komut satırına yazmayın:

```powershell
py -3.13 tools/release_package.py build --ref HEAD --out build/friday-source.zip
$commit = git rev-parse HEAD
py -3.13 tools/release_package.py sign build/friday-source.zip --commit $commit --key C:/FRIDAY-Keys/release.pem --out build/friday-source.sig.json
py -3.13 tools/release_package.py verify build/friday-source.zip --commit $commit --signature build/friday-source.sig.json --public-key C:/FRIDAY-Trust/release-public.pem --require-signature --extract build/FRIDAY-verified
```

Yeni dosya adı gerekir; mevcut aday/imza/kurulum ezilmez. Özel anahtar depo
altından okunmaz. CLI şifreli veya şifresiz Ed25519 PEM yükler; anahtarın disk
şifreleme ve kullanıcı erişim kontrolüyle korunması imzalama ortamına aittir.
Üretim HSM/rotasyon/iptal ve güven kökü dağıtımı ayrı açık iştir.
Testler yalnız geçici, sentetik Ed25519 anahtarları kullanır.

`--require-signature` olmadan eski unsigned aday incelemesi çalışmaya devam
eder ve `publisher_signature_verified=false` döner. İmzalı incelemede hem
ayrı güvenilir anahtar hem imza gerekir; yanlış arşiv, commit veya anahtarla
çıkarma başlamaz. JSON manifest imzalandı diye yeniden yazılmaz; doğrulama
sonucu CLI çıktısında gösterilir. Bu komut imzalı EXE/APK veya GÜNCELLE için
zorunlu güvenilir yayın politikası oluşturmaz.

## GÜNCELLE için kullanıcı profiline yayıncı kaydı

Yayıncının açık PEM dosyasını ve aynı dosyanın SHA-256 parmak izini bağımsız,
kimliği doğrulanmış kanallardan edinin. Windows'ta kuruluma ait Python ile
tek seferlik kayıt örneği (parmak izi yerine doğrulanmış 64 hex haneyi girin):

```powershell
.\.venv\Scripts\python.exe -m core.update_trust --public-key C:/FRIDAY-Trust/release-public.pem --expected-sha256 PARMAK_IZI
```

Kayıt uygulama ağacının dışında kullanıcı profilinde saklanır. İkinci kayıt
mevcut anahtarı ezmez. Aynı profilde bu kodu kullanan Git ve ZIP kurulumları,
dalın tam commit'i için resmi depoda `friday-source-<40 haneli SHA>` etiketli
release altındaki `friday-source.zip` ve `friday-source.sig.json` dosyalarını
ister. Yayıncı yukarıdaki build/sign komutlarının çıktısını bu adlarla yayımlar.
Paket, imza, commit veya güven dosyası geçersizse güncelleme yazma aşamasına
geçmez. Git kanalında imzada onaylanan commit'e fast-forward yapılır; ZIP
kanalında kontrol edilen dosyalar mevcut yedek ve kurtarma işlemiyle kurulur.
Sürüm sorgusu dalı kontrol eder; yayıncı imzası kurulum sırasında denetlenir.

İlk anahtar dağıtımı ve gerçek imzalı yayın yayıncıya aittir. Kayıtsız
profiller mevcut GitHub kanalını kullanır. Eski istemciler, başka OS profilleri
ve yerel güven dosyasının kaldırılması zorunlu imza güvencesi sağlamaz.
Güvenilir anahtarın iptal/devir protokolü ve işletim sistemi paketinin kod
imzası ayrı kabul gerektirir. Kurtarma için mevcut yerel yedek kullanılır.
