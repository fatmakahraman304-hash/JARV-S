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
STRIDE = 18                       # pos3 nrm3 col3 mat4 pid1 ext2 (finish, ambient occlusion) uv2
SHADOW = 4096
_KEY = np.array([-0.45, 0.72, 0.52]); _KEY /= np.linalg.norm(_KEY)
_LU = np.cross([0.0, 1.0, 0.0], _KEY); _LU /= np.linalg.norm(_LU)
_LV = np.cross(_KEY, _LU)

VERT = """
#version 120
attribute vec3 a_pos;
attribute vec3 a_nrm;
attribute vec3 a_col;
attribute vec4 a_mat;
attribute float a_pid;
attribute vec2 a_ext;
attribute vec2 a_uv;
uniform mat4 u_mvp;
uniform vec3 u_off;           // model → world: subtract the centre (x, z) and the floor (y)
uniform float u_pass;         // 0 model, 1 floor, 2 shadow
uniform vec3 u_ldir;          // shadow: direction the light travels
uniform vec3 u_lu;            // key light basis and the shadow map's half extent
uniform vec3 u_lv;
uniform vec3 u_ll;
uniform float u_ext;
uniform vec3 u_lc;
varying vec3 v_lp;
varying vec3 v_wp;
varying vec3 v_n;
varying vec3 v_col;
varying vec4 v_mat;
varying float v_pid;
varying vec2 v_ext;
varying vec2 v_uv;
void main() {
    vec3 wp = a_pos - u_off;
    v_ext = a_ext; v_uv = a_uv;
    if (u_pass > 2.5) wp.y = -wp.y;        // floor reflection: the model upside down under the floor
    else if (u_pass > 1.5) {               // flatten onto the floor along the light
        float t = wp.y / max(-u_ldir.y, 0.05);
        wp = vec3(wp.x + u_ldir.x * t, 0.002, wp.z + u_ldir.z * t);
    }
    v_wp = wp; v_n = a_nrm; v_col = a_col; v_mat = a_mat; v_pid = a_pid;
    vec3 q = wp - u_lc;
    v_lp = vec3(dot(q, u_lu), dot(q, u_lv), -dot(q, u_ll)) / u_ext;
    gl_Position = u_mvp * vec4(wp, 1.0);
}
"""

VERT_SHADOW = """
#version 120
attribute vec3 a_pos;
uniform vec3 u_off;
uniform vec3 u_lu;
uniform vec3 u_lv;
uniform vec3 u_ll;
uniform float u_ext;
uniform vec3 u_lc;
varying float v_d;
void main() {
    vec3 q = a_pos - u_off - u_lc;
    vec3 lp = vec3(dot(q, u_lu), dot(q, u_lv), -dot(q, u_ll)) / u_ext;
    gl_Position = vec4(lp, 1.0);
    v_d = lp.z * 0.5 + 0.5;
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
uniform sampler2D u_shadow;
uniform float u_has_shadow;
uniform float u_cut;           // geometry with x beyond this is cut away (section view); 1e9 = none
uniform float u_iso;           // the one part shown solid, the rest ghosted; -1 = all solid
uniform sampler2D u_tex;       // a scanned model's colour texture
uniform float u_has_tex;
uniform sampler2D u_mr;        // and its PBR maps: metal/roughness (b/g), normal, emissive, occlusion (r)
uniform sampler2D u_nrm;
uniform sampler2D u_emi;
uniform sampler2D u_occ;
uniform float u_has_mr;
uniform float u_has_nrm;
uniform float u_has_emi;
uniform float u_has_occ;
uniform float u_nrm_scale;
varying vec3 v_lp;
varying vec2 v_ext;
varying vec2 v_uv;
vec3 base_rgb() { return u_has_tex > 0.5 ? v_col * texture2D(u_tex, vec2(v_uv.x, 1.0 - v_uv.y)).rgb : v_col; }

float hash3(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vnoise(vec3 x) {
    vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash3(i), hash3(i + vec3(1, 0, 0)), f.x), mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
               mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x), mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}
float fbm(vec3 p) { float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++) { s += a * vnoise(p); p = p * 2.03 + 7.1; a *= 0.5; } return s; }

// surface height (0..1) of a finish at p (cm), on the tangent plane (u, v)
float fin_h(float id, vec3 p, vec2 uv) {
    if (id < 1.5) return vnoise(vec3(uv.y * 60.0, uv.x * 0.8, 0.0));                                   // brushed
    if (id < 2.5) { vec2 c = floor(uv / 0.32); vec2 f = fract(uv / 0.32);                               // carbon twill
        float along = mod(c.x + c.y, 2.0) < 1.0 ? f.x : f.y; return 0.55 + 0.45 * sin(along * 3.14159 * 5.0) * (0.6 + 0.4 * sin((mod(c.x + c.y, 2.0) < 1.0 ? f.y : f.x) * 3.14159)); }
    if (id < 3.5) { float n = vnoise(p * 3.2); return 1.0 - abs(n * 2.0 - 1.0) * 0.8 + 0.2 * vnoise(p * 9.0); }   // leather
    if (id < 4.5) return 0.5 + 0.5 * sin(uv.x * 62.8) * sin(uv.y * 62.8);                              // fabric weave (1 mm)
    if (id < 5.5) return fract(length(p.xz) * 2.2 + fbm(p * vec3(0.6, 0.15, 0.6)) * 1.6);               // wood rings
    if (id < 6.5) return abs(sin((uv.x + uv.y) * 25.0)) * abs(sin((uv.x - uv.y) * 25.0));                // knurl
    if (id < 7.5) return vnoise(p * 22.0);                                                               // rubber
    if (id < 8.5) return hash3(floor(p * 90.0));                                                          // paint flake
    if (id < 9.5) return vnoise(p * 40.0);                                                               // matte bead blast
    if (id < 10.5) return fbm(p * 1.8) * 0.7 + 0.3 * step(0.93, vnoise(p * 7.0));                        // concrete / stone
    return 0.5;
}
float fin_period(float id) {
    if (id < 1.5) return 0.03; if (id < 2.5) return 0.32; if (id < 3.5) return 0.3; if (id < 4.5) return 0.1;
    if (id < 5.5) return 0.45; if (id < 6.5) return 0.25; if (id < 7.5) return 0.05; if (id < 8.5) return 0.012;
    if (id < 9.5) return 0.025; return 0.5;
}
float fin_bump(float id) {
    if (id < 1.5) return 0.10; if (id < 2.5) return 0.35; if (id < 3.5) return 0.55; if (id < 4.5) return 0.45;
    if (id < 5.5) return 0.12; if (id < 6.5) return 0.9; if (id < 7.5) return 0.18; if (id < 8.5) return 0.0;
    if (id < 9.5) return 0.08; if (id < 10.5) return 0.45; return 0.0;
}

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
float lit(float soft) {
    // soft shadow from the key light: 24-tap Poisson disc, rotated per pixel
    if (u_has_shadow < 0.5) return 1.0;
    vec2 uv = v_lp.xy * 0.5 + 0.5;
    if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) return 1.0;
    float d = v_lp.z * 0.5 + 0.5, s = 0.0;
    float ang = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) * 6.2831853;
    mat2 R = mat2(cos(ang), -sin(ang), sin(ang), cos(ang));
    for (int i = 0; i < 24; i++) {
        float fi = float(i);
        float r = sqrt((fi + 0.5) / 24.0);
        float th = fi * 2.39996323;
        vec2 o = R * vec2(cos(th), sin(th)) * r * soft * 2.6;
        vec2 e = texture2D(u_shadow, uv + o).rg;
        s += (d - 0.0022 <= e.x + e.y / 255.0) ? 1.0 : 0.0;
    }
    return s / 24.0;
}
vec3 aces(vec3 x) { return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0); }

void main() {
    vec3 V = normalize(u_eye - v_wp);
    if (u_pass > 1.5 && u_pass < 2.5) { gl_FragColor = vec4(0.0, 0.0, 0.0, u_shadow_a); return; }
    float refl = 1.0;
    if (u_pass > 2.5) {                                    // reflection: fade with depth and towards the floor's edge
        refl = 0.22 * exp(-(-v_wp.y) / max(u_height * 0.35, 0.5)) * (1.0 - smoothstep(0.3, 1.0, length(v_wp.xz) / (u_radius * 1.6)));
        V = normalize(u_eye - vec3(v_wp.x, -v_wp.y, v_wp.z));
    }
    if (u_pass > 0.5 && u_pass < 1.5) {                  // the floor
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
            float a = 1.0 - smoothstep(0.25, 1.0, r);
            float sh = lit(0.0022);
            vec3 c = mix(vec3(0.075, 0.068, 0.062), vec3(0.20, 0.188, 0.175), 1.0 - smoothstep(0.0, 0.85, r));
            c += u_accent * 0.02 * (1.0 - r);
            c *= mix(0.32, 1.0, sh);
            float spec = pow(max(dot(reflect(-V, vec3(0, 1, 0)), normalize(KEY)), 0.0), 60.0);
            c += vec3(0.08) * spec * sh;
            gl_FragColor = vec4(c, a);
        }
        return;
    }
    if (v_wp.x > u_cut) discard;
    float opacity = v_mat.w;
    bool ghost = u_iso > -0.5 && abs(v_pid - u_iso) > 0.5;
    if (u_holo < 0.5) {
        bool see = opacity < 0.99 || ghost;
        if (u_alpha_pass < 0.5 && see) discard;
        if (u_alpha_pass > 0.5 && !see) discard;
    }
    if (u_cut < 1e8 && dot(normalize(v_n), V) < 0.0 && u_pass < 2.5) {        // looking inside through the cut
        float hatch = step(0.5, fract((v_wp.y + v_wp.z) * 1.2));
        vec3 c = u_holo > 0.5 ? u_accent * (0.35 + 0.25 * hatch) : mix(vec3(0.16, 0.13, 0.11), u_accent * 0.55, 0.35 + 0.25 * hatch);
        gl_FragColor = vec4(c, 1.0);
        return;
    }
    vec3 N = normalize(v_n);
    if (u_pass > 2.5) N.y = -N.y;
    if (dot(N, V) < 0.0) N = -N;                          // thin parts: lit from both sides
    float nv = clamp(dot(N, V), 1e-3, 1.0);
    bool sel = abs(v_pid - u_sel) < 0.5;
    if (u_holo > 0.5) {
        float fres = pow(1.0 - nv, 2.2);
        float scan = 0.55 + 0.45 * sin(v_wp.y / max(u_height, 1.0) * 140.0 - u_time * 6.0);
        float band = 0.5 * exp(-pow((v_wp.y / max(u_height, 1.0) - fract(u_time * 0.35)) * 12.0, 2.0));
        float flick = 0.94 + 0.06 * sin(u_time * 53.0 + v_wp.y);
        float lum = dot(base_rgb(), vec3(0.3, 0.59, 0.11));
        vec3 tint = mix(u_accent, vec3(1.0, 0.86, 0.62), 0.25 + 0.35 * lum) * (u_has_tex > 0.5 ? 0.55 + 0.9 * lum : 1.0);
        vec3 c = tint * (0.10 + 1.7 * fres + 0.08 * scan + 0.9 * band) * flick;
        if (sel) c += vec3(1.0, 0.85, 0.55) * (0.35 + fres);
        float a = clamp(0.10 + 0.75 * fres + 0.05 * scan + 0.35 * band + (sel ? 0.2 : 0.0), 0.0, 1.0) * (ghost ? 0.18 : 1.0);
        gl_FragColor = vec4(min(c, vec3(1.0)) * a, a);     // premultiplied (colour ≤ alpha), drawn additively
        return;
    }
    vec3 alb = pow(base_rgb(), vec3(2.2));
    float metal = v_mat.x, rough = max(v_mat.y, 0.045);
    vec2 tuv = vec2(v_uv.x, 1.0 - v_uv.y);
    vec3 emi_map = vec3(0.0);
    float occ_map = 1.0;
    if (u_has_mr > 0.5) { vec3 mr = texture2D(u_mr, tuv).rgb; rough = clamp(rough * mr.g, 0.045, 1.0); metal = clamp(metal * mr.b, 0.0, 1.0); }
    if (u_has_nrm > 0.5) {
        // tangent frame from screen derivatives (no tangents needed in the file)
        vec3 dp1 = dFdx(v_wp), dp2 = dFdy(v_wp);
        vec2 du1 = dFdx(tuv), du2 = dFdy(tuv);
        vec3 p2 = cross(dp2, N), p1 = cross(N, dp1);
        vec3 T = p2 * du1.x + p1 * du2.x;
        vec3 B = p2 * du1.y + p1 * du2.y;
        float inv = inversesqrt(max(max(dot(T, T), dot(B, B)), 1e-20));
        vec3 tn = texture2D(u_nrm, tuv).xyz * 2.0 - 1.0;
        tn.xy *= u_nrm_scale;
        N = normalize(mat3(T * inv, -B * inv, N) * tn);
    }
    if (u_has_emi > 0.5) emi_map = pow(texture2D(u_emi, tuv).rgb, vec3(2.2));
    if (u_has_occ > 0.5) occ_map = texture2D(u_occ, tuv).r;
    float fid = floor(v_ext.x + 0.5), coat = 0.0, ao = v_ext.y * occ_map;
    if (fid > 0.5 && fid < 10.5) {
        // a real surface texture, at true scale, faded out where it would only shimmer
        vec3 T = normalize(abs(N.y) < 0.95 ? cross(N, vec3(0.0, 1.0, 0.0)) : cross(N, vec3(1.0, 0.0, 0.0)));
        vec3 B = cross(N, T);
        vec2 uv = vec2(dot(v_wp, T), dot(v_wp, B));
        float per = fin_period(fid);
        float px = length(fwidth(v_wp));
        float lod = 1.0 - smoothstep(per * 0.35, per * 1.1, px);
        float e = per * 0.18;
        float h0 = fin_h(fid, v_wp, uv);
        float hu = fin_h(fid, v_wp + T * e, uv + vec2(e, 0.0));
        float hv = fin_h(fid, v_wp + B * e, uv + vec2(0.0, e));
        float k = fin_bump(fid) * lod;
        N = normalize(N - (T * (hu - h0) + B * (hv - h0)) * k * 2.0);
        if (fid < 1.5) { rough = clamp(rough * (0.75 + 0.55 * h0 * lod) , 0.05, 1.0); }
        else if (fid < 2.5) { alb *= mix(1.0, 0.55 + 0.6 * h0, lod); rough = mix(rough, 0.22 + 0.25 * (1.0 - h0), lod); }
        else if (fid < 3.5) { rough = clamp(rough + 0.25 * h0 * lod, 0.3, 1.0); alb *= mix(1.0, 0.85 + 0.25 * h0, lod); }
        else if (fid < 4.5) { rough = max(rough, 0.82); alb *= mix(1.0, 0.8 + 0.3 * h0, lod); }
        else if (fid < 5.5) { alb *= mix(0.62, 1.12, smoothstep(0.1, 0.9, h0)) * (0.9 + 0.2 * vnoise(v_wp * vec3(9.0, 0.6, 9.0))); rough = max(rough, 0.45); }
        else if (fid < 6.5) { rough = clamp(rough + 0.15 * h0 * lod, 0.2, 1.0); }
        else if (fid < 7.5) { rough = max(rough, 0.86); alb *= 0.92 + 0.12 * h0 * lod; }
        else if (fid < 8.5) { coat = 1.0; alb *= 0.96 + 0.1 * h0 * lod; }
        else if (fid < 9.5) { rough = max(rough, 0.72) + 0.12 * h0 * lod; }
        else { alb *= 0.82 + 0.35 * h0; rough = max(rough, 0.88); }
    }
    float a = rough * rough;
    vec3 F0 = mix(vec3(0.04), alb, metal);
    vec3 col = vec3(0.0);
    vec3 Ls[3]; Ls[0] = normalize(KEY); Ls[1] = normalize(FILL); Ls[2] = normalize(RIM);
    vec3 Cs[3]; Cs[0] = vec3(2.7, 2.57, 2.4); Cs[1] = vec3(0.65, 0.78, 1.05); Cs[2] = u_accent * 1.6 + vec3(0.6);
    float sh = lit(0.0012);
    if (dot(N, V) < 0.0) N = normalize(N + V * (0.01 - dot(N, V)));          // a bump must not face away
    nv = clamp(dot(N, V), 1e-3, 1.0);
    for (int i = 0; i < 3; i++) {
        vec3 L = Ls[i]; vec3 H = normalize(L + V);
        float nl = max(dot(N, L), 0.0), nh = max(dot(N, H), 0.0), vh = max(dot(V, H), 0.0);
        vec3 F = F0 + (1.0 - F0) * pow(1.0 - vh, 5.0);
        vec3 spec = F * ggx(nh, a) * vis(nl, nv, a) * 0.25;
        vec3 kd = (1.0 - F) * (1.0 - metal);
        vec3 cc = vec3(0.0);
        if (coat > 0.5) { float Fc = 0.04 + 0.96 * pow(1.0 - vh, 5.0); cc = vec3(Fc * ggx(nh, 0.0025) * vis(nl, nv, 0.0025) * 0.25); }
        col += ((kd * alb + spec) * mix(1.0, ao, 0.35) + cc) * Cs[i] * nl * (i == 0 ? sh : 1.0);
    }
    vec3 R = reflect(-V, N);
    vec3 Fe = F0 + (max(vec3(1.0 - rough), F0) - F0) * pow(1.0 - nv, 5.0);
    float sky = 0.5 + 0.5 * N.y;
    vec3 amb = mix(vec3(0.05, 0.045, 0.04) + u_accent * 0.02, vec3(0.16, 0.17, 0.19), sky);
    col += amb * alb * (1.0 - metal) * ao;
    col += env(R, rough) * Fe * (1.0 - 0.6 * rough) * mix(0.55, 1.0, sh) * mix(ao, 1.0, 0.25);
    if (coat > 0.5) col += env(R, 0.03) * (0.04 + 0.96 * pow(1.0 - nv, 5.0)) * mix(0.6, 1.0, sh) * ao;
    float contact = mix(0.72, 1.0, smoothstep(0.0, u_radius * 0.12, v_wp.y));  // a little extra darkening right at the floor
    col *= contact;
    col += (u_has_emi > 0.5 ? emi_map * max(v_mat.z, 1.0) : pow(base_rgb(), vec3(2.2)) * v_mat.z) * 3.0;   // screens, LEDs
    if (sel) col += u_accent * (0.25 + 0.9 * pow(1.0 - nv, 2.0));
    col = aces(col * 1.05);
    col = pow(col, vec3(1.0 / 2.2));
    float alpha = u_alpha_pass > 0.5 ? clamp(opacity + 0.5 * pow(1.0 - nv, 3.0), 0.0, 1.0) : 1.0;
    alpha *= refl;
    if (ghost && u_alpha_pass > 0.5) { col = mix(col, vec3(dot(col, vec3(0.3, 0.59, 0.11))), 0.7); alpha = 0.10 * refl; }
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
        target = np.array([0.0, mesh.size[1] * 0.5, 0.0])
        aspect = w / max(1, h)
        half_v = math.radians(34.0) / 2
        half_h = math.atan(math.tan(half_v) * aspect)
        fit = r / math.sin(min(half_v, half_h))           # the bounding sphere fits the view
        dist = fit * 1.12 / max(0.2, self.zoom)
        y, p = math.radians(self.yaw), math.radians(max(-85, min(85, self.pitch)))
        eye = target + dist * np.array([math.cos(p) * math.sin(y), math.sin(p), math.cos(p) * math.cos(y)])
        view = look_at(eye, target)
        right, up = view[0, :3], view[1, :3]
        shift = (right * self.pan[0] - up * self.pan[1]) * r * 2.0
        view = look_at(eye + shift, target + shift)
        proj = perspective(34.0, aspect, max(0.01, dist - r * 3), dist + r * 4)
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
        self._sprog = self._sfbo = None
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
            for i, name in enumerate(("a_pos", "a_nrm", "a_col", "a_mat", "a_pid", "a_ext", "a_uv")):
                prog.bindAttributeLocation(name, i)
            if not prog.link():
                raise RuntimeError("gölgelendirici bağlanamadı: " + prog.log())
            sp = QOpenGLShaderProgram()
            if not (sp.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERT_SHADOW)
                    and sp.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAG_SHADOW)):
                raise RuntimeError("gölge gölgelendiricisi: " + sp.log())
            sp.bindAttributeLocation("a_pos", 0)
            if not sp.link():
                raise RuntimeError("gölge gölgelendiricisi bağlanamadı: " + sp.log())
            self._sprog = sp
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
        """Framebuffers by size (the live view and the still frame each keep
        theirs). 8× multisampling for normal sizes, fewer samples for huge ones."""
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        cache = self.__dict__.setdefault("_fbos", {})
        if (w, h) in cache:
            self._fbo, self._fbo_size = cache[(w, h)], (w, h)
            return
        px = w * h
        tries = (8, 4, 0) if px <= 4_200_000 else (4, 2, 0) if px <= 9_000_000 else (2, 0)
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        fbo = None
        for n in tries:
            fmt.setSamples(n)
            fbo = QOpenGLFramebufferObject(QSize(w, h), fmt)
            if fbo.isValid():
                break
        if fbo is None or not fbo.isValid():
            raise RuntimeError("çerçeve arabelleği oluşturulamadı")
        if len(cache) >= 2:                                   # keep the newest two sizes
            cache.pop(next(iter(cache)))
        cache[(w, h)] = fbo
        self._fbo, self._fbo_size = fbo, (w, h)

    def _light(self, prog, mesh):
        for name, v in (("u_lu", _LU), ("u_lv", _LV), ("u_ll", _KEY), ("u_lc", (0.0, float(mesh.size[1]) * 0.5, 0.0))):
            prog.setUniformValue(name, QVector3D(*[float(x) for x in v]))
        ext = float(mesh.radius) * 1.7
        if hasattr(prog, "setUniformValue1f"):
            prog.setUniformValue1f("u_ext", ext)
        else:
            prog.setUniformValue("u_ext", ext)

    def _shadow_pass(self, mesh):
        """Depth of the model seen from the key light: soft self-shadows and
        the shadow on the floor."""
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        gl, sp = self._gl, self._sprog
        if self._sfbo is None:
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setAttachment(QOpenGLFramebufferObject.Attachment.Depth)
            self._sfbo = QOpenGLFramebufferObject(QSize(SHADOW, SHADOW), fmt)
            if not self._sfbo.isValid():
                raise RuntimeError("gölge arabelleği oluşturulamadı")
        self._sfbo.bind()
        gl.glViewport(0, 0, SHADOW, SHADOW)
        gl.glClearColor(1.0, 1.0, 1.0, 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_DEPTH_TEST); gl.glDepthFunc(GL_LEQUAL); gl.glDepthMask(True)
        gl.glDisable(GL_BLEND); gl.glDisable(GL_CULL_FACE)
        sp.bind()
        sp.setUniformValue("u_off", QVector3D(*[float(x) for x in Camera.offset(mesh)]))
        self._light(sp, mesh)
        self._vbo.bind()
        sp.enableAttributeArray(0)
        sp.setAttributeBuffer(0, GL_FLOAT, 0, 3, STRIDE * 4)
        gl.glDrawArrays(GL_TRIANGLES, 0, mesh.n_vert)
        sp.disableAttributeArray(0)
        self._vbo.release()
        sp.release()
        self._sfbo.release()

    def _upload(self, mesh, explode: float):
        if mesh is self._mesh and abs(explode - self._explode) < 1e-4:
            return
        buf = np.zeros((mesh.n_vert, STRIDE), np.float32)
        buf[:, 0:3] = mesh.positions(explode)
        buf[:, 3:6], buf[:, 6:9], buf[:, 9:13], buf[:, 13] = mesh.nrm, mesh.col, mesh.mat, mesh.pid
        buf[:, 14], buf[:, 15] = mesh.fin, mesh.ao
        buf[:, 16:18] = getattr(mesh, "uv", 0.0)
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

    def _gl_tex(self, arr):
        from PyQt6.QtOpenGL import QOpenGLTexture
        a = np.ascontiguousarray(arr)
        img = QImage(a.data, a.shape[1], a.shape[0], a.shape[1] * 4, QImage.Format.Format_RGBA8888).copy()
        t = QOpenGLTexture(img, QOpenGLTexture.MipMapGeneration.GenerateMipMaps)
        t.setMinificationFilter(QOpenGLTexture.Filter.LinearMipMapLinear)
        t.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
        t.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
        try:
            t.setMaximumAnisotropy(8.0)
        except Exception:
            pass
        return t

    def _textures(self, mesh):
        """GPU textures of a scanned mesh (made once per mesh): per draw a dict
        of base / mr / normal / emissive / occlusion maps."""
        cache = self.__dict__.setdefault("_tex", {})
        if cache.get("mesh") is not mesh:
            for d in cache.get("list", []):
                for t in d.values():
                    try:
                        t.destroy()
                    except Exception:
                        pass
            lst = []
            for entry in getattr(mesh, "textures", []) or []:
                if not isinstance(entry, dict):
                    entry = {"base": entry}
                lst.append({k: self._gl_tex(v) for k, v in entry.items() if k != "normal_scale" and v is not None})
                lst[-1]["_scale"] = entry.get("normal_scale", 1.0)
            cache.update(mesh=mesh, list=lst)
        return cache["list"]

    _UNITS = (("base", 1, "u_has_tex"), ("mr", 2, "u_has_mr"), ("normal", 3, "u_has_nrm"), ("emissive", 4, "u_has_emi"),
              ("occlusion", 5, "u_has_occ"))

    def _draw_model(self, mesh):
        """The model, range by range, each with its maps."""
        gl = self._gl
        texs = self._textures(mesh) if getattr(mesh, "textures", None) else []
        for first, count, ti in getattr(mesh, "draws", [(0, mesh.n_vert, None)]):
            d = texs[ti] if ti is not None and ti < len(texs) else {}
            for key, unit, flag in self._UNITS:
                t = d.get(key)
                if t is not None:
                    t.bind(unit)
                self._u(flag, 1.0 if t is not None else 0.0)
            self._u("u_nrm_scale", float(d.get("_scale", 1.0)))
            gl.glDrawArrays(GL_TRIANGLES, first, count)
        for _key, _unit, flag in self._UNITS:
            self._u(flag, 0.0)

    def _attrs(self, vbo, on: bool):
        prog = self._prog
        if on:
            vbo.bind()
            for loc, (off, size) in enumerate(((0, 3), (3, 3), (6, 3), (9, 4), (13, 1), (14, 2), (16, 2))):
                prog.enableAttributeArray(loc)
                prog.setAttributeBuffer(loc, GL_FLOAT, off * 4, size, STRIDE * 4)
        else:
            for loc in range(7):
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

    # ── ambient occlusion, baked a few directions per frame ──────────────────
    AO_DIRS, AO_RES, AO_PER_FRAME = 32, 1024, 4

    def ao_ready(self, mesh) -> bool:
        job = self.__dict__.get("_ao")
        return bool(job and job["mesh"] is mesh and job["i"] >= len(job["dirs"]))

    def _ao_step(self, mesh):
        """Light from the whole sky, blocked by the model itself: render the
        model's depth from AO_DIRS directions over the upper hemisphere and
        count, per vertex, from how many it is visible. Crevices, the inside of
        a cup, the gap under a lid come out darker — the depth real photos have."""
        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        job = self.__dict__.get("_ao")
        if job is None or job["mesh"] is not mesh:
            n = self.AO_DIRS
            k = np.arange(n) + 0.5
            y = 0.08 + 0.92 * (k / n)                       # upper hemisphere, denser near the top
            r = np.sqrt(1 - y * y)
            th = k * 2.399963
            dirs = np.c_[np.cos(th) * r, y, np.sin(th) * r]
            job = self._ao = {"mesh": mesh, "dirs": dirs, "i": 0, "acc": np.zeros(mesh.n_vert), "w": np.zeros(mesh.n_vert)}
        if job["i"] >= len(job["dirs"]):
            return False
        gl, sp = self._gl, self._sprog
        if self.__dict__.get("_aofbo") is None:
            fmt = QOpenGLFramebufferObjectFormat()
            fmt.setAttachment(QOpenGLFramebufferObject.Attachment.Depth)
            self._aofbo = QOpenGLFramebufferObject(QSize(self.AO_RES, self.AO_RES), fmt)
        off = Camera.offset(mesh)
        P = mesh.pos0 - off
        c = np.array([0.0, mesh.size[1] * 0.5, 0.0])
        ext = mesh.radius * 1.05
        for _ in range(self.AO_PER_FRAME):
            if job["i"] >= len(job["dirs"]):
                break
            d = job["dirs"][job["i"]]; job["i"] += 1
            up = np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.95 else np.array([1.0, 0.0, 0.0])
            u = np.cross(up, d); u /= np.linalg.norm(u)
            v = np.cross(d, u)
            self._aofbo.bind()
            gl.glViewport(0, 0, self.AO_RES, self.AO_RES)
            gl.glClearColor(1.0, 1.0, 1.0, 1.0)
            gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            gl.glEnable(GL_DEPTH_TEST); gl.glDepthFunc(GL_LEQUAL); gl.glDepthMask(True); gl.glDisable(GL_BLEND)
            sp.bind()
            sp.setUniformValue("u_off", QVector3D(*[float(x) for x in off]))
            for name, vv in (("u_lu", u), ("u_lv", v), ("u_ll", d), ("u_lc", c)):
                sp.setUniformValue(name, QVector3D(*[float(x) for x in vv]))
            if hasattr(sp, "setUniformValue1f"):
                sp.setUniformValue1f("u_ext", float(ext))
            else:
                sp.setUniformValue("u_ext", float(ext))
            self._vbo.bind(); sp.enableAttributeArray(0); sp.setAttributeBuffer(0, GL_FLOAT, 0, 3, STRIDE * 4)
            gl.glDrawArrays(GL_TRIANGLES, 0, mesh.n_vert)
            sp.disableAttributeArray(0); self._vbo.release(); sp.release()
            img = self._aofbo.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            self._aofbo.release()
            ptr = img.constBits(); ptr.setsize(img.sizeInBytes())
            arr = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()]
            depth = arr[:, :, 0].astype(np.float32) / 255.0 + arr[:, :, 1].astype(np.float32) / 65025.0
            q = P - c
            lx, ly, lz = q @ u / ext, q @ v / ext, -(q @ d) / ext
            res = self.AO_RES
            px = np.clip(((lx * 0.5 + 0.5) * (res - 1)).astype(int), 0, res - 1)
            py = np.clip(((1 - (ly * 0.5 + 0.5)) * (res - 1)).astype(int), 0, res - 1)    # toImage is top-down
            seen = (lz * 0.5 + 0.5) - 0.004 <= depth[py, px]
            wgt = np.clip(mesh.nrm @ d, 0, None)
            job["acc"] += seen * wgt
            job["w"] += wgt
        if job["i"] >= len(job["dirs"]):
            ao = np.where(job["w"] > 1e-6, job["acc"] / np.maximum(job["w"], 1e-6), 0.55)
            mesh.ao = (0.18 + 0.82 * np.clip(ao, 0, 1) ** 1.2).astype(np.float32)
            self._explode = -1.0                              # upload again with the AO
        return True

    def render(self, mesh, cam: Camera, w: int, h: int, *, holo: bool, accent, t: float,
               explode: float = 0.0, sel: int = -1, cut: float = 1e9, iso: int = -1) -> QImage | None:
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
            if not holo and explode < 1e-3:
                self._upload(mesh, 0.0)
                try:
                    self._ao_step(mesh)
                except Exception as exc:                          # AO is a bonus: never cost the frame
                    print(f"[Hologram] AO: {exc}")
                    self._ao = {"mesh": mesh, "dirs": [], "i": 0}
            self._upload(mesh, explode)
            mvp, eye = cam.matrices(mesh, w, h)
            if not holo:
                self._shadow_pass(mesh)
            self._fbo.bind()
            gl.glViewport(0, 0, w, h)
            gl.glClearColor(0, 0, 0, 0)
            gl.glClearStencil(0)
            gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_STENCIL_BUFFER_BIT)
            prog.bind()
            prog.setUniformValue("u_mvp", _qmat(mvp))
            self._u("u_eye", eye); self._u("u_accent", accent); self._u("u_time", t)
            self._u("u_holo", 1.0 if holo else 0.0); self._u("u_sel", float(sel))
            self._u("u_cut", float(cut)); self._u("u_iso", float(iso))
            self._u("u_radius", mesh.radius); self._u("u_height", float(mesh.size[1]))
            self._u("u_ldir", (0, -1, 0)); self._u("u_shadow_a", 0.0); self._u("u_alpha_pass", 0.0)
            self._light(prog, mesh)
            self._u("u_has_shadow", 0.0 if holo else 1.0)
            if not holo:
                gl.glActiveTexture(0x84C0)                                 # GL_TEXTURE0
                gl.glBindTexture(0x0DE1, self._sfbo.texture())
                for pname in (0x2801, 0x2800):                             # nearest
                    gl.glTexParameteri(0x0DE1, pname, 0x2600)
                for pname in (0x2802, 0x2803):                             # clamp to edge
                    gl.glTexParameteri(0x0DE1, pname, 0x812F)
                prog.setUniformValue("u_shadow", 0)
            for name, unit in (("u_tex", 1), ("u_mr", 2), ("u_nrm", 3), ("u_emi", 4), ("u_occ", 5)):
                prog.setUniformValue(name, unit)
            gl.glDisable(GL_CULL_FACE)
            # floor
            self._u("u_off", (0, 0, 0)); self._u("u_pass", 1.0)
            gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            gl.glDisable(GL_DEPTH_TEST)
            self._attrs(self._floor, True); gl.glDrawArrays(GL_TRIANGLES, 0, 6); self._attrs(self._floor, False)
            off = Camera.offset(mesh)
            self._u("u_off", off)
            if not holo:
                self._attrs(self._vbo, True)
                # the reflection in the floor's gloss
                self._u("u_pass", 3.0); self._u("u_has_shadow", 0.0)
                gl.glEnable(GL_DEPTH_TEST); gl.glDepthFunc(GL_LEQUAL); gl.glDepthMask(True)
                gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
                self._draw_model(mesh)
                gl.glClear(GL_DEPTH_BUFFER_BIT)
                self._u("u_has_shadow", 1.0)
                # the model: opaque parts, then glass
                self._u("u_pass", 0.0)
                gl.glEnable(GL_DEPTH_TEST); gl.glDepthFunc(GL_LEQUAL); gl.glDepthMask(True)
                gl.glDisable(GL_BLEND)
                self._draw_model(mesh)
                self._u("u_alpha_pass", 1.0)
                gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA); gl.glDepthMask(False)
                self._draw_model(mesh)
                gl.glDepthMask(True)
                self._attrs(self._vbo, False)
            else:
                self._u("u_pass", 0.0)
                gl.glDisable(GL_DEPTH_TEST)
                gl.glEnable(GL_BLEND); gl.glBlendFunc(GL_ONE, GL_ONE)
                self._attrs(self._vbo, True); self._draw_model(mesh); self._attrs(self._vbo, False)
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


def render_still(gl: "HoloGL", mesh, cam: Camera, w: int, h: int, ss: float = 1.5, **kw) -> QImage | None:
    """A finished frame: rendered ss× larger (and 8× multisampled) then scaled
    down smoothly — edges and thin details come out clean, as in a 4K render."""
    from PyQt6.QtCore import Qt
    big = None
    for k in (ss, 1.5, 1.25, 1.0):
        k = min(k, math.sqrt(14_000_000 / max(1, w * h)))        # at most ~14 million pixels
        k = max(1.0, k)
        bw, bh = int(w * k), int(h * k)
        if bw > 8192 or bh > 8192:
            continue
        big = gl.render(mesh, cam, bw, bh, **kw)
        if big is not None:
            break
        if gl.ok is False and gl._ctx is not None:                  # a too-large buffer: try smaller
            gl.ok = True
            gl.__dict__.get("_fbos", {}).pop((bw, bh), None)
    if big is None:
        return None
    if big.width() == w:
        return big
    return big.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def bloom(img: QImage, strength: float = 0.6) -> QImage:
    """A soft glow around the brightest pixels (LEDs, screens, hot highlights)
    — what a camera lens does, and what makes a render read as a photograph."""
    try:
        import cv2
    except ImportError:
        return img
    try:
        im = img.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = im.width(), im.height()
        ptr = im.constBits(); ptr.setsize(im.sizeInBytes())
        a = np.frombuffer(ptr, np.uint8).reshape(h, im.bytesPerLine())[:, :w * 4].reshape(h, w, 4).astype(np.float32) / 255.0
        rgb, alpha = a[:, :, :3], a[:, :, 3:4]
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        bright = rgb * np.clip((lum - 0.72) / 0.28, 0.0, 1.0)[:, :, None]
        small = cv2.resize(bright, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
        glow = np.zeros_like(small)
        for sigma in (2.0, 6.0, 16.0):                       # three widths: tight halo + wide haze
            glow += cv2.GaussianBlur(small, (0, 0), sigma)
        glow = cv2.resize(glow / 3.0, (w, h), interpolation=cv2.INTER_LINEAR)
        out = 1.0 - (1.0 - rgb) * (1.0 - np.clip(glow * strength, 0, 1))       # screen blend: never clips hard
        g_a = np.clip(glow.max(axis=2, keepdims=True) * strength, 0, 1)
        res = np.concatenate([out, np.maximum(alpha, g_a)], axis=2)
        res = np.ascontiguousarray((np.clip(res, 0, 1) * 255).astype(np.uint8))
        return QImage(res.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    except Exception:
        return img


class SoftRenderer:
    """No OpenGL: flat-shaded triangles with QPainter, far to near. Plainer,
    but every machine can draw it."""

    MAX_TRI = 9000

    def render(self, mesh, cam: Camera, w, h, *, holo, accent, t, explode=0.0, sel=-1, cut=1e9, iso=-1) -> QImage:
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
