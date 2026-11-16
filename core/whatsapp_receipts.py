"""Read WhatsApp Desktop's Windows accessibility tree without changing the chat."""
from collections import deque
from dataclasses import dataclass
import re
import time
import unicodedata


_RECEIPTS = {
    "sent": "sent", "gönderildi": "sent", "msg-check": "sent",
    "delivered": "delivered", "teslim edildi": "delivered", "msg-dblcheck": "delivered",
    "read": "read", "okundu": "read",
    "pending": "pending", "sending": "pending", "gönderiliyor": "pending", "msg-time": "pending",
    "failed to send": "failed", "couldn't send": "failed", "gönderilemedi": "failed",
    "msg-error": "failed",
}
_SELF = {"kendim", "kendime", "me", "myself", "you", "siz", "sen"}
_SELF_SUFFIX = re.compile(r"\s*\((?:you|siz|sen|kendim)\)$")
_COMPOSER = {"type a message", "mesaj yaz", "mesaj yazın", "bir mesaj yazın", "bir mesaj yaz"}
_DIRECTION = re.compile(r"^(?:you|siz|sen): ", re.IGNORECASE)


def _text(value: str) -> str:
    value = unicodedata.normalize("NFC", value or "")
    return " ".join(value.translate(dict.fromkeys(map(ord, "\u200e\u200f\u200b\u2066\u2067\u2068\u2069"))).split())


@dataclass
class Node:
    name: str
    kind: str
    key: str
    parent: int
    y: int
    bottom: int


@dataclass
class Conversation:
    matches_recipient: bool
    messages: dict[tuple[int, ...], str]


def foreground_window() -> int | None:
    from core.screenview import _foreground_windows

    process, _title, _pid, handle = _foreground_windows()
    if process.casefold() in {"whatsapp.exe", "whatsapp.root.exe", "whatsappdesktop.exe"}:
        return handle
    return None


def _walk(root, deadline):
    queue = deque([(root, -1)])
    index = 0
    while queue and index < 1600:
        if time.monotonic() >= deadline:
            raise TimeoutError("WhatsApp accessibility scan timed out")
        node, parent = queue.popleft()
        yield node, parent
        queue.extend((child, index) for child in node.children(cache_enable=True))
        index += 1
    if queue:
        raise TimeoutError("WhatsApp accessibility tree exceeded the scan limit")


def _receipt(nodes: list[Node], parents: list[list[int]], index: int) -> str:
    body = nodes[index]
    parent = body.parent
    branch = index
    for _ in range(5):
        if parent <= 0:
            break
        # Inspect this message's nearby accessibility labels, not the whole chat.
        queue = deque((pos, pos == branch) for pos in parents[parent])
        labels = set()
        for _ in range(40):
            if not queue:
                break
            pos, inside_message = queue.popleft()
            node = nodes[pos]
            if node.y > body.bottom + 45 or node.bottom < body.y - 10:
                continue
            if not inside_message and node.kind in {"ListItem", "DataItem"}:
                continue
            if pos != index and node.kind not in {"Edit", "Hyperlink", "Button"}:
                status = _RECEIPTS.get(node.key.casefold()) or _RECEIPTS.get(node.name.casefold())
                if status:
                    labels.add(status)
            queue.extend((child, inside_message) for child in parents[pos])
        if len(labels) == 1:
            return labels.pop()
        if labels or nodes[parent].kind in {"ListItem", "DataItem"}:
            break
        branch, parent = parent, nodes[parent].parent
    return ""


def _conversation(nodes: list[Node], runtime_ids, receiver: str, message: str) -> Conversation | None:
    if not nodes:
        return None
    composer = next((node for node in reversed(nodes) if node.kind == "Edit" and
                     (node.name.casefold() in _COMPOSER or node.key.casefold() == "inputbox")), None)
    if composer is None:
        return None
    target = _text(receiver).casefold()

    def matches_title(node):
        label = node.name.casefold()
        if target in _SELF:
            return label in _SELF or bool(_SELF_SUFFIX.search(label))
        return _SELF_SUFFIX.sub("", label) == target

    header = next((node for node in nodes[1:] if node.kind in {"Text", "Button", "Header", "Group"}
                   and node.bottom > node.y and nodes[0].y <= node.y <= nodes[0].y + 110
                   and matches_title(node)), None)
    if header is None:
        return Conversation(False, {})
    children = [[] for _ in nodes]
    for index, node in enumerate(nodes):
        if node.parent >= 0:
            children[node.parent].append(index)
    candidates = {}
    body = _text(message)
    for index, node in enumerate(nodes):
        if (node.kind not in {"Text", "ListItem", "DataItem", "Group"}
                or node.y < header.bottom or node.bottom > composer.y or node.bottom <= node.y):
            continue
        outgoing = _DIRECTION.match(node.name) and _DIRECTION.sub("", node.name, count=1) == body
        if node.name == body or outgoing:
            candidates[index] = bool(outgoing)
    # A single bubble can expose the text on both its wrapper and a child.
    wrappers = set()
    for index in candidates:
        parent = nodes[index].parent
        while parent > 0:
            if parent in candidates:
                wrappers.add(parent)
                candidates[index] |= candidates[parent]
            parent = nodes[parent].parent
    matches = {}
    for index, outgoing in candidates.items():
        if index in wrappers:
            continue
        status = _receipt(nodes, children, index)
        identifier = runtime_ids(index)
        if identifier:
            matches[identifier] = status or ("visible" if outgoing else "matching_text")
    return Conversation(True, matches)


def read_conversation(window: int, receiver: str, message: str) -> Conversation | None:
    """Observe only the selected conversation. None means the UI is unreadable."""
    try:
        import comtypes
        from pywinauto.uia_defines import IUIA
        from pywinauto.uia_element_info import UIAElementInfo

        if foreground_window() != window:
            return None
        comtypes.CoInitializeEx()
        try:
            root = UIAElementInfo(window)
            automation = IUIA()
            for key in ("main", "ConversationPanel"):
                condition = automation.iuia.CreatePropertyCondition(
                    automation.UIA_dll.UIA_AutomationIdPropertyId, key)
                pane = root.element.FindFirst(automation.UIA_dll.TreeScope_Descendants, condition)
                if pane:
                    break
            else:
                return None
            nodes = []
            elements = []
            for element, parent in _walk(UIAElementInfo(pane, cache_enable=True), time.monotonic() + 2):
                rect = element.rectangle
                nodes.append(Node(_text(element.name), element.control_type, element.auto_id,
                                  parent, rect.top, rect.bottom))
                elements.append(element)
            return _conversation(nodes, lambda index: tuple(elements[index].element.GetRuntimeId()),
                                 receiver, message)
        finally:
            comtypes.CoUninitialize()
    except Exception:
        return None


def wait_for_receipt(window, receiver, message, before, *, timeout=8.0) -> str:
    """Require a new matching row in this chat before trusting a receipt."""
    if before is None or not before.matches_recipient:
        return ""
    deadline = time.monotonic() + timeout
    best = ""
    while time.monotonic() < deadline and foreground_window() == window:
        after = read_conversation(window, receiver, message)
        if after and after.matches_recipient and len(after.messages) > len(before.messages):
            new = {key: value for key, value in after.messages.items() if key not in before.messages}
            if len(new) == 1:
                status = next(iter(new.values()))
                if status in {"delivered", "read", "failed"}:
                    return status
                if status == "sent" or (status in {"pending", "visible"} and best != "sent"):
                    best = status
        time.sleep(0.4)
    return best
