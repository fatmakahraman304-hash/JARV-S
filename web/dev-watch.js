/* AETHER on the smart watch.
 *
 *  1. Round screens: everything stays inside the circle (detected, or ⚙ → Yuvarlak ekran).
 *  2. Tap anywhere on the face to talk — no small button to aim for.
 *  3. Glance: the time, the next reminder and the battery under the core.
 *  4. Short answers: on the watch AETHER answers in a sentence or two.
 *  5. Haptics: a tap when it listens, a double tap when it answers, a long buzz for reminders.
 *  6. Saves the battery: the core draws at 15 fps and stops when nobody looks.
 *  7. Swipe left/right (or turn the crown / bezel) between screens: core · agenda · devices · actions.
 *  8. Actions screen: find my phone, 5-min timer, hush, my to-dos.
 *  9. One question, one answer: the mic closes itself a few seconds after AETHER answers.
 * 10. Always-on dim: after 30 s the face goes dark for the OLED; a touch wakes it.
 */
(() => {
  'use strict';
  const J = window.AETHER, K = window.AetherKit; if (!J || !K) return;
  if (!J.is('watch')) return;
  const $ = J.$, S = J.S;

  J.css(`
    body.watch.round .app { padding: 13vw; }
    body.watch.round .reply { max-height: 22vh; padding: 0 4vw; }
    body.watch .main { cursor: pointer; }
    #w-glance { font-size: 4.2vw; color: var(--dim); text-align: center; line-height: 1.35; margin-top: 1vw; font-variant-numeric: tabular-nums; }
    #w-glance b { color: var(--text); font-size: 9vw; display: block; font-weight: 600; letter-spacing: -.2vw; }
    #w-glance .nx { color: var(--acc); }
    body.watch.replying #w-glance { display: none; }
    #w-screens { position: fixed; inset: 0; z-index: 15; background: radial-gradient(circle at 50% 40%, #1d1007, #050403 75%); display: flex; flex-direction: column; justify-content: center; padding: 14vw 12vw; }
    body.watch.round #w-screens { padding: 18vw 15vw; }
    #w-screens h3 { font-size: 4vw; letter-spacing: 1vw; color: var(--dim); text-align: center; margin-bottom: 3vw; }
    #w-screens .li { font-size: 5vw; padding: 2vw 0; border-bottom: 1px solid var(--line); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    #w-screens .li small { color: var(--dim); }
    #w-screens .acts { display: grid; grid-template-columns: 1fr 1fr; gap: 3vw; }
    #w-screens .acts button { aspect-ratio: 1; border-radius: 50%; border: 1px solid var(--line2); background: rgba(255,138,28,.12); color: var(--text); font-size: 4vw; font-family: inherit; }
    #w-screens .acts button span { display: block; font-size: 9vw; }
    #w-dots { position: fixed; bottom: 4vw; left: 50%; transform: translateX(-50%); display: flex; gap: 2vw; z-index: 16; }
    body.watch.round #w-dots { bottom: 7vw; }
    #w-dots i { width: 2vw; height: 2vw; border-radius: 50%; background: var(--dim); opacity: .5; } #w-dots i.on { background: var(--acc); opacity: 1; }
    body.watch.wdim .app, body.watch.wdim #w-screens { filter: brightness(.28) saturate(.5); transition: filter 1.5s; }
    body.watch.wdim { background: #000; }
  `);

  // 1 ── round screen ───────────────────────────────────────────────────────
  const roundMq = matchMedia('(shape: round)');
  if (S.round === undefined) S.round = roundMq.matches || Math.abs(innerWidth - innerHeight) < 8;
  J.toggleSetting('round', '⌚ Yuvarlak ekran', on => document.body.classList.toggle('round', on));

  // 3 ── glance ─────────────────────────────────────────────────────────────
  const gl = document.createElement('div'); gl.id = 'w-glance';
  $('st-title').after(gl);
  function paintGlance() {
    const d = new Date(), b = J.battery, nx = K.nextUp(J.pendingRem());
    gl.innerHTML = `<b>${d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}</b>` +
      (nx ? `<div class="nx">⏰ ${J.esc(nx)}</div>` : '') + (b.battery != null ? `<div>🔋 %${b.battery}${b.charging ? ' ⚡' : ''}</div>` : '');
    document.body.classList.toggle('replying', J.state !== 'idle' || J.micOn);
  }
  setInterval(paintGlance, 5000); paintGlance();

  // 4 ── short answers ──────────────────────────────────────────────────────
  J.prompt(() => 'BU CİHAZ BİR AKILLI SAAT: ekran çok küçük. Her yanıtı en fazla bir iki kısa cümleyle ver; liste, kod ya da uzun açıklama gerekiyorsa kısaca söyle ve "telefonuna göndereyim mi?" diye sor (send_to_device).');

  // 5 ── haptics ────────────────────────────────────────────────────────────
  let prev = J.state, wokeAt = 0;
  J.on('state', s => {
    if (s === prev) return;
    if (s === 'speaking') J.vibrate([20, 60, 20]);
    else if (s === 'offline' || s === 'setup') J.vibrate([120, 60, 120]);
    prev = s; paintGlance(); wake();
  });
  J.on('reminder', () => { J.vibrate([400, 150, 400, 150, 400]); wake(); return false; });

  // 6 ── battery: slow core, stopped when idle ──────────────────────────────
  setInterval(() => {
    const busy = J.micOn || J.speaking || J.state === 'thinking';
    const fps = K.coreFps({ watch: true, idleMs: busy ? 0 : J.idleMs(), hidden: document.visibilityState !== 'visible' });
    J.core.paused = fps < 0; J.core.fps = fps > 0 ? fps : 0;
  }, 1000);

  // 7/8 ── screens ──────────────────────────────────────────────────────────
  const scr = document.createElement('div'); scr.id = 'w-screens'; scr.hidden = true;
  const dots = document.createElement('div'); dots.id = 'w-dots'; dots.innerHTML = '<i></i><i></i><i></i><i></i>';
  document.body.append(scr, dots);
  let screen = 0;
  const ACTS = [['📳', 'Telefonu bul', async () => J.toast(await J.runTool('find_device', { device: 'telefon' }))],
                ['⏱', '5 dk', () => J.toast(J.reminderTool({ action: 'set', minutes: 5, text: '5 dakikalık zamanlayıcı' }))],
                ['🤐', 'Sustur', () => { J.hush(); J.stopMic(); J.toast('Sustum'); }],
                ['☑', 'Yapılacaklar', () => { show(0); J.say('Yapılacaklar listemde ne var? Çok kısa söyle.'); }]];
  function show(i) {
    screen = i; scr.hidden = i === 0;
    dots.querySelectorAll('i').forEach((d, j) => d.classList.toggle('on', j === i));
    if (i === 1) {
      const rem = J.pendingRem().slice(0, 3).map(r => `<div class="li">⏰ ${J.esc(r.text)} <small>${J.esc(J.remTime(r.due))}</small></div>`);
      const todo = Object.keys(J.memory.notes || {}).filter(k => k.startsWith('yapılacak: ')).slice(0, 3).map(k => `<div class="li">☐ ${J.esc(k.slice(11))}</div>`);
      scr.innerHTML = `<h3>AJANDA</h3>${rem.join('') + todo.join('') || '<div class="li"><small>Boş</small></div>'}`;
    } else if (i === 2) {
      const L = J.devices.filter(d => d.kind !== 'receiver' && d.id !== S.id).slice(0, 4)
        .map(d => `<div class="li">${J.online(d) ? '🟢' : '⚫'} ${J.esc(d.name)} <small>${d.battery != null ? '%' + d.battery : ''}</small></div>`);
      scr.innerHTML = `<h3>CİHAZLAR</h3>${L.join('') || '<div class="li"><small>Görünen yok</small></div>'}`;
    } else if (i === 3) {
      scr.innerHTML = `<h3>EYLEMLER</h3><div class="acts">${ACTS.map(([ic, l], j) => `<button type="button" data-j="${j}"><span>${ic}</span>${l}</button>`).join('')}</div>`;
      scr.querySelectorAll('[data-j]').forEach(b => b.onclick = e => { e.stopPropagation(); J.vibrate(15); ACTS[+b.dataset.j][2](); });
    }
  }
  show(0);
  const step = d => { J.vibrate(8); show(K.cycle(screen, d, 4)); };
  let x0 = 0, y0 = 0, t0 = 0, swiped = false;
  document.addEventListener('touchstart', e => { const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; t0 = Date.now(); swiped = false; }, { passive: true });
  document.addEventListener('touchend', e => {
    const t = e.changedTouches[0], d = K.swipeDir(t.clientX - x0, t.clientY - y0, Date.now() - t0, 30);
    if (d === 'left') { swiped = true; step(1); } else if (d === 'right') { swiped = true; step(-1); }
    else if (d === 'down' && screen) { swiped = true; show(0); }
  }, { passive: true });
  let wheelT = 0;
  addEventListener('wheel', e => { if ($('reply').contains(e.target) && $('reply').scrollHeight > $('reply').clientHeight) return;
    const now = Date.now(); if (now - wheelT < 350) return; wheelT = now; step(e.deltaY > 0 ? 1 : -1); }, { passive: true });
  document.addEventListener('rotarydetent', e => step(e.detail && e.detail.direction === 'CCW' ? -1 : 1));   // Tizen bezel

  // 2 ── tap anywhere to talk ───────────────────────────────────────────────
  document.querySelector('.main').addEventListener('click', e => {
    if (swiped || screen || e.target.closest('#reply')) return;
    $('mic').click();
  });

  // 9 ── one question, one answer ───────────────────────────────────────────
  let answeredAt = 0;
  J.on('turn', () => { answeredAt = Date.now(); });
  setInterval(() => {
    if (!J.micOn || !answeredAt || J.speaking || J.state === 'thinking') return;
    if (J.micLevel > 0.06) { answeredAt = Date.now(); return; }
    if (Date.now() - answeredAt > 8000) { answeredAt = 0; J.stopMic(); }
  }, 1000);

  // 10 ── always-on dim ─────────────────────────────────────────────────────
  function wake() { J.touch(); document.body.classList.remove('wdim'); }
  document.addEventListener('pointerdown', e => { if (document.body.classList.contains('wdim')) { wokeAt = Date.now(); e.preventDefault(); e.stopPropagation(); wake(); } }, true);
  // the tap that woke the face must not also press what was under it
  document.addEventListener('click', e => { if (Date.now() - wokeAt < 700) { e.preventDefault(); e.stopPropagation(); } }, true);
  setInterval(() => {
    const busy = J.micOn || J.speaking || J.state === 'thinking';
    if (busy) { wake(); return; }
    if (J.idleMs() > 30000) { if (screen) show(0); document.body.classList.add('wdim'); }   // back to the face, dimmed
  }, 2000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { wake(); paintGlance(); J.syncNow().catch(() => {}); } });
})();
