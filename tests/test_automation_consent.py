"""Generic input uses a single-use HUD decision bound to the reviewed target."""
import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

with patch("importlib.util.find_spec", return_value=object()):
    from actions import browser_control as browser
from actions import computer_control as computer
from core import confirm


class Consent(unittest.TestCase):
    def setUp(self):
        self.show = Mock()
        self.ended = threading.Event()
        self.enterContext(patch.object(confirm, "_pending", None))
        self.enterContext(patch.object(confirm, "_show_cb", self.show))
        self.enterContext(patch.object(confirm, "_hide_cb", None))
        self.enterContext(patch.object(confirm, "_log_cb", lambda msg: self.ended.set() if "Awaiting" not in msg else None))

    def approve(self):
        token = self.show.call_args.args[-1]
        confirm.resolve(True, "model-made-token")
        confirm.resolve(True, token)
        self.assertTrue(self.ended.wait(2))
        confirm.resolve(True, token)  # single use


class BrowserConsent(Consent):
    def setUp(self):
        super().setUp()
        self.page = object()
        self.state = (self.page, "https://example.invalid/review", "dom-and-input-digest")
        self.snapshot = self.enterContext(patch.object(browser, "_page_snapshot", new=AsyncMock(return_value=self.state)))
        self.dispatch = self.enterContext(patch.object(browser, "_browser_control", return_value="status=unverified action=browser_control"))
        self.registry = self.enterContext(patch.object(browser, "_registry"))
        self.session = Mock()
        self.session.run.side_effect = asyncio.run
        self.registry.get.return_value = self.session
        self.registry.pop_native_url.return_value = ""

    def request(self, **extra):
        params = {"action": "fill_form", "fields": {"#field": "reviewed"}, "confirmed": True} | extra
        self.assertIn("CONFIRMATION_PENDING", browser.browser_control(params))
        self.dispatch.assert_not_called()
        return params

    def test_model_flags_cannot_authorize_and_nested_request_is_frozen(self):
        params = self.request()
        params["fields"]["#field"] = "changed"
        self.approve()
        self.dispatch.assert_called_once()
        self.assertEqual(self.dispatch.call_args.args[0]["fields"]["#field"], "reviewed")
        self.assertIs(self.dispatch.call_args.kwargs["_session"], self.session)

    def test_changed_page_or_live_input_cancels_dispatch(self):
        self.request()
        self.snapshot.return_value = (self.page, self.state[1], "changed input or DOM")
        self.approve()
        self.dispatch.assert_not_called()

    def test_replaced_page_with_same_url_and_content_cancels_dispatch(self):
        self.request()
        self.snapshot.return_value = (object(), self.state[1], self.state[2])
        self.approve()
        self.dispatch.assert_not_called()

    def test_headless_and_cancel_do_not_dispatch(self):
        with patch.object(confirm, "_show_cb", None):
            browser.browser_control({"action": "click", "text": "Pay", "confirmed": True})
        self.dispatch.assert_not_called()
        self.request()
        confirm.resolve(False, self.show.call_args.args[-1])
        self.dispatch.assert_not_called()

    def test_every_generic_browser_input_uses_gate(self):
        for action in browser._INPUT_ACTIONS:
            with self.subTest(action=action), patch.object(browser, "_request_browser_input", return_value="pending") as gate:
                self.assertEqual(browser.browser_control({"action": action, "confirmed": True}), "pending")
                gate.assert_called_once()


class DesktopConsent(Consent):
    def setUp(self):
        super().setUp()
        self.state = (123, "editor", "Reviewed window", (0, 0, 500, 400), "digest", (((10, 10, 40, 20), True),))
        self.snapshot = self.enterContext(patch.object(computer, "_desktop_snapshot", return_value=self.state))
        self.focus = self.enterContext(patch.object(computer, "_focus_window"))
        self.dispatch = self.enterContext(patch.object(computer, "_computer_control", return_value="delivered"))

    def request(self, **extra):
        params = {"action": "click", "x": 30, "y": 40, "confirmed": True} | extra
        self.assertIn("CONFIRMATION_PENDING", computer.computer_control(params))
        self.dispatch.assert_not_called()
        return params

    def test_matching_single_use_decision_dispatches_frozen_coordinates(self):
        params = self.request()
        params["x"] = 999
        self.approve()
        self.focus.assert_called_once_with("Reviewed window")
        self.dispatch.assert_called_once()
        self.assertEqual(self.dispatch.call_args.args[0]["x"], 30)

    def test_changed_window_geometry_or_content_blocks_input(self):
        self.request()
        self.snapshot.return_value = (123, "editor", "Reviewed window", (0, 0, 500, 400), "changed", ())
        self.approve()
        self.dispatch.assert_not_called()

    def test_off_window_coordinates_are_refused_without_prompt(self):
        result = computer.computer_control({"action": "click", "x": 999, "y": 40})
        self.assertTrue(result.startswith("status=failed "))
        self.show.assert_not_called()
        self.dispatch.assert_not_called()

    def test_cancel_or_missing_hud_never_dispatches(self):
        with patch.object(confirm, "_show_cb", None):
            computer.computer_control({"action": "press", "key": "enter", "confirmed": True})
        self.dispatch.assert_not_called()
        self.request()
        confirm.resolve(False, self.show.call_args.args[-1])
        self.dispatch.assert_not_called()

    def test_every_generic_desktop_input_uses_gate(self):
        for action in computer._INPUT_ACTIONS:
            with self.subTest(action=action), patch.object(computer, "_request_desktop_input", return_value="pending") as gate:
                self.assertEqual(computer.computer_control({"action": action, "confirmed": True}), "pending")
                gate.assert_called_once()

    def test_unreadable_target_is_refused(self):
        self.snapshot.side_effect = RuntimeError("target unavailable")
        result = computer.computer_control({"action": "type", "text": "private"})
        self.assertTrue(result.startswith("status=failed "))
        self.dispatch.assert_not_called()
        self.show.assert_not_called()
