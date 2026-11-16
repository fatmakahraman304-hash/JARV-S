"""gui/android_gl.py — the assistant's head as a realistic android, on the GPU.

The HUD is painted with QPainter, which can only fill a triangle with one flat
colour. This module renders the same posed head mesh with OpenGL instead, into
an offscreen framebuffer at the screen's exact pixel size (a 4K screen gets a
4K head) with 4x multisampling, then hands back a QImage the avatar draws in
one call. Every pixel is lit in a fragment shader:

* materials laid out on the head's rest pose, so they stay glued to it as it
  turns: a glossy white ceramic face plate, a cooler cranium, the jaw as its
  own part, satin lips, dark anodised ear modules with a status ring, and a
  graphite neck with joint rings;
* a warm key light, a cool fill, a rim light in the theme colour, Blinn
  speculars with a clear coat, a studio reflection (softbox above, floor with
  a warm bounce) weighted by Fresnel, and baked cavity occlusion;
* panel seams as grooves with a lit edge, kept one or two pixels wide at any
  resolution with screen-space derivatives;
* camera-lens eyes (dark glass, a glowing iris ring, aperture blades, pupil and
  catch-lights) that blink and follow the gaze, and a mouth that opens onto a
  dark cavity with a speaker glow driven by the voice.

Only Qt's own OpenGL classes are used (PyQt6.QtOpenGL), so nothing new to
install. If a machine has no usable OpenGL the renderer reports why and the
avatar falls back to the hologram drawing.
"""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QOffscreenSurface, QOpenGLContext, QSurfaceFormat, QVector2D, QVector3D

GL_TRIANGLES = 0x0004
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_LEQUAL = 0x0203
GL_FLOAT = 0x1406
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100

_STRIDE = 13          # clip xyz, normal xyz, rest xyz, ao, jaw, fade, neck

VERT = """
#version 120
attribute vec3 a_clip;
attribute vec3 a_n;
attribute vec3 a_rest;
attribute vec4 a_misc;
varying vec3 v_n;
varying vec3 v_rest;
varying vec4 v_misc;
void main() {
    gl_Position = vec4(a_clip, 1.0);
    v_n = a_n;
    v_rest = a_rest;
    v_misc = a_misc;
}
"""

FRAG = """
#version 120
varying vec3 v_n;
varying vec3 v_rest;
varying vec4 v_misc;          // ao, jaw weight, fade, neck

uniform vec3 u_accent;       // theme colour: rim light and floor bounce
uniform vec3 u_eyecol;       // state colour: the lenses and the ear rings
uniform float u_glow;
uniform float u_time;
uniform float u_mouth;
uniform float u_muted;
uniform vec3 u_eye_l;         // rest-space centre of each eye opening
uniform vec3 u_eye_r;
uniform vec2 u_eye_size;      // half width, half height of the lens
uniform float u_open;         // 1 open .. 0 shut (blink and sleepy lids)
uniform vec2 u_gaze;
uniform vec3 u_mouth_c;
uniform vec2 u_mouth_size;

const vec3 KEY = vec3(-0.4467, 0.5459, 0.7146);
const vec3 FILL = vec3(0.7700, -0.0513, 0.6365);
const vec3 VIEW = vec3(0.0, 0.0, 1.0);

float groove(float d, float w) {
    float aa = max(fwidth(d), 1e-5);
    return 1.0 - smoothstep(w, w + aa * 1.25, abs(d));
}
float edge(float d, float w) {      // the lit lip just outside a groove
    float aa = max(fwidth(d), 1e-5);
    return smoothstep(w, w + aa, d) * (1.0 - smoothstep(w + aa * 1.5, w + aa * 3.5, d));
}

vec3 lens(vec2 p, vec3 accent) {
    // p: position in the lens, x scaled to the lens radius
    vec2 u = p - u_gaze * 0.28;
    float r = length(u);
    vec3 c = vec3(0.012, 0.014, 0.018);
    float iris = 1.0 - smoothstep(0.50, 0.54, r);
    c += accent * 0.22 * iris;
    float ring = exp(-pow((r - 0.43) / 0.055, 2.0));
    c += accent * (1.5 + 0.9 * u_glow) * ring;
    float a = atan(u.y, u.x);
    c += accent * 0.10 * smoothstep(0.93, 1.0, cos(6.0 * a + 0.6)) * iris * (1.0 - ring);
    float pupil = 1.0 - smoothstep(0.15, 0.185, r);
    c = mix(c, vec3(0.004), pupil);
    c += accent * 0.9 * exp(-r * r / 0.0025);
    vec2 h1 = p - vec2(-0.30, 0.32);
    vec2 h2 = p - vec2(0.24, -0.20);
    c += vec3(1.0) * 1.1 * exp(-dot(h1, h1) / 0.0035);
    c += vec3(1.0) * 0.25 * exp(-dot(h2, h2) / 0.0015);
    c *= 0.65 + 0.35 * (1.0 - smoothstep(0.75, 1.0, length(p)));
    return c;
}

void main() {
    vec3 n = normalize(v_n);
    vec3 p = v_rest;
    float ao = v_misc.x;
    float jw = v_misc.y;
    float fade = v_misc.z;
    bool neck = v_misc.w > 0.5;
    vec3 accent = u_accent * (1.0 - 0.75 * u_muted);
    vec3 eyecol = u_eyecol * (1.0 - 0.75 * u_muted);

    // ── material map from the rest pose ────────────────────────────────────
    vec3 alb = vec3(0.66, 0.68, 0.71);      // cranium
    float ks = 0.45, shin = 70.0, refl = 0.10, metal = 0.0;
    bool front = p.z > -0.12;
    vec2 sp = vec2(abs(p.x) / 0.60, abs(p.y + 0.28) / 0.92);
    float plate_f = pow(pow(sp.x, 3.0) + pow(sp.y, 3.0), 1.0 / 3.0) - 1.0;
    bool plate = front && plate_f < 0.0;
    if (plate) { alb = vec3(0.80, 0.80, 0.79); ks = 0.55; shin = 90.0; refl = 0.12; }
    bool jaw = plate && jw > 0.5;
    if (jaw) { alb = vec3(0.76, 0.76, 0.75); ks = 0.50; shin = 85.0; }
    vec2 mq = (p.xy - u_mouth_c.xy) / vec2(u_mouth_size.x * 1.18, u_mouth_size.y * 1.6 + 0.012);
    bool lips = plate && dot(mq, mq) < 1.0;
    if (lips) { alb = vec3(0.30, 0.30, 0.31); ks = 0.30; shin = 30.0; refl = 0.05; }
    float er = length(vec2(p.y + 0.02, p.z + 0.20));
    bool side = abs(p.x) > 0.40;
    bool ear = side && er < 0.17;
    if (ear) { alb = vec3(0.10, 0.105, 0.115); ks = 0.85; shin = 40.0; refl = 0.45; metal = 1.0; }
    if (neck) { alb = vec3(0.055, 0.057, 0.062); ks = 0.70; shin = 28.0; refl = 0.35; metal = 1.0; }

    // ── light ──────────────────────────────────────────────────────────────
    float ndv = clamp(n.z, 0.0, 1.0);
    float dk = max(dot(n, KEY), 0.0);
    float df = max(dot(n, FILL), 0.0);
    float amb = 0.10 + 0.16 * (0.5 + 0.5 * n.y);
    vec3 diff = vec3(amb) + dk * vec3(1.0, 0.96, 0.90) * 0.95 + df * vec3(0.62, 0.70, 0.86) * 0.32;
    vec3 col = alb * diff * (ao * ao) * (1.0 - 0.75 * metal);

    float nh = max(dot(n, normalize(KEY + VIEW)), 0.0);
    float nhf = max(dot(n, normalize(FILL + VIEW)), 0.0);
    float spec = ks * pow(nh, shin) + 0.10 * pow(nh, 14.0) + 0.25 * ks * pow(nhf, shin * 0.6);
    vec3 spec_col = mix(vec3(1.0, 0.98, 0.95), alb * 2.5 + 0.35, metal);
    col += spec * spec_col * clamp(ao, 0.6, 1.0);

    vec3 r = 2.0 * ndv * n - VIEW;
    float top = smoothstep(0.25, 0.65, r.y) * smoothstep(0.85, 0.35, abs(r.x));
    float floor_ = smoothstep(-0.10, -0.60, r.y);
    vec3 env = vec3(0.10 + 0.95 * top) + floor_ * accent * (0.35 + 0.5 * u_glow);
    float fres = 0.04 + 0.96 * pow(1.0 - ndv, 5.0);
    float wr = (refl + 0.55 * fres * (1.0 - metal) + 0.4 * fres * metal) * ao;
    col = col * (1.0 - 0.3 * wr) + env * wr;

    float rim = pow(1.0 - ndv, 3.0) * (0.55 + 0.45 * clamp(n.y * 0.5 + 0.6, 0.0, 1.0));
    col += rim * accent * (0.55 + 0.6 * u_glow);

    // ── seams ──────────────────────────────────────────────────────────────
    float g = 0.0, b = 0.0;
    if (front) { g = max(g, groove(plate_f * 0.6, 0.0045)); b = max(b, edge(plate_f * 0.6, 0.0045)); }
    if (plate && !lips) g = max(g, 0.85 * groove(jw - 0.5, 0.012));
    if (!plate && !neck && p.y > 0.40) g = max(g, groove(p.x, 0.0035));
    if (side) {
        g = max(g, groove(er - 0.17, 0.0045)); b = max(b, edge(er - 0.17, 0.0045));
        g = max(g, 0.8 * groove(er - 0.105, 0.003));
    }
    if (neck) g = max(g, 0.9 * groove(sin(p.y * 52.0) * 0.02, 0.0018));
    col *= 1.0 - 0.82 * g;
    col += b * 0.12;

    float pulse = 0.55 + 0.45 * sin(u_time * 2.2) * (1.0 - u_glow) + 0.6 * u_glow;
    if (side) col += eyecol * 1.2 * pulse * exp(-pow((er - 0.135) / 0.012, 2.0));

    // ── eyes: lenses behind lids that close with a blink ───────────────────
    if (plate) {
        vec3 ec = (p.x < 0.0) == (u_eye_l.x < 0.0) ? u_eye_l : u_eye_r;
        vec2 ep = (p.xy - ec.xy) / u_eye_size.x;
        float h = max(u_eye_size.y / u_eye_size.x * u_open, 0.0);
        float e = length(vec2(ep.x, ep.y / max(h, 1e-3)));
        if (h > 0.02 && e < 1.0) {
            vec3 lc = lens(vec2(ep.x, ep.y), eyecol);
            float k = 1.0 - smoothstep(0.92, 1.0, e);
            col = mix(col, lc, k);
        }
        float lid = abs(length(vec2(ep.x, ep.y / max(u_eye_size.y / u_eye_size.x, 1e-3))) - 1.0);
        float lidline = 1.0 - smoothstep(0.0, max(fwidth(lid), 1e-4) * 1.5 + 0.03, lid);
        col *= 1.0 - 0.55 * lidline;
    }

    // ── mouth: a dark cavity opening with the jaw, with a speaker glow ──────
    if (lips) {
        vec2 q = (p.xy - u_mouth_c.xy) / vec2(u_mouth_size.x, u_mouth_size.y + 0.004 + 0.05 * u_mouth);
        float e = dot(q, q);
        float open = smoothstep(0.02, 0.10, u_mouth);
        float k = (1.0 - smoothstep(0.80, 1.0, e)) * open;
        vec3 cav = vec3(0.008);
        float bars = 0.5 + 0.5 * cos(q.y * 9.0);
        cav += eyecol * (0.25 + 1.4 * u_glow) * bars * (1.0 - e) * 0.6;
        col = mix(col, cav, k);
    }

    col = max(col, vec3(0.0));
    col = vec3(1.0) - exp(-col * 1.35);
    col = pow(col, vec3(1.0 / 1.25));
    float a = clamp(fade, 0.0, 1.0);
    gl_FragColor = vec4(col * a, a);
}
"""


class AndroidGL:
    """Renders the posed head into a QImage with OpenGL. Not thread-safe: use
    from the Qt thread only, like any widget painting."""

    def __init__(self, faces, face_group, rest, ao, jaw, fade, landmarks):
        self.ok = None                     # None: not tried yet
        self.error = ""
        f = np.asarray(faces, np.int32)
        self._idx = f.reshape(-1)          # expanded, non-indexed triangles
        self._n_vert = self._idx.size
        neck_face = (np.asarray(face_group) < 0.5).astype(np.float32)
        self._static = np.zeros((self._n_vert, 7), np.float32)
        self._static[:, 0:3] = np.asarray(rest, np.float32)[self._idx]
        self._static[:, 3] = np.asarray(ao, np.float32)[self._idx]
        self._static[:, 4] = np.asarray(jaw, np.float32)[self._idx]
        self._static[:, 5] = np.asarray(fade, np.float32)[self._idx]
        self._static[:, 6] = np.repeat(neck_face, 3)
        self._buf = np.zeros((self._n_vert, _STRIDE), np.float32)
        self._buf[:, 6:13] = self._static
        rest = np.asarray(rest, np.float32)

        def ellipse(ring):
            pts = rest[np.asarray(ring)]
            c = pts.mean(0)
            half = (pts.max(0) - pts.min(0)) / 2.0
            return c, half

        el, hl = ellipse(landmarks["eye_l"])
        er_, hr = ellipse(landmarks["eye_r"])
        self.eye_l, self.eye_r = el, er_
        self.eye_size = (float((hl[0] + hr[0]) / 2.0) * 0.92, float((hl[1] + hr[1]) / 2.0) * 1.35)
        mc, mh = ellipse(landmarks["lips_in"])
        self.mouth_c, self.mouth_size = mc, (float(mh[0]), float(mh[1]))
        self._ctx = self._surface = self._prog = self._vbo = self._fbo = self._gl = None
        self._fbo_size = None

    # ── setup ─────────────────────────────────────────────────────────────────
    def _setup(self) -> bool:
        try:
            from PyQt6.QtOpenGL import (QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram,
                                        QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile)
            fmt = QSurfaceFormat()
            fmt.setVersion(2, 1)
            fmt.setDepthBufferSize(24)
            ctx = QOpenGLContext()
            ctx.setFormat(fmt)
            if not ctx.create():
                raise RuntimeError("OpenGL bağlamı oluşturulamadı")
            surf = QOffscreenSurface()
            surf.setFormat(ctx.format())
            surf.create()
            if not surf.isValid() or not ctx.makeCurrent(surf):
                raise RuntimeError("OpenGL yüzeyi etkinleştirilemedi")
            prof = QOpenGLVersionProfile()
            prof.setVersion(2, 1)
            gl = QOpenGLVersionFunctionsFactory.get(prof, ctx)
            if gl is None:
                raise RuntimeError("OpenGL 2.1 işlevleri yok")
            if hasattr(gl, "initializeOpenGLFunctions"):
                gl.initializeOpenGLFunctions()
            prog = QOpenGLShaderProgram()
            if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERT):
                raise RuntimeError("köşe gölgelendiricisi: " + prog.log())
            if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAG):
                raise RuntimeError("piksel gölgelendiricisi: " + prog.log())
            for i, name in enumerate(("a_clip", "a_n", "a_rest", "a_misc")):
                prog.bindAttributeLocation(name, i)
            if not prog.link():
                raise RuntimeError("gölgelendirici bağlanamadı: " + prog.log())
            vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            vbo.create()
            vbo.setUsagePattern(QOpenGLBuffer.UsagePattern.DynamicDraw)
            vbo.bind()
            vbo.allocate(self._buf.nbytes)
            vbo.release()
            self._ctx, self._surface, self._gl, self._prog, self._vbo = ctx, surf, gl, prog, vbo
            self.renderer_name = ""
            try:
                self.renderer_name = str(gl.glGetString(0x1F01) or "")      # GL_RENDERER
            except Exception:
                pass
            ctx.doneCurrent()
            return True
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"[:400]
            return False

    def _ensure_fbo(self, w: int, h: int) -> None:
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        if self._fbo is not None and self._fbo_size == (w, h):
            return
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        fmt.setSamples(4)
        fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
        if not fbo.isValid():                       # no multisampling: plain buffer
            fmt.setSamples(0)
            fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
        if not fbo.isValid():
            raise RuntimeError("çerçeve arabelleği oluşturulamadı")
        self._fbo, self._fbo_size = fbo, (w, h)

    def _uniform(self, name, value) -> None:
        prog = self._prog
        if isinstance(value, (tuple, list, np.ndarray)):
            v = [float(x) for x in value]
            prog.setUniformValue(name, QVector2D(*v) if len(v) == 2 else QVector3D(*v))
        elif hasattr(prog, "setUniformValue1f"):
            prog.setUniformValue1f(name, float(value))
        else:
            prog.setUniformValue(name, float(value))

    # ── frame ─────────────────────────────────────────────────────────────────
    def render(self, posed, normals, sx, sy, w: int, h: int, *, accent, eye=None, glow=0.0, t=0.0,
               mouth=0.0, muted=False, open_=1.0, gaze=(0.0, 0.0)) -> QImage | None:
        """Draw the head into a w×h image. sx, sy: vertex positions in image
        pixels. Returns None (and sets .ok False and .error) if OpenGL fails."""
        if self.ok is False or w < 4 or h < 4:
            return None
        if self.ok is None:
            self.ok = self._setup()
            if not self.ok:
                return None
        ctx, gl, prog = self._ctx, self._gl, self._prog
        try:
            if not ctx.makeCurrent(self._surface):
                raise RuntimeError("OpenGL bağlamı etkinleştirilemedi")
            self._ensure_fbo(w, h)
            idx = self._idx
            posed = np.asarray(posed, np.float32)
            buf = self._buf
            buf[:, 0] = np.asarray(sx, np.float32)[idx] / w * 2.0 - 1.0
            buf[:, 1] = 1.0 - np.asarray(sy, np.float32)[idx] / h * 2.0
            buf[:, 2] = -posed[idx, 2] * 0.45
            buf[:, 3:6] = np.asarray(normals, np.float32)[idx]

            self._fbo.bind()
            gl.glViewport(0, 0, w, h)
            gl.glClearColor(0.0, 0.0, 0.0, 0.0)
            gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            gl.glEnable(GL_DEPTH_TEST)
            gl.glDepthFunc(GL_LEQUAL)
            gl.glDisable(GL_CULL_FACE)
            gl.glDisable(GL_BLEND)

            prog.bind()
            self._vbo.bind()
            self._vbo.write(0, buf.tobytes(), buf.nbytes)
            stride = _STRIDE * 4
            for loc, (off, size) in enumerate(((0, 3), (3, 3), (6, 3), (9, 4))):
                prog.enableAttributeArray(loc)
                prog.setAttributeBuffer(loc, GL_FLOAT, off * 4, size, stride)
            self._uniform("u_accent", accent)
            self._uniform("u_eyecol", eye if eye is not None else accent)
            self._uniform("u_glow", glow)
            self._uniform("u_time", t)
            self._uniform("u_mouth", mouth)
            self._uniform("u_muted", 1.0 if muted else 0.0)
            self._uniform("u_eye_l", self.eye_l)
            self._uniform("u_eye_r", self.eye_r)
            self._uniform("u_eye_size", self.eye_size)
            self._uniform("u_open", open_)
            self._uniform("u_gaze", gaze)
            self._uniform("u_mouth_c", self.mouth_c)
            self._uniform("u_mouth_size", self.mouth_size)
            gl.glDrawArrays(GL_TRIANGLES, 0, self._n_vert)
            for loc in range(4):
                prog.disableAttributeArray(loc)
            self._vbo.release()
            prog.release()
            img = self._fbo.toImage()
            self._fbo.release()
            ctx.doneCurrent()
            if img.isNull():
                raise RuntimeError("görüntü okunamadı")
            return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"[:400]
            self.ok = False
            try:
                ctx.doneCurrent()
            except Exception:
                pass
            return None
