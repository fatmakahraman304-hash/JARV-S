# Aşama 2 — katalogda sunulan uygulama biçimi

[1.000 satırlık CSV](yetenek-envanteri.csv) katalog numarası, Türkçe ad,
birincil sınıf, mevcut çalışma kapsamı ve varsa yerel işlem adını içerir.
Aynı sınıf stüdyo ayrıntısında ve konuşma aracının listesinde görünür.
Özellik eklerken CSV'yi güncellemek için depo kökünde
`python -m tools.capability_inventory` çalıştırın ve UTF-8 çıktısını kaydedin.

| Birincil sınıf | Girdi |
| --- | ---: |
| Dil modeli yeteneği | 872 |
| Gerçek çalışan araç | 33 |
| Davranış ilkesi | 76 |
| Kısmen tamamlanmış özellik | 16 |
| Geliştirilmesi gereken özellik | 2 |
| Harici hesap veya donanım gerektiren özellik | 1 |

33 araç girdisinin 23'ü yerel işlemi olan konuşma yöntemleridir. Aynı
işlemi birkaç yöntem paylaşabilir. Diğer 10 girdi uygulanmış panel/araç
işlemleridir. Sınıf, katalog girdisinin hâlihazırda sunduğu mekanizmayı
belirtir. Örneğin fiyat karşılaştırması kullanıcı tarafından sağlanan
ölçüt ve puanlarla hesaplanır. Güncel fiyat toplama ve satın alma bu bağın
kapsamı dışındadır. Konuşma yöntemleri genel belge/araç kullanımına rehberlik
edebilir. Sınıflama her olası konuşmanın başarıyla yürütüldüğünü ölçmez.

Önceki 18 yerel bağa bütçe sınıflama (251), kapasite çizelgesi (256),
birikim planı (605), ağırlıklı ürün karşılaştırma (607) ve zaman serisi eğilimi
(823) eklendi. Birikim aracı kalan tutarı tam aylara dağıtır, kalan kuruşları
ayrı bildirir. Örnek: kalan 100,00 ve üç ay için iki ay 33,33 ve bir ay 33,34.
Kullanıcı girdileri ve gerçek araç sonucu gerekir. 30 çekirdek alan ve 76
davranış ilkesi mevcut yönlendiricide kalır. Katalog/yönlendirme/yerel araç
ve arşiv için Linux/Python 3.13 üzerinde 51 hedefli test geçti.
