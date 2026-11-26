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
