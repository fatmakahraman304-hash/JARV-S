# FRIDAY ana geliştirme kaydı — 26 Kasım 2026

Yeni ana talep için başlangıç: `6e719a2753462e0c4e7206178ff1c517dab26bbc` (#205).
İzole dal: `friday-dev/stability-audit-20261126`. Eski aşama raporları tarihsel
kanıttır; bu genişletilmiş talebin tamamlandığı anlamına gelmez.

## Kapsam ve korunacak sözleşmeler

Tek FRIDAY kişiliği, mevcut kadın sesi, tasarım, 30 çalışma alanı, kullanıcı
ayarları/hafızası ve izin mekanizmaları korunur. Hesap, model, kamera, mikrofon,
GPU ve gerçek cihaz kullanılmadan bunların çalıştığı iddia edilmez. Güvenli,
geri alınabilir teknik değişiklikler bağımsız geliştirilir. Başarısız kod ana
dala alınmaz. Kritik değişiklik öncesi bu başlangıç commit'i geri dönüş noktasıdır.

| Aşama | Yeni talep için durum | Sonraki somut kapsam |
| --- | --- | --- |
| 1 — Kararlılık/güvenlik | AKTİF; bu değişiklik yalnız aşağıdaki alt kapsamı uygular | Secret store, eklenti izinleri/izolasyon, bağımlılık/CVE, güvenli mod ve güncelleyici imza politikası açık |
| 2 — Beyin | Mevcut işlevler korundu; yeni gereksinimler açık | Sağlayıcı/model doğrulama, 1000 girdinin altı durumlu envanteri, görev/model bütçesi |
| 3 — Ses | Mevcut işlevler korundu; saha kabulü açık | Gerçek Türkçe mikrofon, yankı, barge-in, çevrimdışı ölçüm |
| 4 — Hafıza | Mevcut JSON/SQLite ve unutma kuralları korundu | Kaynaklı öğrenme, RAG/vektör ihtiyacının ölçümü, düzenleme/silme/backup uçtan uca |
| 5 — Araçlar/görevler | Mevcut görev, tarayıcı, Composio ve cihaz altyapısı korundu | MCP SDK/protokol doğrulama, izinli uzman yürütücüler, cihaz/oda sınırları |
| 6 — Görseller | Tasarım değiştirilmedi | Holo Masa/Blender/harita gerçek cihaz kabulü, görsel kalite/ölçüm |
| 7 — Performans | Tarihsel ölçümler yeni hız iddiası sayılmaz | Aynı cihaz/konfigürasyonda açılış, ses, kaynak ve maliyet ölçüm aracı |
| 8 — Nihai kabul | AÇIK | Windows/Linux Python 3.13 CI + fiziksel cihaz/hesap + güvenli dağıtım |

Yeni talepte Abacus AI/RouteLLM ve DeepSeek desteği isteniyor. Başlangıç
kodunda bu sağlayıcılar önceki talep nedeniyle kaldırılmış ve bazı ayar
okuma/yazma yollarında engellenmiş durumda. Bu artık Aşama 2 için açık geri
entegrasyon gereksinimidir. Eski kişisel anahtarlar geri getirildi veya servis
çalışıyor gibi gösterilmez. Resmî uç noktalar/model listeleri doğrulanmadan ve
kaldırma geçişi veri kaybetmeden tasarlanmadan rastgele model adı eklenmez.

## Bu değişikliğin gerçek uygulaması

1. **Açılışta otomatik ZIP kurtarma:** mevcut çevrimdışı, hash doğrulamalı
   kurtarma kullanılır. Bekleyen işlem için canlı güncelleyici kilidi varsa
   açılış durur. Güncel dosya/yedek değişmişse işlem ve yedekler korunur.
   Doğrulanmış kurtarma sonrasında Python süreci yeniden yürütülür; iki
   sürümün belleğe yüklenmiş kodu birlikte çalıştırılmaz. Git veya belirsiz
   işlem kaydı otomatik reset/temizlik yapılmaz.
2. **Anahtar koruması:** ZIP güncelleyici `.jks`, `.keystore`, `.p12`, `.pfx`,
   `.key`, `.pem` dosyalarını getirmez, üzerine yazmaz veya eski manifestten
   silmez. Bunlar `.gitignore` kapsamındadır. Eski bir kurtarma kaydı bu
   tür dosyaları değiştirmeyi içerirse otomatik kurtarma durabilir; kayıt,
   yerel dosya ve yedek korunur, elle inceleme gerekir.
3. **Android:** depodaki eski JKS sürüm kontrolünden çıkarılır; yerel kopya
   silinmez ve geçmiş yeniden yazılmaz. Release artık anahtarsız/unsigned
   adaydır. Debug ayrı uygulama kimliği kullanır; release uygulamasının
   verisini ezmez. Onaylı CI ortamı, depo dışı anahtar ve beklenen yeni
   sertifika ile manuel signed aday üretimi hazırlanır. Eski açık sertifika
   açıkça reddedilir. Otomatik stabil APK yayını kaldırılır.
4. **Kaynak adayı imzası:** mevcut cryptography bağımlılığıyla gerçek Ed25519
   imzalama/doğrulama eklenir. İmza arşivin SHA-256, boyut ve tam commit'ini
   bağlar; güvenilir açık anahtar ayrı sağlanır. Aynı baytlar doğrulanıp
   açılır. Yanlış imza/anahtar/commit, çıkarma başlamadan reddedilir.
   İmzasız aday üretimi mevcut test akışını korur; bu aday yayıncı doğrulaması
   almış sayılmaz.

Bu imza aracı **GÜNCELLE'nin tüm Git/ZIP kanallarında zorunlu yayıncı
imzası doğrulaması yaptığı anlamına gelmez**. Sabit güven kökü, imzalı yayın
kanalı, anahtar devri/iptali ve kullanıcı kurulumuna güvenli ilk dağıtım
ayrı açık çalışmadır. Hiçbir gerçek üretim imza anahtarı oluşturulmadı,
yüklenmedi veya kullanıcı hesabına secret yazılmadı.

## Kanıtlar ve açıklar

İlk statik tarama: 478 izlenen dosya, 387 Python dosyası; Python AST sözdizimi
hatası ve `core/gui/memory/actions/plugins/providers/dashboard` ad alanlarında
bulunamayan mutlak iç modül hedefi yok. Dinamik/opsiyonel import, thread ve
uzun süreli bellek sızıntısı garantisi değildir. 31 proje için kaynak HEAD,
README/lisans ve bakım durumu [ön inceleme kaydındadır](upstream-review-2026-11-26.md).
Bütün projelerin bütün kodu incelendi veya 31 entegrasyon yapıldı sayılmaz.

Yerel ilk hedefli koşu: **79 test geçti**; gerçek Ed25519/tahrifat, APK imza
politikasında sentetik alt süreçler, güncelleyici/anahtar koruma, kesilmiş
süreçten açılış kurtarma ve kimlik koruması dahil. Yerel ortam Python 3.12;
Windows/Linux Python 3.13 CI sonucu PR kaydına eklenecek. Bütün suite
sonucu ayrıca kaydedilir; başarısız testler silinmez veya atlanarak saklanmaz.

Android fiziksel yükseltme, Play hesabı/kurulu sertifika incelemesi, yeni
anahtarın güvenli sahipliği ve güven kökü dağıtımı **DOĞRULANMADI**.
[Android rotasyon adımları](android-signing-rotation.md) tamamlanmadan yeni
signed aday stabil URL'ye yayımlanmaz; eski APK zaten kurulu olabilir.

## Yeni talep ile eski tercih arasındaki fark

Abacus AI/RouteLLM ve DeepSeek daha önce kullanıcı isteğiyle kaldırılmıştı.
Yeni ana talep bunları destek listesine yeniden alıyor; güncel talep geçerlidir.
Bu Aşama 1 değişikliği henüz sağlayıcıları veya mevcut ayar temizleme politikasını
geri getirmedi. Aşama 2'de resmî endpoint/model doğrulaması, izin/maliyet sınırları,
konfigürasyon geçişi ve yeni regresyon sözleşmeleri birlikte uygulanmalıdır.

Yerel geniş koşu gerçek Blender ikilisini bulduğu için Blender model/render
kabulünü de çalıştırdı. Ayrı 150 saniyelik tanılama koşusu Blender render alt
sürecinde süre sınırına ulaştı; başarılı tam regresyon sayılmadı. Hiçbir Blender
testi kaldırılmadı, atlanacak biçimde değiştirilmedi veya gizlenmedi. CI'da
çekirdek regresyon ve mevcut Blender kabul kapsamları ayrı izlenecek.

## Aşama 1 — araç sonucu bütünlüğü

[Boş sonucun başarıya dönüşmesini engelleme](tool-outcomes.md), kayıtlı araçlar,
konuşma/arka plan/bulut ve gerçek onay callback'lerinde ortak sonuç dönüşümü
kullanır. Yerel test ve açık sınırlar ilgili kayıttadır. CI ve birleşme durumu
GitHub PR kaydından doğrulanmalıdır; eski kayıt yeni başarı kanıtı sayılmaz.

## Aşama 1 — ZIP güncellemesinde açık SQLite veritabanı

Bu oturumun ana dal başlangıcı ve geri dönüş noktası
`36970db90ba948bfcf2337a4a6810fce058b22e9` (#207).

- ZIP güncelleyicisi .db, .sqlite ve .sqlite3 veritabanlarının günlük ve
  paylaşılan bellek dosyalarını korur. Eski dosya listesinde yer almaları
  bunların kaldırılmasına yol açmaz. Kaynak paketi oluşturulurken .sqlite3
  yan dosyaları da paket dışında kalır.
- Linux/Python 3.13 üzerinde iki regresyon testi düzeltmeden önce başarısız
  oldu. Düzeltmeyle güncelleyici, sesli güncelleme eklentisi ve kaynak paketi
  testlerinin 57'si geçti. Açık WAL bağlantısı sırasında yerel yan dosyaların
  baytları korundu. Yeniden açılan veritabanı bütünlük denetimini geçti ve
  kaydedilmiş satır okundu. Ağ yanıtları bu testte yerel örnektir.
- Ürün sürümü ve Windows paketi yayımlanmadı. Yukarıdaki aşama tablosunda
  açık kalan işler sürüyor. Bu değişiklik için Windows panelinden gerçek
  yükseltme ve yeniden başlatma kabulü bekleniyor.
