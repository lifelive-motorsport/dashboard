// Filtre BU à deux niveaux (docs/BRAND.md §4) : niveau 1 = Toutes / XC Cross / CARS ; avec CARS (ou une BU CARS) : niveau 2 = Toutes CARS / Modern Rally / Historic Racing / Historic Rally.
// La sélection est mémorisée ; la dernière ligne du logo prend la couleur de la BU filtrée (CARS : trois tirets bleu / vert / jaune). Chargé après bu.js, avant app.js.
let buSel = (() => { try { return localStorage.getItem('lm_bu') || 'all'; } catch { return 'all'; } })();
if (buSel !== 'all' && !BUS[buSel]) buSel = 'all';
const buIsCars = id => id === 'cars' || (BUS[id] && BUS[id].parent === 'cars');
// Clés du P&L de l'application pour chaque sélection
const BU_KEYS = {all: null, xc: ['XC'], cars: ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'], mr: ['MODERN_RALLY'], hrc: ['HISTORIC_RACING'], hrl: ['HISTORIC_RALLY']};
const BU_PNL_LABEL = {all: 'Groupe', xc: 'XC Cross', cars: 'CARS', mr: 'Modern Rally', hrc: 'Historic Racing', hrl: 'Historic Rally'};

/** Chiffres de la sélection : {label, ca, direct_costs, margin, scoped}. `d` = données du tableau de bord (d.pnl). */
function buScope(d, sel = buSel) {
  if (sel === 'all') return {...d.pnl.total, label: BU_PNL_LABEL.all, scoped: false};
  const rows = sel === 'xc' ? [grp(d, 'XC')] : sel === 'cars' ? [grp(d, 'CARS')] : d.pnl.bus.filter(b => BU_KEYS[sel].includes(b.key));
  const o = rows.reduce((t, r) => ({ca: t.ca + (r.ca || 0), direct_costs: t.direct_costs + (r.direct_costs || 0), margin: t.margin + (r.margin || 0)}), {ca: 0, direct_costs: 0, margin: 0});
  return {...o, label: BU_PNL_LABEL[sel], scoped: true};
}
function buSetSel(sel) {
  buSel = sel; try { localStorage.setItem('lm_bu', sel); } catch {}
  buLogo(); if (typeof render === 'function') render();
}
// Logo : la dernière ligne (entrée en cours) prend la couleur de la BU active
function buLogo() {
  const el = document.getElementById('logo-line'), el2 = document.getElementById('logo-line-cars'); if (!el) return;
  const dark = buDark();
  if (buSel === 'cars') { el.setAttribute('display', 'none'); el2.removeAttribute('display'); el2.querySelectorAll('line').forEach((l, i) => l.setAttribute('stroke', buSymbolColors('cars', '#fff', dark)[i])); }
  else { el2.setAttribute('display', 'none'); el.removeAttribute('display'); el.setAttribute('stroke', buSel === 'all' ? '#fff' : buSel === 'mr' ? (dark ? '#6F8FD6' : '#2C4F9C') : BUS[buSel].color); el.setAttribute('stroke-width', buSel === 'all' ? '4' : '5'); }
}
const buPill = (id, label, on, sym) => `<button type="button" class="bu-pill" data-bu="${id}" aria-pressed="${on}">${sym ? BuSymbol(sym, {size: 15}) : ''}<span>${esc(label)}</span></button>`;
function buBarHtml() {
  const l1 = [['all', 'Toutes', 'groupe'], ['xc', 'XC Cross', 'xc'], ['cars', 'CARS', 'cars']];
  let h = `<div class="bu-filter" role="group" aria-label="Filtrer par BU">${l1.map(([id, l, sym]) => buPill(id, l, id === 'all' ? buSel === 'all' : id === 'cars' ? buIsCars(buSel) : buSel === id, sym)).join('')}</div>`;
  if (buIsCars(buSel)) h += `<div class="bu-filter bu-l2" role="group" aria-label="Filtrer par BU CARS">${[['cars', 'Toutes CARS', 'cars'], ['mr', 'Modern Rally', 'mr'], ['hrc', 'Historic Racing', 'hrc'], ['hrl', 'Historic Rally', 'hrl']].map(([id, l, sym]) => buPill(id, l, buSel === id, sym)).join('')}</div>`;
  return h;
}
const BU_BAR = () => ({static: `<div class="bu-bar">${buBarHtml()}</div>`});
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('.bu-pill'); if (b) buSetSel(b.dataset.bu); });

// Jauge de répartition qui accepte des valeurs négatives : les valeurs positives s'empilent à droite du zéro, les négatives (hachurées) à gauche.
// items = [{v, label, color}] ; sans valeur négative : jauge de parts classique, légende en %.
function signedGauge(items) {
  const pos = items.filter(i => i.v > 0), neg = items.filter(i => i.v < 0), P = pos.reduce((t, i) => t + i.v, 0), N = neg.reduce((t, i) => t - i.v, 0);
  if (P + N <= 0) return '';
  if (!neg.length) return `<div class="stack">${pos.map(i => `<div style="width:${i.v / P * 100}%;background:${i.color}"></div>`).join('')}</div><small class="na">${pos.map(i => `${i.label} ${pct(i.v / P)}`).join(' · ')}</small>`;
  const zero = N / (P + N) * 100, seg = (list, tot, cl) => list.map(i => `<div class="${cl}" style="width:${Math.abs(i.v) / tot * 100}%;background:${i.color}"></div>`).join('');
  return `<div class="sgauge" role="img" aria-label="${esc(items.map(i => i.label + ' ' + eur(i.v)).join(', '))}"><div class="sg-neg" style="width:${zero}%">${seg(neg, N, 'hatch')}</div><div class="sg-pos" style="width:${100 - zero}%">${seg(pos, P, '')}</div></div>`
    + `<small class="na">${items.map(i => `${i.label} <span class="${i.v < 0 ? 'neg' : ''}">${eur(i.v)}</span>`).join(' · ')} <span class="na">(hachuré : négatif)</span></small>`;
}
