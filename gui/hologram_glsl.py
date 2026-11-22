"""Reference-style cyan hologram shader; no photoreal skin, hair or human eyeballs.

Uses the same posed 3D head/shoulder mesh as the old renderer, so head rotation,
speech-driven jaw and eyelid animations remain live. The visible form is made
from surface-space luminous contour slices rather than a flat portrait texture.
"""

FRAG_HOLOGRAM = """
#version 120
varying vec3 v_n;
varying vec3 v_rest;
varying vec3 v_pos;
varying vec4 v_misc;
uniform float u_time;
uniform float u_glow;
uniform float u_muted;
uniform float u_mouth;
uniform float u_open;
uniform float u_scale;
uniform vec2 u_eye_x;
uniform vec2 u_eye_c;
uniform vec4 u_eye_up;
uniform vec4 u_eye_lo;
uniform vec4 u_lip_uo;
uniform vec4 u_lip_lo;
uniform vec4 u_lip_ui;
uniform vec4 u_lip_li;
uniform vec2 u_lip_w;

float poly(vec4 c, float x) {
    return c.x + x * (c.y + x * (c.z + x * c.w));
}
float contour(float d, float width) {
    float aa = max(fwidth(d), 0.001);
    return 1.0 - smoothstep(width, width + 1.3 * aa, abs(d));
}
void main() {
    vec3 p = v_rest;
    vec3 n = normalize(v_n);
    float fade = clamp(v_misc.z, 0.0, 1.0);
    float ndv = clamp(n.z, 0.0, 1.0);
    float key = clamp(dot(n, normalize(vec3(-0.45, 0.5, 0.77))), 0.0, 1.0);
    float rim = pow(1.0 - ndv, 3.1);
    float ax = abs(p.x);
    float face = smoothstep(0.05, 0.38, p.z) *
                 (1.0 - step(0.5, v_misc.w));
    float front = face * smoothstep(0.05, 0.25, ndv);

    // A real hologram does not print straight parallel stripes across the
    // nose and eyelids. The scan contours bend around measured facial
    // anatomy. These small, smooth distortions follow the head as it rotates.
    float bridge = exp(-pow(p.x / 0.16, 2.0) -
                       pow((p.y + 0.09) / 0.30, 2.0));
    float tip = exp(-pow(p.x / 0.15, 2.0) -
                    pow((p.y + 0.27) / 0.095, 2.0));
    float eyeSocket = exp(-pow((ax - u_eye_c.x) / 0.155, 2.0) -
                          pow((p.y - u_eye_c.y) / 0.09, 2.0));
    float cheek = exp(-pow((ax - 0.30) / 0.19, 2.0) -
                      pow((p.y + 0.19) / 0.18, 2.0));
    // Mostly screen-horizontal like the user's approved render, not concentric
    // loops on the skull or twisting fingerprints around nose and eyes. A
    // *small* portion of the surface coordinates makes the pattern breathe
    // with a turning 3D face while the visible stripes stay calm and clean.
    float horizontal = v_pos.y / max(u_scale, 1.0);
    float contourY = mix(horizontal, p.y, 0.13) +
                     face * (0.0028 * bridge - 0.0018 * tip -
                             0.0025 * eyeSocket + 0.0018 * cheek);

    // Subpixel anti-aliased neon scan lines.
    float frequency = clamp(u_scale * 0.19, 34.0, 88.0);
    float phase = contourY * frequency;
    float d = abs(fract(phase) - 0.5);
    float halfwidth = clamp(0.11 + 0.22 * fwidth(phase), 0.11, 0.34);
    float bands = 1.0 - smoothstep(halfwidth * 0.50, halfwidth, d);

    // Concentrate bright light at the contour while leaving deep blue
    // negative space between fine lines.
    float relief = 0.22 + 0.37 * key + 0.49 * rim;
    float lineLight = bands * relief;
    float eyes = 0.0;
    if (front > 0.0 && ax > u_eye_x.x - 0.015 && ax < u_eye_x.y + 0.015) {
        float t = clamp((ax - u_eye_x.x) /
                        max(0.015, u_eye_x.y - u_eye_x.x), 0.0, 1.0);
        float ends = smoothstep(0.0, 0.10, t) *
                     (1.0 - smoothstep(0.88, 1.0, t));
        // Almond lid arcs, not large pupil-less geometric ellipses.
        float arc = sin(3.14159265 * t);
        float upper = poly(u_eye_up, ax) + 0.005 * arc;
        float lower = poly(u_eye_lo, ax) - 0.0025 * arc;
        float lid = mix(lower, upper, clamp(u_open, 0.0, 1.0));
        eyes = max(contour(p.y - lid, 0.0010),
                   contour(p.y - lower, 0.0010)) * ends;
        // Sculpted brow ridge, faintly above the lid; no pupil or iris.
        eyes += 0.22 * contour(p.y - upper - 0.024 * arc,
                               0.0016) * ends;
    }

    // Only a luminous lip contour and an animated opening, not teeth or skin.
    float lips = 0.0;
    float mouthCavity = 0.0;
    if (front > 0.0 && ax < u_lip_w.x + 0.008) {
        float taper = 1.0 - smoothstep(u_lip_w.x * 0.80, u_lip_w.x, ax);
        float upper = poly(u_lip_uo, ax);
        float lower = poly(u_lip_lo, ax);
        float innerUpper = poly(u_lip_ui, ax);
        float innerLower = poly(u_lip_li, ax);
        // At rest the mouth is a thin single luminous line, like the user's
        // image. Split into independently moving lips only while talking.
        float talk = smoothstep(0.10, 0.48, clamp(u_mouth, 0.0, 1.0));
        float mid = 0.5 * (upper + lower);
        // The reference keeps a relaxed, gently curved mouth even when the
        // assistant speaks; avoid a large horizontal oval or bright teeth.
        float smile = 0.005 * pow(ax / max(u_lip_w.x, 0.01), 2.0);
        float opening = 0.024 * talk * taper;
        float topLine = mix(mid + smile, upper, talk * 0.52);
        float bottomLine = topLine - opening;
        lips = max(contour(p.y - topLine, 0.0012),
                   talk * contour(p.y - bottomLine, 0.0012)) * taper;
        lips += talk * 0.12 * contour(p.y - innerUpper, 0.0013) * taper;
        mouthCavity = smoothstep(innerLower - opening - 0.003,
                                 innerLower + 0.003, p.y);
        mouthCavity *= 1.0 - smoothstep(innerUpper - 0.003,
                                       innerUpper + 0.003, p.y);
        mouthCavity *= taper * talk;
    }
    float features = front * (0.90 * eyes + 0.75 * lips);
    float pulse = 0.95 + 0.05 * sin(u_time * 1.4) + 0.13 * u_glow;

    // Dark translucent interior, bright electric cyan scan lines and edge.
    vec3 night = vec3(0.002, 0.050, 0.14);
    vec3 neon = vec3(0.010, 0.70, 1.25);
    vec3 ice = vec3(0.23, 0.96, 1.39);
    vec3 col = night * (0.18 + 0.12 * key);
    // Intentionally emissive: the reference is a lit projection, not an
    // opaque blue mannequin. The edge is several times brighter than
    // the inter-line interior, with dynamic voice-synchronised highlights.
    col += neon * lineLight * (1.45 + 0.24 * u_glow);
    // Add a subtle translucent anatomical bloom at the nose and cheekbones
    // so the scanline portrait has depth instead of looking like a striped egg.
    float ridge = face * (0.35 * bridge + 0.28 * tip +
                          0.17 * cheek) * max(key, 0.22);
    col += neon * ridge * 0.27;
    float bust = 1.0 - smoothstep(-1.67, -1.14, p.y);
    col += ice * rim * (2.48 + 0.45 * u_glow) * mix(1.0, 0.57, bust);
    col += ice * features * 1.15;
    col *= 1.0 - 0.75 * mouthCavity;
    col *= pulse * (1.0 - 0.44 * u_muted);
    float alpha = clamp(0.080 + 1.33 * lineLight + 1.40 * rim +
                        0.93 * features, 0.0, 1.0) * fade;
    col = vec3(1.0) - exp(-max(col, vec3(0.0)) * 2.10);
    gl_FragColor = vec4(col * alpha, alpha);
}
"""
