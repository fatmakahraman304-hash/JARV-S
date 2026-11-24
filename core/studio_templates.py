"""Editable local templates; no information is collected or saved automatically."""
from core.thinking_studio import FEATURES

FIELDS = {
    508: ("Tarih", "Durum", "Kendi gözlemim", "İşe yarayan şey"),
    523: ("Tarih/saat", "Kendi tarifim", "Süre", "Eşlik eden belirtiler", "Doktora sorular"),
    530: ("Fatura", "Son ödeme tarihi", "Tutar ve para birimi", "Durum"),
    540: ("Ürün", "Satın alma tarihi", "Garanti sonu", "Belge konumu"),
    564: ("Tarih", "Yer", "Deneyim", "Hatırlamak istediğim"),
    590: ("Porsiyon", "Malzemeler", "Hazırlama adımları", "Alerjen notları", "Kendi notum"),
    598: ("Tarih", "Yemek", "Beğendiğim", "Değiştireceğim"),
    604: ("Borç türü", "Kalan tutar", "Para birimi", "Vade", "Not"),
    616: ("Tarih", "Gelir/gider", "Kategori", "Tutar", "Belge"),
    684: ("Tarih", "Yer (isteğe bağlı)", "Gözlem", "Belirsizlik"),
    797: ("Tarih", "Eser", "Kendi deneyimim", "Not"),
    903: ("Tarih", "Bugünkü önemli olay", "Düşünce", "Sonraki adım"),
    910: ("Tarih", "Etkinlik", "İsteğe bağlı not"),
    912: ("Proje", "Ne oldu", "Ne öğrendim", "Sonraki deneme"),
    918: ("Tarih veya dönem", "Anı", "Kendi yorumum"),
    920: ("Kitap", "Yazar", "Kendi notlarım", "Açık sorular"),
}


def draft(n):
    fields = FIELDS[n]
    return {"kind": "note", "title": FEATURES[n][0], "tags": f"mod-{n}",
            "body": "\n\n".join(f"{field}: " for field in fields)}
