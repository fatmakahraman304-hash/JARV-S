# FRIDAY kimliği

Masaüstü, web/PWA, telefon, tablet, TV, projeksiyon, saat ve Android Alıcı arayüzlerinde asistan adı FRIDAY'dır. Giriş ekranının parçalı eski logosu da FRIDAY olarak değiştirilmiştir. Koyu lacivert ve camgöbeği arayüzde yazı renkleri ortaklaştırılmıştır.

Sesli uyandırma FRIDAY içindir. Eski asistan adları uyandırma ve açık kapatma komutlarından kaldırılmıştır. Kaynakları yeniden eski kimliğe dönüştürebilen geçiş betiği ve ona bağlı iş akışı kaldırılmıştır.

**Aether API model sağlayıcısı korunur:** sağlayıcı kimliği `openai_compat@aether`, API adresi, anahtar alanları, ücretsiz model seçimi ve ücretli kullanım tercihi değişmez.

Mevcut kurulumların hafızasını ve eşleşmelerini korumak için kayıt anahtarları, veri klasörleri, Android paket kimliği, imza anahtarı, indirme adresleri ve cihaz protokolündeki teknik kimlikler korunur. Harici eklentilerin `AetherUI` ve `AetherLive` içe aktarımları, yeni `FridayUI` ve `FridayLive` sınıflarına uyumluluk takma adlarıdır. Bunlar ek asistan kişilikleri değildir.

Android Alıcı sürümü 2.3 / 13'tür; APK iş akışı yeni görünür adı mevcut uygulamanın güncellemesi olarak paketler.

Doğrulama: `tests/test_friday_identity.py` görünen HTML metnini (parçalı logo dâhil), PWA/Android adlarını, masaüstü kimliğini ve Aether API adresini denetler. Mevcut sağlayıcı, Türkçe komut ve arayüz testleriyle birlikte çalıştırılır.

Yerel kontrol sonucu: kimlik/sağlayıcı/arayüz grubu 43 testte başarılı; güncelleme, paketleme, yeniden başlatma, ikinci beyin ve cihaz eşitleme grubu 111 testte başarılı (1 platform testi atlandı). Python kaynakları ve web/dashboard JavaScript dosyaları ile HTML içi betikler sözdizimi kontrolünden geçti. Genel `unittest discover` çalışması tamamlanmadığı için tüm depo testlerinin geçtiği iddia edilmez; Windows ve APK paketleme GitHub Actions üzerinden ayrıca doğrulanır.

Ek regresyon kontrolü: güncelleyici, Türkçe ses anlama, yeniden başlatma/yerleşim ve proje/görsel grubu 75 testte başarılı. Toplam 229 test çalıştırıldı; 1 platform testi atlandı. Genel test keşfi tamamlanmadığından tüm depo testlerinin geçtiği iddia edilmez.
