/* AETHER — orbital energy core. Real artwork with audio-reactive cyan 3D HUD. */
(() => {
  'use strict';
  const scriptBase = document.currentScript && document.currentScript.src || location.href;
  const art = new Image();
  art.decoding = 'async';
  art.src = new URL('aether-core.webp', scriptBase).href;
  window.AetherReactor = function(canvas, opts = {}) {
    const ctx = canvas.getContext('2d', {alpha: true});
    const small = Boolean(opts.small);
    const api = { state: 'idle', level: 0, name: opts.name || 'AETHER', fps: opts.fps || 0, paused: false };
    let t = 0, amp = 0, last = performance.now(), drawn = 0;
    function circle(cx, cy, rx, ry, phase, opacity, width) {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(Math.sin(phase * 0.11) * 0.055);
      ctx.beginPath();
      ctx.ellipse(0, 0, rx, ry, 0, phase, phase + 0.82);
      ctx.lineWidth = width;
      ctx.strokeStyle = 'rgba(80,227,255,' + opacity + ')';
      ctx.shadowBlur = Math.max(6, width * 4);
      ctx.shadowColor = '#17bfff';
      ctx.stroke();
      ctx.restore();
    }
    function render(now) {
      requestAnimationFrame(render);
      if (api.paused || (api.fps > 0 && now - drawn < 1000 / api.fps - 2)) return;
      drawn = now;
      const dt = Math.min(.10, Math.max(0, (now - last) / 1000)); last = now;
      const speaking = api.state === 'speaking';
      const thinking = api.state === 'thinking' || api.state === 'processing';
      const sleeping = api.state === 'sleeping' || api.state === 'offline';
      amp += ((speaking ? api.level : thinking ? .12 : 0) - amp) * .18;
      t += dt * (sleeping ? .18 : thinking ? 1.25 : speaking ? 1.05 : .58);
      const dpr = Math.min(window.devicePixelRatio || 1, small ? 1.5 : 2);
      const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      const cx = w / 2, cy = h / 2, d = Math.min(w, h);
      ctx.clearRect(0, 0, w, h);
      ctx.save();
      ctx.globalAlpha = sleeping ? .4 : .93 + Math.min(.07, amp * .08);
      if (art.complete && art.naturalWidth) {
        // Crop only the empty outer margins, leaving the energy sphere and
        // both orbital docking rings exactly as they appear in the artwork.
        const scale = Math.min(w / art.naturalWidth, h / art.naturalHeight) * 1.03;
        const aw = art.naturalWidth * scale, ah = art.naturalHeight * scale;
        ctx.drawImage(art, cx - aw / 2, cy - ah / 2, aw, ah);
      } else {
        const grad = ctx.createRadialGradient(cx,cy,1,cx,cy,d*.37);
        grad.addColorStop(0,'#e8fcff'); grad.addColorStop(.10,'#61ddff');
        grad.addColorStop(.33,'rgba(4,128,220,.50)'); grad.addColorStop(1,'rgba(0,55,120,0)');
        ctx.fillStyle = grad; ctx.beginPath(); ctx.arc(cx,cy,d*.37,0,Math.PI*2); ctx.fill();
      }
      ctx.restore();
      if (!small) {
        circle(cx, cy, d * .365, d * .078, t + .32, sleeping ? .12 : .17 + amp * .16, Math.max(1,d*.004));
        circle(cx, cy, d * .365, d * .078, t + Math.PI + .32, sleeping ? .10 : .14 + amp * .16, Math.max(1,d*.003));
        circle(cx, cy, d * .22, d * .22, -t*.18, sleeping ? .06 : .10, Math.max(.8,d*.002));
      }
      if (api.name) {
        ctx.font = Math.max(11, Math.round(d*.047)) + 'px "Segoe UI", sans-serif';
        ctx.textAlign='center'; ctx.fillStyle='rgba(181,239,255,.88)';
        ctx.shadowColor='#17bfff'; ctx.shadowBlur=12;
        ctx.fillText(api.name, cx, Math.min(h-3, cy+d*.45));
      }
    }
    requestAnimationFrame(render);
    return api;
  };
})();