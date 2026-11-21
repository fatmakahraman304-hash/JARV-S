/* MAYK reactor core — the same orange energy sphere as the desktop
 * (gui/reactor.py), drawn on a <canvas> for the phone, tablet, TV and watch
 * pages. A white-hot core inside a geodesic wireframe sphere, 3-D light rays,
 * thick orbiting arcs and swirling particle bands, all projected through a
 * perspective camera. Spin speed follows the state; brightness follows the
 * real voice level.
 *
 *   const core = JarvisReactor(canvas);
 *   core.state = 'thinking';   // idle | thinking | speaking | sleeping | offline
 *   core.level = 0.6;          // 0..1, MAYK's voice
 */
(function () {
  'use strict';
  const CAM_D = 4.4, MESH_R = 0.64, CORE_R = 0.12;
  const N_RAYS = 24, N_ARCS = 5, N_ARC_PTS = 40, N_BANDS = 5;
  const HOT = [255, 242, 191], GOLD = [255, 173, 42], ORANGE = [255, 116, 16], EMBER = [255, 74, 0];

  // deterministic random, so every device draws the same sphere
  function rng(seed) {
    let s = seed >>> 0;
    const f = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    f.u = (a, b) => a + (b - a) * f();
    f.n = (m, sd) => { const u = Math.max(1e-9, f()), v = f(); return m + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
    return f;
  }
  const rx = a => { const c = Math.cos(a), s = Math.sin(a); return [1, 0, 0, 0, c, -s, 0, s, c]; };
  const ry = a => { const c = Math.cos(a), s = Math.sin(a); return [c, 0, s, 0, 1, 0, -s, 0, c]; };
  const rz = a => { const c = Math.cos(a), s = Math.sin(a); return [c, -s, 0, s, c, 0, 0, 0, 1]; };
  const mm = (A, B) => { const C = new Array(9);
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++)
      C[i * 3 + j] = A[i * 3] * B[j] + A[i * 3 + 1] * B[3 + j] + A[i * 3 + 2] * B[6 + j];
    return C; };
  const mv = (M, p) => [M[0] * p[0] + M[1] * p[1] + M[2] * p[2], M[3] * p[0] + M[4] * p[1] + M[5] * p[2],
                        M[6] * p[0] + M[7] * p[1] + M[8] * p[2]];
  const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${Math.max(0, Math.min(1, a)).toFixed(3)})`;
  const norm = v => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };

  function icosphere(sub) {
    const t = (1 + Math.sqrt(5)) / 2;
    let V = [[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
             [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]].map(norm);
    let F = [[0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11], [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6],
             [7, 1, 8], [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9], [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1]];
    for (let s = 0; s < sub; s++) {
      const cache = {}, NF = [];
      const mid = (a, b) => { const k = a < b ? a + '_' + b : b + '_' + a;
        if (cache[k] === undefined) { const p = V[a], q = V[b]; V.push(norm([(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2])); cache[k] = V.length - 1; }
        return cache[k]; };
      for (const [a, b, c] of F) { const ab = mid(a, b), bc = mid(b, c), ca = mid(c, a);
        NF.push([a, ab, ca], [b, bc, ab], [c, ca, bc], [ab, bc, ca]); }
      F = NF;
    }
    const E = new Set();
    for (const [a, b, c] of F) for (const [u, v] of [[a, b], [b, c], [c, a]]) E.add(u < v ? u + '_' + v : v + '_' + u);
    return { V: V.map(p => [p[0] * MESH_R, p[1] * MESH_R, p[2] * MESH_R]), E: [...E].map(k => k.split('_').map(Number)) };
  }

  window.JarvisReactor = function (canvas, opts) {
    opts = opts || {};
    const small = opts.small || false;               // watches and slow devices
    const R = rng(57);
    const mesh = icosphere(small ? 1 : 2);
    const rays = [];
    for (let i = 0; i < N_RAYS; i++) {
      const a = (i + R.u(-0.35, 0.35)) * 2 * Math.PI / N_RAYS;
      rays.push({ d: norm([Math.cos(a), Math.sin(a), R.u(-0.35, 0.35)]), len: R.u(1.0, 1.55), w: R.u(0.7, 1.3),
                  ph: R.u(0, 6.283), sp: R.u(0.8, 2.4) });
    }
    const arcs = [];
    for (let k = 0; k < N_ARCS; k++)
      arcs.push({ tilt: mm(rx(R.u(-0.55, 0.55)), ry(R.u(-0.55, 0.55))), radius: R.u(0.8, 1.1),
                  span: R.u(0.87, 2.09), speed: R.u(0.5, 1.4) * (R() < 0.5 ? 1 : -1),
                  phase: (k + R.u(-0.25, 0.25)) * 2 * Math.PI / N_ARCS, width: R.u(0.016, 0.030) });
    const nBand = small ? 90 : 260, bands = [];
    for (let b = 0; b < N_BANDS; b++) {
      const tilt = mm(mm(rz(R.u(0, 6.283)), rx(R.u(0, 0.9))), ry(R.u(0, 6.283)));
      const Rr = R.u(0.8, 1.12), centres = [R.u(0, 6.283), R.u(0, 6.283), R.u(0, 6.283), R.u(0, 6.283)];
      const pts = [];
      for (let i = 0; i < nBand; i++) {
        const a = centres[Math.floor(R() * 4)] + R.n(0, 0.55), rr = Rr + R.n(0, 0.05);
        pts.push({ p: mv(tilt, [Math.cos(a) * rr, Math.sin(a) * rr, R.n(0, 0.025)]), ph: R.u(0, 6.283) });
      }
      bands.push({ pts, spd: R.u(0.4, 1.0) * (R() < 0.5 ? 1 : -1) });
    }
    const shell = [], dust = [];
    for (let i = 0; i < (small ? 150 : 420); i++) { const v = norm([R.n(0, 1), R.n(0, 1), R.n(0, 1)]), r = R.u(0.62, 0.98);
      shell.push({ p: [v[0] * r, v[1] * r, v[2] * r], ph: R.u(0, 6.283) }); }
    for (let i = 0; i < (small ? 60 : 180); i++) { const v = norm([R.n(0, 1), R.n(0, 1), R.n(0, 1)]), r = R.u(1.05, 1.45);
      dust.push({ p: [v[0] * r, v[1] * r, v[2] * r], ph: R.u(0, 6.283) }); }

    const api = { state: 'idle', level: 0, name: opts.name || '' };
    const ctx = canvas.getContext('2d');
    let spin = 0, t = 0, last = performance.now(), amp = 0;

    function size() {
      const dpr = Math.min(window.devicePixelRatio || 1, small ? 1.5 : 2.5);
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr)), h = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      return [w, h];
    }

    // api.fps caps the frame rate (battery savers, watches); api.paused stops
    // drawing but keeps the last frame on screen. 0 = no cap.
    api.fps = opts.fps || 0; api.paused = false;
    let drawn = 0;
    function frame(now) {
      if (api.paused || (api.fps > 0 && now - drawn < 1000 / api.fps - 2)) { requestAnimationFrame(frame); return; }
      drawn = now;
      const dt = Math.min(0.1, Math.max(0, (now - last) / 1000)); last = now;
      const st = api.state, thinking = st === 'thinking', speaking = st === 'speaking';
      const asleep = st === 'sleeping' || st === 'offline';
      spin += dt * (asleep ? 0.10 : 0.34 + (thinking ? 1.3 : 0) + (speaking ? 0.6 : 0));
      t += dt;
      amp += ((speaking ? api.level : thinking ? 0.12 : 0) - amp) * 0.2;
      const [W, H] = size();
      const cx = W / 2, cy = H / 2, r = Math.min(W, H) / 3.9;
      const dim = asleep ? 0.45 : 1.0, energy = Math.min(1, 0.8 + 0.35 * amp);
      const proj = p => { const s = CAM_D / (CAM_D - p[2]); return [cx + p[0] * s * r, cy - p[1] * s * r, p[2]]; };

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      ctx.lineCap = 'round';

      // glow underneath
      const gr = r * (1.25 + 0.35 * amp);
      let g = ctx.createRadialGradient(cx, cy, 0, cx, cy, gr);
      g.addColorStop(0, rgba(GOLD, 0.55 * dim)); g.addColorStop(0.25, rgba(ORANGE, 0.28 * dim));
      g.addColorStop(0.6, rgba(EMBER, 0.08 * dim)); g.addColorStop(1, rgba(EMBER, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, gr, 0, 6.2832); ctx.fill();

      const Rm = mm(ry(spin * 0.5), rx(spin * 0.17));
      const px = Math.max(1.1, r * 0.0105);
      // particles
      const dot = (q, a, col, s) => { if (a <= 0.02) return; ctx.fillStyle = rgba(col, a); ctx.fillRect(q[0] - s / 2, q[1] - s / 2, s, s); };
      bands.forEach((b, i) => {
        const M = mm(Rm, rz(spin * b.spd)), col = i % 2 ? GOLD : ORANGE;
        for (const e of b.pts) { const q = proj(mv(M, e.p)); const tw = 0.45 + 0.55 * Math.sin(e.ph + t * 2.6) ** 2;
          dot(q, (0.3 + 0.7 * (q[2] + 1.3) / 2.6) * tw * dim * energy, col, px); }
      });
      for (const e of shell) { const q = proj(mv(Rm, e.p)); const tw = 0.4 + 0.6 * Math.sin(e.ph + t * 3.1) ** 2;
        dot(q, (0.15 + 0.85 * (q[2] + 1) / 2) * tw * dim * energy, ORANGE, px * 0.9); }
      const Rd = ry(spin * 0.2);
      for (const e of dust) dot(proj(mv(Rd, e.p)), (0.25 + 0.45 * Math.sin(e.ph + t * 1.7) ** 2) * dim, GOLD, px * 0.8);

      // wireframe
      const PV = mesh.V.map(p => proj(mv(Rm, p)));
      ctx.lineWidth = Math.max(0.8, r * 0.005);
      const buckets = [[], [], []];
      for (const [a, b] of mesh.E) { const zm = (PV[a][2] + PV[b][2]) / (2 * MESH_R);
        buckets[Math.max(0, Math.min(2, Math.floor((zm + 1) * 1.5)))].push(a, b); }
      [0.32, 0.58, 0.9].forEach((al, k) => {
        ctx.strokeStyle = rgba(ORANGE, al * dim * energy); ctx.beginPath();
        const B = buckets[k]; for (let i = 0; i < B.length; i += 2) { ctx.moveTo(PV[B[i]][0], PV[B[i]][1]); ctx.lineTo(PV[B[i + 1]][0], PV[B[i + 1]][1]); }
        ctx.stroke();
      });

      // rays
      const Rr = mm(rz(spin * 0.25), ry(0.25 * Math.sin(spin * 0.4)));
      ctx.lineCap = 'butt';
      for (const ray of rays) {
        const fl = 0.75 + 0.25 * Math.sin(t * ray.sp + ray.ph), L = ray.len * (0.9 + 0.18 * amp) * fl;
        const tip = proj(mv(Rr, [ray.d[0] * L, ray.d[1] * L, ray.d[2] * L]));
        const a = dim * fl * 0.85;
        g = ctx.createLinearGradient(cx, cy, tip[0], tip[1]);
        g.addColorStop(0, rgba(HOT, a)); g.addColorStop(0.15, rgba(GOLD, 0.95 * a));
        g.addColorStop(0.45, rgba(ORANGE, 0.9 * a)); g.addColorStop(0.85, rgba(EMBER, 0.7 * a)); g.addColorStop(1, rgba(EMBER, 0));
        ctx.strokeStyle = g; ctx.lineWidth = Math.max(1, r * 0.0095 * ray.w * (1 + 0.4 * amp));
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(tip[0], tip[1]); ctx.stroke();
        ctx.strokeStyle = rgba(EMBER, 0.12 * a); ctx.lineWidth = r * 0.04;
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(tip[0], tip[1]); ctx.stroke();
      }

      // arcs
      const Ra = rz(spin * 0.3);
      for (const arc of arcs) {
        const start = arc.phase + spin * arc.speed * (1 + 0.6 * amp), rad = arc.radius * (1 + 0.04 * amp);
        const M = mm(Ra, arc.tilt), P = [];
        for (let i = 0; i < N_ARC_PTS; i++) { const a = start + arc.span * i / (N_ARC_PTS - 1);
          P.push(proj(mv(M, [Math.cos(a) * rad, Math.sin(a) * rad, 0]))); }
        for (const [col, wm, al] of [[EMBER, 3.0, 0.18], [ORANGE, 1.0, 0.9], [GOLD, 0.3, 0.7]]) {
          ctx.lineWidth = Math.max(1.4, r * arc.width * wm); ctx.lineCap = col === EMBER ? 'round' : 'butt';
          for (let i = 0; i < P.length - 1; i++) {
            const front = (P[i][2] + P[i + 1][2]) / 2 >= 0;
            ctx.strokeStyle = rgba(col, al * (front ? 1 : 0.55) * dim * energy);
            ctx.beginPath(); ctx.moveTo(P[i][0], P[i][1]); ctx.lineTo(P[i + 1][0], P[i + 1][1]); ctx.stroke();
          }
        }
      }

      // the white-hot core
      const cr = r * CORE_R * (1 + 0.45 * amp);
      g = ctx.createRadialGradient(cx, cy, 0, cx, cy, cr * 1.6);
      g.addColorStop(0, rgba(HOT, dim)); g.addColorStop(0.45, rgba(HOT, dim));
      g.addColorStop(0.62, rgba(GOLD, 0.95 * dim)); g.addColorStop(1, rgba(ORANGE, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, cr * 1.6, 0, 6.2832); ctx.fill();

      ctx.globalCompositeOperation = 'source-over';
      if (api.name) {
        const fpx = Math.max(10, r * 0.13);
        ctx.font = `300 ${fpx}px Bahnschrift, 'Segoe UI', system-ui, sans-serif`;
        ctx.fillStyle = `rgba(255,248,240,${0.8 + 0.2 * Math.min(1, amp * 2)})`;
        ctx.textAlign = 'center';
        if ('letterSpacing' in ctx) ctx.letterSpacing = Math.round(r * 0.04) + 'px';
        ctx.fillText(api.name, cx, cy + r * 1.72);
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    return api;
  };
})();
