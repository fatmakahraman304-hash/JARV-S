# Araç sonuçları: boş dönüş başarı kanıtı değildir

Eylem/eklenti kayıtları, konuşma hattı, arka plan ve bulut araçları, geç gelen
sonuçlar ve kullanıcı tarafından onaylanan callback'ler boş dönüşü `Done.`
metnine dönüştürebiliyordu. İşlemin gerçekleştiği gözlenmeden başarı üretmek
ve boş sonuç yüzünden aynı işlemi yeniden çağırmak yanlış olabilir.

`core.outcome.result_text`, mevcut metni değiştirmeden geçirir. `None`, boş
ve yalnız boşluk içeren metin `status=unverified verified=false
retry_automatically=false` olarak döner. İşlem zaten yapılmış olabilir;
sonraki karar için gerçek durum incelenmelidir. Bu işlev aracı yeniden
çalıştırmaz, onay oluşturmaz veya yeni izin vermez.

`False`, `0`, boş liste/sözlük ve diğer JSON verileri kendi anlamlarını
korur; bunlar `Done.` veya eksik sonuç sayılmaz. Serileştirilemeyen veya
sonlu olmayan veri de başarıya çevrilmez. Açık `done`, `started`, `failed`
ve `unverified` metinleri korunur. Araçların kendi yanlış iddialarını tespit
eden evrensel doğrulayıcı değildir; her aracın işlem sonrası kanıtı gerekir.

Yerel doğrulama: 30 hedefli test başarılı; eylem/eklenti ve gerçek thread
callback'inde tek çağrı, sahte onay tokenının reddi, hızlı/geciken boş sonuç,
bulut/arka plan sınırı ve sıfır/False/boş veri korunması dahil. 107 ilgili
entegrasyon testi koşuldu: 106 başarılı, 1 mevcut Windows-only atlama.
Python 3.13 Windows/Linux ve kurulum kabulü PR kaydında ayrıca izlenir.

Tasarım, FRIDAY sesi, sağlayıcılar, hafıza ve onay gereksinimleri değişmez.
Bu Aşama 1'in ikinci sınırlı güvenilirlik düzeltmesidir; bütün ana geliştirme
isteğinin veya eklenti izolasyonu/izin sisteminin tamamlandığı anlamına gelmez.

Aracın kendi `TimeoutError` hatası, bekleme süresinin dolmasıyla karıştırılmaz.
İş zaten bittiğinde hata doğrudan üst yürütücüye aktarılır; arka planda devam
ediyormuş gibi gösterilmez ve callback/iş yeniden başlatılmaz.
