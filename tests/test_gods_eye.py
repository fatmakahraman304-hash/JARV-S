import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core import gods_eye
from plugins import gods_eye_view


class GlobeCommandTests(unittest.TestCase):
    def test_typed_open_and_close(self):
        self.assertEqual(gods_eye.globe_command_for_text("JARVIS, God's Eye View’u aç."), "open")
        self.assertEqual(gods_eye.globe_command_for_text("3D küreyi kapat"), "close")
        self.assertIsNone(gods_eye.globe_command_for_text("Mersin'i haritada aç"))

    def test_describes_exact_installed_schema_and_dispatches_arguments(self):
        schema = {"name": "fly_to_location", "parameters": {"properties": {"query": {"type": "string"}}}}
        player = Mock()
        player.control_gods_eye.side_effect = lambda payload, reply: reply.finish("Harita sonucu")
        with patch.object(gods_eye_view, "read_catalog", return_value={schema["name"]: schema}):
            self.assertEqual(json.loads(gods_eye_view.run({
                "action": "describe", "command": schema["name"],
            })), schema)
            result = gods_eye_view.run({
                "action": "call", "command": schema["name"],
                "arguments_json": '{"query":"Gazimağusa"}',
            }, player)
            self.assertEqual(result, "Harita sonucu")
            self.assertEqual(player.control_gods_eye.call_args.args[0], {
                "name": schema["name"], "args": {"query": "Gazimağusa"},
            })
            self.assertIn("komut adı bulunamadı", gods_eye_view.run({
                "action": "call", "command": "unlisted",
            }, player))
            player.control_gods_eye.assert_called_once()


class GlobePanelTests(unittest.TestCase):
    def test_local_service_opens_once_without_logging_a_url_and_runs_browser_command(self):
        from PyQt6.QtWidgets import QApplication
        from gui import gods_eye_panel

        node = shutil.which("node")
        if node is None or gods_eye_panel.QWebEngineView is None:
            self.skipTest("Node.js and Qt WebEngine required")
        app = self.__class__.app = QApplication.instance() or QApplication(["godseye-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vite = root / gods_eye.VITE
            vite.parent.mkdir(parents=True)
            vite.write_text("""
const http = require('node:http');
const port = Number(process.argv[process.argv.indexOf('--port') + 1]);
http.createServer((req, res) => {
    if (req.url === '/src/main.js') {
        res.writeHead(200, {'Content-Type': 'text/javascript'});
        res.end('');
        return;
    }
    res.writeHead(200, {'Content-Type': 'text/html'});
    res.end(`<title>God's Eye View</title><script type="module" src="/src/main.js"></script>
        <script>window.__godsEyeView = {voiceCommands: {runner: async (name, args) => ({ok:true,name,query:args.query})}};</script>`);
}).listen(port, '127.0.0.1', () => console.log('Ready'));
""", encoding="utf-8")
            with patch.object(gods_eye, "ROOT", root), patch.object(gods_eye, "read_catalog", return_value={}):
                panel = gods_eye_panel.GodsEyePanel()
                self.addCleanup(panel._stop)
                received = []
                panel.result.connect(received.append)
                panel.submit({"kind": "open"}, None)
                panel.submit({"name": "fly_to_location", "args": {"query": "Gazimağusa"}}, None)
                deadline = time.monotonic() + 20
                while len(received) < 2 and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.025)
                self.assertEqual(received[0], "God's Eye View hazır.", received)
                self.assertIn("Gazimağusa", received[1])
                self.assertEqual(panel._epoch, 1)
                panel._stop()
