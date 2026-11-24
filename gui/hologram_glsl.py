"""Volume-lit female hologram with restrained surface sampling.

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
uniform vec2 u_nose_tip;
uniform vec2 u_nose_bridge;
uniform vec2 u_gaze;
uniform vec3 u_brow;
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
    float bridge = exp(-pow((p.x - u_nose_bridge.x) / 0.16, 2.0) -
                       pow((p.y - u_nose_bridge.y) / 0.30, 2.0));
    float tip = exp(-pow((p.x - u_nose_tip.x) / 0.15, 2.0) -
                    pow((p.y - u_nose_tip.y) / 0.095, 2.0));
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
    // Finer hologram sampling recreates the high-density reference scanlines
    // without mapping a photograph to the surface.
    float frequency = clamp(u_scale * 0.30, 48.0, 116.0);
    float phase = contourY * frequency;
    float d = abs(fract(phase) - 0.5);
    float halfwidth = clamp(0.08 + 0.16 * fwidth(phase), 0.08, 0.25);
    float bands = 1.0 - smoothstep(halfwidth * 0.50, halfwidth, d);

    // Concentrate bright light at the contour while leaving deep blue
    // negative space between fine lines.
    float relief = 0.22 + 0.37 * key + 0.49 * rim;
    float lineLight = bands * relief;
    // A fine triangular light network follows the three-dimensional surface.
    float gridScale = clamp(u_scale * 0.09, 14.0, 34.0);
    vec2 grid = vec2(p.x, p.y + p.z * 0.16) * gridScale;
    float diagonalA = abs(fract(grid.x * 0.866 + grid.y * 0.5) - 0.5);
    float diagonalB = abs(fract(grid.x * 0.866 - grid.y * 0.5) - 0.5);
    float gridAA = max(fwidth(grid.x), 0.015);
    float network = (1.0 - smoothstep(0.035, 0.035 + gridAA, min(diagonalA, diagonalB))) * front;
    // Iris and pupil are procedural shader geometry painted on the moving
    // face mesh. They follow the real eye landmarks, head rotation, blinking,
    // gaze and ambient lighting; no photo, sprite, UV atlas or texture.
    float eyes = 0.0;
    float iris = 0.0;
    float irisRing = 0.0;
    float pupil = 0.0;
    float irisThreads = 0.0;
    float irisGlint = 0.0;
    float eyeSclera = 0.0;
    float browShade = 0.0;
    if (front > 0.0 && ax > u_eye_x.x - 0.015 && ax < u_eye_x.y + 0.015) {
        float t = clamp((ax - u_eye_x.x) /
                        max(0.015, u_eye_x.y - u_eye_x.x), 0.0, 1.0);
        float ends = smoothstep(0.0, 0.08, t) *
                     (1.0 - smoothstep(0.92, 1.0, t));
        float arc = sin(3.14159265 * t);
        float upper = poly(u_eye_up, ax) + 0.005 * arc;
        float lower = poly(u_eye_lo, ax) - 0.0025 * arc;
        float lid = mix(lower, upper, clamp(u_open, 0.0, 1.0));
        // Pale cyan eye chamber inside an anatomically measured almond lid.
        float aa = max(fwidth(p.y) * 1.3, 0.002);
        float aperture = front * ends *
            smoothstep(lower - aa, lower + aa, p.y) *
            (1.0 - smoothstep(lid - aa, lid + aa, p.y));
        eyeSclera = aperture * 0.62;

        vec2 centre = vec2(sign(p.x) * u_eye_c.x, u_eye_c.y) +
                      vec2(u_gaze.x * 0.027, u_gaze.y * 0.016);
        vec2 dEye = (p.xy - centre) / vec2(0.039, 0.042);
        float rad = length(dEye);
        float radAA = max(fwidth(rad), 0.012);
        iris = aperture * (1.0 - smoothstep(0.86, 1.0 + radAA, rad));
        irisRing = aperture * contour(rad - 0.89, 0.067);
        pupil = aperture * (1.0 - smoothstep(0.35, 0.42 + radAA, rad));
        float angle = atan(dEye.y, dEye.x);
        irisThreads = iris * (0.5 + 0.5 * sin(angle * 38.0 + rad * 8.0)) *
                      smoothstep(0.37, 0.55, rad) *
                      (1.0 - smoothstep(0.83, 0.96, rad));
        // Twin specular catchlights give the hologram readable, alert eyes.
        irisGlint = aperture *
                    (0.85 * exp(-dot((dEye - vec2(-0.29, 0.34)) * 9.0,
                                      (dEye - vec2(-0.29, 0.34)) * 9.0)) +
                     0.40 * exp(-dot((dEye - vec2(0.31, -0.27)) * 16.0,
                                      (dEye - vec2(0.31, -0.27)) * 16.0)));

        eyes = max(contour(p.y - lid, 0.0011),
                   contour(p.y - lower, 0.0011)) * ends;
        // Real mesh-fitted eyebrows: expressive without dark solid hair.
        float browLine = u_brow.x + ax * (u_brow.y + ax * u_brow.z);
        browShade = exp(-pow((p.y - browLine) / 0.011, 2.0)) * ends;
        eyes += 0.16 * contour(p.y - browLine + 0.006, 0.0018) * ends;
        // Fine luminous eyelashes trace the upper lid, not large cartoon lashes.
        float lashes = pow(max(0.0, sin(t * 68.0)), 18.0) *
                       smoothstep(0.40, 0.85, t);
        eyes += 0.28 * lashes * contour(p.y - lid - 0.008, 0.004) * ends;
    }

    // Only a luminous lip contour and an animated opening, not teeth or skin.
    float lips = 0.0;
    float mouthCavity = 0.0;
    float lipBody = 0.0;
    float lipSeam = 0.0;
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
        float lipAA = max(fwidth(p.y), 0.0015);
        lipBody = smoothstep(lower - lipAA, lower + lipAA, p.y) *
                  (1.0 - smoothstep(upper - lipAA, upper + lipAA, p.y)) * taper;
        lipSeam = exp(-pow((p.y - 0.5 * (innerUpper + innerLower)) / 0.0035, 2.0)) * taper;
        // The reference keeps a relaxed, gently curved mouth even when the
        // assistant speaks; avoid a large horizontal oval or bright teeth.
        float smile = 0.005 * pow(ax / max(u_lip_w.x, 0.01), 2.0);
        float opening = 0.024 * talk * taper;
        float topLine = mix(mid + smile, upper, talk * 0.52);
        float bottomLine = topLine - opening;
        // Preserve the actual speaking viseme while adding dimensional,
        // softly smiling upper/lower lips at rest, like the visual reference.
        lips = max(contour(p.y - topLine, 0.0012),
                   talk * contour(p.y - bottomLine, 0.0012)) * taper;
        float upperBow = 0.0028 * exp(-pow((ax - 0.07) / 0.037, 2.0));
        lips += 0.42 * contour(p.y - upper - upperBow, 0.0015) * taper;
        lips += 0.55 * contour(p.y - lower, 0.0017) * taper;
        lips += 0.15 * exp(-pow((p.y - lower) / 0.016, 2.0)) * taper;
        lips += talk * 0.12 * contour(p.y - innerUpper, 0.0013) * taper;
        mouthCavity = smoothstep(innerLower - opening - 0.003,
                                 innerLower + 0.003, p.y);
        mouthCavity *= 1.0 - smoothstep(innerUpper - 0.003,
                                       innerUpper + 0.003, p.y);
        mouthCavity *= taper * talk;
    }
    // Facial light is evaluated on the moving 3D surface. Its lids, iris,
    // nose and lips remain aligned in side views and during speech.
    float features = front * (0.62 * eyes + 0.55 * lips);
    float pulse = 0.95 + 0.05 * sin(u_time * 1.4) + 0.13 * u_glow;

    // Dark translucent interior, bright electric cyan scan lines and edge.
    vec3 night = vec3(0.002, 0.050, 0.14);
    vec3 neon = vec3(0.010, 0.70, 1.25);
    vec3 ice = vec3(0.23, 0.96, 1.39);
    float cavity = clamp(v_misc.x, 0.35, 1.0);
    float fill = max(0.0, dot(n, normalize(vec3(0.70, -0.10, 0.70))));
    // Continuous directional light carries the anatomy between scan samples.
    // Keep shadows in sockets and under the nose instead of flooding them
    // with uniform neon. The narrow sheen follows the actual surface normals.
    float volume = (0.08 + 0.86 * pow(key, 1.45) + 0.12 * fill) * cavity * cavity;
    vec3 halfLight = normalize(normalize(vec3(-0.45, 0.5, 0.77)) + vec3(0.0, 0.0, 1.0));
    float sheen = pow(max(0.0, dot(n, halfLight)), 34.0) * face * cavity;
    vec3 col = night * (0.18 + 0.12 * key);
    col += mix(neon, ice, 0.40) * volume * 0.88;
    col += ice * sheen * 0.16;
    // Intentionally emissive: the reference is a lit projection, not an
    // opaque blue mannequin. The edge is several times brighter than
    // the inter-line interior, with dynamic voice-synchronised highlights.
    col += neon * lineLight * (0.10 + 0.035 * u_glow);
    col += ice * network * 0.018;
    // Add a subtle translucent anatomical bloom at the nose and cheekbones
    // so the scanline portrait has depth instead of looking like a striped egg.
    float ridge = face * (0.35 * bridge + 0.28 * tip +
                          0.17 * cheek) * max(key, 0.22);
    col += neon * ridge * 0.10;
    float bust = 1.0 - smoothstep(-1.67, -1.14, p.y);
    col += ice * rim * (0.46 + 0.12 * u_glow) * mix(1.0, 0.57, bust);
    col *= 1.0 - 0.42 * front * browShade;
    col = mix(col, col * vec3(0.78, 0.84, 1.05) + ice * 0.032, lipBody * front);
    col *= 1.0 - 0.42 * lipSeam * front;
    col += ice * features * 0.28;
    // Inner eye volume stays luminous yet translucent; the electric iris
    // reads as a circular optical structure rather than a painted eyeball.
    col += vec3(0.18, 0.52, 0.68) * eyeSclera;
    col += neon * iris * 0.28 + ice * irisRing * 0.18;
    col += ice * irisThreads * 0.10 + ice * irisGlint * 0.70;
    col *= 1.0 - 0.72 * pupil;
    col += ice * irisGlint * 0.065;
    col *= 1.0 - 0.75 * mouthCavity;
    col *= pulse * (1.0 - 0.44 * u_muted);
    float alpha = clamp(0.32 + 0.42 * volume + 0.008 * network + 0.045 * lineLight + 0.32 * rim +
                        0.15 * features + 0.01 * eyeSclera +
                        0.025 * iris + 0.035 * irisRing +
                        0.03 * irisGlint, 0.0, 1.0) * fade;
    col = vec3(1.0) - exp(-max(col, vec3(0.0)) * 2.10);
    gl_FragColor = vec4(col * alpha, alpha);
}
"""
