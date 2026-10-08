// Tri par colonne sur les tableaux de données : un clic sur un en-tête trie, un second clic inverse, un troisième revient à l'ordre d'origine.
// Les tableaux sont reconstruits à chaque affichage : l'état de tri est mémorisé par bloc et tableau, puis réappliqué.
(() => {
  const state = {};                                                         // clé tableau -> {col, dir}
  const NUM = /^[−-]?\s*\d[\d\s.,]*\s*(€|%|j|km|ETP)?$/;
  const val = td => {
    if (td.dataset && td.dataset.v !== undefined) { const n = parseFloat(td.dataset.v); return isFinite(n) ? n : null; }
    const inp = td.querySelector('input,select'); let t = (inp ? inp.value : td.textContent).replace(/[  ]/g, ' ').trim();
    if (t === '' || /^[–—-]$/.test(t)) return null;
    const d = t.match(/^(\d{2})\/(\d{2})\/(\d{4})$/); if (d) return +(d[3] + d[2] + d[1]);
    if (NUM.test(t)) { const n = parseFloat(t.replace(/[€%]|ETP|km|\sj$/g, '').replace(/\s/g, '').replace('−', '-').replace(',', '.')); if (isFinite(n)) return n; }
    return t.toLowerCase();
  };
  const cmp = (a, b) => (a === null) - (b === null) || (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), 'fr', {numeric: true, sensitivity: 'base'}));
  const keyOf = (tb, i) => { const blk = tb.closest('[data-bid]'); return (blk ? blk.dataset.bid : 'page') + '#' + [...(blk || document).querySelectorAll('table.tsort')].indexOf(tb); };
  function apply(tb) {
    const body = tb.tBodies[0], st = state[tb.dataset.sk]; if (!body) return;
    const rows = [...body.rows]; if (!tb._orig) tb._orig = rows.slice();
    const fixed = rows.filter(r => r.classList.contains('tot') || r.classList.contains('subtot')), free = rows.filter(r => !fixed.includes(r));
    const cell = (r, i) => val(r.cells[i] || document.createElement('td'));
    const sorted = st ? free.slice().sort((x, y) => { const A = cell(x, st.col), B = cell(y, st.col); return A === null || B === null ? (A === null) - (B === null) : (st.dir === 'asc' ? 1 : -1) * cmp(A, B); }) : tb._orig.filter(r => free.includes(r));
    sorted.concat(fixed).forEach(r => body.appendChild(r));
    [...tb.tHead.rows[0].cells].forEach((th, i) => { if (st && st.col === i) th.dataset.tsort = st.dir; else delete th.dataset.tsort; });
  }
  function prepare(tb) {
    tb.dataset.sx = '1'; const head = tb.tHead && tb.tHead.rows;
    if (!head || head.length !== 1 || [...head[0].cells].some(c => c.colSpan > 1 || c.rowSpan > 1) || !tb.tBodies[0] || tb.tBodies[0].querySelector('tr.grp') || tb.classList.contains('nmtable') || tb.classList.contains('sdsplit') || tb.classList.contains('tn11table') || tb.querySelector('th.sortable')) return;
    if (tb.tBodies[0].rows.length < 4) return;
    tb.classList.add('tsort'); tb.dataset.sk = keyOf(tb);
    [...head[0].cells].forEach(th => { th.title = 'Cliquer pour trier'; });
    if (state[tb.dataset.sk]) apply(tb);
  }
  const scan = () => document.querySelectorAll('table:not([data-sx])').forEach(prepare);
  let queued = false; new MutationObserver(() => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; scan(); }); }).observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener('click', e => {
    const th = e.target.closest('table.tsort thead th'); if (!th || e.target.closest('button,input,select,a')) return;
    const tb = th.closest('table'), col = th.cellIndex, k = tb.dataset.sk, cur = state[k];
    if (!cur || cur.col !== col) state[k] = {col, dir: 'asc'}; else if (cur.dir === 'asc') state[k] = {col, dir: 'desc'}; else delete state[k];
    apply(tb);
  });
  scan();
})();
