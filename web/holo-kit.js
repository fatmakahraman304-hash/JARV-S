/* JARVIS hologram kit — the pure part of the hologram table (hologram.html).
 *
 * A model is a list of simple parts (box, cylinder, sphere …) in centimetres,
 * y up, origin at the bottom centre — what Gemini returns from a camera photo.
 * This file turns parts into wireframe meshes, projects them, reads hand
 * gestures from MediaPipe landmarks and writes STL. Nothing here touches the
 * page, so tests/test_hologram.py runs all of it under Node.
 */
(function (root) {
  'use strict';
  const H = {};
  const D2R = Math.PI / 180;
  H.SHAPES = ['box', 'cylinder', 'sphere', 'cone', 'torus', 'capsule', 'wedge', 'hemisphere'];

  // ── model hygiene: whatever the model says, keep it drawable ────────────
  const num = (v, d) => (Number.isFinite(+v) ? +v : d);
  const vec = (a, d) => [0, 1, 2].map(i => num(Array.isArray(a) ? a[i] : undefined, d[i]));
  const HEX = /^#[0-9a-f]{6}$/i;
  H.clean = (m) => {
    m = m && typeof m === 'object' ? m : {};
    const parts = (Array.isArray(m.parts) ? m.parts : []).slice(0, 80).map((p, i) => {
      p = p && typeof p === 'object' ? p : {};
      const shape = H.SHAPES.includes(String(p.shape).toLowerCase()) ? String(p.shape).toLowerCase() : 'box';
      const size = vec(p.size, [5, 5, 5]).map(v => Math.min(1000, Math.max(0.05, Math.abs(v))));
      return { name: String(p.name || `parça ${i + 1}`).slice(0, 40), shape, size,
               pos: vec(p.pos, [0, size[1] / 2, 0]).map(v => Math.max(-2000, Math.min(2000, v))),
               rot: vec(p.rot, [0, 0, 0]).map(v => ((v % 360) + 360) % 360),
               color: HEX.test(p.color || '') ? p.color : '#ff9a2e' };
    });
    return { name: String(m.name || 'Model').slice(0, 60), summary: String(m.summary || '').slice(0, 400),
             parts, created: m.created || '', id: m.id || '' };
  };

  // Bounding box of the whole model (cm), from part centres ± half sizes.
  H.bounds = (m) => {
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (const p of m.parts) for (let i = 0; i < 3; i++) {
      const r = Math.max(...p.size) / 2;                    // rotation-safe
      lo[i] = Math.min(lo[i], p.pos[i] - r); hi[i] = Math.max(hi[i], p.pos[i] + r);
    }
    if (!m.parts.length) return { lo: [0, 0, 0], hi: [0, 0, 0], size: [0, 0, 0], center: [0, 0, 0], radius: 1 };
    const size = hi.map((h, i) => h - lo[i]), center = hi.map((h, i) => (h + lo[i]) / 2);
    return { lo, hi, size, center, radius: Math.max(1, Math.hypot(...size) / 2) };
  };

  // ── meshes: unit shapes (fit in a 1×1×1 box), quads/polygons + edges ────
  // {v: [[x,y,z]], f: [[i,j,k,l…]], e: [[i,j]]}
  function ring(n, y, r, rz = r) { const o = []; for (let i = 0; i < n; i++) { const a = i / n * 2 * Math.PI; o.push([Math.cos(a) * r, y, Math.sin(a) * rz]); } return o; }
  function lathe(profile, n = 20, everyEdge = 4) {
    // profile: [[r, y]] bottom → top; r 0 = a pole
    const v = [], f = [], e = [], idx = [];
    profile.forEach(([r, y]) => {
      if (r === 0) { idx.push([v.length]); v.push([0, y, 0]); }
      else { const row = []; for (let i = 0; i < n; i++) { const a = i / n * 2 * Math.PI; row.push(v.length); v.push([Math.cos(a) * r, y, Math.sin(a) * r]); } idx.push(row); }
    });
    for (let k = 0; k < idx.length - 1; k++) {
      const A = idx[k], B = idx[k + 1];
      for (let i = 0; i < n; i++) {
        const a0 = A[A.length === 1 ? 0 : i], a1 = A[A.length === 1 ? 0 : (i + 1) % n], b0 = B[B.length === 1 ? 0 : i], b1 = B[B.length === 1 ? 0 : (i + 1) % n];
        const face = [a0, a1, b1, b0].filter((x, j, s) => s.indexOf(x) === j);
        if (face.length >= 3) f.push(face);
        if (i % everyEdge === 0 && a0 !== b0) e.push([a0, b0]);
      }
    }
    idx.forEach(row => { if (row.length > 1) for (let i = 0; i < n; i++) e.push([row[i], row[(i + 1) % n]]); });
    // flat caps where the profile ends on a ring
    const first = idx[0], last = idx[idx.length - 1];
    if (first.length > 1) f.push(first.slice().reverse());
    if (last.length > 1) f.push(last.slice());
    return { v, f, e };
  }
  const UNIT = {};
  UNIT.box = (() => {
    const v = []; for (const x of [-.5, .5]) for (const y of [-.5, .5]) for (const z of [-.5, .5]) v.push([x, y, z]);
    const f = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
    const e = [[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
    return { v, f, e };
  })();
  UNIT.cylinder = lathe([[.5, -.5], [.5, .5]], 24, 3);
  UNIT.cone = lathe([[.5, -.5], [0, .5]], 24, 3);
  const sphereProfile = (from, to, steps, stretch = 0) => { const o = []; for (let i = 0; i <= steps; i++) { const t = from + (to - from) * i / steps; const r = Math.cos(t) * .5; o.push([Math.abs(r) < 1e-9 ? 0 : r, Math.sin(t) * .5]); } return o; };
  UNIT.sphere = lathe(sphereProfile(-Math.PI / 2, Math.PI / 2, 10), 18, 3);
  UNIT.hemisphere = lathe([[.5, -.5], ...sphereProfile(0, Math.PI / 2, 6).map(([r, y]) => [r, y * 2 - .5])], 18, 3);
  UNIT.capsule = (() => {
    const bot = sphereProfile(-Math.PI / 2, 0, 4).map(([r, y]) => [r, y * .5 - .25]);
    const top = sphereProfile(0, Math.PI / 2, 4).map(([r, y]) => [r, y * .5 + .25]);
    return lathe([...bot, ...top], 18, 3);
  })();
  UNIT.torus = (() => {
    const v = [], f = [], e = [], N = 24, M = 10, R = .35, r = .15;
    for (let i = 0; i < N; i++) for (let j = 0; j < M; j++) {
      const a = i / N * 2 * Math.PI, b = j / M * 2 * Math.PI;
      v.push([Math.cos(a) * (R + r * Math.cos(b)), Math.sin(b) * .5, Math.sin(a) * (R + r * Math.cos(b))]);   // size[1] = tube thickness
    }
    const id = (i, j) => (i % N) * M + (j % M);
    for (let i = 0; i < N; i++) for (let j = 0; j < M; j++) {
      f.push([id(i, j), id(i + 1, j), id(i + 1, j + 1), id(i, j + 1)]);
      if (j % 3 === 0) e.push([id(i, j), id(i + 1, j)]);
      if (i % 3 === 0) e.push([id(i, j), id(i, j + 1)]);
    }
    return { v, f, e };
  })();
  UNIT.wedge = (() => {
    const v = [[-.5, -.5, -.5], [.5, -.5, -.5], [-.5, .5, -.5], [-.5, -.5, .5], [.5, -.5, .5], [-.5, .5, .5]];
    const f = [[0, 1, 2], [3, 5, 4], [0, 3, 4, 1], [0, 2, 5, 3], [1, 4, 5, 2]];
    const e = [[0, 1], [1, 2], [2, 0], [3, 4], [4, 5], [5, 3], [0, 3], [1, 4], [2, 5]];
    return { v, f, e };
  })();
  H.unit = shape => UNIT[shape] || UNIT.box;

  // ── maths ────────────────────────────────────────────────────────────────
  H.rotate = (p, rx, ry, rz) => {          // degrees, X then Y then Z
    let [x, y, z] = p;
    if (rx) { const c = Math.cos(rx * D2R), s = Math.sin(rx * D2R); [y, z] = [y * c - z * s, y * s + z * c]; }
    if (ry) { const c = Math.cos(ry * D2R), s = Math.sin(ry * D2R); [x, z] = [x * c + z * s, -x * s + z * c]; }
    if (rz) { const c = Math.cos(rz * D2R), s = Math.sin(rz * D2R); [x, y] = [x * c - y * s, x * s + y * c]; }
    return [x, y, z];
  };
  // A part's vertices in model space (cm). explode: 0…1 pushes parts away from the centre.
  H.partVerts = (p, center = [0, 0, 0], explode = 0) => {
    const u = H.unit(p.shape);
    const push = p.pos.map((c, i) => (c - center[i]) * explode * 1.2);
    return u.v.map(q => {
      const s = [q[0] * p.size[0], q[1] * p.size[1], q[2] * p.size[2]];
      const r = H.rotate(s, ...p.rot);
      return [r[0] + p.pos[0] + push[0], r[1] + p.pos[1] + push[1], r[2] + p.pos[2] + push[2]];
    });
  };
  // View: yaw/pitch (deg) around the model centre; zoom 1 = the model fills
  // ~40 % of the short side; pan in fractions of the short side.
  // Returns [sx, sy, depth] or null when behind the eye.
  H.project = (pt, view, W, Hh, center, radius) => {
    let p = [pt[0] - center[0], pt[1] - center[1], pt[2] - center[2]];
    p = H.rotate(p, 0, view.yaw || 0, 0);
    p = H.rotate(p, view.pitch || 0, 0, 0);
    const dist = radius * 3 / (view.zoom || 1), zc = dist - p[2];
    if (zc < radius * 0.05) return null;
    const m = Math.min(W, Hh), F = 1.26 * m;
    return [W / 2 + (view.panX || 0) * m + p[0] * F / zc, Hh / 2 + (view.panY || 0) * m - p[1] * F / zc, zc];
  };

  // ── gestures from MediaPipe hand landmarks (21 points, x/y in 0…1) ──────
  const d = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  H.handScale = L => d(L[0], L[9]) || 0.1;
  const extended = (L, tip, pip) => d(L[0], L[tip]) > d(L[0], L[pip]) * 1.15;
  H.fingers = L => ({ index: extended(L, 8, 6), middle: extended(L, 12, 10), ring: extended(L, 16, 14), pinky: extended(L, 20, 18) });
  H.pinching = L => d(L[4], L[8]) < H.handScale(L) * 0.35;
  H.pose = L => {
    if (!L || L.length < 21) return 'none';
    const f = H.fingers(L), n = f.index + f.middle + f.ring + f.pinky;
    if (H.pinching(L)) return 'pinch';
    if (n === 4) return 'open';
    if (n === 0) return 'fist';
    if (f.index && !f.middle && !f.ring && !f.pinky) return 'point';
    if (f.index && f.middle && !f.ring && !f.pinky) return 'peace';
    return 'other';
  };
  H.pinchPoint = L => ({ x: (L[4].x + L[8].x) / 2, y: (L[4].y + L[8].y) / 2 });

  // Turns a stream of hand frames into view changes. State lives in `st`.
  // hands: [{pose, at:{x,y}}] (x already mirrored like the preview), t in ms.
  // Returns {rotate:[dyaw,dpitch], zoom:factor, pan:[dx,dy], action, cursor}.
  H.gestureStep = (st, hands, t) => {
    const out = { rotate: [0, 0], zoom: 1, pan: [0, 0], action: '', cursor: null };
    const pinches = hands.filter(h => h.pose === 'pinch');
    if (pinches.length >= 2) {
      const [a, b] = pinches, dist = Math.hypot(a.at.x - b.at.x, a.at.y - b.at.y), mid = { x: (a.at.x + b.at.x) / 2, y: (a.at.y + b.at.y) / 2 };
      if (st.two) { out.zoom = Math.max(0.8, Math.min(1.25, dist / Math.max(0.02, st.two.dist))); out.pan = [(mid.x - st.two.mid.x), (mid.y - st.two.mid.y)]; }
      st.two = { dist, mid }; st.one = null;
    } else if (pinches.length === 1) {
      const p = pinches[0].at;
      if (st.one) out.rotate = [(p.x - st.one.x) * 360, (p.y - st.one.y) * 240];
      st.one = { x: p.x, y: p.y }; st.two = null;
    } else { st.one = null; st.two = null; }
    // held poses: open palm → explode/assemble, fist → reset (once per hold)
    const held = hands.length === 1 ? hands[0].pose : hands.length === 2 && hands[0].pose === hands[1].pose ? hands[0].pose + '2' : '';
    if (held !== st.held) { st.held = held; st.since = t; st.fired = false; }
    if (!st.fired && t - st.since > 700) {
      if (held === 'open' || held === 'open2') { out.action = 'explode'; st.fired = true; }
      else if (held === 'fist' || held === 'fist2') { out.action = 'reset'; st.fired = true; }
    }
    // a fast open-hand swipe sideways: throw the model away
    const open = hands.find(h => h.pose === 'open');
    if (open) {
      st.trail = (st.trail || []).filter(p => t - p.t < 350); st.trail.push({ t, x: open.at.x });
      const dx = st.trail[st.trail.length - 1].x - st.trail[0].x;
      if (Math.abs(dx) > 0.45 && st.trail.length >= 3) { out.action = 'throw'; st.trail = []; st.fired = true; }
    } else st.trail = [];
    const pt = hands.find(h => h.pose === 'point');
    if (pt) out.cursor = pt.at;
    return out;
  };

  // ── STL (ASCII) for 3D printing — millimetres ───────────────────────────
  H.toSTL = (m) => {
    const lines = [`solid ${m.name.replace(/\s+/g, '_')}`];
    for (const p of m.parts) {
      const V = H.partVerts(p).map(q => q.map(c => c * 10));
      for (const face of H.unit(p.shape).f) for (let i = 1; i < face.length - 1; i++) {
        const a = V[face[0]], b = V[face[i]], c = V[face[i + 1]];
        const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]], w = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
        const n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]; const l = Math.hypot(...n) || 1;
        const f = x => x.toFixed(3);
        lines.push(` facet normal ${f(n[0] / l)} ${f(n[2] / l)} ${f(n[1] / l)}`, '  outer loop',
          ...[a, b, c].map(q => `   vertex ${f(q[0])} ${f(q[2])} ${f(q[1])}`), '  endloop', ' endfacet');   // z up for printers
      }
    }
    lines.push(`endsolid ${m.name.replace(/\s+/g, '_')}`);
    return lines.join('\n');
  };

  // Spoken/typed commands that need no model call.
  H.localCommand = (text) => {
    const t = String(text || '').toLocaleLowerCase('tr').trim();
    if (/^(tara|modelle|dijitalleştir|dijital olarak modelle|bunu modelle|kameradakini modelle)/.test(t) || /(bunu|şunu|kameradakini) (dijital olarak )?modelle/.test(t)) return 'scan';
    if (/parçala|parçalara ayır|patlat|aç(ıl)? göster/.test(t)) return 'explode';
    if (/birleştir|topla|kapat parçaları/.test(t)) return 'assemble';
    if (/sıfırla|ortala|başa al/.test(t)) return 'reset';
    if (/^kaydet$|modeli kaydet/.test(t)) return 'save';
    if (/stl|indir|yazdır|3 ?d yazıcı/.test(t)) return 'stl';
    if (/çöpe at|sil(?! ).*model|modeli sil|fırlat/.test(t)) return 'throw';
    return '';
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = H; else root.HoloKit = H;
})(typeof self !== 'undefined' ? self : this);
