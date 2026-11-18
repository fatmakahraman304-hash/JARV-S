/* JARVIS device kit — small pure helpers the device modules (dev-*.js) share.
 *
 * Nothing here touches the page, so tests/test_web_devices.py runs every
 * function under Node. In the browser it is window.JarvisKit.
 */
(function (root) {
  'use strict';
  const K = {};

  // A finger moved (dx, dy) px in dt ms: which way was it swiped, if at all.
  K.swipeDir = (dx, dy, dt = 300, min = 40) => {
    if (dt > 900) return null;                                   // a slow drag, not a swipe
    const ax = Math.abs(dx), ay = Math.abs(dy);
    if (Math.max(ax, ay) < min) return null;
    if (ax > ay * 1.3) return dx > 0 ? 'right' : 'left';
    if (ay > ax * 1.3) return dy > 0 ? 'down' : 'up';
    return null;                                                 // diagonal: ignore
  };

  // TV remote / D-pad: from the focused box, the best box in that direction.
  // Boxes are {x, y, w, h}. Closer along the arrow, and better lined up across
  // it, wins — the same feel as Android TV's focus search.
  K.nearest = (from, boxes, dir) => {
    const c = b => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 });
    const f = c(from);
    let best = -1, score = Infinity;
    boxes.forEach((b, i) => {
      if (b === from || (b.x === from.x && b.y === from.y && b.w === from.w && b.h === from.h)) return;
      const p = c(b);
      let along, across;
      if (dir === 'right') { along = b.x - (from.x + from.w) ; across = p.y - f.y; if (p.x <= f.x) return; }
      else if (dir === 'left') { along = from.x - (b.x + b.w); across = p.y - f.y; if (p.x >= f.x) return; }
      else if (dir === 'down') { along = b.y - (from.y + from.h); across = p.x - f.x; if (p.y <= f.y) return; }
      else if (dir === 'up') { along = from.y - (b.y + b.h); across = p.x - f.x; if (p.y >= f.y) return; }
      else return;
      const s = Math.max(0, along) + Math.abs(across) * 2;
      if (s < score) { score = s; best = i; }
    });
    return best;
  };

  // Is this hour inside the night window? (22 → 7 wraps past midnight.)
  K.isNight = (hour, from = 22, to = 7) => from === to ? false : from < to ? hour >= from && hour < to : hour >= from || hour < to;

  // Milliseconds until the next hh:00 local time.
  K.msUntil = (hour, now = new Date()) => {
    const d = new Date(now.getTime()); d.setHours(hour, 0, 0, 0);
    if (d.getTime() <= now.getTime()) d.setDate(d.getDate() + 1);
    return d.getTime() - now.getTime();
  };

  // 130 → "2 sa 10 dk"
  K.fmtMinutes = m => {
    m = Math.max(0, Math.round(m)); const h = Math.floor(m / 60), r = m % 60;
    return h ? `${h} sa${r ? ' ' + r + ' dk' : ''}` : `${r} dk`;
  };

  // Projector lamp log: {"2026-11-18": minutes}. Adds, keeps the last 90 days.
  K.lampAdd = (log, day, minutes) => {
    const out = { ...(log || {}) }; out[day] = (out[day] || 0) + minutes;
    const keep = Object.keys(out).sort().slice(-90); const res = {};
    for (const k of keep) res[k] = out[k];
    return res;
  };
  K.lampTotal = log => Object.values(log || {}).reduce((a, b) => a + (+b || 0), 0);

  K.clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, +v || 0));

  // How fast the reactor core may draw, given what the device is doing.
  K.coreFps = ({ reduced = false, saver = false, battery = null, charging = false, hidden = false, watch = false, idleMs = 0 } = {}) => {
    if (hidden) return -1;                                       // paused
    if (watch) return idleMs > 20000 ? -1 : 15;
    if (saver || reduced) return 20;
    if (battery != null && battery <= 20 && !charging) return 24;
    return 0;                                                    // no cap
  };

  // Typed-command history: newest last, no repeats, at most `max`.
  K.histPush = (list, text, max = 20) => {
    text = String(text || '').trim(); if (!text) return (list || []).slice(-max);
    return [...(list || []).filter(t => t !== text), text].slice(-max);
  };

  // What a TV remote / keyboard key means on a big screen.
  const CODES = { 10009: 'back', 461: 'back', 8: 'back', 27: 'back', 403: 'agenda', 404: 'devices', 405: 'chat', 406: 'remote',
                  415: 'mic', 19: 'mic', 179: 'mic', 37: 'left', 38: 'up', 39: 'right', 40: 'down', 13: 'ok' };
  const KEYS = { Escape: 'back', GoBack: 'back', BrowserBack: 'back', Backspace: 'back', MediaPlayPause: 'mic', MediaPlay: 'mic', MediaPause: 'mic',
                 ColorF0Red: 'agenda', ColorF1Green: 'devices', ColorF2Yellow: 'chat', ColorF3Blue: 'remote',
                 ArrowLeft: 'left', ArrowUp: 'up', ArrowRight: 'right', ArrowDown: 'down', Enter: 'ok',
                 '1': 'agenda', '2': 'devices', '3': 'chat', '4': 'remote', '0': 'pattern' };
  K.tvKey = (key, keyCode) => KEYS[key] || CODES[keyCode] || null;

  // Phone keyboard → projector remote key, while the remote sheet is open.
  const RKEYS = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', Enter: 'ok', Escape: 'back', Backspace: 'back',
                  ' ': 'play_pause', Home: 'home', '+': 'volume_up', '=': 'volume_up', '-': 'volume_down', m: 'mute', M: 'mute' };
  K.remoteKey = key => RKEYS[key] || null;

  // Burn-in protection: a slow walk around a small box, a new spot each minute.
  K.drift = (minute, range = 24) => {
    const a = minute * 2.399963;                                 // golden angle: never the same place twice in a row
    const r = range * (0.35 + 0.65 * ((minute * 7) % 10) / 9);
    return { x: Math.round(Math.cos(a) * r), y: Math.round(Math.sin(a) * r) };
  };

  // Cycle through n screens.
  K.cycle = (i, delta, n) => ((i + delta) % n + n) % n;

  // A YouTube link → the embeddable player URL (autoplay), or '' if not YouTube.
  K.youtubeEmbed = url => {
    const m = String(url || '').match(/(?:youtube\.com\/(?:watch\?(?:.*&)?v=|shorts\/|live\/|embed\/)|youtu\.be\/)([A-Za-z0-9_-]{6,15})/);
    return m ? `https://www.youtube.com/embed/${m[1]}?autoplay=1&rel=0` : '';
  };

  // Shake: enough strong jolts (m/s² beyond gravity) inside the window.
  K.shaken = (samples, now, { threshold = 15, count = 3, windowMs = 900 } = {}) =>
    samples.filter(s => now - s.t <= windowMs && s.a >= threshold).length >= count;

  // Pomodoro-like countdown text for the watch / glance: 75 s → "1:15"
  K.mmss = ms => { const s = Math.max(0, Math.ceil(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

  // Next upcoming item text for a glance face.
  K.nextUp = (rems, now = Date.now()) => {
    const r = (rems || []).filter(x => !x.cancelled && +x.due > now).sort((a, b) => a.due - b.due)[0];
    if (!r) return '';
    const min = Math.round((r.due - now) / 60000);
    return `${min < 60 ? min + ' dk' : K.fmtMinutes(min)} sonra: ${r.text}`;
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = K; else root.JarvisKit = K;
})(typeof self !== 'undefined' ? self : this);
