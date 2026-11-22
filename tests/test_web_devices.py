"""Web AETHER device modules (web/devkit.js, web/dev-*.js).

devkit.js is pure, so its helpers run under Node here; the device modules are
checked for syntax and wiring. Skipped where Node is not installed.
"""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
NODE = shutil.which("node")


def node(script: str) -> str:
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30, cwd=str(ROOT))
    if out.returncode:
        raise AssertionError(out.stderr)
    return out.stdout.strip()


def kit(expr: str):
    return json.loads(node(f"const K = require('./web/devkit.js'); console.log(JSON.stringify({expr}));"))


@unittest.skipUnless(NODE, "node not installed")
class SyntaxTests(unittest.TestCase):
    def test_every_web_script_parses(self):
        for f in sorted(WEB.glob("*.js")):
            r = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr}")


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.html = (WEB / "index.html").read_text(encoding="utf-8")
        self.app = (WEB / "app.js").read_text(encoding="utf-8")

    def test_every_device_module_is_loaded_after_app_and_common(self):
        scripts = re.findall(r'<script src="([^"]+)"', self.html)
        self.assertLess(scripts.index("devkit.js"), scripts.index("app.js"))
        self.assertLess(scripts.index("app.js"), scripts.index("dev-common.js"))
        for f in sorted(WEB.glob("dev-*.js")):
            self.assertIn(f.name, scripts, f"{f.name} is not loaded by index.html")
            if f.name != "dev-common.js":
                self.assertLess(scripts.index("dev-common.js"), scripts.index(f.name))

    def test_modules_use_only_the_public_api(self):
        api = re.search(r"window\.AETHER = \{(.*?)\n  \};", self.app, re.S).group(1)
        common = (WEB / "dev-common.js").read_text(encoding="utf-8")
        added = set(re.findall(r"\bJ\.(\w+) =", common))
        for f in sorted(WEB.glob("dev-*.js")):
            used = set(re.findall(r"\bJ\.(\w+)", f.read_text(encoding="utf-8"))) - added
            for name in used:
                self.assertRegex(api, rf"\b{name}\b", f"{f.name} uses J.{name}, which app.js does not expose")

    def test_pages_build_versions_every_script(self):
        yml = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn('s#src=\\"([a-z-]+\\.js)\\"#', yml)


@unittest.skipUnless(NODE, "node not installed")
class DevkitTests(unittest.TestCase):
    def test_swipe(self):
        self.assertEqual(kit("[K.swipeDir(0,-120,200), K.swipeDir(150,10,200), K.swipeDir(10,10,200), K.swipeDir(0,-200,2000), K.swipeDir(80,80,200)]"),
                         ["up", "right", None, None, None])

    def test_nearest_picks_the_lined_up_box(self):
        boxes = "[{x:0,y:0,w:10,h:10},{x:50,y:0,w:10,h:10},{x:20,y:40,w:10,h:10},{x:50,y:100,w:10,h:10}]"
        self.assertEqual(kit(f"(() => {{ const b = {boxes}; return [K.nearest(b[0], b, 'right'), K.nearest(b[0], b, 'down'), K.nearest(b[0], b, 'left'), K.nearest(b[1], b, 'left')]; }})()"),
                         [1, 2, -1, 0])

    def test_night_window_wraps_midnight(self):
        self.assertEqual(kit("[K.isNight(23), K.isNight(3), K.isNight(7), K.isNight(12), K.isNight(14, 13, 15), K.isNight(5, 5, 5)]"),
                         [True, True, False, False, True, False])

    def test_ms_until(self):
        self.assertEqual(kit("K.msUntil(4, new Date(2026, 0, 1, 3, 30))"), 30 * 60000)
        self.assertEqual(kit("K.msUntil(4, new Date(2026, 0, 1, 5, 0))"), 23 * 3600000)

    def test_minutes_and_clock(self):
        self.assertEqual(kit("[K.fmtMinutes(130), K.fmtMinutes(45), K.fmtMinutes(120), K.mmss(75000), K.mmss(0)]"),
                         ["2 sa 10 dk", "45 dk", "2 sa", "1:15", "0:00"])

    def test_lamp_log_keeps_90_days(self):
        r = kit("(() => { let L = {}; for (let i = 1; i <= 95; i++) L = K.lampAdd(L, '2026-' + String(Math.ceil(i / 28)).padStart(2, '0') + '-' + String((i - 1) % 28 + 1).padStart(2, '0'), 10); L = K.lampAdd(L, '2026-04-11', 5); return [Object.keys(L).length, K.lampTotal(L)]; })()")
        self.assertEqual(r, [90, 905])

    def test_core_fps(self):
        self.assertEqual(kit("[K.coreFps({}), K.coreFps({hidden:true}), K.coreFps({saver:true}), K.coreFps({battery:15}), K.coreFps({battery:15, charging:true}), K.coreFps({watch:true}), K.coreFps({watch:true, idleMs:30000})]"),
                         [0, -1, 20, 24, 0, 15, -1])

    def test_history(self):
        self.assertEqual(kit("K.histPush(['a','b','c'], 'a', 3)"), ["b", "c", "a"])
        self.assertEqual(kit("K.histPush(['a'], '  ')"), ["a"])

    def test_keys(self):
        self.assertEqual(kit("[K.tvKey('Escape'), K.tvKey('', 10009), K.tvKey('', 461), K.tvKey('ColorF0Red'), K.tvKey('', 406), K.tvKey('ArrowUp'), K.tvKey('x', 0)]"),
                         ["back", "back", "back", "agenda", "remote", "up", None])
        self.assertEqual(kit("[K.remoteKey('ArrowLeft'), K.remoteKey('Enter'), K.remoteKey(' '), K.remoteKey('q')]"),
                         ["left", "ok", "play_pause", None])

    def test_drift_moves_and_stays_small(self):
        r = kit("[0,1,2,3,4,5,6,7,8,9].map(m => K.drift(m, 24))")
        self.assertTrue(all(abs(p["x"]) <= 24 and abs(p["y"]) <= 24 for p in r))
        self.assertTrue(all(r[i] != r[i + 1] for i in range(len(r) - 1)))

    def test_youtube(self):
        self.assertEqual(kit("[K.youtubeEmbed('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), K.youtubeEmbed('https://youtu.be/dQw4w9WgXcQ?t=3'), K.youtubeEmbed('https://example.com')]"),
                         ["https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1&rel=0"] * 2 + [""])

    def test_shake_and_cycle_and_next(self):
        self.assertTrue(kit("K.shaken([{t:100,a:20},{t:300,a:18},{t:500,a:16}], 600)"))
        self.assertFalse(kit("K.shaken([{t:100,a:20},{t:300,a:5},{t:500,a:16}], 600)"))
        self.assertEqual(kit("[K.cycle(0,-1,4), K.cycle(3,1,4)]"), [3, 0])
        self.assertEqual(kit("K.nextUp([{text:'b', due: 1000 + 90*60000}, {text:'a', due: 1000 + 5*60000}, {text:'x', due: 10, cancelled:'y'}], 1000)"),
                         "5 dk sonra: a")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(NODE, "node not installed")
class GistReadTests(unittest.TestCase):
    def test_raw_read_failure_retains_previous_snapshot_and_etag(self):
        self.assertEqual(node("""
            const fs = require('node:fs'), assert = require('node:assert/strict');
            const src = fs.readFileSync('web/app.js', 'utf8');
            const impl = src.slice(src.indexOf('  async function gistContent'), src.indexOf('  const J ='));
            const S = {tok:'test', gist:'example'}, GH = 'https://api.github.com';
            const cloud = eval(impl + '\\nCloud');
            cloud.etag = 'old'; cloud.cache = {'memory.json': 'previous'};
            global.fetch = async url => String(url).startsWith(GH)
              ? {ok:true, headers:{get:()=>'new'}, json:async()=>({files:{
                  'memory.json':{truncated:true, raw_url:'https://gist.githubusercontent.com/file'}}})}
              : {ok:false, status:503};
            (async () => {
              await assert.rejects(cloud.read());
              assert.equal(cloud.etag, 'old');
              assert.equal(cloud.cache['memory.json'], 'previous');
              console.log('ok');
            })().catch(e => {console.error(e); process.exitCode = 1;});
        """), "ok")
