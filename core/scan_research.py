"""Research a user-selected scan item and prepare HUD reading pages."""

import re
import textwrap
import unicodedata
from urllib.parse import urlsplit

import httpx


def _words(text):
    return tuple(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold()))


def _gutenberg(title, author):
    response = httpx.get("https://gutendex.com/books/", params={"search": f"{title} {author}".strip()},
                         timeout=7, follow_redirects=False)
    response.raise_for_status()
    matches = []
    for book in response.json().get("results", []):
        if book.get("copyright") is not False or _words(book["title"]) != _words(title):
            continue
        if author and not any(set(_words(author)) <= set(_words(a["name"])) for a in book["authors"]):
            continue
        matches.append(book)
    if len(matches) != 1:
        return []
    ebook = matches[0]["id"]
    if type(ebook) is not int or ebook <= 0:
        return []
    with httpx.stream("GET", f"https://www.gutenberg.org/cache/epub/{ebook}/pg{ebook}.txt",
                      timeout=10, follow_redirects=False) as response:
        response.raise_for_status()
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 4_000_000:
                return []
    text = raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
    start = re.search(r"(?m)^\*\*\* START OF .*\*\*\*[ \t]*$", text)
    end = re.search(r"(?m)^\*\*\* END OF .*\*\*\*[ \t]*$", text)
    if not start or not end or start.end() >= end.start():
        return []
    body = text[start.end():end.start()].strip()
    pages = textwrap.TextWrapper(width=1800, replace_whitespace=False, expand_tabs=False)
    address = f"https://www.gutenberg.org/ebooks/{ebook}"
    return [("Project Gutenberg · Açık metin (ABD kamu malı)", page.strip(), address)
            for page in pages.wrap(body)]


def research(subject, author="", book=True):
    from actions.web_search import _ddg_search

    query = " ".join(part for part in (subject, author, "kitap" if book else "") if part)
    pages = []
    try:
        results = _ddg_search(query, max_results=5)
    except Exception:
        results = []
    for result in results:
        address = result.get("url", "")
        try:
            parsed = urlsplit(address)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
                continue
        except ValueError:
            continue
        snippet = result.get("snippet", "")
        if isinstance(snippet, str) and snippet.strip():
            heading = str(result.get("title") or parsed.hostname)[:150]
            pages.append(("Web araştırması · " + heading,
                          snippet.strip()[:1250], address))
    if book:
        try:
            pages.extend(_gutenberg(subject, author))
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            pass
    return pages
