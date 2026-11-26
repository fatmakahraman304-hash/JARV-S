# Kalıcı hafıza ve uygulama geliştirme

Konuşma kayıtları ve uygulama işlerinin sonuçları Windows'ta
`%LOCALAPPDATA%/AetherMurat/continuity.sqlite3` içinde tutulur. Bilgi hafızası
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

Windows kabul denemesi: kısa bir konuşma yap, FRIDAY'ı kapatıp yeniden aç;
Nerede kaldık panelini ve hafıza sorgusunu kontrol et. Güncellemeden sonra
aynı kayıtların kaldığını kontrol et. Uygulamalar'da gerçek bir uygulama seç,
önce otomatik yayını kapatarak araştırma ve geliştirme sonuçlarını incele.
Üretilen kontrolü uygulamanın gerçek arayüzünde denemeden doğrulanmış sayma.

## WhatsApp Business

Business/Twilio otomatik yanıt dinleyicisi kaldırıldı. Eski yerel ayarlar
çalıştırılmaz veya dışarı aktarılmaz; kullanıcı verileri silinmez. Normal
WhatsApp için kullanıcı onayına bağlı mesajlaşma araçları korunur.
