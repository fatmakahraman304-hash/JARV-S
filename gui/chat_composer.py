"""Insert plain text in supported, visible web chat composers."""

import json

from core.social_sites import CHAT_HOSTS, CHAT_DRAFT_LIMIT

_SELECTORS = {
    "chatgpt": ('#prompt-textarea[contenteditable="true"]', 'textarea#prompt-textarea'),
    "claude": (
        'div.ProseMirror[contenteditable="true"][role="textbox"]',
        'div.ProseMirror[contenteditable="true"][data-placeholder]',
        'fieldset div.ProseMirror[contenteditable="true"]',
    ),
}


def composer_script(site, draft):
    if site not in _SELECTORS or not draft.strip() or len(draft) > CHAT_DRAFT_LIMIT:
        raise ValueError("Geçersiz sohbet taslağı")
    arguments = json.dumps([sorted(CHAT_HOSTS[site]), _SELECTORS[site], draft])
    return r"""
(([hosts, selectors, draft]) => {
    if (location.protocol !== 'https:' || (location.port && location.port !== '443') ||
        !hosts.includes(location.hostname)) return 'wrong-page';
    const candidates = new Set(selectors.flatMap(selector =>
        Array.from(document.querySelectorAll(selector))
    ));
    const visible = Array.from(candidates).filter(el => {
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 &&
            getComputedStyle(el).visibility === 'visible' &&
            !el.closest('[hidden], [inert], [aria-hidden="true"], [aria-disabled="true"]') &&
            !el.disabled && !el.readOnly;
    });
    if (visible.length !== 1) return 'no-composer';
    const editor = visible[0];
    editor.focus();
    if (document.activeElement !== editor) return 'no-composer';
    const isField = editor instanceof HTMLTextAreaElement;
    const previous = isField ? editor.value : editor.innerText;
    const text = (previous.trim() ? '\n' : '') + draft;
    if (isField) {
        editor.setSelectionRange(editor.value.length, editor.value.length);
    } else {
        const range = document.createRange();
        range.selectNodeContents(editor);
        range.collapse(false);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
    }
    document.execCommand('insertText', false, text);
    const current = isField ? editor.value : editor.innerText;
    return current !== previous ? 'inserted' : 'no-change';
})
""" + "(" + arguments + ")"
