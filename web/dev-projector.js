/* Mayk and the projector (HY320 and any Android projector / TV box).
 *
 * On the projector's own Mayk page:
 *  1. Pure-black, high-contrast look (dark gradients turn grey on a projector).
 *  2. Focus / keystone test pattern — key 0, or "test desenini aç".
 *  3. Presentation mode: only the core and the answer, big — key P, or "sunum modu".
 *  4. Lamp hours: how long it has been on today and in total, and a break
 *     reminder after 3 hours ("projeksiyon ne kadar açık kaldı").
 *
 * The remote (📽️ Kumanda) on every device:
 *  5. Hold an arrow or volume button: it repeats.
 *  6. Touchpad: swipe to move, tap for OK, long-press for back.
 *  7. A keyboard works as the remote while it is open (arrows, Enter, Esc, space, +/−, M).
 *  8. More apps: Prime Video, Disney+, Spotify, Ayarlar.
 *  9. Sleep timer: 30 / 60 / 90 min, then the projector turns off — shared, so
 *     whichever device is awake does it ("projeksiyonu 1 saat sonra kapat").
 * 10. Status line: which path the remote uses (Alıcı / laptop) and whether it is reachable.
 */
(() => {
  'use strict';
  const J = window.JARVIS, K = window.JarvisKit; if (!J || !K) return;
  const $ = J.$, S = J.S;

  J.css(`
    body.k-projector { background: #000; }
    body.k-projector { --text: #fff; --med: #eee3d8; --dim: #c3b5a8; --line: rgba(255,160,70,.32); --line2: rgba(255,170,80,.6); --card: rgba(18,12,8,.9); }
    body.k-projector .brand b { text-shadow: 0 0 18px rgba(255,150,40,.8); }
    #pattern { position: fixed; inset: 0; z-index: 33; background: #000; cursor: none; }
    #pattern svg { width: 100%; height: 100%; display: block; }
    body.present .top, body.present .bottom, body.present .left, body.present .side, body.present #wave, body.present #st-sub { display: none !important; }
    body.present .app { grid-template-columns: 1fr !important; }
    body.present .main { grid-column: 1 / -1 !important; grid-row: 1 / -1 !important; }
    body.present .core { width: min(62vh, 50vw) !important; }
    body.present .reply { font-size: 2.6vw !important; max-width: 80vw !important; max-height: 30vh; background: none; border: 0; text-align: center; }
    #rm-pad { margin: 12px auto 0; height: 150px; max-width: 320px; border-radius: 16px; border: 1px dashed var(--line2); background: rgba(255,138,28,.06);
              display: grid; place-items: center; text-align: center; padding: 0 18px; color: var(--dim); font-size: 13px; touch-action: none; user-select: none; -webkit-user-select: none; }
    #rm-status { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--med); margin-top: 4px; }
    #rm-sleep .btn.on { background: var(--pri); color: #1a0d03; }
  `);

  // ── the remote, on every device ──────────────────────────────────────────
  const sheet = $('s-remote');
  const press = async k => { J.vibrate(12); const r = await J.remote('key', k); if (r) J.toast(r); };

  // 5 ── hold to repeat (replaces the one-shot click on repeatable keys) ──
  const REPEAT = new Set(['up', 'down', 'left', 'right', 'volume_up', 'volume_down']);
  sheet.querySelectorAll('[data-k]').forEach(b => {
    if (!REPEAT.has(b.dataset.k)) return;
    let t1 = null, t2 = null, n = 0;
    b.onclick = null;
    const stop = () => { clearTimeout(t1); clearInterval(t2); t1 = t2 = null; };
    b.addEventListener('pointerdown', e => { e.preventDefault(); n = 0; press(b.dataset.k); t1 = setTimeout(() => { t2 = setInterval(() => { if (++n > 25) stop(); else press(b.dataset.k); }, 220); }, 450); });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach(ev => b.addEventListener(ev, stop));
    b.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); press(b.dataset.k); } });
  });

  // 6 ── touchpad ──────────────────────────────────────────────────────────
  const pad = document.createElement('div'); pad.id = 'rm-pad';
  pad.textContent = 'Dokunmatik alan: kaydır = yön · dokun = OK · basılı tut = geri';
  sheet.querySelector('.pad').after(pad);
  let px = 0, py = 0, pt = 0, longT = null, longDone = false;
  pad.addEventListener('pointerdown', e => { px = e.clientX; py = e.clientY; pt = Date.now(); longDone = false;
    longT = setTimeout(() => { longDone = true; press('back'); }, 650); });
  pad.addEventListener('pointermove', e => { if (Math.hypot(e.clientX - px, e.clientY - py) > 12) clearTimeout(longT); });
  pad.addEventListener('pointerup', e => {
    clearTimeout(longT); if (longDone) return;
    const d = K.swipeDir(e.clientX - px, e.clientY - py, Date.now() - pt, 30);
    press(d || 'ok');
  });

  // 7 ── keyboard as the remote while the sheet is open ────────────────────
  document.addEventListener('keydown', e => {
    if (sheet.hidden || J.is('tv', 'projector') || J.typing() || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = K.remoteKey(e.key); if (!k) return;
    if (k === 'back' && e.key === 'Escape' && e.shiftKey) return;
    e.preventDefault(); e.stopPropagation(); press(k);
  }, true);

  // 8 ── more apps ─────────────────────────────────────────────────────────
  const apps = document.createElement('div'); apps.className = 'pcgrid'; apps.style.marginTop = '8px';
  apps.innerHTML = [['prime', 'Prime Video'], ['disney', 'Disney+'], ['spotify', 'Spotify'], ['ayarlar', '⚙ Ayarlar'], ['chrome', 'Chrome'], ['play store', 'Play Store']]
    .map(([a, l]) => `<button class="btn" type="button" data-app2="${a}">${l}</button>`).join('');
  sheet.querySelector('.pcgrid').after(apps);
  apps.querySelectorAll('[data-app2]').forEach(b => b.onclick = async () => J.toast(await J.remote('app', b.dataset.app2)));

  // 9 ── sleep timer ───────────────────────────────────────────────────────
  const sleepRow = document.createElement('div'); sleepRow.className = 'row'; sleepRow.id = 'rm-sleep';
  sleepRow.innerHTML = '<span style="align-self:center;color:var(--dim);font-size:12px;letter-spacing:2px">UYKU</span>' +
    [30, 60, 90].map(m => `<button class="btn" type="button" data-m="${m}">${m} dk</button>`).join('') + '<button class="btn" type="button" data-m="0">İptal</button>';
  apps.after(sleepRow);
  const sleepOpen = () => J.pendingRem().filter(r => r.op === 'projector_off');
  function setSleep(min) {
    if (sleepOpen().length) J.reminderTool({ action: 'cancel', id: 'Projeksiyon kapanıyor' });
    if (!min) return sleepOpen().length ? 'İptal edilemedi.' : 'Uyku zamanlayıcısı kapalı.';
    J.reminderTool({ action: 'set', minutes: min, text: 'Projeksiyon kapanıyor (uyku zamanlayıcısı)', op: 'projector_off' });
    return `Projeksiyon ${K.fmtMinutes(min)} sonra kapanacak.`;
  }
  function paintSleep() {
    const r = sleepOpen()[0];
    sleepRow.querySelectorAll('[data-m]').forEach(b => b.classList.remove('on'));
    sleepRow.querySelector('span').textContent = r ? `UYKU · ${J.remTime(r.due)}` : 'UYKU';
  }
  sleepRow.querySelectorAll('[data-m]').forEach(b => b.onclick = () => { J.toast(setSleep(+b.dataset.m)); paintSleep(); if (+b.dataset.m) b.classList.add('on'); });
  J.on('reminder', r => {
    if (r.op !== 'projector_off') return false;
    if (J.owner) J.remote('key', 'power').then(m => J.sys('😴 Uyku zamanlayıcısı: ' + m)).catch(() => {});
    return true;
  });
  J.tool({ name: 'projector_sleep', description: 'Projeksiyon/TV uyku zamanlayıcısı: "projeksiyonu 1 saat sonra kapat", "uyku zamanlayıcısını iptal et". minutes: kaç dakika sonra (0 = iptal). Zamanı gelince hangi cihaz açıksa projeksiyonu kapatır.',
           parameters: { type: 'OBJECT', properties: { minutes: { type: 'NUMBER' } }, required: ['minutes'] } }, a => setSleep(Math.max(0, Math.round(+a.minutes || 0))));

  // 10 ── status line ──────────────────────────────────────────────────────
  const st = document.createElement('div'); st.id = 'rm-status'; $('rm-note').after(st);
  function paintStatus() {
    const rx = J.receiver, pc = J.findPc('');
    const dot = on => `<span class="dot ${on ? 'on' : ''}"></span>`;
    st.innerHTML = rx && J.online(rx) ? `${dot(true)} Mayk Alıcı açık — laptop kapalıyken de çalışır`
      : pc && J.online(pc) ? `${dot(true)} ${J.esc(pc.name)} üzerinden (ADB)${rx ? ' · Alıcı çevrimdışı' : ''}`
      : `${dot(false)} Ulaşılamıyor: projeksiyon kapalı ya da Alıcı/laptop çevrimdışı`;
  }
  $('t-remote').addEventListener('click', () => { paintStatus(); paintSleep(); J.syncNow().then(paintStatus).catch(() => {}); });

  // ── on the projector's own page ──────────────────────────────────────────
  if (!J.is('projector')) return;

  // 2 ── test pattern ──────────────────────────────────────────────────────
  const pat = document.createElement('div'); pat.id = 'pattern'; pat.hidden = true;
  const grid = [];
  for (let i = 1; i < 16; i++) grid.push(`<line x1="${i * 100}" y1="0" x2="${i * 100}" y2="900" />`);
  for (let i = 1; i < 9; i++) grid.push(`<line x1="0" y1="${i * 100}" x2="1600" y2="${i * 100}" />`);
  const corner = (x, y, sx, sy) => `<path d="M${x} ${y + sy * 80} V${y} H${x + sx * 80}" stroke="#ff8a1c" stroke-width="8" fill="none"/>`;
  pat.innerHTML = `<svg viewBox="0 0 1600 900" preserveAspectRatio="none"><g stroke="#555" stroke-width="2">${grid.join('')}</g>
    <rect x="4" y="4" width="1592" height="892" fill="none" stroke="#fff" stroke-width="6"/>
    ${corner(4, 4, 1, 1)}${corner(1596, 4, -1, 1)}${corner(4, 896, 1, -1)}${corner(1596, 896, -1, -1)}
    <circle cx="800" cy="450" r="300" fill="none" stroke="#fff" stroke-width="4"/><circle cx="800" cy="450" r="150" fill="none" stroke="#ff8a1c" stroke-width="4"/>
    <line x1="800" y1="0" x2="800" y2="900" stroke="#fff" stroke-width="3"/><line x1="0" y1="450" x2="1600" y2="450" stroke="#fff" stroke-width="3"/>
    <g font-family="sans-serif" fill="#fff" text-anchor="middle"><text x="800" y="120" font-size="44">Mayk · ODAK / KEYSTONE</text>
    <text x="800" y="820" font-size="26" fill="#bbb">Çizgiler düz, köşeler eşit, yazı keskin olana kadar ayarla · kapatmak için Geri / 0</text>
    <text x="800" y="470" font-size="14" fill="#aaa">ince yazı: keskin mi?</text></g></svg>`;
  document.body.appendChild(pat);
  const pattern = on => { pat.hidden = !on; return on ? 'Test deseni ekranda.' : 'Test deseni kapandı.'; };
  pat.addEventListener('pointerdown', () => pattern(false));

  // 3 ── presentation mode ─────────────────────────────────────────────────
  const present = on => { document.body.classList.toggle('present', on); return on ? 'Sunum modu açık.' : 'Sunum modu kapandı.'; };

  document.addEventListener('keydown', e => {
    if (J.typing() || J.sheetOpen()) return;
    if (e.key === '0') { e.preventDefault(); pattern(pat.hidden); }
    else if (e.key === 'p' || e.key === 'P') { e.preventDefault(); present(!document.body.classList.contains('present')); }
    else if ((K.tvKey(e.key, e.keyCode) === 'back') && (!pat.hidden || document.body.classList.contains('present'))) { e.preventDefault(); e.stopImmediatePropagation(); pattern(false); present(false); }
  }, true);

  // 4 ── lamp hours ────────────────────────────────────────────────────────
  const today = () => new Date().toISOString().slice(0, 10);
  let onSince = Date.now(), warned = false;
  setInterval(() => {
    if (document.visibilityState !== 'visible') { onSince = Date.now(); return; }
    S.lamp = K.lampAdd(S.lamp, today(), 1); J.save();
    if (!warned && Date.now() - onSince > 3 * 3600e3) { warned = true; J.toast('Projeksiyon 3 saattir açık — lamba için biraz ara vermek iyi olur'); J.sys('💡 Projeksiyon 3 saattir aralıksız açık.'); }
  }, 60000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') { onSince = Date.now(); warned = false; } });
  const usage = () => `Bugün ${K.fmtMinutes((S.lamp || {})[today()] || 0)} açık; Mayk'ın saydığı toplam ${K.fmtMinutes(K.lampTotal(S.lamp))} (son 90 gün). Şu anki oturum ${K.fmtMinutes((Date.now() - onSince) / 60000)}.`;

  J.tool({ name: 'projector_screen', description: 'Projeksiyonun kendi ekranı: pattern (odak/keystone test deseni), present (sunum modu: yalnız çekirdek ve yanıt), normal (ikisini kapat), usage ("projeksiyon ne kadar açık kaldı", lamba süresi). action: pattern | present | normal | usage.',
           parameters: { type: 'OBJECT', properties: { action: { type: 'STRING' } }, required: ['action'] } },
         a => { const x = String(a.action || '').toLowerCase();
           if (x === 'pattern') return pattern(true); if (x === 'present') return present(true);
           if (x === 'usage') return usage(); pattern(false); present(false); return 'Normal ekran.'; });
})();
