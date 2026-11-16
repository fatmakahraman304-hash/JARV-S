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

Bu sürüm genel uygulama öğrenme ve geliştirme altyapısıdır. Bir uygulamanın
bütün özelliklerini desteklediğini veya üretilen adaptörün Windows'ta gerçek
uygulamayla doğrulandığını iddia etmez. Özellikle WhatsApp aramasında sesli
konuşma için ses köprüsü, gelen mesajlara sürekli yanıt için olay dinleyicisi
ve kapsamlı otomasyon kuralları henüz bu değişiklikte uygulanmamıştır.
Hesap bağlamak bu yetenekleri kendiliğinden sağlamaz.

Windows kabul denemesi: kısa bir konuşma yap, JARVIS'i kapatıp yeniden aç;
Nerede kaldık panelini ve hafıza sorgusunu kontrol et. Güncellemeden sonra
aynı kayıtların kaldığını kontrol et. Uygulamalar'da gerçek bir uygulama seç,
önce otomatik yayını kapatarak araştırma ve geliştirme sonuçlarını incele.
Üretilen kontrolü uygulamanın gerçek arayüzünde denemeden doğrulanmış sayma.
