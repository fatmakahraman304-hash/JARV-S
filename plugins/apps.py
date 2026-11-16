"""Use 1000+ apps (Gmail, Google Calendar/Drive/Docs/Sheets, Notion, Slack, …)
through Composio.

Three steps the model follows, all through this one tool:
  1. action='search' with a plain description of the task → the matching tool
     slugs, their inputs (required ones marked *), and whether the app is
     connected.
  2. If the app is not connected: action='connect' with the toolkit → its login
     page opens in the user's browser; they sign in once.
  3. action='run' with tool_slug and arguments (a JSON object as text) → the
     real result, or the real error.

The key is entered once in Settings → Bağlantılar → Uygulamalar (free Composio
Hobby plan). Results are facts for the model (core.outcome), never prose.
"""
import json
import webbrowser

from core import outcome

PLUGIN = {
    "name": "apps",
    "description": (
        "Act in the user's online apps through Composio: Gmail, Google Calendar, Google Drive, "
        "Google Docs, Google Sheets, Notion, Slack, Trello, Todoist, Outlook, Dropbox, HubSpot, "
        "and 1000+ more. Read and send email, create calendar events, make docs and sheets, "
        "save files to Drive, post to apps. Always: first action='search' with use_case "
        "describing the task (e.g. 'create a Google Calendar event tomorrow 18:30'); it returns "
        "tool slugs with their inputs (* = required) and whether the app is connected. If not "
        "connected, call action='connect' with toolkit (e.g. 'gmail') and tell the user to sign "
        "in on the page that opened, then search again. Then action='run' with tool_slug and "
        "arguments as a JSON object string. Use action='connected' to list connected apps. "
        "Before sending email, posting publicly or deleting anything, confirm with the user. "
        "Not for WhatsApp/Telegram messages (send_message) or local files (file_controller)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "description": "'search', 'connect', 'run' or 'connected'."},
            "use_case": {"type": "STRING",
                         "description": "For search: the task in plain words."},
            "toolkit": {"type": "STRING",
                        "description": "For connect: app slug such as gmail, googlecalendar, "
                                       "googledrive, googledocs, googlesheets, notion, slack."},
            "tool_slug": {"type": "STRING",
                          "description": "For run: the exact slug from search, e.g. GMAIL_SEND_EMAIL."},
            "arguments": {"type": "STRING",
                          "description": "For run: the tool's inputs as a JSON object string."},
        },
        "required": ["action"],
    },
}


def _log(player, text: str) -> None:
    try:
        if player is not None:
            player.write_log(text)
    except Exception:
        pass


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from core import composio
    except Exception as exc:
        return outcome.failed("apps", f"Composio module unavailable: {exc}")
    p = parameters or {}
    action = str(p.get("action") or "").strip().lower()
    if not composio.is_configured():
        return outcome.failed(
            "apps", "no Composio API key yet",
            fix="user opens Settings → Bağlantılar → Uygulamalar, creates a free key at "
                "composio.dev and pastes it there")
    try:
        if action == "search":
            use_case = str(p.get("use_case") or "").strip()
            if not use_case:
                return outcome.failed("apps", "use_case is empty")
            r = composio.search(use_case)
            tools = " | ".join(f"{t['slug']} ({t['toolkit']}): {t['description'][:100]} "
                               f"inputs: {t['inputs']}" for t in r["tools"]) or "none found"
            conns = ", ".join(f"{c['toolkit']}={'connected' if c['connected'] else 'NOT connected'}"
                              for c in r["connections"]) or "unknown"
            return outcome.done("apps", tools=tools, connections=conns,
                                guidance=r["guidance"][:400] or "-")
        if action == "connect":
            toolkit = str(p.get("toolkit") or "").strip().lower()
            if not toolkit:
                return outcome.failed("apps", "toolkit is empty")
            url = composio.link(toolkit)
            if not url:
                return outcome.done("apps", toolkit=toolkit, already_connected=True)
            opened = False
            try:
                opened = webbrowser.open(url)
            except Exception:
                opened = False
            _log(player, f"SYS: {toolkit} bağlantısı için giriş sayfası açıldı — {url}")
            if not opened:
                return outcome.unverified("apps", "could not open the browser", toolkit=toolkit,
                                          login_url=url)
            return outcome.done("apps", toolkit=toolkit, login_page_opened=True,
                                next="user signs in on the page, then search again")
        if action == "run":
            slug = str(p.get("tool_slug") or "").strip()
            if not slug:
                return outcome.failed("apps", "tool_slug is empty")
            raw = p.get("arguments") or "{}"
            try:
                args = raw if isinstance(raw, dict) else json.loads(str(raw))
                if not isinstance(args, dict):
                    raise ValueError
            except ValueError:
                return outcome.failed("apps", "arguments is not a JSON object", tool=slug)
            r = composio.execute(slug, args)
            if not r["ok"]:
                return outcome.failed("apps", r["error"] or "the app returned an error", tool=slug)
            return (outcome.done("apps", tool=slug) + "\n"
                    + outcome.untrusted(f"{slug} result", composio.compact(r["data"], 2500)))
        if action == "connected":
            items = composio.toolkits(connected_only=True)
            names = ", ".join(t["slug"] for t in items if t["connected"]) or "none"
            return outcome.done("apps", connected=names)
        return outcome.failed("apps", f"unknown action '{action}'")
    except Exception as exc:                      # a plugin never raises
        return outcome.failed("apps", str(exc)[:200])
