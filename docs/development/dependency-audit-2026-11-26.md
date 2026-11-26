# Python bağımlılık denetimi

Linux, Python 3.13.5. İlk pip-audit koşusunda cryptography 49.0.0 için 2,
Pillow 12.3.0 için 42, PyPDF2 3.0.1 için 1 bilinen güvenlik kaydı döndü.
requirements.txt ve bulut kurulumu güncellendi. PDF yedek okuyucusu pypdf
kullanıyor. İzole temiz kurulum cryptography 50.0.2, Pillow 13.0.0 ve
pypdf 7.1.1 seçti. 103 kurulu dağıtımda uv pip check başarılı oldu ve
pip-audit aynı gün bilinen açık döndürmedi. Bu sonuç danışma veritabanına,
tarihe ve taranan kurulu dağıtımlara bağlıdır. Sistem, Qt ve tarayıcı
ikili dosyalarının tamamına veya başka platformlara genellenemez.

Gerçek PDF'nin metni pdfplumber devre dışıyken FRIDAY dosya işleyicisinden
geçerek UTF-8 dosyasına yazıldı. İmza, görsel, Android render ve güncelleyici
testlerinde 54 test geçti. Yeni veya güncel ortamla önceki sürümün tüm
bağımlılıklarını karşılaştırmak için:

```text
uv pip check --python <ortam-python>
pip-audit --path <ortam-site-packages>
python tools/release_package.py inventory --out <yeni-klasör>
```

Lisans envanteri değişen üç dağıtımda dosya buldu. Metadata beyanları
cryptography için Apache-2.0 OR BSD-3-Clause, Pillow için MIT-CMU ve pypdf
için BSD-3-Clause. 103 dağıtımdan 10'unda araç lisans dosyası bulamadı:
et_xmlfile, gradio_client, MouseInfo, nvidia-ml-py, openpyxl, primp,
PyGetWindow, pypdfium2, python3-xlib ve tqdm. Kaynak depolar ve ikili
dağıtımlar için ayrıca inceleme gerekiyor.

## Kurulum ve yükseltme

Bu sürüm bağımlılık değiştirir. Mevcut GÜNCELLE, çalışan Qt/ses sürecinde
pip çalıştırmadan önce durur. Yeni sürümün kaynak paketini ayrı klasöre
açarak FRIDAY kapalıyken setup.py ile kurun. Eski kurulum ve kişisel
veriler geri dönüş için korunmalıdır. Mevcut sanal ortamda yeniden pip
kurulumu kullanımdan kalkan PyPDF2 paketini otomatik kaldırmaz.

Windows kaynak ZIP'inde FRIDAY_BASLAT.cmd ilk çalıştırmada yerel .venv
kurar, setup.py ve pip check sonucunu doğrular. Sonraki çift tıklamada
pythonw ile FRIDAY açılır. --install-only CI ve kapalı uygulamayla yeniden
kurulum için aynı yolu kullanır. Python 3.13 ve ilk kurulumda internet gerekir.

### Mevcut verilerle yerinde geçiş

Eski istemcide GÜNCELLE bağımlılık değişikliği bildirirse FRIDAY'i kapatın.
Aşağıdaki PowerShell örneğinde komutları doğrulanmış yeni paketin açıldığı
klasörden çalıştırın. Hedef klasör adı kendi mevcut kurulumunuza ait olmalı.
Önceki Python ortamına dönebilmek için kapalıyken .venv yedeğini alın.
Kullanıcı ayarlarını veya hafızayı yeni klasöre kopyalamak gerekmez.

```powershell
$fridayDir = 'C:\FRIDAY'
$fridayPython = Join-Path $fridayDir '.venv\Scripts\python.exe'
& $fridayPython .\setup.py
if ($LASTEXITCODE -ne 0) { throw 'Bağımlılık kurulumu durdu.' }
& $fridayPython -m tools.update_prepared_install $fridayDir
if ($LASTEXITCODE -ne 0) { throw 'Güncelleme tamamlanmadı.' }
```

Bakım komutu hedefin kendi .venv ortamını, gerçek pip çözücüsünün kuracak
paket bulmadığını ve pip check sonucunu doğrular. Ardından mevcut kurulumda
aynı Git/ZIP yedek, imza ve güncelleme yollarını kullanır. Gelen bağımlılıklar
hazırlanan sürümle uyuşmazsa dosya yazılmaz. Uygulamayı mevcut konumundan
yeniden açın. Depoda .venv kullanmayan özel kurulumlar bu komuta dahil değildir.
