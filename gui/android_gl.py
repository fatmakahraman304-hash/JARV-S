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
from PyQt6.QtGui import (QImage, QOffscreenSurface, QOpenGLContext, QSurfaceFormat, QVector2D, QVector3D,
                         QVector4D)

GL_TRIANGLES = 0x0004
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_LEQUAL = 0x0203
GL_FLOAT = 0x1406
GL_COLOR_BUFFER_BIT = 0x4000
GL_DEPTH_BUFFER_BIT = 0x0100

_STRIDE = 16          # clip xyz, normal xyz, rest xyz, ao, jaw, fade, neck, posed xyz
_SHADOW = 2048        # shadow map size
_SH_EXT = 1.8         # half extent of the shadow map's view, head units

VERT = """
#version 120
attribute vec3 a_clip;
attribute vec3 a_n;
attribute vec3 a_rest;
attribute vec4 a_misc;
attribute vec3 a_pos;
uniform vec3 u_lu;            // light space basis (key light)
uniform vec3 u_lv;
uniform vec3 u_ll;
uniform vec2 u_px;            // half the image size in pixels
uniform float u_scale;        // pixels per head unit
varying vec3 v_n;
varying vec3 v_rest;
varying vec4 v_misc;
varying vec3 v_pos;
varying vec3 v_lp;
void main() {
    gl_Position = vec4(a_clip, 1.0);
    v_lp = vec3(dot(a_pos, u_lu), dot(a_pos, u_lv), -dot(a_pos, u_ll)) / 1.8;
    v_pos = vec3(a_clip.x * u_px.x, a_clip.y * u_px.y, -a_clip.z / 0.45 * u_scale);
    v_n = a_n;
    v_rest = a_rest;
    v_misc = a_misc;
}
"""

VERT_SHADOW = """
#version 120
attribute vec3 a_pos;
uniform vec3 u_lu;
uniform vec3 u_lv;
uniform vec3 u_ll;
varying float v_d;
void main() {
    float z = -dot(a_pos, u_ll) / 1.8;
    gl_Position = vec4(dot(a_pos, u_lu) / 1.8, dot(a_pos, u_lv) / 1.8, z, 1.0);
    v_d = z * 0.5 + 0.5;
}
"""

FRAG_SHADOW = """
#version 120
varying float v_d;
void main() {
    vec2 e = fract(vec2(1.0, 255.0) * clamp(v_d, 0.0, 0.999));
    e.x -= e.y / 255.0;
    gl_FragColor = vec4(e, 0.0, 1.0);
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
    if (jaw) { ks = 0.52; }
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
    // (no jaw seam: the weight field contour reads as a broken line)
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


# The realistic human face: skin with pores and subsurface-style wrap light,
# stubble, eyebrows, short hair with volume, ears, wet eyes with lashes, lips,
# teeth and tongue. Everything is procedural from the rest-pose position, so
# it sticks to the animated surface and stays sharp at any resolution.
FRAG_HUMAN = """
#version 120
varying vec3 v_n;
varying vec3 v_rest;
varying vec4 v_misc;          // ao, jaw weight, fade, neck
varying vec3 v_pos;           // image-space position in pixels (for bump mapping)
varying vec3 v_lp;            // position in the key light's shadow map space
uniform sampler2D u_shadow;   // key light depth, packed in red/green

uniform vec3 u_accent;        // theme colour: a faint rim light only
uniform vec3 u_eyecol;
uniform float u_glow;
uniform float u_time;
uniform float u_mouth;
uniform float u_muted;
uniform float u_holographic;
uniform float u_open;         // 1 open .. 0 shut (blink and sleepy lids)
uniform vec2 u_gaze;
uniform float u_scale;        // pixels per head unit
uniform vec2 u_eye_x;         // |x| of the inner and outer eye corner
uniform vec4 u_eye_up;        // upper / lower lid: y = c0 + c1|x| + c2x² + c3|x|³
uniform vec4 u_eye_lo;
uniform vec2 u_eye_c;         // |x|, y of the eye centre
uniform vec3 u_brow;          // brow centre line: y = c0 + c1|x| + c2x²
uniform vec2 u_brow_x;        // |x| of the inner and outer brow end
uniform vec4 u_lip_uo;        // lip outlines, same polynomial form
uniform vec4 u_lip_lo;
uniform vec4 u_lip_ui;
uniform vec4 u_lip_li;
uniform vec2 u_lip_w;         // half width of the outer and inner lip outline

const vec3 KEY = vec3(-0.3693, 0.4748, 0.7989);
const vec3 FILL = vec3(0.7700, -0.0513, 0.6365);
const vec3 VIEW = vec3(0.0, 0.0, 1.0);

float hash(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.11, 0.17, 0.13));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vnoise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x),
                   mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
               mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
                   mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float poly(vec4 c, float a) { return c.x + a * (c.y + a * (c.z + a * c.w)); }
// fades detail out where it would be finer than ~1.5 px (no shimmering at HUD size)
float lod(float freq) { return 1.0 - smoothstep(0.35, 0.9, freq / max(u_scale, 1.0)); }

float hairline(vec3 p) {
    float ax = abs(p.x);
    float front = 0.53 + 0.11 * (ax / 0.48) * (ax / 0.48);
    float hl = mix(-0.44, 0.25, smoothstep(-0.74, -0.46, p.z));
    hl = mix(hl, front, smoothstep(-0.02, 0.26, p.z));
    float sb = exp(-pow((p.z + 0.165) / 0.05, 2.0)) * smoothstep(0.45, 0.6, ax);
    return mix(hl, -0.07, sb);
}
// ear relief (head units) and its outline distance; 0 away from the sides
float ear(vec3 p, out float r) {
    float side = smoothstep(0.50, 0.62, abs(p.x));
    float v = (p.y + 0.03) / 0.27;
    float u = (p.z + 0.37 + 0.14 * (p.y + 0.03)) / 0.15;
    r = length(vec2(u * (1.0 - 0.16 * v), v));
    if (side <= 0.0) { r = 9.0; return 0.0; }
    float inside = 1.0 - smoothstep(0.86, 1.0, r);
    float base = inside * (0.026 + 0.05 * clamp(0.5 - 0.5 * u, 0.0, 1.0));
    float hm = 1.0 - smoothstep(0.1, 0.6, u) * smoothstep(0.3, -0.3, v);
    float helix = exp(-pow((r - 0.80) / 0.085, 2.0)) * hm;
    float anti = exp(-pow((r - 0.50) / 0.07, 2.0)) * smoothstep(-0.45, 0.05, v)
                 * (1.0 - smoothstep(0.2, 0.6, u));
    float concha = exp(-(pow((u - 0.18) / 0.36, 2.0) + pow((v + 0.10) / 0.34, 2.0)));
    float tragus = exp(-(pow((u - 0.80) / 0.12, 2.0) + pow((v + 0.08) / 0.14, 2.0)));
    return side * (base + 0.020 * helix + 0.010 * anti - 0.030 * concha * inside + 0.010 * tragus);
}

float shadowKey(float ndl) {
    vec2 uv = v_lp.xy * 0.5 + 0.5;
    float d = v_lp.z * 0.5 + 0.5;
    float bias = 0.0016 + 0.0035 * (1.0 - clamp(ndl, 0.0, 1.0));
    float tx = 1.0 / 2048.0;
    float lit = 0.0;
    for (int i = 0; i < 16; i++) {
        float a = float(i) * 2.39996;
        float rr = 1.0 + 9.0 * sqrt(float(i) / 16.0);
        vec2 o = vec2(cos(a), sin(a)) * rr * tx;
        vec4 t = texture2D(u_shadow, uv + o);
        float sd = t.r + t.g / 255.0;
        lit += d - bias <= sd ? 1.0 : 0.0;
    }
    return lit / 16.0;
}

vec3 bumpN(vec3 n, vec3 pos, float H) {
    vec3 dpx = dFdx(pos);
    vec3 dpy = dFdy(pos);
    vec3 r1 = cross(dpy, n);
    vec3 r2 = cross(n, dpx);
    float det = dot(dpx, r1);
    vec3 g = sign(det) * (dFdx(H) * r1 + dFdy(H) * r2);
    return normalize(abs(det) * n - g);
}

void main() {
    vec3 n0 = normalize(v_n);
    vec3 p = v_rest;
    float ax = abs(p.x);
    float sgn = p.x < 0.0 ? -1.0 : 1.0;
    float ao = v_misc.x;
    float fade = v_misc.z;
    bool neck = v_misc.w > 0.5;
    bool front = p.z > 0.05 && !neck;
    vec3 accent = u_accent * (1.0 - 0.75 * u_muted);

    // ── skin ───────────────────────────────────────────────────────────────
    vec3 alb = vec3(0.60, 0.40, 0.31);
    float mott = vnoise(p * 9.0) - 0.5;
    alb *= 1.0 + 0.10 * mott;
    float cheek = exp(-(pow((ax - 0.36) / 0.15, 2.0) + pow((p.y + 0.20) / 0.16, 2.0))) * float(front);
    float nose = exp(-(pow(p.x / 0.10, 2.0) + pow((p.y + 0.24) / 0.10, 2.0))) * smoothstep(0.45, 0.6, p.z);
    alb = mix(alb, vec3(0.62, 0.32, 0.27), 0.30 * cheek + 0.35 * nose);
    float under = exp(-(pow((ax - 0.28) / 0.12, 2.0) + pow((p.y - 0.005) / 0.045, 2.0))) * float(front);
    alb *= 1.0 - 0.16 * under;
    alb = mix(alb, alb * vec3(1.03, 1.0, 0.92), smoothstep(0.30, 0.50, p.y) * float(front));
    float H = 0.0;                                   // bump height, head units
    float poreL = lod(420.0);
    H += poreL * ((vnoise(p * 420.0) - 0.5) * 0.00045 + (vnoise(p * 160.0) - 0.5) * 0.0005);
    // Skin has broad, uneven highlights. Strong uniform specular makes
    // a low-resolution head read as wax, especially across the cheeks.
    float skinGrain = vnoise(p * 85.0);
    float ks = mix(0.11, 0.19, skinGrain), shin = mix(22.0, 38.0, skinGrain);
    float wet = 0.0, sss = 1.0;
    float faceFront = float(front);
    float eyeFold = exp(-pow((p.y - (0.015 - 0.045 * pow((ax - 0.28) / 0.16, 2.0))) / 0.010, 2.0));
    eyeFold *= exp(-pow((ax - 0.28) / 0.15, 4.0)) * faceFront;
    float smileFold = exp(-pow((ax - (0.15 + 0.22 * clamp(-p.y - 0.20, 0.0, 0.50))) / 0.018, 2.0));
    smileFold *= smoothstep(-0.70, -0.55, p.y) * (1.0 - smoothstep(-0.34, -0.22, p.y)) * faceFront;
    alb *= 1.0 - 0.055 * eyeFold - 0.065 * smileFold;
    H -= eyeFold * 0.0005 + smileFold * 0.0007;

    // ── ears ───────────────────────────────────────────────────────────────
    float er = 2.0;
    float earH = neck ? 0.0 : ear(p, er);
    float earM = neck ? 0.0 : (1.0 - smoothstep(0.92, 1.02, er)) * smoothstep(0.50, 0.62, ax);
    H += earH;
    alb = mix(alb, vec3(0.64, 0.34, 0.28), 0.45 * earM);
    float earShadow = (1.0 - earM) * exp(-pow((er - 1.04) / 0.07, 2.0)) * smoothstep(0.5, 0.62, ax);

    // ── beard shadow (short stubble) ───────────────────────────────────────
    float bl = -0.33 - 0.12 * smoothstep(0.10, 0.28, ax) + 0.40 * smoothstep(0.34, 0.66, ax);
    bl += (vnoise(p * 30.0) - 0.5) * 0.05;
    float beard = (1.0 - smoothstep(bl - 0.10, bl + 0.04, p.y)) * smoothstep(-0.26, -0.10, p.z);
    beard *= 0.55 + 0.45 * (1.0 - smoothstep(-0.75, -0.45, p.y)) + 0.0 * float(neck);
    if (neck) beard = smoothstep(-0.97, -0.84, p.y) * smoothstep(-0.25, 0.10, p.z);
    beard *= 1.0 - earM;

    // ── lips and mouth ─────────────────────────────────────────────────────
    float yuo = poly(u_lip_uo, ax), ylo = poly(u_lip_lo, ax);
    float yui = poly(u_lip_ui, ax), yli = poly(u_lip_li, ax);
    float lipD = min(yuo - p.y, p.y - ylo);
    float lipM = front && ax < u_lip_w.x + 0.01 ? smoothstep(-0.006, 0.012, lipD) : 0.0;
    beard *= 1.0 - smoothstep(-0.012, 0.004, lipD) * float(ax < u_lip_w.x + 0.03);
    alb = mix(alb, vec3(0.50, 0.29, 0.26), lipM * 0.85);
    H += lipM * lod(380.0) * (vnoise(vec3(p.x * 380.0, p.y * 35.0, 1.0)) - 0.5) * 0.0012;
    float roll = front ? exp(-pow((yuo - p.y + 0.004) / 0.004, 2.0)) * float(ax < u_lip_w.x) : 0.0;
    ks = mix(ks, 0.34, lipM); shin = mix(shin, 44.0, lipM);

    // stubble is applied after the lips are cut out of it
    float dots = smoothstep(0.58, 0.82, vnoise(p * 700.0));
    float dl = lod(700.0);
    alb = mix(alb, alb * vec3(0.66, 0.66, 0.75), beard * 0.50);
    alb *= 1.0 - beard * 0.40 * mix(0.30, dots, dl);
    H += beard * dl * dots * 0.0007;

    // ── eyebrows ───────────────────────────────────────────────────────────
    float browC = 0.0;
    float bt = (ax - u_brow_x.x) / (u_brow_x.y - u_brow_x.x);
    if (front && bt > -0.1 && bt < 1.1) {
        float yfit = u_brow.x + ax * (u_brow.y + ax * u_brow.z);
        float ylin = mix(0.292, 0.235, bt);
        float yc = mix(yfit, ylin, 0.45) - 0.006;
        float ht = mix(0.040, 0.019, smoothstep(0.10, 1.0, bt));
        float en = (vnoise(p * 140.0) - 0.5) * 0.014 + (vnoise(p * 600.0) - 0.5) * 0.008;
        float shape = 1.0 - smoothstep(ht * 0.55, ht * 1.15 + en, abs(p.y - yc - ht * 0.15));
        shape *= smoothstep(-0.06, 0.10, bt + 0.04 * abs(p.y - yc) / ht) * (1.0 - smoothstep(0.88, 1.06, bt));
        float ang = mix(1.25, 0.20, smoothstep(0.0, 0.35, bt));
        ang = mix(ang, -0.30, smoothstep(0.65, 1.0, bt));
        vec2 dir = vec2(cos(ang) * sgn, sin(ang));
        vec2 per = vec2(-dir.y, dir.x);
        float s1 = vnoise(vec3(dot(p.xy, per) * 1100.0, dot(p.xy, dir) * 70.0, sgn * 7.0));
        float s2 = vnoise(vec3(dot(p.xy, per) * 480.0, dot(p.xy, dir) * 32.0, 3.0));
        float hairs = mix(0.75, clamp(0.10 + 1.7 * s1 * s2 + 0.35 * s1, 0.0, 1.0), lod(1100.0));
        browC = clamp(shape * hairs * 1.15, 0.0, 1.0);
        alb = mix(alb, vec3(0.030, 0.022, 0.017), browC * 0.95);
        H += browC * s1 * 0.0018;
    }

    // ── hair ───────────────────────────────────────────────────────────────
    float hairC = 0.0, strand = 0.0;
    if (!neck) {
        float hl = hairline(p) + (vnoise(p * 28.0) - 0.5) * 0.016 + (vnoise(p * 210.0) - 0.5) * 0.010;
        float hm = smoothstep(hl - 0.010, hl + 0.045, p.y) * (1.0 - earM);
        if (hm > 0.0) {
            vec3 nr = normalize(p - vec3(0.0, 0.10, -0.32));
            float px = p.x + 0.17;                                // side parting
            float ps = clamp(px / 0.05, -1.0, 1.0);
            vec3 topDir = normalize(vec3(0.38 + 0.0 * ps, 0.05, -0.75 + 0.35 * smoothstep(0.0, 0.4, p.z)));   // swept back and to one side
            vec3 d0 = mix(vec3(0.0, -0.75, -0.66), topDir, smoothstep(0.30, 0.72, p.y));
            float sideFade = 1.0 - smoothstep(0.05, 0.42, p.y);           // short faded sides
            float part = exp(-pow(px / 0.0030, 2.0)) * smoothstep(0.62, 0.80, p.y) * smoothstep(-0.75, 0.25, p.z);
            vec3 T = normalize(d0 - nr * dot(d0, nr));
            vec3 B = cross(nr, T);
            float a = dot(p, T), b = dot(p, B);
            float f1 = vnoise(vec3(b * 900.0, a * 110.0, 0.5));
            float f2 = vnoise(vec3(b * 260.0, a * 40.0, 2.5));
            float cl = vnoise(vec3(b * 60.0, a * 6.0, 4.5));
            strand = mix(0.5, f1, lod(900.0)) * 0.15 + f2 * 0.40 + cl * 0.45;
            float edgeHairs = smoothstep(0.15, 0.85, hm * 1.4 - 0.2 + 0.7 * (f1 - 0.5));
            hairC = mix(edgeHairs, 1.0, smoothstep(0.6, 1.0, hm)) * hm;
            hairC *= 1.0 - 0.30 * sideFade * (1.0 - f1 * 0.8);
            vec3 hcol = mix(vec3(0.020, 0.0135, 0.009), vec3(0.085, 0.056, 0.036), strand * strand * 1.2);
            alb = mix(alb, hcol, hairC);
            H += hairC * (f1 * 0.0006 + f2 * 0.0026 + cl * 0.008);
        }
    }

    // ── neck: a dark crew-neck T-shirt at the bottom ───────────────────────
    float shirt = neck ? smoothstep(-1.135, -1.155, p.y) : 0.0;
    if (shirt > 0.0) {
        float rib = sin(atan(p.x, p.z + 0.45) * 160.0);
        float collar = smoothstep(-1.155, -1.165, p.y) * (1.0 - smoothstep(-1.20, -1.21, p.y));
        alb = mix(alb, vec3(0.035, 0.036, 0.042) * (1.0 + 0.25 * vnoise(p * 300.0)), shirt);
        H += shirt * (collar * rib * 0.0012 + (vnoise(p * 500.0) - 0.5) * 0.0008);
        ks = mix(ks, 0.05, shirt); shin = mix(shin, 8.0, shirt); sss = 1.0 - shirt;
    }

    if (u_holographic > 0.5) {
        // Spectral translucent skin, not a smooth blue mask. Retain the
        // sculpted hair, ear relief, pores, brow follicles, beard shadow and
        // lip microrelief: these are what make a human head read as human.
        vec3 ice = mix(vec3(0.085, 0.22, 0.34), vec3(0.23, 0.53, 0.68),
                       clamp(0.48 + 0.30 * mott + 0.18 * cheek - 0.15 * under, 0.0, 1.0));
        ice *= 1.0 - beard * (0.22 + 0.11 * dots);
        ice = mix(ice, vec3(0.020, 0.070, 0.12), hairC * 0.96);
        ice = mix(ice, vec3(0.023, 0.080, 0.13), browC * 0.94);
        ice = mix(ice, vec3(0.12, 0.30, 0.43), lipM * 0.75);
        ice = mix(ice, vec3(0.040, 0.13, 0.23), shirt * 0.90);
        alb = ice;
        ks = mix(0.12, 0.32, lipM + hairC * 0.30);
        shin = mix(24.0, 52.0, lipM);
        sss = 0.42;
    }
    vec3 n = bumpN(n0, v_pos, H * u_scale);
    float fwy = max(fwidth(p.y), 1e-5);
    float sMouth = clamp((p.y - yli) / max(yui - yli, 1e-4), 0.0, 1.0);
    float fws = max(fwidth(sMouth), 1e-4);

    // ── lighting ───────────────────────────────────────────────────────────
    float ndv = clamp(n.z, 0.0, 1.0);
    vec3 wrap = vec3(0.50, 0.26, 0.18) * sss;
    float dk = dot(n, KEY), df = dot(n, FILL);
    vec3 lk = clamp((vec3(dk) + wrap) / (1.0 + wrap), 0.0, 1.0);
    float sh = shadowKey(dot(n0, KEY));
    float shk = 0.30 + 0.70 * sh;                                   // a big soft key: shadows are not black
    lk *= vec3(shk) + (1.0 - shk) * vec3(0.20, 0.08, 0.05) * sss;  // red bleed in the penumbra
    vec3 lf = clamp((vec3(df) + wrap) / (1.0 + wrap), 0.0, 1.0);
    float amb = 0.07 + 0.12 * (0.5 + 0.5 * n.y);
    vec3 diff = vec3(amb) + lk * vec3(1.0, 0.95, 0.88) * 1.15 + lf * vec3(0.60, 0.68, 0.85) * 0.24;
    float occ = ao * ao * (1.0 - 0.45 * earShadow);
    if (neck) occ *= mix(0.40, 1.0, smoothstep(-0.70, -0.98, p.y));
    // jawline: the mandible edge runs y ≈ -1 + 1.1x² from the chin to under the
    // ear; everything below and behind it is in shadow, the edge itself catches light
    float yj = -1.0 + 1.1 * ax * ax;
    float zj = 0.38 - 1.6 * ax * ax;
    float jawSide = smoothstep(0.05, 0.25, ax) * float(!neck) * smoothstep(-0.45, -0.25, p.z);
    float underJaw = smoothstep(-0.015, 0.10, yj - p.y) * jawSide;
    underJaw = max(underJaw, smoothstep(-0.45, -0.62, p.y) * smoothstep(-0.05, -0.55, n0.y) * float(!neck));
    occ *= 1.0 - 0.42 * underJaw;
    float jawEdge = exp(-pow((p.y - yj - 0.012) / 0.010, 2.0)) * jawSide * smoothstep(0.0, 0.3, dot(n0, KEY));
    vec3 col = alb * diff * occ;

    vec3 hk = normalize(KEY + VIEW), hf = normalize(FILL + VIEW);
    float nh = max(dot(n, hk), 0.0), nhf = max(dot(n, hf), 0.0);
    float oily = 1.0 + 0.25 * float(front) * (nose + smoothstep(0.3, 0.5, p.y));
    float spec = ks * oily * (0.55 * pow(nh, shin) + 0.25 * pow(nh, shin * 0.3)) * sh + 0.12 * ks * pow(nhf, shin * 0.5);
    float hs = 0.0;
    if (hairC > 0.0) {
        hs = (0.13 * pow(nh, 32.0) + 0.035 * pow(nh, 8.0)) * (0.35 + 0.9 * strand);
        spec = mix(spec, hs, hairC);
        col *= mix(1.0, 0.8, hairC);
    }
    spec *= 1.0 - 0.85 * browC;
    col += spec * vec3(1.0, 0.97, 0.93) * clamp(ao, 0.5, 1.0);
    float fres = 0.03 + 0.97 * pow(1.0 - ndv, 5.0);
    vec3 r = 2.0 * ndv * n - VIEW;
    float top = smoothstep(0.25, 0.70, r.y) * smoothstep(0.85, 0.35, abs(r.x));
    col += vec3(0.22 * top + 0.03) * fres * (1.0 - 0.8 * hairC) * (1.0 - shirt) * ao;
    col += roll * 0.008;
    col += jawEdge * alb * 0.18;
    float rim = pow(1.0 - ndv, 3.0);
    col += rim * accent * (0.16 + 0.30 * u_glow) * (1.0 - 0.5 * hairC);

    // ── eyes ───────────────────────────────────────────────────────────────
    if (front && ax > u_eye_x.x - 0.02 && ax < u_eye_x.y + 0.02 && p.y > 0.0 && p.y < 0.20) {
        float xa = clamp(ax, u_eye_x.x, u_eye_x.y);
        float yu = poly(u_eye_up, xa) + 0.002, yl = poly(u_eye_lo, xa) - 0.001;
        float inX = smoothstep(u_eye_x.x - 0.001, u_eye_x.x + 0.006, ax) * (1.0 - smoothstep(u_eye_x.y - 0.006, u_eye_x.y + 0.001, ax));
        float lid = yl + (yu - yl) * clamp(u_open, 0.0, 1.0);
        float t = (ax - u_eye_x.x) / (u_eye_x.y - u_eye_x.x);   // 0 inner .. 1 outer
        float aa = fwy;
        float vis = inX * smoothstep(yl - aa, yl + aa, p.y) * (1.0 - smoothstep(lid - aa, lid + aa, p.y));
        if (vis > 0.0) {
            vec2 ec = vec2(sgn * u_eye_c.x, u_eye_c.y);
            vec2 d = (p.xy - ec) / 0.11;
            vec3 nb = normalize(n0 + vec3(d, 0.0) * 1.3);
            vec2 q = p.xy - ec - u_gaze * vec2(0.032, 0.018);
            float rr = length(q) / 0.042;
            vec3 sc = vec3(0.62, 0.59, 0.55);
            sc = mix(sc, vec3(0.74, 0.46, 0.42), 0.55 * smoothstep(0.62, 1.0, abs(t - 0.45) * 1.9));
            sc *= 1.0 - 0.05 * vnoise(vec3(p.xy * 300.0, 2.0));
            float a = atan(q.y, q.x);
            float fib = vnoise(vec3(cos(a) * 34.0, sin(a) * 34.0, rr * 4.0));
            float fib2 = vnoise(vec3(cos(a) * 90.0, sin(a) * 90.0, rr * 9.0));
            vec3 iris = mix(vec3(0.090, 0.048, 0.022), vec3(0.30, 0.18, 0.075), smoothstep(0.85, 0.40, rr) * (0.45 + 0.55 * fib));
            iris *= 0.75 + 0.5 * fib2;
            iris *= 1.0 - 0.6 * smoothstep(0.80, 1.0, rr);
            float ir = 1.0 - smoothstep(0.97, 1.03, rr);
            vec3 ecol = mix(sc, iris, ir);
            ecol = mix(ecol, vec3(0.006), 1.0 - smoothstep(0.33, 0.37, rr));
            ecol = mix(ecol, vec3(0.70, 0.40, 0.38), (1.0 - smoothstep(0.0, 0.12, t)) * 0.8);   // caruncle
            float shade = mix(0.30, 1.0, smoothstep(0.0, 0.030, lid - p.y));
            shade *= mix(0.65, 1.0, smoothstep(0.0, 0.012, p.y - yl));
            shade *= 1.0 - 0.35 * smoothstep(0.55, 1.0, abs(t - 0.45) * 2.0);
            float ed = max(dot(nb, KEY), 0.0) * 0.75 * (0.25 + 0.75 * sh) + 0.22;
            vec3 eyeC = ecol * ed * shade;
            float hl1 = pow(max(dot(nb, hk), 0.0), 900.0) * 2.2 * (0.3 + 0.7 * sh);
            float hl2 = pow(max(dot(nb, hf), 0.0), 400.0) * 0.5;
            eyeC += vec3(1.0, 0.98, 0.95) * (hl1 + hl2) * shade;
            float fe = pow(1.0 - clamp(nb.z, 0.0, 1.0), 4.0);
            eyeC += vec3(0.10) * fe;
            eyeC += vec3(0.25) * exp(-pow((p.y - yl - 0.002) / 0.0015, 2.0)) * inX;    // tear line
            col = mix(col, eyeC, vis);
        }
        // lash lines and the lid crease
        float dl2 = p.y - lid;
        float lashLen = 0.004 + 0.008 * smoothstep(0.15, 0.95, t);
        float lashN = vnoise(vec3(t * 220.0, dl2 * 180.0, sgn));
        float lash = inX * smoothstep(-0.0025, -0.0005, dl2) * (1.0 - smoothstep(0.0, lashLen, dl2 * (0.7 + 0.6 * lashN)));
        col *= 1.0 - 0.88 * lash;
        float lo2 = yl - p.y;
        col *= 1.0 - 0.45 * inX * smoothstep(-0.0015, 0.0, lo2) * (1.0 - smoothstep(0.0, 0.0028, lo2));
        float crease = yu + 0.026 - 0.006 * (t - 0.5) * (t - 0.5) * 4.0;
        col *= 1.0 - 0.28 * inX * exp(-pow((p.y - crease) / 0.006, 2.0));
    }

    // ── inside the mouth: contact line, teeth, tongue ──────────────────────
    if (front && ax < u_lip_w.y && p.y < yui + 0.004 && p.y > yli - 0.004) {
        float s = sMouth;
        float ha = 0.118 * u_mouth * (1.0 - 0.55 * (ax / u_lip_w.y) * (ax / u_lip_w.y));
        float o = ha / (0.050 + ha);
        float lo3 = 0.5 - 0.5 * o, hi3 = 0.5 + 0.5 * o;
        float aa = fws;
        float cav = smoothstep(lo3 - aa, lo3 + aa, s) * (1.0 - smoothstep(hi3 - aa, hi3 + aa, s));
        float side = ax / u_lip_w.y;
        col *= 1.0 - 0.75 * exp(-pow((s - 0.5) / max(0.06, 0.6 * o), 2.0)) * (1.0 - smoothstep(0.0, 0.06, o)) * (1.0 - side * side);
        if (cav > 0.0) {
            float c = (s - lo3) / max(o, 1e-4);                 // 0 bottom .. 1 top
            float hpx = max(ha, 1e-4);
            vec3 m = vec3(0.10, 0.025, 0.022);
            float tongue = (1.0 - smoothstep(0.30, 0.55, c)) * (1.0 - smoothstep(0.08, 0.15, ax));
            m = mix(m, vec3(0.34, 0.11, 0.10), tongue * 0.8);
            // teeth: tooth boundaries along the arch, incisal edges rounded per tooth
            float wb = 0.0, tl = 0.0;
            float b0 = 0.0, b1 = 0.072;
            if (ax > 0.072) { b0 = 0.072; b1 = 0.128; }
            if (ax > 0.128) { b0 = 0.128; b1 = 0.172; }
            if (ax > 0.172) { b0 = 0.172; b1 = 0.215; }
            tl = (ax - b0) / (b1 - b0);
            float gap = 1.0 - smoothstep(0.0, 0.0035, min(ax - b0, b1 - ax));
            float round_ = 0.007 * pow(abs(2.0 * tl - 1.0), 3.0);
            float upE = 1.0 - (0.050 * (1.0 - 0.30 * side * side) - round_) / hpx;
            float up = smoothstep(upE - 0.02, upE + 0.02, c);
            float lb0 = floor(ax / 0.050) * 0.050;
            float ltl = (ax - lb0) / 0.050;
            float lgap = 1.0 - smoothstep(0.0, 0.003, min(ax - lb0, lb0 + 0.050 - ax));
            float loE = (0.026 - 0.005 * pow(abs(2.0 * ltl - 1.0), 3.0)) / hpx;
            float low = 1.0 - smoothstep(loE - 0.02, loE + 0.02, c);
            vec3 tooth = vec3(0.80, 0.74, 0.62);
            float dark = 1.0 - 0.85 * smoothstep(0.03, 0.19, ax);
            vec3 tu = tooth * dark * (1.0 - 0.35 * gap) * mix(0.55, 1.0, smoothstep(1.0, 0.75, c));
            tu += vec3(0.45, 0.47, 0.52) * 0.15 * smoothstep(upE + 0.10, upE, c);
            vec3 tlw = tooth * 0.72 * dark * (1.0 - 0.35 * lgap);
            m = mix(m, tlw, low);
            m = mix(m, tu, up);
            float gl = pow(max(dot(n0, hk), 0.0), 40.0) * 0.25 * (up + low) * dark;
            m += vec3(gl);
            col = mix(col, m, cav);
        }
    }

    if (u_holographic > 0.5) {
        // Filmic, depth-preserving spectral grade. Dark eye sockets, hair,
        // nostrils and the lip line stay dark; nose bridge, brow ridge and
        // cheekbones catch separate key/fill highlights instead of turning
        // into one overexposed cyan silhouette.
        float luminance = max(0.0, dot(col, vec3(0.2126, 0.7152, 0.0722)));
        float tonal = smoothstep(0.015, 0.65, luminance);
        vec3 deep = vec3(0.002, 0.022, 0.045);
        vec3 mid = vec3(0.018, 0.34, 0.56);
        vec3 frost = vec3(0.40, 0.93, 1.08);
        col = mix(deep, mid, pow(tonal, 0.90));
        col += frost * pow(max(luminance - 0.19, 0.0), 1.4) * 0.70;
        float edge = pow(1.0 - clamp(dot(n, VIEW), 0.0, 1.0), 2.8);
        col += vec3(0.17, 0.62, 0.94) * edge * (0.72 + 0.32 * u_glow);
        // A barely visible moving scan says hologram without obscuring
        // facial anatomy; screen-size LOD suppresses sparkling on small HUDs.
        float scan = 1.0 + 0.018 * sin(p.y * 540.0 - u_time * 1.7) * lod(540.0);
        col *= scan;
    }
    col = max(col, vec3(0.0));
    col = vec3(1.0) - exp(-col * 1.45);
    col = pow(col, vec3(1.0 / 1.18));
    float al = clamp(fade, 0.0, 1.0);
    gl_FragColor = vec4(col * al, al);
}
"""


def _light_basis():
    ll = np.array([-0.3693, 0.4748, 0.7989])          # the human shader's KEY
    ll /= np.linalg.norm(ll)
    lu = np.cross([0.0, 1.0, 0.0], ll)
    lu /= np.linalg.norm(lu)
    lv = np.cross(ll, lu)
    return lu, lv, ll


_LIGHT_BASIS = _light_basis()


def _hairline(p: np.ndarray) -> np.ndarray:
    """Same hairline as the shader (without its noise), head units."""
    ax = np.abs(p[:, 0])
    front = 0.53 + 0.11 * (ax / 0.48) ** 2
    ss = lambda e0, e1, x: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0, 1))
    hl = -0.44 + (0.25 + 0.44) * ss(-0.74, -0.46, p[:, 2])
    hl = hl + (front - hl) * ss(-0.02, 0.26, p[:, 2])
    sb = np.exp(-((p[:, 2] + 0.165) / 0.05) ** 2) * ss(0.45, 0.6, ax)
    return hl + (-0.07 - hl) * sb


def _human_relief(p: np.ndarray, with_hair: bool = True) -> np.ndarray:
    """Outward displacement per vertex: hair volume (thick on top, a short
    fade at the sides and nape) and the ears standing off the skull."""
    ss = lambda e0, e1, x: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0, 1))
    ax = np.abs(p[:, 0])
    v = (p[:, 1] + 0.03) / 0.27
    u = (p[:, 2] + 0.37 + 0.14 * (p[:, 1] + 0.03)) / 0.15
    r = np.hypot(u * (1.0 - 0.16 * v), v)
    side = ss(0.50, 0.62, ax)
    ear_in = 1.0 - ss(0.86, 1.0, r)
    ear = side * ear_in * (0.026 + 0.05 * np.clip(0.5 - 0.5 * u, 0.0, 1.0))
    if not with_hair:
        return ear
    ear_m = side * (1.0 - ss(0.92, 1.02, r))
    hl = _hairline(p)
    lift = ss(0.45, 0.78, p[:, 1]) * ss(-0.35, 0.30, p[:, 2])
    hair = ss(hl - 0.005, hl + 0.09, p[:, 1]) * (0.008 + 0.042 * ss(0.0, 0.7, p[:, 1]) + 0.026 * lift)
    return np.maximum(hair * (1.0 - ear_m), ear)


def _human_params(rest: np.ndarray, lm) -> dict:
    """Fit the face's features (lids, brows, lip outlines) from the measured
    landmarks as polynomials in |x|, for the shader."""
    def fit(idx, terms=4):
        pts = rest[np.asarray(idx)]
        a = np.abs(pts[:, 0])
        basis = np.stack([a ** k for k in range(terms)], 1)
        c = np.linalg.lstsq(basis, pts[:, 1], rcond=None)[0]
        return tuple(float(x) for x in c) + (0.0,) * (4 - terms)

    eye, lo, li = list(lm["eye_r"]), list(lm["lips_out"]), list(lm["lips_in"])
    ex = np.abs(rest[eye, 0])
    brow = np.abs(rest[list(lm["brow_r"]), 0])
    pe = rest[eye]
    return {
        "u_eye_x": (float(ex.min()), float(ex.max())),
        "u_eye_lo": fit(eye[:9]),
        "u_eye_up": fit([eye[0]] + eye[8:]),
        "u_nose_tip": (float(rest[1, 0]), float(rest[1, 1])),
        "u_nose_bridge": (float(rest[6, 0]), float(rest[6, 1])),
        "u_eye_c": (float(np.abs(pe[:, 0]).mean()), float(pe[:, 1].mean())),
        "u_brow": fit(list(lm["brow_r"]), 3)[:3],
        "u_brow_x": (float(brow.min()) - 0.01, float(brow.max()) + 0.02),
        "u_lip_uo": fit([lo[10]] + lo[11:] + [lo[0]]),
        "u_lip_lo": fit(lo[:11]),
        "u_lip_ui": fit([li[10]] + li[11:] + [li[0]]),
        "u_lip_li": fit(li[:11]),
        "u_lip_w": (float(np.abs(rest[lo, 0]).max()), float(np.abs(rest[li, 0]).max())),
    }


class AndroidGL:
    """Renders the posed head into a QImage with OpenGL. Not thread-safe: use
    from the Qt thread only, like any widget painting."""

    def __init__(self, faces, face_group, rest, ao, jaw, fade, landmarks, subdiv: int = 2,
                 look: str = "human"):
        self.ok = None                     # None: not tried yet
        self.error = ""
        self.look = look if look in ("human", "android", "holographic") else "human"
        f = np.asarray(faces, np.int32)
        n_base = len(rest)
        neck_face = (np.asarray(face_group) < 0.5).astype(np.float32)
        # Loop-subdivide the mesh (fixed stencil, re-applied to the posed
        # vertices each frame) so the silhouette and shading are smooth curved
        # surfaces instead of visible polygons, even at 4K.
        if subdiv > 0:
            from core.android_render import apply_stencil, loop_subdivision
            f, self._st_idx, self._st_w, parent = loop_subdivision(f, n_base, subdiv)
            neck_face = neck_face[parent]
            sub = lambda a: apply_stencil(np.asarray(a, np.float32), self._st_idx, self._st_w)
        else:
            self._st_idx = self._st_w = None
            sub = lambda a: np.asarray(a, np.float32)
        self._idx = f.reshape(-1)          # expanded, non-indexed triangles
        self._n_vert = self._idx.size
        self._static = np.zeros((self._n_vert, 7), np.float32)
        self._static[:, 0:3] = sub(rest)[self._idx]
        self._static[:, 3] = sub(ao)[self._idx]
        self._static[:, 4] = sub(jaw)[self._idx]
        self._static[:, 5] = sub(fade)[self._idx]
        self._static[:, 6] = np.repeat(neck_face, 3)
        # Hair volume and ears are real geometry: the subdivided vertices are
        # pushed out along their normal each frame by this static amount.
        rest_sub = sub(rest)
        neck_v = np.zeros(len(rest_sub), bool)
        neck_v[f[neck_face > 0.5].reshape(-1)] = True
        neck_v[f[neck_face < 0.5].reshape(-1)] = False
        self._disp = (_human_relief(rest_sub, with_hair=self.look == "human") * ~neck_v).astype(np.float32) \
            if self.look in ("human", "holographic") else None
        self._scale = 1.0
        self._human = _human_params(np.asarray(rest, np.float32), landmarks)
        self._buf = np.zeros((self._n_vert, _STRIDE), np.float32)
        self._buf[:, 6:13] = self._static
        self._sfbo = self._sprog = None
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
            if self.look == "holographic":
                from gui.hologram_glsl import FRAG_HOLOGRAM
                frag = FRAG_HOLOGRAM
            else:
                frag = FRAG_HUMAN if self.look == "human" else FRAG
            if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, frag):
                raise RuntimeError("piksel gölgelendiricisi: " + prog.log())
            for i, name in enumerate(("a_clip", "a_n", "a_rest", "a_misc", "a_pos")):
                prog.bindAttributeLocation(name, i)
            if not prog.link():
                raise RuntimeError("gölgelendirici bağlanamadı: " + prog.log())
            if self.look == "human":
                sp = QOpenGLShaderProgram()
                if not (sp.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERT_SHADOW)
                        and sp.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAG_SHADOW)):
                    raise RuntimeError("gölge gölgelendiricisi: " + sp.log())
                sp.bindAttributeLocation("a_pos", 4)
                if not sp.link():
                    raise RuntimeError("gölge gölgelendiricisi bağlanamadı: " + sp.log())
                self._sprog = sp
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

    def _shadow_pass(self) -> None:
        """Depth of the posed head seen from the key light, so the nose, brows,
        ears, hair and jaw cast real soft shadows in the main pass."""
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        gl, sp = self._gl, self._sprog
        if self._sfbo is None:
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setAttachment(QOpenGLFramebufferObject.Attachment.Depth)
            self._sfbo = QOpenGLFramebufferObject(QSize(_SHADOW, _SHADOW), fmt)
            if not self._sfbo.isValid():
                raise RuntimeError("gölge arabelleği oluşturulamadı")
        self._sfbo.bind()
        gl.glViewport(0, 0, _SHADOW, _SHADOW)
        gl.glClearColor(1.0, 1.0, 1.0, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        gl.glDisable(GL_CULL_FACE)
        gl.glDisable(GL_BLEND)
        sp.bind()
        self._vbo.bind()
        sp.enableAttributeArray(4)
        sp.setAttributeBuffer(4, GL_FLOAT, 13 * 4, 3, _STRIDE * 4)
        for name, value in zip(("u_lu", "u_lv", "u_ll"), _LIGHT_BASIS):
            sp.setUniformValue(name, QVector3D(*[float(x) for x in value]))
        gl.glDrawArrays(GL_TRIANGLES, 0, self._n_vert)
        sp.disableAttributeArray(4)
        self._vbo.release()
        sp.release()
        self._sfbo.release()

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
            vec = {2: QVector2D, 3: QVector3D, 4: QVector4D}[len(v)]
            prog.setUniformValue(name, vec(*v))
        elif hasattr(prog, "setUniformValue1f"):
            prog.setUniformValue1f(name, float(value))
        else:
            prog.setUniformValue(name, float(value))

    # ── frame ─────────────────────────────────────────────────────────────────
    def _dynamic(self, posed, normals, sx, sy, w, h) -> np.ndarray:
        """Per-base-vertex clip xyz + normal, subdivided when enabled."""
        d = np.empty((len(sx), 9), np.float32)
        d[:, 0] = np.asarray(sx, np.float32) / w * 2.0 - 1.0
        d[:, 1] = 1.0 - np.asarray(sy, np.float32) / h * 2.0
        d[:, 2] = -np.asarray(posed, np.float32)[:, 2] * 0.45
        d[:, 3:6] = normals
        d[:, 6:9] = posed
        if self._st_idx is not None:
            d = np.einsum("mk,mkd->md", self._st_w, d[self._st_idx])
            n = d[:, 3:6]
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)
        py = np.asarray(posed, np.float32)[:, 1]
        sy = np.asarray(sy, np.float32)
        span = float(py.max() - py.min())
        self._scale = float(sy.max() - sy.min()) / span if span > 1e-6 else 1.0
        if self._disp is not None:
            k = self._disp * self._scale
            d[:, 0] += d[:, 3] * k / (w * 0.5)
            d[:, 1] += d[:, 4] * k / (h * 0.5)
            d[:, 2] -= d[:, 5] * self._disp * 0.45
            d[:, 6:9] += d[:, 3:6] * self._disp[:, None]
        return d

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
            buf = self._buf
            dyn = self._dynamic(posed, normals, sx, sy, w, h)[self._idx]
            buf[:, 0:6] = dyn[:, 0:6]
            buf[:, 13:16] = dyn[:, 6:9]
            self._vbo.bind()
            self._vbo.write(0, buf.tobytes(), buf.nbytes)
            self._vbo.release()
            if self.look == "human":
                self._shadow_pass()

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
            stride = _STRIDE * 4
            for loc, (off, size) in enumerate(((0, 3), (3, 3), (6, 3), (9, 4), (13, 3))):
                prog.enableAttributeArray(loc)
                prog.setAttributeBuffer(loc, GL_FLOAT, off * 4, size, stride)
            self._uniform("u_accent", accent)
            self._uniform("u_eyecol", eye if eye is not None else accent)
            self._uniform("u_glow", glow)
            self._uniform("u_holographic", 1.0 if self.look == "holographic" else 0.0)
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
            self._uniform("u_px", (w * 0.5, h * 0.5))
            self._uniform("u_scale", self._scale)
            if self.look in ("human", "holographic"):
                for name, value in self._human.items():
                    self._uniform(name, value)
            if self.look == "human":
                for name, value in zip(("u_lu", "u_lv", "u_ll"), _LIGHT_BASIS):
                    self._uniform(name, value)
                gl.glActiveTexture(0x84C0)                         # GL_TEXTURE0
                gl.glBindTexture(0x0DE1, self._sfbo.texture())     # GL_TEXTURE_2D
                for pname in (0x2801, 0x2800):                     # min / mag: nearest
                    gl.glTexParameteri(0x0DE1, pname, 0x2600)
                for pname in (0x2802, 0x2803):                     # clamp to edge
                    gl.glTexParameteri(0x0DE1, pname, 0x812F)
                prog.setUniformValue("u_shadow", 0)
            gl.glDrawArrays(GL_TRIANGLES, 0, self._n_vert)
            for loc in range(5):
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
