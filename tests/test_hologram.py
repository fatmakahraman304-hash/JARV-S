"""Hologram table (web/hologram.html, web/holo-kit.js, plugins/hologram.py)."""
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")

HAND = """
function hand(kind) {           // 21 MediaPipe-style landmarks
  const L = Array.from({length: 21}, () => ({x: .5, y: .8}));
  const fingers = [[5, .38], [9, .46], [13, .54], [17, .62]];
  for (const [m, x] of fingers) {
    const open = kind === 'open' || (kind === 'point' && m === 5) || kind === 'pinch';
    L[m] = {x, y: .6}; L[m + 1] = {x, y: .5};
    L[m + 2] = open ? {x, y: .42} : {x, y: .56}; L[m + 3] = open ? {x, y: .36} : {x, y: .64};
  }
  L[1] = {x: .42, y: .74}; L[2] = {x: .36, y: .68}; L[3] = {x: .32, y: .62}; L[4] = {x: .30, y: .58};
  if (kind === 'pinch') L[4] = {x: L[8].x + .01, y: L[8].y + .01};
  return L;
}
"""


def run(expr: str):
    script = f"const H = require('./web/holo-kit.js');{HAND} console.log(JSON.stringify({expr}));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30, cwd=str(ROOT))
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node not installed")
class KitTests(unittest.TestCase):
    def test_every_shape_is_a_valid_unit_mesh(self):
        r = run("H.SHAPES.map(s => { const u = H.unit(s); const n = u.v.length; return [s, u.f.length > 0, u.e.length > 0, "
                "u.f.every(f => f.length >= 3 && f.every(i => i < n)), u.e.every(e => e.every(i => i < n)), "
                "Math.max(...u.v.flat().map(Math.abs))]; })")
        for s, has_f, has_e, f_ok, e_ok, extent in r:
            self.assertTrue(has_f and has_e and f_ok and e_ok, s)
            self.assertLessEqual(extent, 0.5001, s)

    def test_clean_keeps_bad_model_output_drawable(self):
        m = run("H.clean({name: 'x', parts: [{shape: 'blob', size: [0, -3, 'a'], pos: [1], rot: [370, -10, 0], color: 'red'}, null]})")
        p = m["parts"][0]
        self.assertEqual(p["shape"], "box")
        self.assertEqual(p["size"], [0.05, 3, 5])
        self.assertEqual(p["rot"], [10, 350, 0])
        self.assertEqual(p["color"], "#ff9a2e")
        self.assertEqual(len(m["parts"]), 2)
        self.assertEqual(run("H.clean(null).parts"), [])

    def test_bounds_and_projection_centre(self):
        r = run("(() => { const m = H.clean({parts: [{shape: 'box', size: [10, 20, 10], pos: [0, 10, 0]}]}); const b = H.bounds(m); "
                "return [b.center, H.project(b.center, {yaw: 0, pitch: 0, zoom: 1}, 800, 600, b.center, b.radius).slice(0, 2), "
                "H.project([0, 20, 0], {yaw: 0, pitch: 0, zoom: 1}, 800, 600, b.center, b.radius)[1] < 300, "
                "H.project([0, 20, 0], {yaw: 0, pitch: 0, zoom: 2}, 800, 600, b.center, b.radius)[1] < H.project([0, 20, 0], {yaw: 0, pitch: 0, zoom: 1}, 800, 600, b.center, b.radius)[1]]; })()")
        self.assertEqual(r[0], [0, 10, 0])
        self.assertEqual(r[1], [400, 300])
        self.assertTrue(r[2])     # up is up on screen
        self.assertTrue(r[3])     # zooming in makes it bigger

    def test_explode_pushes_parts_out(self):
        r = run("(() => { const p = H.clean({parts: [{shape: 'box', size: [2, 2, 2], pos: [10, 0, 0]}]}).parts[0]; "
                "const c = v => v.reduce((a, q) => a + q[0], 0) / v.length; return [c(H.partVerts(p, [0, 0, 0], 0)), c(H.partVerts(p, [0, 0, 0], 1))]; })()")
        self.assertAlmostEqual(r[0], 10)
        self.assertAlmostEqual(r[1], 22)

    def test_rotate(self):
        r = run("H.rotate([1, 0, 0], 0, 90, 0).map(v => Math.round(v * 1e6) / 1e6)")
        self.assertEqual(r, [0, 0, -1])

    def test_hand_poses(self):
        self.assertEqual(run("['open', 'fist', 'point', 'pinch'].map(k => H.pose(hand(k)))"), ["open", "fist", "point", "pinch"])
        self.assertEqual(run("H.pose([])"), "none")

    def test_gestures(self):
        r = run("""(() => {
          const st = {}, o = [];
          o.push(H.gestureStep(st, [{pose: 'pinch', at: {x: .5, y: .5}}], 0));
          o.push(H.gestureStep(st, [{pose: 'pinch', at: {x: .6, y: .5}}], 30));
          const z = {}; H.gestureStep(z, [{pose: 'pinch', at: {x: .4, y: .5}}, {pose: 'pinch', at: {x: .6, y: .5}}], 0);
          const zoom = H.gestureStep(z, [{pose: 'pinch', at: {x: .38, y: .5}}, {pose: 'pinch', at: {x: .62, y: .5}}], 30).zoom;
          const e = {}; H.gestureStep(e, [{pose: 'open', at: {x: .5, y: .5}}], 0);
          const ex1 = H.gestureStep(e, [{pose: 'open', at: {x: .5, y: .5}}], 400).action, ex2 = H.gestureStep(e, [{pose: 'open', at: {x: .5, y: .5}}], 800).action,
                ex3 = H.gestureStep(e, [{pose: 'open', at: {x: .5, y: .5}}], 1600).action;
          const f = {}; H.gestureStep(f, [{pose: 'fist', at: {x: .5, y: .5}}], 0); const reset = H.gestureStep(f, [{pose: 'fist', at: {x: .5, y: .5}}], 800).action;
          const t = {}; H.gestureStep(t, [{pose: 'open', at: {x: .2, y: .5}}], 0); H.gestureStep(t, [{pose: 'open', at: {x: .45, y: .5}}], 100);
          const thr = H.gestureStep(t, [{pose: 'open', at: {x: .8, y: .5}}], 200).action;
          const cur = H.gestureStep({}, [{pose: 'point', at: {x: .3, y: .4}}], 0).cursor;
          return [o[0].rotate, o[1].rotate.map(v => Math.round(v)), zoom > 1, ex1, ex2, ex3, reset, thr, cur];
        })()""")
        self.assertEqual(r[0], [0, 0])
        self.assertEqual(r[1], [36, 0])
        self.assertTrue(r[2])
        self.assertEqual(r[3:6], ["", "explode", ""])       # once per hold
        self.assertEqual(r[6], "reset")
        self.assertEqual(r[7], "throw")
        self.assertEqual(r[8], {"x": 0.3, "y": 0.4})

    def test_stl(self):
        stl = run("H.toSTL(H.clean({name: 'Küp test', parts: [{shape: 'box', size: [1, 1, 1], pos: [0, .5, 0]}]}))")
        self.assertTrue(stl.startswith("solid Küp_test"))
        self.assertEqual(stl.count("facet normal"), 12)
        self.assertIn("vertex 5.000 5.000 10.000", stl)     # mm, z up

    def test_local_commands(self):
        r = run("['bunu dijital olarak modelle', 'parçalara ayır', 'birleştir', 'sıfırla', 'STL indir', 'kanatları kırmızı yap', 'tara'].map(H.localCommand)")
        self.assertEqual(r, ["scan", "explode", "assemble", "reset", "stl", "", "scan"])


class PageTests(unittest.TestCase):
    def test_page_wiring(self):
        html = (ROOT / "web" / "hologram.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script src="([^"]+)"', html)
        self.assertEqual(scripts, ["holo-kit.js", "holo.js"])
        js = (ROOT / "web" / "holo.js").read_text(encoding="utf-8")
        for el in re.findall(r"\$\('([\w-]+)'\)", js):
            self.assertIn(f'id="{el}"', html, el)

    def test_main_page_has_the_tool_and_chip(self):
        app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("name: 'hologram'", app)
        self.assertIn("case 'hologram':", app)
        self.assertIn("hologram.html", (ROOT / "web" / "index.html").read_text(encoding="utf-8"))


class PluginTests(unittest.TestCase):
    def test_urls(self):
        from plugins import hologram
        u = hologram.build_url("scan", setup={"g": "AIzaX", "t": "", "i": "", "n": "JARVIS"})
        self.assertTrue(u.startswith("https://fatmakahraman304-hash.github.io/JARV-S/hologram.html?scan=1&hands=1#s="))
        import base64
        blob = u.split("#s=")[1]
        self.assertEqual(json.loads(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))["g"], "AIzaX")
        self.assertIn("make=bir+Iron+Man+kask", hologram.build_url("make", "bir Iron Man kaskı", hands=False))
        self.assertNotIn("#s=", hologram.build_url("open", setup={}))

    def test_run_opens_the_browser(self):
        from plugins import hologram
        with mock.patch("webbrowser.open", return_value=True) as w, mock.patch.object(hologram, "_setup", return_value={}):
            r = hologram.run({"action": "scan"})
        self.assertIn("kameraya göster", r)
        self.assertIn("hologram.html?scan=1", w.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
