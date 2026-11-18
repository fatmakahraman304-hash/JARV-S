"""gui/holo_gl.py — the hologram table's models, drawn on the GPU.

Two looks, one renderer:

* REAL: a studio render — physically based shading (GGX speculars, Schlick
  Fresnel, metal/roughness per part), a warm key, a cool fill, a rim light in
  the theme colour, a soft studio reflection that blurs with roughness,
  emissive screens/LEDs, glass, ACES tone mapping, a floor with a soft contact
  shadow (several jittered planar shadows, stencilled so each lands once) and
  a dark reflective sheen. 4× multisampling at the screen's own resolution.
* HOLO: the Iron Man workbench — the same geometry as glowing translucent
  light in the theme colour: Fresnel edges, moving scan lines, a faint flicker
  and the floor's projector rings.

Like gui/android_gl.py: only Qt's own OpenGL classes (offscreen surface +
framebuffer → QImage), nothing to install. If OpenGL is missing,
SoftRenderer paints a flat-shaded version with QPainter.
"""
from __future__ import annotations

import math

import numpy as np
from PyQt6.QtCore import QPointF, QSize
from PyQt6.QtGui import (QColor, QImage, QMatrix4x4, QOffscreenSurface, QOpenGLContext, QPainter, QPolygonF,
                         QSurfaceFormat, QVector3D)

GL_TRIANGLES = 0x0004
GL_DEPTH_TEST, GL_BLEND, GL_CULL_FACE, GL_STENCIL_TEST = 0x0B71, 0x0BE2, 0x0B44, 0x0B90
GL_LEQUAL, GL_EQUAL, GL_ALWAYS = 0x0203, 0x0202, 0x0207
GL_KEEP, GL_INCR = 0x1E00, 0x1E02
GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE = 0x0302, 0x0303, 1
GL_FLOAT = 0x1406
GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_STENCIL_BUFFER_BIT = 0x4000, 0x0100, 0x0400
GL_POLYGON_OFFSET_FILL = 0x8037
STRIDE = 14                       # pos3 nrm3 col3 mat4 pid1

VERT = """
#version 120
attribute vec3 a_pos;
attribute vec3 a_nrm;
attribute vec3 a_col;
attribute vec4 a_mat;
attribute float a_pid;
uniform mat4 u_mvp;
uniform vec3 u_off;           // model → world: subtract the centre (x, z) and the floor (y)
uniform float u_pass;         // 0 model, 1 floor, 2 shadow
uniform vec3 u_ldir;          // shadow: direction the light travels
varying vec3 v_wp;
varying vec3 v_n;
varying vec3 v_col;
varying vec4 v_mat;
varying float v_pid;
void main() {
    vec3 wp = a_pos - u_off;
    if (u_pass > 1.5) {                    // flatten onto the floor along the light
        float t = wp.y / max(-u_ldir.y, 0.05);
        wp = vec3(wp.x + u_ldir.x * t, 0.002, wp.z + u_ldir.z * t);
    }
    v_wp = wp; v_n = a_nrm; v_col = a_col; v_mat = a_mat; v_pid = a_pid;
    gl_Position = u_mvp * vec4(wp, 1.0);
}
"""

FRAG = """
#version 120
varying vec3 v_wp;
varying vec3 v_n;
varying vec3 v_col;
varying vec4 v_mat;            // metal, rough, emissive, opacity
varying float v_pid;
uniform vec3 u_eye;
uniform vec3 u_accent;
uniform float u_pass;
uniform float u_holo;
uniform float u_time;
uniform float u_sel;           // highlighted part, -1 none
uniform float u_radius;
uniform float u_height;
uniform float u_alpha_pass;    // 0 opaque parts only, 1 see-through parts only
uniform float u_shadow_a;

const vec3 KEY = vec3(-0.45, 0.72, 0.52);
const vec3 FILL = vec3(0.70, 0.25, 0.66);
const vec3 RIM = vec3(0.10, 0.35, -0.93);
const float PI = 3.14159265;

vec3 env(vec3 r, float rough) {
    // studio: a big softbox overhead, a strip on the left, dark walls, warm floor bounce
    float top = smoothstep(0.35, 0.9, r.y) * (0.8 + 0.2 * smoothstep(0.6, 0.0, abs(r.x)));
    float strip = smoothstep(0.82, 0.97, dot(normalize(vec3(r.x, r.y * 0.4, r.z)), normalize(vec3(-0.9, 0.0, 0.4))));
    float floor_ = smoothstep(0.0, -0.5, r.y);
    vec3 sharp = vec3(0.035) + vec3(1.0, 0.97, 0.92) * (2.2 * top + 1.2 * strip) + u_accent * 0.10 * floor_;
    vec3 blurry = vec3(0.10 + 0.55 * smoothstep(-0.2, 1.0, r.y)) + u_accent * 0.05;
    return mix(sharp, blurry, smoothstep(0.08, 0.75, rough));
}

float ggx(float nh, float a) { float a2 = a * a; float d = nh * nh * (a2 - 1.0) + 1.0; return a2 / (PI * d * d); }
float vis(float nl, float nv, float a) { float k = a * 0.5; return 1.0 / ((nl * (1.0 - k) + k) * (nv * (1.0 - k) + k)); }
vec3 aces(vec3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }

void main() {
    vec3 V = normalize(u_eye - v_wp);
    if (u_pass > 1.5) { gl_FragColor = vec4(0.0, 0.0, 0.0, u_shadow_a); return; }
    if (u_pass > 0.5) {                                   // the floor
        float r = length(v_wp.xz) / (u_radius * 1.6);
        if (u_holo > 0.5) {
            float rings = 0.0;
            for (int i = 1; i <= 3; i++) { float rr = float(i) / 3.0; rings += 0.5 * exp(-pow((r - rr) * 90.0, 2.0)); }
            float ang = atan(v_wp.z, v_wp.x);
            float spokes = 0.18 * smoothstep(0.985, 1.0, cos(ang * 24.0)) * step(0.33, r) * step(r, 1.0);
            float sweep = 0.9 * exp(-pow((r - fract(u_time * 0.25)) * 18.0, 2.0)) * step(r, 1.05);
            float disc = 0.10 * (1.0 - smoothstep(0.0, 1.0, r));
            float a = (rings + spokes + sweep * 0.35 + disc) * (1.0 - smoothstep(0.95, 1.1, r));
            gl_FragColor = vec4(u_accent * a * 1.4, a);
        } else {
            float a = (1.0 - smoothstep(0.15, 1.0, r)) * 0.85;
            vec3 c = vec3(0.045, 0.040, 0.036) + u_accent * 0.035 * (1.0 - r);
            // a dark gloss: the softbox and the key light catch the floor
            float spec = pow(max(dot(reflect(-V, vec3(0, 1, 0)), normalize(KEY)), 0.0), 40.0);
            c += vec3(0.10) * spec;
            gl_FragColor = vec4(c, a);
        }
        return;
    }
    float opacity = v_mat.w;
    if (u_holo < 0.5) {
        if (u_alpha_pass < 0.5 && opacity < 0.99) discard;
        if (u_alpha_pass > 0.5 && opacity >= 0.99) discard;
    }
    vec3 N = normalize(v_n);
    if (dot(N, V) < 0.0) N = -N;                          // thin parts: lit from both sides
    float nv = clamp(dot(N, V), 1e-3, 1.0);
    bool sel = abs(v_pid - u_sel) < 0.5;
    if (u_holo > 0.5) {
        float fres = pow(1.0 - nv, 2.2);
        float scan = 0.55 + 0.45 * sin(v_wp.y / max(u_height, 1.0) * 140.0 - u_time * 6.0);
        float band = exp(-pow((v_wp.y / max(u_height, 1.0) - fract(u_time * 0.35)) * 9.0, 2.0));
        float flick = 0.94 + 0.06 * sin(u_time * 53.0 + v_wp.y);
        vec3 tint = mix(u_accent, vec3(1.0, 0.86, 0.62), 0.25 + 0.35 * dot(v_col, vec3(0.33)));
        vec3 c = tint * (0.10 + 1.7 * fres + 0.08 * scan + 0.9 * band) * flick;
        if (sel) c += vec3(1.0, 0.85, 0.55) * (0.35 + fres);
        float a = clamp(0.10 + 0.75 * fres + 0.05 * scan + 0.35 * band + (sel ? 0.2 : 0.0), 0.0, 1.0);
        gl_FragColor = vec4(c * a, a);                     // premultiplied, drawn additively
        return;
    }
    vec3 alb = pow(v_col, vec3(2.2));
    float metal = v_mat.x, rough = max(v_mat.y, 0.045), a = rough * rough;
    vec3 F0 = mix(vec3(0.04), alb, metal);
    vec3 col = vec3(0.0);
    vec3 Ls[3]; Ls[0] = normalize(KEY); Ls[1] = normalize(FILL); Ls[2] = normalize(RIM);
    vec3 Cs[3]; Cs[0] = vec3(3.1, 2.95, 2.75); Cs[1] = vec3(0.65, 0.78, 1.05); Cs[2] = u_accent * 1.6 + vec3(0.6);
    for (int i = 0; i < 3; i++) {
        vec3 L = Ls[i]; vec3 H = normalize(L + V);
        float nl = max(dot(N, L), 0.0), nh = max(dot(N, H), 0.0), vh = max(dot(V, H), 0.0);
        vec3 F = F0 + (1.0 - F0) * pow(1.0 - vh, 5.0);
        vec3 spec = F * ggx(nh, a) * vis(nl, nv, a) * 0.25;
        vec3 kd = (1.0 - F) * (1.0 - metal);
        col += (kd * alb / PI + spec) * Cs[i] * nl * PI;
    }
    vec3 R = reflect(-V, N);
    vec3 Fe = F0 + (max(vec3(1.0 - rough), F0) - F0) * pow(1.0 - nv, 5.0);
    float sky = 0.5 + 0.5 * N.y;
    vec3 amb = mix(vec3(0.05, 0.045, 0.04) + u_accent * 0.02, vec3(0.16, 0.17, 0.19), sky);
    col += amb * alb * (1.0 - metal);
    col += env(R, rough) * Fe * (0.35 + 0.65 * (1.0 - rough * 0.5));
    float ao = mix(0.45, 1.0, smoothstep(0.0, u_radius * 0.18, v_wp.y));       // contact darkening near the floor
    col *= ao;
    col += pow(v_col, vec3(2.2)) * v_mat.z * 3.0;                                // screens, LEDs
    if (sel) col += u_accent * (0.25 + 0.9 * pow(1.0 - nv, 2.0));
    col = aces(col * 1.05);
    col = pow(col, vec3(1.0 / 2.2));
    float alpha = u_alpha_pass > 0.5 ? clamp(opacity + 0.5 * pow(1.0 - nv, 3.0), 0.0, 1.0) : 1.0;
    gl_FragColor = vec4(col * alpha, alpha);
}
"""


# ── camera maths (shared with the soft renderer and picking) ─────────────────

def perspective(fovy: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fovy) / 2)
    return np.array([[f / aspect, 0, 0, 0], [0, f, 0, 0],
                     [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)], [0, 0, -1, 0]], np.float64)


def look_at(eye, target, up=(0, 1, 0)) -> np.ndarray:
    eye, target, up = (np.asarray(v, np.float64) for v in (eye, target, up))
    f = target - eye; f /= np.linalg.norm(f) or 1
    s = np.cross(f, up); s /= np.linalg.norm(s) or 1
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


class Camera:
    """Orbit camera around the model: yaw/pitch in degrees, zoom, pan."""

    def __init__(self):
        self.yaw, self.pitch, self.zoom, self.pan = -32.0, 18.0, 1.0, [0.0, 0.0]

    def reset(self):
        self.__init__()

    def matrices(self, mesh, w: int, h: int):
        r = mesh.radius
        target = np.array([0.0, mesh.size[1] * 0.45, 0.0])
        dist = r * 2.9 / max(0.2, self.zoom)
        y, p = math.radians(self.yaw), math.radians(max(-85, min(85, self.pitch)))
        eye = target + dist * np.array([math.cos(p) * math.sin(y), math.sin(p), math.cos(p) * math.cos(y)])
        view = look_at(eye, target)
        right, up = view[0, :3], view[1, :3]
        shift = (right * self.pan[0] - up * self.pan[1]) * r * 2.0
        view = look_at(eye + shift, target + shift)
        proj = perspective(34.0, w / max(1, h), max(0.01, dist - r * 3), dist + r * 4)
        return proj @ view, eye + shift

    @staticmethod
    def offset(mesh) -> np.ndarray:
        return np.array([mesh.center[0], mesh.floor, mesh.center[2]], np.float32)

    def project(self, mesh, pts, w, h):
        """Model-space points → screen pixels (x, y, depth); depth ≤ 0 = behind."""
        mvp, _ = self.matrices(mesh, w, h)
        P = np.asarray(pts, np.float64) - self.offset(mesh)
        q = np.c_[P, np.ones(len(P))] @ mvp.T
        wq = q[:, 3:4]
        ndc = q[:, :3] / np.where(np.abs(wq) < 1e-9, 1e-9, wq)
        return np.c_[(ndc[:, 0] + 1) * 0.5 * w, (1 - ndc[:, 1]) * 0.5 * h, wq[:, 0]]


def _qmat(m: np.ndarray) -> QMatrix4x4:
    return QMatrix4x4(*[float(x) for x in m.reshape(-1)])


class HoloGL:
    """Offscreen OpenGL renderer. Qt thread only."""

    def __init__(self):
        self.ok = None
        self.error = ""
        self.renderer_name = ""
        self._ctx = self._surf = self._gl = self._prog = self._vbo = self._floor = self._fbo = None
        self._fbo_size = None
        self._mesh = None
        self._explode = -1.0

    def _setup(self) -> bool:
        try:
            from PyQt6.QtOpenGL import (QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram,
                                        QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile)
            fmt = QSurfaceFormat()
            fmt.setVersion(2, 1)
            fmt.setDepthBufferSize(24)
            fmt.setStencilBufferSize(8)
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
            for i, name in enumerate(("a_pos", "a_nrm", "a_col", "a_mat", "a_pid")):
                prog.bindAttributeLocation(name, i)
            if not prog.link():
                raise RuntimeError("gölgelendirici bağlanamadı: " + prog.log())
            vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer); vbo.create()
            floor = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer); floor.create()
            try:
                self.renderer_name = str(gl.glGetString(0x1F01) or "")
            except Exception:
                pass
            self._ctx, self._surf, self._gl, self._prog, self._vbo, self._floor = ctx, surf, gl, prog, vbo, floor
            ctx.doneCurrent()
            return True
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"[:400]
            return False

    def _ensure_fbo(self, w, h):
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        if self._fbo is not None and self._fbo_size == (w, h):
            return
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        fmt.setSamples(4)
        fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
        if not fbo.isValid():
            fmt.setSamples(0)
            fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
        if not fbo.isValid():
            raise RuntimeError("çerçeve arabelleği oluşturulamadı")
        self._fbo, self._fbo_size = fbo, (w, h)

    def _upload(self, mesh, explode: float):
        if mesh is self._mesh and abs(explode - self._explode) < 1e-4:
            return
        buf = np.zeros((mesh.n_vert, STRIDE), np.float32)
        buf[:, 0:3] = mesh.positions(explode)
        buf[:, 3:6], buf[:, 6:9], buf[:, 9:13], buf[:, 13] = mesh.nrm, mesh.col, mesh.mat, mesh.pid
        data = buf.tobytes()
        self._vbo.bind()
        if mesh is not self._mesh:
            self._vbo.allocate(len(data))
            r = mesh.radius * 1.6                       # the floor disc (world space)
            f = np.zeros((6, STRIDE), np.float32)
            f[:, 0:3] = [(-r, 0, -r), (r, 0, -r), (r, 0, r), (-r, 0, -r), (r, 0, r), (-r, 0, r)]
            f[:, 4] = 1.0
            fd = f.tobytes()
            self._floor.bind(); self._floor.allocate(len(fd)); self._floor.write(0, fd, len(fd)); self._floor.release()
            self._vbo.bind()
        self._vbo.write(0, data, len(data))
        self._vbo.release()
        self._mesh, self._explode = mesh, explode

    def _attrs(self, vbo, on: bool):
        prog = self._prog
        if on:
            vbo.bind()
            for loc, (off, size) in enumerate(((0, 3), (3, 3), (6, 3), (9, 4), (13, 1))):
                prog.enableAttributeArray(loc)
                prog.setAttributeBuffer(loc, GL_FLOAT, off * 4, size, STRIDE * 4)
        else:
            for loc in range(5):
                prog.disableAttributeArray(loc)
            vbo.release()

    def _u(self, name, v):
        prog = self._prog
        if isinstance(v, (list, tuple, np.ndarray)):
            prog.setUniformValue(name, QVector3D(*[float(x) for x in v]))
        elif hasattr(prog, "setUniformValue1f"):
            prog.setUniformValue1f(name, float(v))
        else:
            prog.setUniformValue(name, float(v))

    def render(self, mesh, cam: Camera, w: int, h: int, *, holo: bool, accent, t: float,
               explode: float = 0.0, sel: int = -1) -> QImage | None:
        if self.ok is False or w < 8 or h < 8 or mesh is None or mesh.n_vert == 0:
            return None
        if self.ok is None:
            self.ok = self._setup()
            if not self.ok:
                return None
        gl, prog = self._gl, self._prog
        try:
            if not self._ctx.makeCurrent(self._surf):
                raise RuntimeError("OpenGL bağlamı etkinleştirilemedi")
            self._ensure_fbo(w, h)
            self._upload(mesh, explode)
            mvp, eye = cam.matrices(mesh, w, h)
            self._fbo.bind()
            gl.glViewport(0, 0, w, h)
            gl.glClearColor(0, 0, 0, 0)
            gl.glClearStencil(0)
            gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)
            prog.bind()
            prog.setUniformValue("u_mvp", _qmat(mvp))
            self._u("u_eye", eye); self._u("u_accent", accent); self._u("u_time", t)
            self._u("u_holo", 1.0 if holo else 0.0); self._u("u_sel", float(sel))
            self._u("u_radius", mesh.radius); self._u("u_height", float(mesh.size[1]))
            self._u("u_ldir", (0, -1, 0)); self._u("u_shadow_a", 0.0); self._u("u_alpha_pass", 0.0)
            gl.glDisable(GL_CULL_FACE)
            # floor
            self._u("u_off", (0, 0, 0)); self._u("u_pass", 1.0)
            gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            gl.glDisable(GL_DEPTH_TEST)
            self._attrs(self._floor, True); gl.glDrawArrays(GL_TRIANGLES, 0, 6); self._attrs(self._floor, False)
            off = Camera.offset(mesh)
            self._u("u_off", off)
            if not holo:
                # soft contact shadow: jittered planar shadows, each pixel darkened once per light
                self._u("u_pass", 2.0)
                gl.glEnable(GL_STENCIL_TEST)
                self._attrs(self._vbo, True)
                lights = [(-0.35 + dx, -1.0, -0.30 + dz) for dx, dz in ((0, 0), (0.12, 0.05), (-0.1, 0.1), (0.05, -0.12), (-0.08, -0.06), (0.16, -0.02))]
                for i, ld in enumerate(lights):
                    gl.glClear(GL_STENCIL_BUFFER_BIT)
                    gl.glStencilFunc(GL_EQUAL, 0, 0xFF); gl.glStencilOp(GL_KEEP, GL_KEEP, GL_INCR)
                    self._u("u_ldir", ld); self._u("u_shadow_a", 0.13 if i == 0 else 0.075)
                    gl.glDrawArrays(GL_TRIANGLES, 0, mesh.n_vert)
                gl.glDisable(GL_STENCIL_TEST)
                # the model: opaque parts, then glass
                self._u("u_pass", 0.0)
                gl.glEnable(GL_DEPTH_TEST); gl.glDepthFunc(GL_LEQUAL); gl.glDepthMask(True)
                gl.glDisable(GL_BLEND)
                gl.glDrawArrays(GL_TRIANGLES, 0, mesh.n_vert)
                self._u("u_alpha_pass", 1.0)
                gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA); gl.glDepthMask(False)
                gl.glDrawArrays(GL_TRIANGLES, 0, mesh.n_vert)
                gl.glDepthMask(True)
                self._attrs(self._vbo, False)
            else:
                self._u("u_pass", 0.0)
                gl.glDisable(GL_DEPTH_TEST)
                gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_ONE, GL_ONE)
                self._attrs(self._vbo, True); gl.glDrawArrays(GL_TRIANGLES, 0, mesh.n_vert); self._attrs(self._vbo, False)
            prog.release()
            img = self._fbo.toImage()
            self._fbo.release()
            self._ctx.doneCurrent()
            if img.isNull():
                raise RuntimeError("görüntü okunamadı")
            return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"[:400]
            self.ok = False
            try:
                self._ctx.doneCurrent()
            except Exception:
                pass
            return None


class SoftRenderer:
    """No OpenGL: flat-shaded triangles with QPainter, far to near. Plainer,
    but every machine can draw it."""

    MAX_TRI = 9000

    def render(self, mesh, cam: Camera, w, h, *, holo, accent, t, explode=0.0, sel=-1) -> QImage:
        img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        if mesh is None or mesh.n_vert == 0:
            return img
        P = mesh.positions(explode)
        tri_n = mesh.n_vert // 3
        step = max(1, tri_n // self.MAX_TRI)
        idx = np.arange(0, tri_n, step)
        S = cam.project(mesh, P, w, h).reshape(-1, 3, 3)[idx]
        N = mesh.nrm.reshape(-1, 3, 3)[idx].mean(1)
        C = mesh.col.reshape(-1, 3, 3)[idx].mean(1)
        pid = mesh.pid.reshape(-1, 3)[idx, 0]
        ok = (S[:, :, 2] > 0).all(1)
        order = np.argsort(-S[:, :, 2].mean(1))
        key = np.array([-0.45, 0.72, 0.52]); key /= np.linalg.norm(key)
        lam = np.clip(np.abs(N @ key), 0, 1)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(0, 0, 0, 0))
        acc = [int(c * 255) for c in accent]
        for i in order:
            if not ok[i]:
                continue
            if holo:
                a = 40 + int(80 * (1 - abs(N[i][2])))
                col = QColor(acc[0], acc[1], acc[2], min(255, a + (90 if pid[i] == sel else 0)))
            else:
                k = 0.25 + 0.75 * lam[i]
                c = np.clip(C[i] * k + (np.array(accent) * 0.35 if pid[i] == sel else 0), 0, 1)
                col = QColor(int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))
            p.setBrush(col)
            p.drawPolygon(QPolygonF([QPointF(float(S[i, j, 0]), float(S[i, j, 1])) for j in range(3)]))
        p.end()
        return img
