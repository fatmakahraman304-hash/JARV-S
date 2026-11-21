# Kalıcı hafıza ve uygulama geliştirme

Konuşma kayıtları ve uygulama işlerinin sonuçları Windows'ta
`%LOCALAPPDATA%/JarvisMurat/continuity.sqlite3` içinde tutulur. Bilgi hafızası
aynı dizindeki `long_term.json` dosyasında saklanır; eski kurulumdaki dosya ilk
kullanımda kopyalanır, aslı silinmez. Güncelleyici bu dizini değiştirmez.
Kayıtlar yereldir; son konuşma bölümü model bağlamına eklenir, eski konuşmalar
`recall_memory` üzerinden aranır. `/hafiza` ve Ayarlar → Zekâ ve hafıza →
Nerede kaldık kayıtları gösterir. Tarihsel kayıt bir işlemin başarı kanıtı değildir.

Ayarlar → Uygulamalar: uygulama adı ve isteğe bağlı somut işlemler girilir.
Araştırma sonuçsuzsa iş durur. Kaynaklar bulunursa mevcut kod ajanı ayrı
çalışma kopyasında adaptör geliştirir. Otomatik yayın seçiliyse mevcut
`self_release` süreci yerel testleri ve GitHub kontrollerini çalıştırır;
başarılı kontrolleri doğrulamadan main'e birleştirme yapmaz. Seçili değilse
çalışma geliştirme kopyasında kalır. Kod sağlayıcısı, Git ve yayın için GitHub
CLI oturumu gereklidir. Eksik araç veya başarısız test sonucu ekranda saklanır.
Bilgisayar kapanırsa iş 'yarıda kaldı' olur; dış uygulama eylemleri tekrarlanmaz.

Uygulamaların sunduğu işlemler ve gereken izinler değişir. Kod testleri,
gerçek Windows uygulamasında yapılan denemenin yerini tutmaz.

Windows kabul denemesi: kısa bir konuşma yap, Mayk'ı kapatıp yeniden aç;
Nerede kaldık panelini ve hafıza sorgusunu kontrol et. Güncellemeden sonra
aynı kayıtların kaldığını kontrol et. Uygulamalar'da gerçek bir uygulama seç,
önce otomatik yayını kapatarak araştırma ve geliştirme sonuçlarını incele.
Üretilen kontrolü uygulamanın gerçek arayüzünde denemeden doğrulanmış sayma.

## WhatsApp Business asistanını bağlama

Ayarlar → Uygulamalar → WhatsApp Business → Ayarla. Twilio WhatsApp
Business göndericisinin numarasını, Auth Token'ı ve dışarıdan erişilebilen
HTTPS alan adını gir. HTTPS'te yalnızca aşağıdaki iki webhook yolunu,
Mayk'ın çalıştığı bilgisayarda `127.0.0.1:8769` adresine yönlendir.

- Twilio göndericisinin gelen mesaj webhook'u **POST `/whatsapp/message`**
  olmalı. WhatsApp Sandbox üzerinden mesaj akışı da denenebilir.
- Aramalar için göndericide WhatsApp Business Calling'i aç. Giriş için
  bağladığın TwiML uygulamasının Voice Request URL'si **POST `/whatsapp/voice`**
  olmalı. Proxy, sesli konuşma sırasındaki `?turn=` sorgusunu korumalı.

Mesaj ve arama için ayrı açma/kapama seçenekleri var. Mesajlara tanımladığın
metin döner. Aramalarda Mayk kendini otomatik asistan olarak tanıtır ve
sık sorulan sorular alanındaki anahtar kelimelerle eşleşen cevapları Türkçe
okur. Örnek kural `çalışma saatleri = Hafta içi 9–18.`. Arama sesi Twilio
tarafında işlenir. Mayk arama transkriptini diske yazmaz. Mayk ve HTTPS
bağlantısı açık olduğu sürece çalışır. Bu bağlantı Twilio'ya kayıtlı Business
numarası içindir. Yerel dinleyicinin açılması dış bağlantının kurulduğunu
belirtmez. Gerçek telefondan önce mesaj, ardından sesli arama yaparak doğrula.
