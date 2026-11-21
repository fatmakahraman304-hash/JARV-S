"""Gemini Live ses dökümü parçalarını güvenle birleştirme.

Live API giriş konuşmasını bazen artan (kümülatif), bazen bağımsız metin
parçalarıyla yayınlar. Her parçayı koşulsuz eklemek kullanıcı cümlesini
tekrarlayabilir ("ışığı aç ışığı aç"). Bu işlem yalnızca metin dökümünün
günlüğünü ve komut güvenlik kontrolünü iyileştirir; akustik tanımayı değiştirmez.
"""
from __future__ import annotations

import re


def _tokens(text: str) -> list[str]:
    return [w.casefold() for w in re.findall(r"[^\W_]+", text, re.UNICODE)]


def merge_input_chunk(chunks: list[str], text: str) -> list[str]:
    """Giriş ses dökümündeki yinelenen veya örtüşen parçaları birleştir.

    Gerçek tekrarları koru: "evet, evet" gibi tek kelimeli yeni parçalar
    otomatik olarak silinmez. Birden fazla kelimelik kümülatif güncellemeler
    ise tekrar kaydedilmez. Girdi listesini yerinde değiştirmez.
    """
    incoming = " ".join(str(text or "").split())
    if not incoming:
        return list(chunks)
    if not chunks:
        return [incoming]
    out = list(chunks)
    current = " ".join(out)
    incoming_words = _tokens(incoming)
    current_words = _tokens(current)
    previous_words = _tokens(out[-1])

    # "MAYK" gibi tek kelimelik bir kısmi dökümün ardından tüm cümle
    # gelirse adı iki defa yazma. "evet, evet" gibi doğal tekrarları koru.
    if (len(current_words) == 1 and len(incoming_words) > 1
            and incoming_words[0] == current_words[0]
            and current_words[0] not in {"evet", "hayir", "hayır", "tamam", "yok", "var"}):
        return [incoming]

    # Servis önce tamamını, ardından düzeltilmiş/uzatılmış tamamını yayınladı.
    # Sadece kelime sınırında uzama kabul et; birbirine benzeyen tek kelimeleri
    # ("ev", "evet") yanlışlıkla birleştirme.
    if (len(current_words) >= 2 and len(incoming_words) > len(current_words)
            and incoming_words[:len(current_words)] == current_words):
        return [incoming]
    if len(incoming_words) >= 2 and incoming_words == current_words:
        return out
    if (len(previous_words) >= 2 and len(incoming_words) > len(previous_words)
            and incoming_words[:len(previous_words)] == previous_words):
        out[-1] = incoming
        return out
    if len(previous_words) >= 2 and incoming_words == previous_words:
        return out

    # Art arda iki parçanın son/ilk kelimeleri çakışıyorsa yalnızca ortak
    # kısmı bir kez yaz. Tek sözcüklük tekrarları ("evet, evet") koru.
    for count in range(min(len(previous_words), len(incoming_words)), 0, -1):
        if previous_words[-count:] != incoming_words[:count]:
            continue
        if count == len(incoming_words):
            if len(incoming_words) >= 2:
                return out
            break
        if len(previous_words) < 2 or len(incoming_words) < 2:
            break
        # Noktalama veya kesme işaretinden dolayı "Spotify'ı" iki
        # sözlük tokenı olabilir. Sözcük sınırlarını orijinal yazıdan bul.
        spans = list(re.finditer(r"[^\W_]+", incoming, re.UNICODE))
        if len(spans) != len(incoming_words):
            break
        tail = incoming[spans[count - 1].end():].strip(" \t,.;:!?")
        if tail:
            out.append(tail)
        return out
    out.append(incoming)
    return out


def combined_text(chunks: list[str]) -> str:
    return " ".join(chunks).strip()
