# FRIDAY geliştirme aşamaları

Kullanıcının belirlediği sıra geçerlidir. Aynı anda bir aktif aşama yürütülür.
Bir düzeltmenin birleşmesi, bütün aşamanın tamamlandığı anlamına gelmez.

| Aşama | Kapsam | Durum |
| --- | --- | --- |
| 1 — Sistem kararlılığı | Hatalar, güncelleyici, veri güvenliği, dayanıklılık | **Aktif** |
| 2 — Yapay zekâ beyni | 1.000 yetenek, düşünme, öğrenme, Abacus AI, sohbet | Bekliyor |
| 3 — Ses sistemi | FRIDAY sesi, sürekli dinleme, hızlı konuşma | Bekliyor |
| 4 — Hafıza sistemi | Kalıcı hafıza, projeler, bağlam | Bekliyor |
| 5 — Otomasyon | Bilgisayar, uygulamalar, gerçek araçlar | Bekliyor |
| 6 — Görsel sistem | 3D yüz, holografik arayüz, dünya, görsel analiz | Bekliyor |
| 7 — Performans | Açılış, CPU, RAM, yanıt süresi | Bekliyor |
| 8 — Nihai sistem | Bütünleşik testler, Windows kurulumu, son denetim | Bekliyor |

## Aşama 1 kabul koşulları

- Güncelleme hatası ve kesintisinde önceki kod, kullanıcı verileri ve yedekler korunmalı.
- Yarım kurulumu normal uygulama açılışı çalıştırmamalı; kurtarma yolu açıklanmalı.
- Kurtarma, yeniden başlatma ve kontrollü kapanış testleri Windows/Linux üzerinde geçmeli.
- Veri yazımı, yedekleme ve geri yüklemenin hata senaryoları gözden geçirilmeli.
- Temiz Windows kurulumu ve yeniden kurulum doğrulanmalı; donanım/servis gerektiren açıklar ayrıca kaydedilmeli.

## Son çalışma: açılış ve yarım güncelleme

`main.py`, üçüncü taraf modüllerden önce `core/startup_guard.py` kontrolünü çağırır.
Bekleyen yazma/geri dönüş kaydı veya canlı güncelleyici varken normal açılış durur.
Kontrol, uygulama verisi veya yedek silmez; kurtarma çevrimdışı komutla yapılır.
Regresyon testleri gerçek giriş noktasını ayrı süreçte çalıştırır ve uygulama
modüllerine ulaşılmadığını, kişisel dosyaların korunduğunu sınar.

Bu çalışma Aşama 1'in yalnızca bir parçasıdır. Fiziksel Windows cihazında güç
kesintisi, gerçek mikrofon/hoparlör ve uzun süreli çalışma **DOĞRULANMADI**.
Nihai kabul ve Aşama 2'ye geçiş henüz ilan edilmedi.
