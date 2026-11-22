"""Reference-style cyan hologram shader; no photoreal skin, hair or human eyeballs.

Uses the same posed 3D head/shoulder mesh as the old renderer, so head rotation,
speech-driven jaw and eyelid animations remain live. The visible form is made
from surface-space luminous contour slices rather than a flat portrait texture.
"""

FRAG_HOLOGRAM = """
#version 120
varying vec3 v_n;
varying vec3 v_rest;
varying vec4 v_misc;
uniform float u_time;
uniform float u_glow;
uniform float u_muted;
uniform float u_mouth;
uniform float u_open;
uniform float u_scale;
uniform vec2 u_eye_x;
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
    float rim = pow(1.0 - ndv, 2.1);

    // Close horizontal lines wrap the 3D surface and move with the head.
    // Reduce line density for small HUD canvases to prevent aliasing.
    float frequency = clamp(u_scale * 0.18, 34.0, 83.0);
    float phase = p.y * frequency;
    float d = abs(fract(phase) - 0.5);
    float halfwidth = clamp(0.075 + 0.25 * fwidth(phase), 0.10, 0.35);
    float bands = 1.0 - smoothstep(halfwidth * 0.48, halfwidth, d);

    float relief = 0.38 + 0.50 * key + 0.25 * rim;
    float lineLight = bands * relief;
    float front = (p.z > 0.05 && v_misc.w < 0.5 && ndv > 0.10) ? 1.0 : 0.0;
    float ax = abs(p.x);
    float eyes = 0.0;
    if (front > 0.0 && ax > u_eye_x.x - 0.015 && ax < u_eye_x.y + 0.015) {
        float t = clamp((ax - u_eye_x.x) /
                        max(0.015, u_eye_x.y - u_eye_x.x), 0.0, 1.0);
        float ends = smoothstep(0.0, 0.10, t) *
                     (1.0 - smoothstep(0.88, 1.0, t));
        float upper = poly(u_eye_up, ax);
        float lower = poly(u_eye_lo, ax);
        float lid = mix(lower, upper, clamp(u_open, 0.0, 1.0));
        eyes = max(contour(p.y - lid, 0.0015),
                   contour(p.y - lower, 0.0015)) * ends;
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
        float opening = 0.050 * clamp(u_mouth, 0.0, 1.0) * taper;
        lips = max(contour(p.y - upper, 0.002),
                   contour(p.y - (lower - opening), 0.002)) * taper;
        lips += 0.5 * contour(p.y - innerUpper, 0.0015) * taper;
        mouthCavity = smoothstep(innerLower - opening - 0.003,
                                 innerLower + 0.003, p.y);
        mouthCavity *= 1.0 - smoothstep(innerUpper - 0.003,
                                       innerUpper + 0.003, p.y);
        mouthCavity *= taper * clamp(0.3 + 2.0 * u_mouth, 0.0, 1.0);
    }
    float features = front * (0.90 * eyes + 0.75 * lips);
    float pulse = 0.95 + 0.05 * sin(u_time * 1.4) + 0.13 * u_glow;

    // Dark translucent interior, bright electric cyan scan lines and edge.
    vec3 night = vec3(0.002, 0.075, 0.17);
    vec3 neon = vec3(0.020, 0.80, 1.42);
    vec3 ice = vec3(0.52, 1.14, 1.48);
    vec3 col = night * (0.18 + 0.12 * key);
    // Intentionally emissive: the reference is a lit projection, not an
    // opaque blue mannequin. The edge is several times brighter than
    // the inter-line interior, with dynamic voice-synchronised highlights.
    col += neon * lineLight * (1.82 + 0.22 * u_glow);
    col += ice * rim * (2.20 + 0.42 * u_glow);
    col += ice * features * 1.75;
    col *= 1.0 - 0.75 * mouthCavity;
    col *= pulse * (1.0 - 0.44 * u_muted);
    float alpha = clamp(0.080 + 1.33 * lineLight + 1.40 * rim +
                        0.93 * features, 0.0, 1.0) * fade;
    col = vec3(1.0) - exp(-max(col, vec3(0.0)) * 2.10);
    gl_FragColor = vec4(col * alpha, alpha);
}
"""
