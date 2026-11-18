# JARVIS ile Blender

Masaüstü JARVIS'i Blender kurulu bilgisayarda başlat. Eklenti Blender'ı PATH'te,
Windows'ta standart Blender Foundation klasöründe veya macOS'ta Applications
altında arar. Sahne planlama ve soru yanıtlama JARVIS'in ayarlı modelini kullanır.

| Örnek komut | Sonuç |
| --- | --- |
| “Blender'da metal ayaklı ahşap masa yap. Kamerayı önden yerleştir ve üstten aydınlat.” | Yeni bir sahne oluşturur. |
| “Son Blender projesinde masanın etrafına dört tabure ekle.” | Kayıtlı sahneyi okuyup yeni bir sürüm oluşturur. |
| “Blender projesinde hangi nesneler var?” | Nesne sayısını, etkin kamerayı ve ilk 20 ismi bildirir. |
| “Blender'da masayı 1. kareden 90. kareye kadar döndür.” | Nesnenin dönüşüne anahtar kareler ekleyebilir. |
| “Blender projemi aç / render al / GLB olarak dışa aktar.” | İlgili işlemi yapar ve dosya yolunu bildirir. |
| “Blender'da UV unwrap nasıl yapılır?” | Kurulu Blender'ın operatör bilgilerini kullanarak adımları açıklar. |
| “Blender işleminin durumu ne?” | Sonucu veya devam eden işlemin durumunu bildirir. |

Kendi dosyanı düzenlemek için önce Blender'da kaydet ve JARVIS'e tam
`.blend` yolunu ver. İşlemler ayrı bir Blender sürecinde yürür. Yeni sürümler
kullanıcı klasöründeki `JARVIS/Blender` altında oluşur. “Son proje” en son
başarıyla kaydedilip yeniden açılarak doğrulanan sahnedir. Render, sahnenin
geçerli karesini PNG olarak kaydeder.

Uygulama araçları arasında özel mesh, metin, kopyalama, yüzey malzemeleri,
bevel, subdivision, solidify, mirror, array, boolean, UV açma, kemik ve
ağırlık grupları, poz ve nesne animasyonu, kamera ve ışık, shader ve Geometry Nodes ağları bulunur. Bilgi alma
daha geniş konuları kapsar. Örneğin sıvı simülasyonu ve elle sculpt fırça darbeleri bu sürümün uygulama araçlarının dışındadır.
