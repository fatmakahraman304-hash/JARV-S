"""Real QtWebEngine/WebGL and network acceptance, not a mocked DOM test.

python tools/verify_earth.py OUT_DIR
Requires a display, internet and WebGL. A missing capability fails explicitly.
"""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from PyQt6.QtCore import QCoreApplication, Qt
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    from gui.earth_panel import EarthPanel
    panel = EarthPanel()
    panel.resize(1180, 800)
    panel.show()
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "earth-preview")
    out.mkdir(parents=True, exist_ok=True)
    if panel.view is None:
        raise RuntimeError("QtWebEngine unavailable")

    def js(source):
        answer = []
        panel.view.page().runJavaScript(source, answer.append)
        deadline = time.monotonic() + 5
        while not answer and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if not answer:
            raise TimeoutError("JavaScript bridge did not respond")
        return answer[0]

    def wait(expression, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            state = js("window.earthState || {}") or {}
            if state.get("error"):
                raise RuntimeError(state["error"])
            if js(expression):
                return state
            time.sleep(.10)
        raise TimeoutError("Earth condition failed: " + expression + " | " + str(js("window.earthState")))

    try:
        wait("window.earthState?.ready && earthState.rendered && earthState.images > 0 && earthState.tiles === 0")
        assert js("document.querySelector('canvas').width > 100"), "No visible WebGL canvas"
        panel.grab().save(str(out / "1-holographic.png"))
        for mode in ("natural", "street"):
            js("document.querySelector('[data-mode=" + mode + "]').click()")
            wait("earthState.mode === '" + mode + "' && earthState.images > 0 && earthState.tiles === 0")
            panel.grab().save(str(out / ("2-" + mode + ".png")))
        # A real street-level fly-to and map image load, not a camera-only claim.
        panel.go_to(35.12, 33.94, 19)
        wait("fridayEarth.centre() && Math.abs(fridayEarth.centre().lat - 35.12)<.001 && Math.abs(fridayEarth.centre().lon - 33.94)<.001 && earthState.tiles===0 && earthState.height<150")
        panel.grab().save(str(out / "3-street-detail.png"))
        js("document.getElementById('dimension').click()")
        # Wait for morph to finish before testing the same native page again.
        wait("earthState.sceneMode === 2")
        panel.hide()
        app.processEvents()
        assert not js("earthState.active"), "Hidden Earth kept rendering"
        panel.show()
        app.processEvents()
        wait("earthState.active")
        print("PASS: QtWebEngine globe, real imagery, 3 modes, street destination and hide/show")
        print("Earth state:", js("window.earthState"))
    finally:
        panel.close()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
