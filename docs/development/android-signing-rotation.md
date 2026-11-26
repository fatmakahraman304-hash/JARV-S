# Android imzalama ve veri koruyan geçiş

Resmî temel: [Android uygulama imzalama](https://developer.android.com/studio/publish/app-signing)
ve [apksigner](https://developer.android.com/tools/apksigner). Anahtar rotasyonu,
kurulu uygulamaların sertifika geçmişi ve desteklenen Android sürümüne bağlıdır;
yeni bir sertifikayla imzalamak tek başına veri koruyan güncelleme sağlamaz.

Eski `aether-alici.jks` açık Git geçmişinde kalır ve güvenilir üretim anahtarı
sayılmaz. Bu değişiklik geçmişi silmez ve eski kurulu uygulamanın kimliğini
iptal edemez. Eski anahtarla yeniden yayın yapılmaz. Yerel eski dosya kullanıcı
incelemesi/geri dönüş için yerinde kalabilir; güncelleme bunu silmez.

1. Gerçek cihazdaki APK sertifikasını ve uygulama sürümünü tespit et; kişisel
   cihaz verisini ve eşleştirme bilgilerini depo dışında yedekle.
2. Dağıtım yolunu doğrula: Play App Signing varsa hesapta uygun key upgrade/
   upload-key prosedürünü uygula. Yandan yüklemede desteklenen Android
   sürümleri için imza soy ağacı ve yükseltme yolunu ayrı test et. Uygulamayı
   kaldırıp yeniden kurmak veri koruyan rotasyon kabul edilmez.
3. Yeni anahtarı güvenilir kullanıcı/CI yöneticisi depo dışında oluştursun;
   özel anahtar veya parolalar sohbet/commit/rapora konmasın. Burada üretim
   anahtarı oluşturulmadı. Gerekirse yeni Ed25519 kaynak-paket anahtarı Android
   anahtarından tamamen ayrı tutulur.
4. GitHub `android-release` environment'ı için required reviewers ve dal
   sınırlarını hesap yöneticisi yapılandırsın. Workflow'da environment adı
   bulunması bu korumaların hesapta kurulduğu anlamına gelmez.
5. Ortama `FRIDAY_ANDROID_KEYSTORE_BASE64`, `FRIDAY_ANDROID_STORE_PASSWORD`,
   `FRIDAY_ANDROID_KEY_ALIAS`, `FRIDAY_ANDROID_KEY_PASSWORD` secret'larını ve
   `FRIDAY_ANDROID_CERT_SHA256` değişkenini güvenli arayüzden ekle. Yeni
   sertifika parmak izi bağımsız kanaldan doğrulanmalı; eski açık sertifika
   script tarafından reddedilir. Bu hesap adımları tamamlanmadı.
6. Ana dalda manuel `sign_candidate=true` ile aday üret. Script anahtarı
   geçici, erişimi kısıtlı klasörde açar; apksigner sign + verify çalıştırır,
   sertifikayı beklenen değerle karşılaştırır ve geçici dosyaları temizler.
   Parola hata çıktıları rapora aktarılmaz. Aday otomatik yayımlanmaz.
7. Gerçek test cihazlarında release üstüne güncelleme, veri/eşleştirme,
   izinler, TV kumandası ve yeniden başlatmayı doğrula. İmza soy ağacı henüz
   bu aday imzalama scriptinde üretilmez; uyumlu rotasyon kanıtı açıktır.
8. Yalnız bu kabulden sonra stabil yayın akışı için ayrı testli değişiklik
   yap. Tarih silme/force-push, mağaza hesabı işlemleri ve gerçek cihazda
   silme/yeniden kurma otomatik uygulanmaz.

Geliştirici `debug` paketi `.debug` applicationIdSuffix kullanır; üretim
uygulamasını güncellemez. Unsigned aday kurulabilir nihai APK olarak sunulmaz.
