/* MAYK — what every device module (dev-*.js) shares: a place for its own
 * settings in ⚙, a style sheet, a vibration that never throws.
 * The modules reach the app only through window.JARVIS (end of app.js).
 */
(() => {
  'use strict';
  const J = window.JARVIS; if (!J) return;

  J.is = (...kinds) => kinds.includes(J.kind);
  J.idleMs = () => Date.now() - J.lastInteract;
  J.vibrate = p => { try { if (navigator.vibrate) navigator.vibrate(p); } catch { /* not on iPhone */ } };
  J.css = text => { const st = document.createElement('style'); st.textContent = text; document.head.appendChild(st); return st; };
  J.typing = () => { const a = document.activeElement; return !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.tagName === 'SELECT' || a.isContentEditable); };
  J.sheetOpen = () => [...document.querySelectorAll('.sheet')].some(s => !s.hidden);

  // ⚙ → "Bu cihaz için": each module adds its own rows here.
  const box = document.createElement('div');
  box.id = 'dev-settings';
  box.innerHTML = '<label>BU CİHAZ İÇİN</label>';
  box.hidden = true;
  const status = J.$('f-status');
  status.parentNode.insertBefore(box, status);
  J.addSetting = (html) => {
    const row = document.createElement('div'); row.className = 'row'; row.style.marginTop = '6px'; row.style.alignItems = 'center';
    row.innerHTML = html; box.appendChild(row); box.hidden = false; return row;
  };
  // A toggle button bound to S[key]; fn(on) runs now and on every change.
  J.toggleSetting = (key, label, fn, def = false) => {
    if (J.S[key] === undefined) J.S[key] = def;
    const row = J.addSetting(`<button class="btn" type="button"></button>`);
    const b = row.firstChild;
    const paint = () => { b.textContent = `${label}: ${J.S[key] ? 'açık' : 'kapalı'}`; b.classList.toggle('pri', !!J.S[key]); };
    b.onclick = () => { J.S[key] = !J.S[key]; J.save(); paint(); fn && fn(!!J.S[key]); };
    paint(); fn && fn(!!J.S[key]);
    return b;
  };

  // Changing "Bu cihaz" in ⚙ reloads, so the right device module takes over.
  const before = J.kind;
  J.$('f-save').addEventListener('click', () => setTimeout(() => { if (J.kind !== before) location.reload(); }, 900));
})();
