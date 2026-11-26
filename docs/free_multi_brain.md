# FRIDAY — Ücretsiz çoklu beyin (deneysel)

## Kurulum

1. Google AI Studio: https://aistudio.google.com/apikey
2. Groq: https://console.groq.com/keys
3. Cloudflare Workers AI: https://dash.cloudflare.com/ (Workers Free planı)
4. OpenRouter: https://openrouter.ai/keys
5. İsteğe bağlı: Ollama https://ollama.com/ — kurulu yerel model seçin.

Motor ve Sağlayıcılar → Arka Plan İstekleri bölümünde Groq, Cloudflare ve
OpenRouter'ı tek tek seçerek API anahtarlarını girin. Her seçim değişiminde
ayarlar yerelde saklanır. Sonra öncelik menüsünde **Ücretsiz çoklu beyin**
seçip Uygula deyin. Kodlama ajanı için yerleşik FRIDAY ajanını seçin.
Cloudflare için API adresi alanına 32 karakterli Account ID girin; API anahtarı
alanına sadece Workers AI izinli token girin. Cerebras ödeme yöntemi istediği
için otomatik havuza dahil değildir. Sesli konuşma mevcut Gemini Live veya
seçilmiş pipeline üzerinden devam eder.

Hızlı metin: GPT-OSS 20B; zor metin/kod: GPT-OSS 120B, Qwen 3.8;
Cloudflare ve OpenRouter ücretsiz yönlendirici yedek; yapılandırılmış yerel
Ollama son harici yedek. Aether API'nin ücretsiz rolleri de yapılandırılmışsa
kullanılır. Gemini mevcut yedek merdivenini korur; Hydrogen SMART'a eklenmiştir.
Görseller ve kayıtlar mevcut Gemini yolunu, kaynaklı arama REST yolunu korur.

API anahtarlarını sadece yerel ayarlara girin. Ücretsiz hesaplar kullanın,
ücretli faturalandırmayı açmayın. Ücretsiz model listesi ücretli hesaptaki
faturalandırmayı engelleyemez; kota ve fiyatlar değişebilir. 1M bağlam, 1M
ücretsiz günlük token anlamına gelmez. Kodlama ve metin istekleri ayarlanan
bulut sağlayıcılarına gönderilir. Gemini Live, ses ve pipeline'ın maliyet
kontrolü bu yeni metin havuzunun dışında kalır.

Arka plan çağrıları mevcut hata/kota bekleme mekanizmasını kullanır; 429
alan model yerine başka model denenir. `core.free_models.usage_report()`
işlem süresince UTC gününe göre sağlayıcının bildirdiği tokenları sayar;
kalıcı bütçe veya tüm sağlayıcıların kesin kalan kota göstergesi değildir.
Ollama yalnızca varsayılan yerel IPv4 adresindeki ayarlanmış modelle kullanılır.
Yeni bağımlılık gerekmez.

Resmi model/kota belgeleri:
- https://console.groq.com/docs/rate-limits
- https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://openrouter.ai/openrouter/free
- https://ai.google.dev/gemini-api/docs/pricing

Çevrimdışı test: `python -m unittest -v tests.test_free_multi_brain`.
