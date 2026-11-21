/* MAYK chess for every device — the same rules and engine as the desktop
 * (core/chess_engine.py), ported line for line: castling, en passant,
 * promotion, check, mate, stalemate, 50-move rule, threefold repetition,
 * insufficient material; SAN out; SAN, UCI or Turkish in ("at f3", "Af3",
 * "kısa rok"); alpha-beta with quiescence and iterative deepening bounded by
 * time; levels kolay / orta / zor.
 * Squares 0..63, a1 = 0, a8 = 56. A move is [from, to, promo] with promo
 * '' or one of 'qrbn'.
 */
(() => {
  'use strict';
  const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const FILES = 'abcdefgh';
  const KNIGHT = [17, 15, 10, 6, -6, -10, -15, -17], KING = [1, -1, 8, -8, 9, 7, -7, -9];
  const ROOK = [1, -1, 8, -8], BISHOP = [9, 7, -7, -9];
  const VALUE = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 0 };
  const sqName = s => FILES[s % 8] + (Math.floor(s / 8) + 1);
  const sqIndex = n => (+n[1] - 1) * 8 + FILES.indexOf(n[0]);
  const stepOk = (f, t, j) => t >= 0 && t < 64 && Math.abs(t % 8 - f % 8) <= j;
  const isUp = p => p !== '.' && p === p.toUpperCase();
  const isLow = p => p !== '.' && p === p.toLowerCase();
  const same = (a, b) => a && b && a[0] === b[0] && a[1] === b[1] && a[2] === b[2];

  class Board {
    constructor(fen = START) { this.setFen(fen); }
    setFen(fen) {
      const parts = fen.trim().split(/\s+/), rows = parts[0].split('/'), sq = Array(64).fill('.');
      rows.forEach((row, r) => { let f = 0; for (const ch of row) { if (/\d/.test(ch)) f += +ch; else { sq[(7 - r) * 8 + f] = ch; f++; } } });
      this.sq = sq; this.white = parts[1] === 'w'; this.castling = parts[2] === '-' ? '' : parts[2];
      this.ep = parts[3] === '-' || !parts[3] ? null : sqIndex(parts[3]);
      this.halfmove = +(parts[4] || 0); this.fullmove = +(parts[5] || 1);
      this.history = []; this.keys = [this.key()];
    }
    fen() {
      const rows = [];
      for (let r = 7; r >= 0; r--) { let row = '', e = 0; for (let f = 0; f < 8; f++) { const p = this.sq[r * 8 + f]; if (p === '.') e++; else { row += (e || '') + p; e = 0; } } rows.push(row + (e || '')); }
      return `${rows.join('/')} ${this.white ? 'w' : 'b'} ${this.castling || '-'} ${this.ep !== null ? sqName(this.ep) : '-'} ${this.halfmove} ${this.fullmove}`;
    }
    key() { return this.sq.join('') + (this.white ? 'w' : 'b') + this.castling + (this.ep ?? '-'); }
    copy() { const b = Object.create(Board.prototype); Object.assign(b, { sq: this.sq.slice(), white: this.white, castling: this.castling, ep: this.ep, halfmove: this.halfmove, fullmove: this.fullmove, history: [], keys: this.keys.slice() }); return b; }

    attacked(s, byWhite) {
      const sq = this.sq;
      const [pawn, knight, king] = byWhite ? ['P', 'N', 'K'] : ['p', 'n', 'k'];
      const bq = byWhite ? 'BQ' : 'bq', rq = byWhite ? 'RQ' : 'rq';
      for (const d of byWhite ? [-7, -9] : [7, 9]) { const t = s + d; if (stepOk(s, t, 1) && sq[t] === pawn) return true; }
      for (const d of KNIGHT) { const t = s + d; if (stepOk(s, t, 2) && sq[t] === knight) return true; }
      for (const d of KING) { const t = s + d; if (stepOk(s, t, 1) && sq[t] === king) return true; }
      for (const [dirs, pcs] of [[BISHOP, bq], [ROOK, rq]]) for (const d of dirs) {
        let t = s;
        for (;;) { const nt = t + d; if (!stepOk(t, nt, 1)) break; t = nt; const p = sq[t]; if (p !== '.') { if (pcs.includes(p)) return true; break; } }
      }
      return false;
    }
    kingSquare(white) { return this.sq.indexOf(white ? 'K' : 'k'); }
    inCheck(white = this.white) { return this.attacked(this.kingSquare(white), !white); }

    pseudo(capturesOnly = false) {
      const sq = this.sq, white = this.white, own = white ? isUp : isLow, moves = [];
      for (let s = 0; s < 64; s++) {
        const p = sq[s]; if (p === '.' || !own(p)) continue;
        const k = p.toLowerCase();
        if (k === 'p') {
          const fwd = white ? 8 : -8, [start, last] = white ? [1, 7] : [6, 0];
          let t = s + fwd;
          if (!capturesOnly && t >= 0 && t < 64 && sq[t] === '.') {
            if (Math.floor(t / 8) === last) for (const pr of 'qrbn') moves.push([s, t, pr]);
            else { moves.push([s, t, '']); const t2 = t + fwd; if (Math.floor(s / 8) === start && sq[t2] === '.') moves.push([s, t2, '']); }
          }
          for (const d of white ? [7, 9] : [-7, -9]) {
            t = s + d; if (!stepOk(s, t, 1)) continue;
            const tg = sq[t];
            if ((tg !== '.' && !own(tg)) || t === this.ep) {
              if (Math.floor(t / 8) === last) for (const pr of 'qrbn') moves.push([s, t, pr]); else moves.push([s, t, '']);
            }
          }
        } else if (k === 'n' || k === 'k') {
          for (const d of k === 'n' ? KNIGHT : KING) {
            const t = s + d;
            if (stepOk(s, t, k === 'n' ? 2 : 1)) { const tg = sq[t]; if (tg === '.') { if (!capturesOnly) moves.push([s, t, '']); } else if (!own(tg)) moves.push([s, t, '']); }
          }
        } else {
          const dirs = k === 'b' ? BISHOP : k === 'r' ? ROOK : BISHOP.concat(ROOK);
          for (const d of dirs) {
            let t = s;
            for (;;) { const nt = t + d; if (!stepOk(t, nt, 1)) break; t = nt; const tg = sq[t];
              if (tg === '.') { if (!capturesOnly) moves.push([s, t, '']); continue; }
              if (!own(tg)) moves.push([s, t, '']); break; }
          }
        }
      }
      if (!capturesOnly) moves.push(...this.castles());
      return moves;
    }
    castles() {
      const out = [], sq = this.sq, c = this.castling;
      if (this.white) {
        if (c.includes('K') && sq[4] === 'K' && sq[7] === 'R' && sq[5] === '.' && sq[6] === '.' && ![4, 5, 6].some(x => this.attacked(x, false))) out.push([4, 6, '']);
        if (c.includes('Q') && sq[4] === 'K' && sq[0] === 'R' && sq[1] === '.' && sq[2] === '.' && sq[3] === '.' && ![4, 3, 2].some(x => this.attacked(x, false))) out.push([4, 2, '']);
      } else {
        if (c.includes('k') && sq[60] === 'k' && sq[63] === 'r' && sq[61] === '.' && sq[62] === '.' && ![60, 61, 62].some(x => this.attacked(x, true))) out.push([60, 62, '']);
        if (c.includes('q') && sq[60] === 'k' && sq[56] === 'r' && sq[57] === '.' && sq[58] === '.' && sq[59] === '.' && ![60, 59, 58].some(x => this.attacked(x, true))) out.push([60, 58, '']);
      }
      return out;
    }
    legalMoves(capturesOnly = false) {
      const out = [], mover = this.white;
      for (const m of this.pseudo(capturesOnly)) { this.push(m); if (!this.attacked(this.kingSquare(mover), !mover)) out.push(m); this.pop(); }
      return out;
    }
    push(m) {
      const [frm, to, promo] = m, sq = this.sq, piece = sq[frm], captured = sq[to];
      this.history.push([m, piece, captured, this.castling, this.ep, this.halfmove, this.fullmove]);
      const epCap = piece.toLowerCase() === 'p' && to === this.ep && captured === '.';
      sq[to] = piece; sq[frm] = '.';
      if (epCap) sq[this.white ? to - 8 : to + 8] = '.';
      if (promo) sq[to] = this.white ? promo.toUpperCase() : promo;
      if ((piece === 'K' || piece === 'k') && Math.abs(to - frm) === 2) {
        if (to % 8 === 6) { sq[to - 1] = sq[to + 1]; sq[to + 1] = '.'; } else { sq[to + 1] = sq[to - 2]; sq[to - 2] = '.'; }
      }
      let rights = this.castling;
      if (rights) { for (const s of [frm, to]) for (const ch of ({ 4: 'KQ', 60: 'kq', 0: 'Q', 7: 'K', 56: 'q', 63: 'k' })[s] || '') rights = rights.replace(ch, ''); this.castling = rights; }
      this.ep = (piece === 'P' || piece === 'p') && Math.abs(to - frm) === 16 ? (frm + to) / 2 : null;
      this.halfmove = piece === 'P' || piece === 'p' || captured !== '.' || epCap ? 0 : this.halfmove + 1;
      if (!this.white) this.fullmove++;
      this.white = !this.white; this.keys.push(this.key());
    }
    pop() {
      const [m, piece, captured, castling, ep, half, full] = this.history.pop();
      this.castling = castling; this.ep = ep; this.halfmove = half; this.fullmove = full;
      this.keys.pop(); this.white = !this.white;
      const [frm, to] = m, sq = this.sq;
      sq[frm] = piece; sq[to] = captured;
      if ((piece === 'P' || piece === 'p') && to === this.ep && captured === '.') sq[this.white ? to - 8 : to + 8] = this.white ? 'p' : 'P';
      if ((piece === 'K' || piece === 'k') && Math.abs(to - frm) === 2) {
        if (to % 8 === 6) { sq[to + 1] = sq[to - 1]; sq[to - 1] = '.'; } else { sq[to - 2] = sq[to + 1]; sq[to + 1] = '.'; }
      }
      return m;
    }
    insufficient() {
      const rest = this.sq.filter(p => !'.Kk'.includes(p));
      if (!rest.length) return true;
      if (rest.length === 1 && 'NBnb'.includes(rest[0])) return true;
      if (rest.every(p => p === 'B' || p === 'b')) { const c = new Set(); this.sq.forEach((p, s) => { if (p === 'B' || p === 'b') c.add((Math.floor(s / 8) + s % 8) % 2); }); return c.size === 1; }
      return false;
    }
    outcome() {
      if (!this.legalMoves().length) return this.inCheck() ? [this.white ? '0-1' : '1-0', 'şah mat'] : ['1/2-1/2', 'pat'];
      if (this.halfmove >= 100) return ['1/2-1/2', '50 hamle kuralı'];
      const last = this.keys[this.keys.length - 1];
      if (this.keys.filter(k => k === last).length >= 3) return ['1/2-1/2', 'üç kez tekrar'];
      if (this.insufficient()) return ['1/2-1/2', 'yetersiz taş'];
      return null;
    }
    san(m) {
      const [frm, to, promo] = m, piece = this.sq[frm], k = piece.toUpperCase();
      let s;
      if (k === 'K' && Math.abs(to - frm) === 2) s = to % 8 === 6 ? 'O-O' : 'O-O-O';
      else {
        const capture = this.sq[to] !== '.' || (k === 'P' && to === this.ep);
        if (k === 'P') { s = (capture ? FILES[frm % 8] + 'x' : '') + sqName(to); if (promo) s += '=' + promo.toUpperCase(); }
        else {
          const others = this.legalMoves().filter(o => o[1] === to && o[0] !== frm && this.sq[o[0]] === piece);
          let dis = '';
          if (others.length) {
            if (others.every(o => o[0] % 8 !== frm % 8)) dis = FILES[frm % 8];
            else if (others.every(o => Math.floor(o[0] / 8) !== Math.floor(frm / 8))) dis = String(Math.floor(frm / 8) + 1);
            else dis = sqName(frm);
          }
          s = k + dis + (capture ? 'x' : '') + sqName(to);
        }
      }
      this.push(m);
      if (this.inCheck()) s += this.legalMoves().length ? '+' : '#';
      this.pop();
      return s;
    }
    uci(m) { return sqName(m[0]) + sqName(m[1]) + m[2]; }
    parse(text) {
      let raw = String(text || '').trim();
      const low = raw.toLocaleLowerCase('tr').replace(/ı/g, 'i').replace(/’/g, "'");
      const legal = this.legalMoves(); if (!legal.length) return null;
      if (/kisa rok|kısa rok|short castle|küçük rok/.test(low)) raw = 'O-O';
      else if (/uzun rok|long castle|büyük rok|buyuk rok/.test(low)) raw = 'O-O-O';
      const compact = low.replace(/[\s-]/g, '');
      let m = compact.match(/^([a-h][1-8])([a-h][1-8])([qrbn])?$/);
      if (m) { const f = sqIndex(m[1]), t = sqIndex(m[2]), pr = m[3] || ''; return legal.find(mv => mv[0] === f && mv[1] === t && (mv[2] === pr || (!pr && mv[2] === 'q'))) || null; }
      const TRW = [['şah', 'K'], ['sah', 'K'], ['vezir', 'Q'], ['kale', 'R'], ['fil', 'B'], ['at', 'N'], ['piyon', ''], ['king', 'K'], ['queen', 'Q'], ['rook', 'R'], ['bishop', 'B'], ['knight', 'N'], ['pawn', '']];
      let letter = null; const words = low.match(/[a-zçğışöü]+/g) || [];
      outer: for (const w of words) for (const [tr, en] of TRW) if (w === tr || (tr.length > 2 && w.startsWith(tr)) || (tr === 'at' && (w === 'ati' || w === 'atı'))) { letter = en; break outer; }
      let san = raw.replace('0-0-0', 'O-O-O').replace('0-0', 'O-O');
      if (letter !== null) { const sqs = low.match(/[a-h][1-8]/g); if (sqs) san = letter + (low.includes('x') || words.includes('al') ? 'x' : '') + sqs[sqs.length - 1]; }
      else if ('ŞVKFA'.includes(san[0] || '#') && san.length >= 3 && /[a-h1-8x]/.test(san[1])) san = ({ Ş: 'K', V: 'Q', K: 'R', F: 'B', A: 'N' })[san[0]] + san.slice(1);
      const want = san.replace(/[+#!?\s]/g, '').replace('=', ''), loose = want.replace(/x/g, '');
      const matches = legal.filter(mv => { const s = this.san(mv).replace(/[+#]/g, '').replace('=', ''); return s === want || s.replace(/x/g, '') === loose; });
      if (matches.length === 1) return matches[0];
      if (!matches.length) {
        const tgt = want.match(/[a-h][1-8]/g), L = 'NBRQK'.includes(want[0]) ? want[0] : '';
        if (tgt) { const t = sqIndex(tgt[tgt.length - 1]); const c = legal.filter(mv => mv[1] === t && this.sq[mv[0]].toUpperCase() === (L || 'P') && (!mv[2] || mv[2] === 'q')); if (c.length === 1) return c[0]; }
      }
      return null;
    }
  }

  // ── evaluation (same tables as the desktop) ─────────────────────────────
  const T = txt => { const n = txt.match(/-?\d+/g).map(Number), out = Array(64).fill(0); for (let r = 0; r < 8; r++) for (let f = 0; f < 8; f++) out[(7 - r) * 8 + f] = n[r * 8 + f]; return out; };
  const PST = {
    p: T('0 0 0 0 0 0 0 0 50 50 50 50 50 50 50 50 10 10 20 30 30 20 10 10 5 5 10 25 25 10 5 5 0 0 0 20 20 0 0 0 5 -5 -10 0 0 -10 -5 5 5 10 10 -20 -20 10 10 5 0 0 0 0 0 0 0 0'),
    n: T('-50 -40 -30 -30 -30 -30 -40 -50 -40 -20 0 0 0 0 -20 -40 -30 0 10 15 15 10 0 -30 -30 5 15 20 20 15 5 -30 -30 0 15 20 20 15 0 -30 -30 5 10 15 15 10 5 -30 -40 -20 0 5 5 0 -20 -40 -50 -40 -30 -30 -30 -30 -40 -50'),
    b: T('-20 -10 -10 -10 -10 -10 -10 -20 -10 0 0 0 0 0 0 -10 -10 0 5 10 10 5 0 -10 -10 5 5 10 10 5 5 -10 -10 0 10 10 10 10 0 -10 -10 10 10 10 10 10 10 -10 -10 5 0 0 0 0 5 -10 -20 -10 -10 -10 -10 -10 -10 -20'),
    r: T('0 0 0 0 0 0 0 0 5 10 10 10 10 10 10 5 -5 0 0 0 0 0 0 -5 -5 0 0 0 0 0 0 -5 -5 0 0 0 0 0 0 -5 -5 0 0 0 0 0 0 -5 -5 0 0 0 0 0 0 -5 0 0 0 5 5 0 0 0'),
    q: T('-20 -10 -10 -5 -5 -10 -10 -20 -10 0 0 0 0 0 0 -10 -10 0 5 5 5 5 0 -10 -5 0 5 5 5 5 0 -5 0 0 5 5 5 5 0 -5 -10 5 5 5 5 5 0 -10 -10 0 5 0 0 0 0 -10 -20 -10 -10 -5 -5 -10 -10 -20'),
    k: T('-30 -40 -40 -50 -50 -40 -40 -30 -30 -40 -40 -50 -50 -40 -40 -30 -30 -40 -40 -50 -50 -40 -40 -30 -30 -40 -40 -50 -50 -40 -40 -30 -20 -30 -30 -40 -40 -30 -30 -20 -10 -20 -20 -20 -20 -20 -20 -10 20 20 0 0 0 0 20 20 20 30 10 0 0 10 30 20'),
    k_end: T('-50 -40 -30 -20 -20 -30 -40 -50 -30 -20 -10 0 0 -10 -20 -30 -30 -10 20 30 30 20 -10 -30 -30 -10 30 40 40 30 -10 -30 -30 -10 30 40 40 30 -10 -30 -30 -10 20 30 30 20 -10 -30 -30 -30 0 0 0 0 -30 -30 -50 -30 -30 -30 -30 -30 -30 -50'),
  };
  function evaluate(b) {
    const sq = b.sq; let queens = 0, minors = 0;
    for (const p of sq) { if (p === 'Q' || p === 'q') queens++; else if ('NBRnbr'.includes(p) && p !== '.') minors++; }
    const end = queens === 0 || (queens <= 2 && minors <= 2);
    let score = 0;
    for (let s = 0; s < 64; s++) {
      const p = sq[s]; if (p === '.') continue;
      const k = p.toLowerCase(), t = k === 'k' && end ? PST.k_end : PST[k];
      if (isUp(p)) score += VALUE[k] + t[s]; else score -= VALUE[k] + t[(7 - Math.floor(s / 8)) * 8 + s % 8];
    }
    return b.white ? score : -score;
  }

  // ── search ──────────────────────────────────────────────────────────────
  const MATE = 100000;
  const LEVELS = { kolay: [2, 500, 0.30], orta: [3, 1200, 0], zor: [5, 3000, 0] };
  const order = (b, moves, best) => moves.map(m => {
    let s = 0;
    if (same(m, best)) s = 1e6;
    else { const v = b.sq[m[1]]; if (v !== '.') s += 10 * VALUE[v.toLowerCase()] - Math.floor(VALUE[b.sq[m[0]].toLowerCase()] / 10) + 1000; if (m[2]) s += VALUE[m[2]]; }
    return [s, m];
  }).sort((a, z) => z[0] - a[0]).map(x => x[1]);

  function search(board, level = 'orta') {
    const [maxDepth, ms, weak] = LEVELS[level] || LEVELS.orta;
    const b = board.copy(), root = b.legalMoves();
    if (!root.length) return [null, 0, 0];
    if (root.length === 1) return [root[0], 0, 0];
    const deadline = performance.now() + ms; let nodes = 0;
    const STOP = {};
    const tick = () => { if ((++nodes & 255) === 0 && performance.now() > deadline) throw STOP; };
    function quiesce(alpha, beta, depth = 0) {
      tick();
      const stand = evaluate(b);
      if (stand >= beta) return beta;
      if (stand > alpha) alpha = stand;
      if (depth > 6) return alpha;
      for (const m of order(b, b.legalMoves(true))) {
        b.push(m); const sc = -quiesce(-beta, -alpha, depth + 1); b.pop();
        if (sc >= beta) return beta; if (sc > alpha) alpha = sc;
      }
      return alpha;
    }
    function negamax(depth, alpha, beta, ply) {
      tick();
      if (ply) { const last = b.keys[b.keys.length - 1]; if (b.keys.filter(k => k === last).length >= 2) return 0; }
      const moves = b.legalMoves();
      if (!moves.length) return b.inCheck() ? -MATE + ply : 0;
      if (depth <= 0) return quiesce(alpha, beta);
      for (const m of order(b, moves)) {
        b.push(m); const sc = -negamax(depth - 1, -beta, -alpha, ply + 1); b.pop();
        if (sc >= beta) return beta; if (sc > alpha) alpha = sc;
      }
      return alpha;
    }
    let best = order(b, root)[0], bestScore = 0, reached = 0, scored = [];
    for (let depth = 1; depth <= maxDepth; depth++) {
      try {
        let alpha = -MATE - 1, cur = null, curScore = -MATE - 1; const results = [];
        for (const m of order(b, root, best)) {
          b.push(m);
          const sc = -negamax(depth - 1, -MATE - 1, weak ? MATE + 1 : -alpha, 1);
          b.pop();
          results.push([sc, m]);
          if (sc > curScore) { curScore = sc; cur = m; }
          if (sc > alpha) alpha = sc;
        }
        best = cur; bestScore = curScore; reached = depth; scored = results;
        if (Math.abs(bestScore) > MATE - 100) break;
      } catch (e) {
        if (e !== STOP) throw e;
        while (b.history.length) b.pop();
        break;
      }
    }
    if (weak && scored.length && Math.random() < weak) {
      const ranked = scored.slice().sort((a, z) => z[0] - a[0]);
      const pool = ranked.slice(1, 4).filter(([s]) => s > bestScore - 250 && s > -MATE + 100).map(x => x[1]);
      if (pool.length && bestScore < MATE - 100) best = pool[Math.floor(Math.random() * pool.length)];
    }
    return [best, bestScore, reached];
  }

  // Every legal move scored to the same fixed depth (plus captures), best first:
  // a fair comparison for the teaching coach (core/chess_engine.root_scores).
  function rootScores(board, depth = 2) {
    const b = board.copy();
    function quiesce(alpha, beta, d = 0) {
      const stand = evaluate(b); if (stand >= beta) return beta; if (stand > alpha) alpha = stand; if (d > 4) return alpha;
      for (const m of order(b, b.legalMoves(true))) { b.push(m); const sc = -quiesce(-beta, -alpha, d + 1); b.pop(); if (sc >= beta) return beta; if (sc > alpha) alpha = sc; }
      return alpha;
    }
    function negamax(d, alpha, beta, ply) {
      const moves = b.legalMoves(); if (!moves.length) return b.inCheck() ? -MATE + ply : 0;
      if (d <= 0) return quiesce(alpha, beta);
      for (const m of order(b, moves)) { b.push(m); const sc = -negamax(d - 1, -beta, -alpha, ply + 1); b.pop(); if (sc >= beta) return beta; if (sc > alpha) alpha = sc; }
      return alpha;
    }
    const out = [];
    for (const m of b.legalMoves()) { b.push(m); out.push([-negamax(depth - 1, -MATE - 1, MATE + 1, 1), m]); b.pop(); }
    return out.sort((a, z) => z[0] - a[0]);
  }

  // "Nf3" → "at f3", "O-O" → "kısa rok" (desktop plugins/chess._spoken)
  function spoken(san) {
    if (!san) return '';
    const TR = { N: 'at', B: 'fil', R: 'kale', Q: 'vezir', K: 'şah' };
    let base;
    if (san.startsWith('O-O-O')) base = 'uzun rok'; else if (san.startsWith('O-O')) base = 'kısa rok';
    else {
      base = TR[san[0]] ? TR[san[0]] + ' ' + san.slice(1) : san;
      base = base.replace('x', ' alır ').replace('=', ' terfi ').replace('+', '').replace('#', '');
      for (const [k, v] of Object.entries(TR)) base = base.replace(' terfi ' + k, ' terfi ' + v);
    }
    if (san.endsWith('#')) base += ', şah mat'; else if (san.endsWith('+')) base += ', şah';
    return base.split(/\s+/).join(' ');
  }

  window.JarvisChess = { Board, search, rootScores, evaluate, spoken, sqName, sqIndex, START, MATE };
})();
