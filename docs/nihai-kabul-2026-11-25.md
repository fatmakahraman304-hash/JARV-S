# FRIDAY — Aşama 8 otomatik kabul ve yayın sınırları

İnceleme temeli `main` commit'i `83dc5ace1c9083cedd2d5218c5b86bc7f2537e2f`
(Aşama 7, #202). İnceleme başlangıcı olan `d797ec8...` sürümünden daha yenidir.
Bu değişikliğin tam commit'i, PR'nin test edilmiş head kaydı ve kaynak ZIP
manifestindeki `source_commit` alanıyla belirlenir. Test sonuçları ve artifact
bağlantıları ilgili PR kabul kaydında tutulur; eski aşama sonuçları yeni head'in
sonucu gibi kullanılmaz.

## Yapılan işler

- `core/installer.py`: pip hatası, modülün kurulumdan sonra bulunamaması,
  tarayıcı indirme/açma hatası veya timeout durumunda artık hazır mesajı
  verilmez. Sonuç `False` olur ve hata günlüğe yazılır. Başarı için Chromium
  ve Firefox ayrı çocuk süreçte gerçekten açılıp kapanır. Pip 300 s, tarayıcı
  indirmesi 600 s, başlatma kontrolü 60 s ile sınırlandırılır. Bu fonksiyon
  mevcut sözleşmesi gereği arka plan worker'ında kullanılmalıdır.
- `tools/release_package.py`: yalnızca belirtilen commit'in Git nesnelerinden
  kaynak adayı üretir. Çalışma ağacındaki kişisel ayar, hafıza veya henüz
  commit edilmemiş değişiklikler okunmaz. İzlenen imzalama dosyaları ve runtime
  verileri de adaydan süzülür; depodaki orijinalleri silinmez/değiştirilmez.
- ZIP'te gereken kod, yüz modeli, lisans, kurulum ve güncelleme kanalı korunur.
  Her dosyanın SHA-256 özeti, uzunluğu ve kaynak commit'i manifesttedir.
  Aynı commit iki kez üretildiğinde aynı ZIP baytlarını vermelidir. Olan
  adayın veya kurulum klasörünün üzerine yazılmaz.
- Doğrulama; değişmiş/eksik/bildirilmeyen dosya, yanlış commit, yinelenen veya
  Windows'ta çakışan ad, symlink, dizin dışına çıkış, hassas dosya yolu ve
  aşırı büyük ZIP'i çıkarma başlamadan reddeder. Dar kapsamlı anahtar deseni
  taraması yalnızca dosya adını bildirir; anahtar değerini yazdırmaz.
- Windows kabulü Git çalışma kopyasını değil, Linux'ta üretilen **aynı ZIP'i**
  doğrular, yeni klasöre çıkarır, iki kez `setup.py` ve `pip check` çalıştırır.
  Paket içindeki gerçek varlıklarla görünür pencere, restart receipt ve normal
  kapanış kontrol edilir. Kurulu Chromium/Firefox gerçek çevrimdışı sayfalarla
  sınanır; güncelleme/HUD/başlangıç/kapanış regresyonları paketten çalışır.
- Kurulan Python dağıtımlarının ad/sürüm, SPDX ifadesi (varsa), lisans
  sınıflandırmaları ve lisans/atıf metinleri artifact olarak kaydedilir.
  Bu envanter otomatik uyumluluk veya güvenlik açığı onayı değildir.
- Son kabul raporu değiştiğinde mevcut yüz render, Dünya WebGL, gerçek
  Chromium/Firefox otomasyonu, Holo Masa çıkarım ve Windows kurulum
  workflow'ları yeniden çalışır. Önceki performans karşılaştırmasının
  “iyileşme zorunlu” eşiği değiştirilmez; aynı sürümde tekrar hızlanma
  iddiası yapılmaz.

## Yeniden üretilebilir hatalar ve regresyonlar

Eski bağımlılık kurucusunda altı kontrollü senaryo başarısızdı: pip hatası,
pip sıfır çıkışına rağmen modülün bulunmaması, tarayıcı indirme hatası,
kurulu Playwright yanında tarayıcının eksik olması, başlatma timeout'u ve
başarılı kurulum sonucunun doğrulanabilir bir değer döndürmemesi. Bunlar
çalışma sırasında gerçek paket indirmeden deterministik olarak sınanır.
Pip timeout'u da ayrı testtir. ZIP testleri geçici Git depoları ve saldırgan
ZIP girdileriyle gerçek üretim/doğrulama kodunu çalıştırır; hiçbir test
başarısızlığı saklamak için kapatılmaz.

## Dağıtım adayı nasıl üretilir?

Python 3.13 ve Git bulunan temiz checkout'ta:

```powershell
py -3.13 tools/release_package.py build --ref HEAD --out build/friday-source.zip
$commit = git rev-parse HEAD
py -3.13 tools/release_package.py verify build/friday-source.zip --commit $commit --extract build/FRIDAY
cd build/FRIDAY
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe setup.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe main.py
```

`--commit` için güvendiğiniz PR/checkout'taki tam commit'i kullanın; bir
ZIP'in kendi bildirdiği commit kimliği tek başına yayıncıyı doğrulamaz.
Manifest/yanındaki SHA-256 yalnızca bütünlük denetimidir, imza değildir.
Kaynak adayına Python, üçüncü taraf wheel'ler veya tarayıcı ikilileri gömülmez;
kurulum bunları indirir. Artifact adaydır; imzalı EXE veya APK yayını değildir.
Mevcut kurulumdaki hafıza ve anahtarları test klasörüne taşımayın.

Günlük kurulumda mevcut **GÜNCELLE** yolunu ve
[Windows kurulum/geri alma talimatlarını](guncelleme-tr.md) kullanın. Yeni
bağımlılık halinde ayrı klasörde sınayın. Başarısız güncellemede kullanıcı
verileri ve yedekler korunmalıdır; test için eski veri klasörünü silmeyin.

## Güvenlik ve uyumluluk

25 Kasım denetiminde `keytool -list -v`, sürüm kontrolündeki
`android-receiver/app/aether-alici.jks` dosyasında gerçek **PrivateKeyEntry**
bulunduğunu yeniden doğruladı. Sertifikanın SHA-256 parmak izi:
`F7:28:3E:63:FA:67:9C:4C:41:4C:6F:AC:84:E7:8B:95:27:BD:3D:CD:9B:5D:B6:DC:97:2B:2E:47:9F:81:1B:72`.
Bu halka açık sertifika bilgisidir; özel anahtar veya parola rapora alınmaz.
Gradle debug ve release için aynı anahtarı kullanıyor. Dosya ve Git geçmişi
bu çalışma tarafından değiştirilmedi. Anahtar kaynak adayından dışlanır;
eski GitHub geçmişinde ve mevcut APK iş akışında bulunması çözülmüş sayılmaz.

Nihai Android yayını öncesinde kurulu APK sertifikası karşılaştırılmalı;
yeni release anahtarı depo dışında tutulmalı, debug ayrılmalı, CI imzalama
korumalı ortamdan yapılmalı ve gerçek cihazda veri koruyan geçiş sınanmalı.
Anahtar rotasyonu, silme ve geçmişi yeniden yazma mevcut yetki kapsamında
uygulanmaz. **Android güvenli yayın kabulü engelleniyor.**

Proje `LICENSE` ve mevcut FatihMakes atıfları korunur. Qt/PyQt, tarayıcılar,
üçüncü taraf varlıklar ve geçişli bağımlılıkların ikili dağıtım koşulları
ayrı inceleme gerektirir. Envanterde eksik SPDX/lisans dosyası bulunabilir;
yokluğu “serbest kullanım” olarak yorumlanmaz. Tam CVE ve lisans uyumluluk
incelemesi **DOĞRULANMADI**. Kaynak adayı ticari kullanım hakkı vermez.

## Nihai kabul matrisi

| Alan | Otomatik kanıt | Açık saha/yayın kabulü |
| --- | --- | --- |
| Kurulum | Python 3.13 Windows ZIP temiz kurulum/yeniden kurulum, pip check | Kullanıcının Windows cihazı, imzalı EXE |
| Başlangıç/kapanış | Gerçek görünür Windows penceresi, receipt, normal çıkış | Yapılandırılmış profil, fiziksel sürücüler |
| Veri/güncelleme | Hafıza, unutma/tombstone, SQLite, rollback ve yarım güncelleme regresyonları | Güç kesintisi, gerçek cihaz eşitlemesi |
| Beyin/ses | Sağlayıcı sözleşmeleri, fallback, timeout, kuyruk ve söz kesme regresyonları | Canlı NVIDIA/Gemini hesabı, FRIDAY ses kalitesi, Türkçe mikrofon/yankı |
| Otomasyon | İzole gerçek Chromium/Firefox, hedefe bağlı kullanıcı onayı ve iptal | Kullanıcının oturumundaki gerçek uygulama ve teslim sonucu |
| Görsel | Windows/Linux gerçek OpenGL yüz, QtWebEngine/WebGL dünya, Holo Masa fixture çıkarımı | Kullanıcının GPU'su, webcam, görsel kabul |
| Kaynaklar | Sınırlı kuyruk, gizli HUD ve sentetik yük regresyonları | Saatlerce gerçek CPU/RAM/yanıt ölçümü |
| Yayın güvenliği | Adayda anahtar/veri dışlama, bütünlük ve dependency lisans envanteri | İmzalama rotasyonu, geçişli lisans/CVE ve ikili paket incelemesi |

Saha sütunundaki her madde **DOĞRULANMADI**. CI GPU/WebGL veya fixture,
fiziksel kullanıcı GPU'su/kamerası olarak sunulmaz. Sahte sağlayıcı testleri
canlı servis testi değildir. README'deki geçmiş gecikme, ücretsiz kullanım ve
her komutu yerine getirme ifadeleri kullanıcı hesabı için yeni kanıt sayılmaz.

Aşama 8'in burada yürütülebilen otomatik kabul kapsamı PR'nin bütün kontrolleri
geçtiğinde kapanır. Nihai yayın/günlük kullanım kabulü bu açıklarla kapanmaz.
Genel durum **KISMEN HAZIR**; koşulsuz “HAZIR” sürümü veya imzalı paket
ilan edilmemiştir. Başarısız/atlanmış test sayıları ve son commit PR'de açık
olarak kaydedilir.
