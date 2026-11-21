import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from core import activity, confirm, outcome
from core.lazyimport import LazyModule, installed

# Imported on first USE, not at launch — see core/lazyimport.py. PAUSE is 0.06
# here rather than computer_control's 0.05, as it always was: typing into
# somebody else's chat window wants a little more room than a hotkey does.
_PYAUTOGUI = installed("pyautogui")
_PYPERCLIP = installed("pyperclip")
_SEND_LOCK = threading.Lock()


def _configure_pyautogui(module) -> None:
    module.FAILSAFE = True
    module.PAUSE    = 0.06


pyautogui = LazyModule("pyautogui", _configure_pyautogui)
pyperclip = LazyModule("pyperclip")

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        return "windows"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _paste_text(text: str) -> None:
    _require_pyautogui()

    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")

    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        pyautogui.write(text, interval=0.03)


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(text)

def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()

    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _paste_text(app_name)
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True

        elif os_name == "mac":
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                )
            time.sleep(2.5)
            return result.returncode == 0

        else: 
            launched = False
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            time.sleep(2.5)
            return launched

    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        time.sleep(4.0) 
        return True
    except Exception as e:
        print(f"[SendMessage] ⚠️ Could not open browser: {e}")
        return False

def _search_in_app(query: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    search_hotkey = ("command", "f") if os_name == "mac" else ("ctrl", "f")

    pyautogui.hotkey(*search_hotkey)
    time.sleep(0.5)
    _clear_and_paste(query)
    time.sleep(1.0)

def _desktop_send(app_name: str, receiver: str, message: str) -> str:
    if not _open_app(app_name):
        return outcome.failed(
            "send_message", f"{app_name} could not be opened, so nothing was "
            f"typed and no message was sent",
            platform=app_name, to=receiver,
        )

    time.sleep(1.0)
    _search_in_app(receiver)
    pyautogui.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    # UNVERIFIED, AND THAT IS THE HONEST ANSWER.
    #
    # Everything above is keystrokes with sleeps between them: press Win, type
    # the app name, Ctrl+F, type the contact, Enter, paste, Enter. Nothing
    # reads back which window received any of it. On a machine one second
    # slower than these sleeps assume, the whole sequence lands somewhere else
    # — and the old code still returned "Message sent to X via Y."
    #
    # There is no read-back to add here without a driver per application, and
    # `_send_whatsapp` shows what that costs to build. Until one exists for a
    # given app, the truthful thing is to say the keystrokes went out and the
    # result is unconfirmed, which is something the user can glance at their
    # screen and check.
    return outcome.unverified(
        "send_message",
        f"the message was typed into {app_name} blind - no confirmation is "
        f"available for this app, so it is NOT known to have been sent",
        platform=app_name, to=receiver,
    )

def _send_whatsapp(receiver: str, message: str) -> str:
    if sys.platform != "win32":
        return _desktop_send("WhatsApp", receiver, message)

    from core import whatsapp_receipts as receipts

    facts = {"platform": "WhatsApp", "to": receiver}
    if not _open_app("WhatsApp") or not (window := receipts.foreground_window()):
        return outcome.failed("send_message", "WhatsApp could not be brought to the foreground", **facts)
    _search_in_app(receiver)
    if receipts.foreground_window() != window:
        return outcome.failed("send_message", "WhatsApp lost focus during contact search", **facts)
    pyautogui.press("enter")
    time.sleep(0.8)

    before = receipts.read_conversation(window, receiver, message)
    if before is not None and not before.matches_recipient:
        return outcome.failed("send_message", "the open WhatsApp chat does not match the requested contact", **facts)
    if receipts.foreground_window() != window:
        return outcome.failed("send_message", "WhatsApp lost focus before typing", **facts)
    _paste_text(message)
    time.sleep(0.2)
    if receipts.foreground_window() != window:
        return outcome.failed("send_message", "WhatsApp lost focus before sending", **facts)
    pyautogui.press("enter")

    # A read-back error after pressing Enter must never cause another send.
    try:
        status = receipts.wait_for_receipt(window, receiver, message, before)
    except Exception as exc:
        print(f"[SendMessage] WhatsApp receipt read failed: {type(exc).__name__}")
        status = ""
    if status in {"sent", "delivered", "read"}:
        return outcome.done("send_message", verified=True, receipt=status, **facts)
    if status == "failed":
        return outcome.failed("send_message", "WhatsApp marked the message as failed to send", receipt=status, **facts)
    reasons = {
        "pending": "WhatsApp shows the new message as still sending",
        "visible": "the message text appeared as a new entry in the WhatsApp conversation; no send receipt was visible",
    }
    return outcome.unverified("send_message", reasons.get(status, "WhatsApp did not expose a receipt for this send"),
                              receipt=status or "unknown", **facts)


def _send_telegram(receiver: str, message: str) -> str:
    return _desktop_send("Telegram", receiver, message)

def _send_signal(receiver: str, message: str) -> str:
    return _desktop_send("Signal", receiver, message)


def _send_discord(receiver: str, message: str) -> str:
    return _desktop_send("Discord", receiver, message)


def _send_instagram(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.instagram.com/direct/new/"):
        return outcome.failed(
            "send_message", "Instagram could not be opened in the browser, so "
            "nothing was sent", platform="Instagram", to=receiver)

    _paste_text(receiver)
    time.sleep(1.5)

    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")   
    time.sleep(0.4)

    for _ in range(4):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    time.sleep(2.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return outcome.unverified(
        "send_message",
        "the message was typed into Instagram in the browser blind - the page "
        "was never read back, so it is NOT known to have been sent",
        platform="Instagram", to=receiver)


def _send_messenger(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.messenger.com/"):
        return outcome.failed(
            "send_message", "Messenger could not be opened in the browser, so "
            "nothing was sent", platform="Messenger", to=receiver)


    _search_in_app(receiver)
    time.sleep(0.5)
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    _paste_text(message)
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(0.3)

    return outcome.unverified(
        "send_message",
        "the message was typed into Messenger in the browser blind - the page "
        "was never read back, so it is NOT known to have been sent",
        platform="Messenger", to=receiver)

_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},              _send_whatsapp),
    ({"telegram", "tg"},                      _send_telegram),
    ({"instagram", "ig", "insta"},            _send_instagram),
    ({"signal"},                               _send_signal),
    ({"discord"},                              _send_discord),
    ({"messenger", "facebook", "fb"},         _send_messenger),
]


def _resolve_platform(platform_str: str):
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return lambda r, m: _desktop_send(platform_str.strip().title(), r, m)


def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params       = parameters or {}
    receiver     = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform     = params.get("platform", "whatsapp").strip()

    if not receiver:
        return outcome.failed("send_message", "no recipient was given")
    if not message_text:
        return outcome.failed("send_message", "no message text was given",
                              to=receiver)
    if not _PYAUTOGUI:
        return outcome.failed(
            "send_message",
            "PyAutoGUI is not installed, so the desktop cannot be driven - "
            "run: pip install pyautogui",
            to=receiver, platform=platform,
        )

    detail = f"Platform: {platform}\nAlıcı: {receiver}\nMesaj: {message_text}"
    return confirm.request("send_message", "Mesaj gönderilsin mi?", detail,
                           lambda: _send_and_report(player, platform, receiver, message_text))


def _send_and_report(player, platform: str, receiver: str,
                     message_text: str) -> str:
    """Do the sending, then say what actually happened — including when it did
    not happen, and including when nobody can tell.

    Every path here reports. A tool that says `started` and then goes quiet on
    failure has only moved the false success one step later, which is the whole
    thing this rewrite exists to stop.
    """
    try:
        with _SEND_LOCK:
            result = _resolve_platform(platform)(receiver, message_text)
    except Exception as exc:
        print(f"[SendMessage] {type(exc).__name__}: {exc}")
        result = outcome.failed("send_message", f"it failed: {exc}",
                                to=receiver, platform=platform)

    print(f"[SendMessage] {result[:200]}")
    node = activity.node_for_tool("send_message", {"platform": platform})
    verified = result.startswith(f"status={outcome.DONE} ")
    if node == "whatsapp":
        fields = result.split(maxsplit=4)[2:4]
        if fields[:1] == ["verified=true"]:
            fields = fields[1:]
        receipt = fields[0][8:] if fields and fields[0].startswith("receipt=") else "unknown"
        labels = {
            "sent": "Gönderildi",
            "delivered": "Teslim edildi",
            "read": "Okundu",
            "pending": "Gönderim bekliyor",
            "visible": "Sohbette göründü, WhatsApp onayı görünmüyor",
            "failed": "Gönderilemedi",
            "unknown": "Gönderim doğrulanamadı",
        }
        if receipt == "unknown" and result.startswith(f"status={outcome.FAILED} "):
            receipt = "failed"
        line = f"WhatsApp → {receiver} · {labels.get(receipt, labels['unknown'])}"
        activity.record(node, line, activity.status_of(result), count=False)
        if player:
            player.write_log(f"[msg] {line}")
    elif player and outcome.is_problem(result):
        player.write_log(f"[msg] {receiver} için mesaj gönderimi doğrulanamadı.")

    if player and hasattr(player, "request_say") and (node == "whatsapp" or not verified):
        try:
            player.request_say(
                "Tell the user the result in their language. WhatsApp receipt=sent means sent, "
                "receipt=delivered means delivered, and receipt=read means read. Report only "
                "the observed status and do not send or retry anything: " + result
            )
        except Exception:
            pass

    return result


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "send_message",
    "description": (
        "Sends a text message via WhatsApp, Telegram, or another messaging "
        "platform. Write 'message_text' in the USER'S OWN LANGUAGE, exactly "
        "what they asked to be said. Only send on an explicit request with a recipient and message. "
        "A request to connect or configure messaging does not request a test message. "
        "This tool answers immediately and sends in the background. On "
        "status=started say only that you are sending it, never that it is "
        "sent. The result follows separately. For WhatsApp, status=done carries the exact "
        "receipt: sent, delivered or read. Status=unverified means the send is pending "
        "or a receipt could not be checked. Status=failed means the send failed. "
        "Never claim that a message was delivered unless the receipt confirms it. "
        "Ask the user to review the recipient and full text on the HUD. Only the user can authorize sending."
    ),
    "tier": "core",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "receiver": {
                "type": "STRING",
                "description": "Recipient contact name"
            },
            "message_text": {
                "type": "STRING",
                "description": "The message to send"
            },
            "platform": {
                "type": "STRING",
                "description": "Platform: WhatsApp, Telegram, etc."
            },

        },
        "required": [
            "receiver",
            "message_text"
        ]
    },
    "handler": send_message,
}
