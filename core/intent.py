"""What kind of thing did the user just say?

The voice model decides on its own whether to call a tool; this module is the
safety net under that decision. A tool that changes something (installs, builds,
sends, deletes) asks `kind(text)` first, and when the words are a question about
the state of things ("Blender'ı yükledin mi?"), a how-to question, a "what if"
("ileride ev istesem nasıl yapar?") or plain chat, it does not act — it answers
what was asked instead.

Kinds:
    task        — a command: "duvar yap", "Blender'ı kur", "make it red"
    feedback    — a verdict on the last result: "beğenmedim", "olmamış", "güzel olmuş"
    status      — a question about state: "yükledin mi?", "bitti mi?", "is it done?"
    how         — "nasıl yapılır?", "how do I …?" (wants an explanation, not the act)
    hypothetical— "ileride … istesem", "if I asked …", "yapabilir mi?" (capability)
    chat        — greetings, thanks, feelings, opinions, small talk
"""
from __future__ import annotations

import re
import unicodedata


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").replace("İ", "i").replace("I", "ı").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.replace("ı", "i")).strip()


# Turkish verbs take the question particle mı/mi/mu/mü (after normalisation: mi/mu)
_Q_PARTICLE = r"\b(mi|mu|misin|musun|miyim|miyiz|midir|mudur|mi ki|miydi|muydu|misiniz|musunuz)\b"
_STATUS = re.compile(
    r"(\b(yukledin|kurdun|yaptin|bitirdin|actin|kaydettin|gonderdin|indirdin|ogrendin|bitti|tamamlandi|hazir|calisiyor|"
    r"oldu|yuklendi|kuruldu|indi|basladi|durdu|acildi|kapandi|var|devam ediyor|guncelledin|kontrol ettin|test ettin|duzelttin|calistirdin|baslattin|tamamladin|sildin|tasidin)\w*\s+" + _Q_PARTICLE + r")"
    r"|\b(ne durumda|ne asamada|nerede kaldi|ne zaman biter|ne kadar kaldi|durum ne|durumu ne)\b"
    r"|\b(is it done|did you|have you|is it (ready|installed|finished|running)|what'?s the status|how far)\b")
_HOW = re.compile(r"\b(nasil (yapilir|yaparim|yapabilirim|yapiyorsun|olur|calisir|kullanilir|acilir|kurulur)|"
                  r"ne ise yarar|nedir|ne demek|nasil bir sey|how (do|can|does|to)|what is|what does)\b")
_HYPO = re.compile(r"\b(ileride|ilerde|bir gun|istesem|desem|dersem|yapsam|olsa|olursa|olsaydi|acaba|"
                   r"yapabilir mi|yapar mi|becerebilir mi|mumkun mu|if i (asked|said|wanted)|"
                   r"would you be able|could you ever|is it possible)\b")
_FEEDBACK = re.compile(r"\b(begenmedim|begendim|olmamis|olmus|guzel olmus|kotu olmus|yanlis olmus|harika olmus|"
                       r"super olmus|tam istedigim|istedigim gibi degil|boyle olmaz|bu olmadi|"
                       r"yanlis anladin|beni yanlis anladin|yanlis duydun|oyle demedim|"
                       r"bunu demedim|ben oyle demedim|beni anlamiyorsun|beni yanlis anliyorsun|"
                       r"anlamadin|yanlis anliyorsun|"
                       r"i don'?t like|you misunderstood|that's not what i said|looks (good|bad))\b")
_CHAT = re.compile(r"^(selam|merhaba|naber|nasilsin|gunaydin|iyi aksamlar|iyi geceler|tesekkur(ler)?|sagol|"
                   r"eyvallah|tamam|peki|anladim|harika|super|evet|hayir|hi|hello|thanks|thank you|ok|okay)\b")
_COMMAND_END = re.compile(r"\b(yap|kur|ac|kapat|sil|ekle|cikar|degistir|getir|goster|gonder|kaydet|indir|yukle|baslat|"
                          r"durdur|dur|iptal et|iptal|vazgec|olustur|ciz|render al|tasi|buyut|kucult|boya|cevir|uygula|ogren|ogret|"
                          r"yapin|kurun|acin|silin|ekleyin|gelistir|duzelt|hazirla|bul|ara|yaz|oku|cal|"r"kontrol et|test et|guncelle|incele|duzenle|arastir|listele|acikla|ozetle|yeniden baslat|"
                          r"make|build|create|install|open|close|delete|remove|add|change|show|send|save|render|start|stop|"
                          r"fix|move|paint|draw)\b[^?]*[.!]?$")


# a polite request is a command: "yapar mısın?", "kurabilir misin?", "lütfen …", "can you …"
_POLITE = re.compile(r"\b\w+(ar|er|ir|ur|abilir|ebilir|iver|ıver) (misin|musun|misiniz|musunuz)\b|\blutfen\b|\brica (etsem|ediyorum)\b|"
                     r"^(can|could|would|will) you\b|\bplease\b")


def kind(text: str) -> str:
    t = _norm(text)
    if not t:
        return "chat"
    question = t.endswith("?") or re.search(_Q_PARTICLE + r"\s*\??$", t) is not None
    if _STATUS.search(t) and (question or "durum" in t or "status" in t):
        return "status"
    strong = re.search(r"\b(istesem|desem|dersem|yapsam|soylesem|olsaydi|ileride|ilerde|if i (asked|said|wanted))\b", t)
    if strong:
        return "hypothetical"
    if _POLITE.search(t) and not _STATUS.search(t):
        return "task"
    if _HYPO.search(t) and not re.search(r"\b(simdi|hemen|now)\b", t):
        return "hypothetical"
    if _HOW.search(t) and (question or t.startswith(("nasil", "how", "what"))):
        return "how"
    if _FEEDBACK.search(t) and not _COMMAND_END.search(t):
        return "feedback"
    if _COMMAND_END.search(t) and not question:
        return "task"
    if _CHAT.search(t) and len(t.split()) <= 4:
        return "chat"
    if question:
        return "status" if _STATUS.search(t) else "how" if _HOW.search(t) else "chat"
    return "task"


ACTS = {"task", "feedback"}


def should_act(text: str) -> bool:
    """Only commands and corrections change things; questions and chat get an answer."""
    return kind(text) in ACTS


def not_a_command(text: str, status: str = "") -> str:
    """What a tool tells the model when it was called for something that is not a command."""
    k = kind(text)
    what = {"status": "a question about the current state", "how": "a question about HOW something is done",
            "hypothetical": "a hypothetical / capability question", "chat": "conversation"}.get(k, "not a command")
    return (f"NOT EXECUTED: the user's words were {what}, not a request to do it now. Answer them in their language"
            + (f" — current state: {status}" if status else "") + ". Do it only if they then ask for it.")


# tools (or tool actions) that only look — they may answer any kind of question
_LOOK_NAME = re.compile(r"(search|recall|weather|time|clock|date|status|screen|read|get_|list|find|look|check|info|news|"
                        r"translat|calc|describe|inspect|query|web|memory|vision|camera|explain|define|knowledge|"
                        r"lookup|fetch|price|stock|currency|wiki|summar|scan_research|capabilit|help)", re.I)
_LOOK_ACTIONS = {"status", "list", "inspect", "info", "get", "read", "search", "guide", "lessons", "knowledge",
                 "preview", "show", "help", "query", "find", "check", "describe", "explain", "history", "state",
                 "errors", "logs", "report"}


def is_read_only(name: str, args: dict | None = None) -> bool:
    """A tool call that only looks. An explicit action decides first (todo_list action=add changes
    things, blender_studio action=status only looks); without one, the tool's name does."""
    if name == "studio_utilities":
        return True
    args = args or {}
    for key in ("action", "mode", "op", "command"):
        v = str(args.get(key) or "").lower().strip()
        if v:
            return v in _LOOK_ACTIONS
    return bool(_LOOK_NAME.search(name or ""))


def guard(name: str, args: dict, said: str) -> str:
    """For every tool call: '' when it may run; NOT EXECUTED when the user's words were a status question,
    a how-to question or a hypothetical and the tool would change something."""
    if not said or is_read_only(name, args):
        return ""
    if kind(said) in ("status", "how", "hypothetical"):
        return not_a_command(said)
    return ""
