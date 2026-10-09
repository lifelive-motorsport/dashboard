// Logbook › Accueil : message de bienvenue, profil, indicateurs visuels selon les accès de l'utilisateur, dernières mises à jour. Chargé avant app.js.
let me = {name: '', first: '', profile: '', email: ''};
const homeHello = () => { const h = new Date().getHours(); return h >= 5 && h < 18 ? 'Bonjour' : 'Bonsoir'; };
function homeBlocks() {
  const dt = new Date().toLocaleDateString('fr-BE', {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
  const first = me.first || '';
  return [
    {static: `<section class="block home-hero"><div class="hello">${homeHello()}${first ? ' ' + esc(first) : ''} !</div><div class="who">${esc(me.name || me.email || '')}${me.profile ? ` <span class="badge-profile">${esc(me.profile)}</span>` : ''}</div><small class="na">${esc(dt.charAt(0).toUpperCase() + dt.slice(1))}</small></section>`},
    BU_BAR(),
    {static: '<section class="block" data-bid="home-kpis"><div class="block-head"><h3>Vos indicateurs</h3><span class="per-wrap"><small class="per-dates">année en cours</small></span></div><div class="block-body" id="home-kpis"><p class="na">Chargement…</p></div></section>'},
    {static: '<section class="block" data-bid="home-news"><div class="block-head"><h3>Dernières mises à jour</h3></div><div class="block-body" id="home-news"></div></section>'},
  ];
}
const homeGauge = (a, b, la, lb) => signedGauge([{v: a, label: la, color: 'var(--red)'}, {v: b, label: lb, color: 'var(--mut)'}]);
const homeTile = (title, value, cl, sub, extra = '', href = '') => `<${href ? 'a href="' + href + '"' : 'div'} class="card home-tile"><div class="l">${esc(title)}</div><div class="v ${cl}">${value}</div>${sub ? `<div class="l">${sub}</div>` : ''}${extra}</${href ? 'a' : 'div'}>`;

async function homeDraw() {
  homeData = null;
  const news = document.getElementById('home-news');
  if (news) news.innerHTML = CHANGELOG.slice(0, 6).map(c => `<div class="news"><div class="news-h"><b>${esc(c.title)}</b> <span class="badge-profile">${esc(c.tag)}</span> <small class="na">${esc(c.date)}</small></div><ul>${c.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>`).join('');
  homeRedraw();
}
let homeData = null;
async function homeRedraw() {
  const el = document.getElementById('home-kpis'); if (!el) return;
  const want = ['overview/ca', 'overview/mb', 'overview/nm', 'xc/webshop_xc', 'xc/webshop_gs', 'xc/events', 'cars/events', 'xc/inventory'].filter(allowedPage);
  if (!want.length) { el.innerHTML = '<p class="na">Utilisez le menu pour accéder à vos sections.</p>'; return; }
  const needData = want.some(k => k !== 'xc/inventory');
  if (needData && !homeData) {
    try { homeData = viewData(await getData('ytd')); } catch (e) { el.innerHTML = `<p class="neg">${esc(e.message)}</p>`; return; }
    if (!document.getElementById('home-kpis')) return;
  }
  const d = homeData, tiles = [];
  if (d && allowedPage('overview/ca')) {
    const x = grp(d, 'XC'), c = grp(d, 'CARS'), pv = d.pnl_prev, sc = buScope(d);
    tiles.push(homeTile('Chiffre d’affaires' + (sc.scoped ? ' · ' + sc.label : ''), eur(sc.ca), '', !sc.scoped && pv && pv.total.ca > 0 ? vsPrev(sc.ca, pv.total.ca, pv.period.from.slice(0, 4)) : sc.scoped && d.pnl.total.ca > 0 ? pct(sc.ca / d.pnl.total.ca) + ' du CA total' : '', sc.scoped ? '' : homeGauge(x.ca, c.ca, 'XC', 'CARS'), '#/overview/ca'));
    pjEnsure();
    if (pj.ready && buSel === 'all') { const t = pjAll().TOTAL.total, prev = pj.prev.reduce((s, m) => s + m.ca, 0);
      tiles.push(homeTile('Projection du CA ' + pj.year + '', eur(t), '', prev > 0 ? pjVs(t, prev) + ' vs ' + (pj.year - 1) : 'selon le CA espéré encodé', '', '#/overview/ca')); }
  }
  if (d && allowedPage('overview/mb')) { const x = grp(d, 'XC'), c = grp(d, 'CARS'), t = buScope(d);
    tiles.push(homeTile('Marge brute' + (t.scoped ? ' · ' + t.label : ''), eur(t.margin), cls(t.margin), t.ca ? pct(t.margin / t.ca) + ' du CA' : '', t.scoped ? '' : homeGauge(x.margin, c.margin, 'XC', 'CARS'), '#/overview/mb')); }
  if (d && allowedPage('overview/nm')) {
    nm.d = d; nmEnsure();
    if (nm.ready && ex.alloc) { const cols = nmCompute(d).cols, keys = BU_KEYS[buSel] || Object.keys(cols), o = nmSum(cols, keys), net = nmNet(o);
      tiles.push(homeTile('Marge nette' + (buSel !== 'all' ? ' · ' + BU_PNL_LABEL[buSel] : ''), eur(net), cls(net), o.ca ? pct(net / o.ca) + ' du CA' : '', buSel !== 'all' ? '' : homeGauge(nmNet(nmSum(cols, ['XC'])), nmNet(nmSum(cols, NM_CARS)), 'XC', 'CARS'), '#/overview/nm')); }
    else tiles.push(homeTile('Marge nette', '…', '', nm.err ? esc(nm.err) : 'calcul en cours', '', '#/overview/nm'));
  }
  // Effectifs (ETP) : données du personnel, réservées aux administrateurs
  if (allowedPage('staff/people')) { const t = homeEtpTile(); if (t) tiles.push(t); }
  // Événements : ceux de la sélection (toutes les BU accessibles, XC, CARS ou une BU CARS)
  if (d && d.events && d.events.events) {
    const keys = BU_KEYS[buSel], groups = ['XC', 'CARS'].filter(g => allowedPage(g === 'XC' ? 'xc/events' : 'cars/events')), ok = e => groups.includes(e.group) && (!keys || (e.bus || []).some(b => keys.includes(b.bu)) || (buSel === 'xc' && e.group === 'XC') || (buSel === 'cars' && e.group === 'CARS'));
    const ev = d.events.events.filter(ok);
    if (ev.length) { const ca = ev.reduce((s2, e) => s2 + e.ca, 0), res = ev.reduce((s2, e) => s2 + e.result, 0);
      tiles.push(homeTile('Événements' + (buSel !== 'all' ? ' · ' + BU_PNL_LABEL[buSel] : ''), `${ev.length}`, '', `CA ${eur(ca)} · résultat cash <span class="${cls(res)}">${eur(res)}</span>`, '', (buSel === 'all' ? (groups.length === 1 ? '#/' + (groups[0] === 'XC' ? 'xc/events' : 'cars/events') : '') : '#/' + (buSel === 'xc' ? 'xc/events' : 'cars/events')))); } }          // « Toutes » mélange XC et CARS : pas de lien (sauf si une seule des deux est accessible)
  // Webshops et stock : propres à XC, affichés uniquement quand XC est sélectionné
  if (buSel === 'xc') {
    if (d && !d.webshops.unavailable) [['xc/webshop_xc', w => !/goldspeed/i.test(w.name)], ['xc/webshop_gs', w => /goldspeed/i.test(w.name)]].forEach(([k, pick]) => {
      if (!allowedPage(k)) return; const w = d.webshops.find(pick);
      if (w) tiles.push(homeTile(w.name, eur(w.revenue), '', `${w.orders} commandes · panier moyen ${eur(w.avg_basket)}`, '', '#/' + k)); });
    if (allowedPage('xc/inventory')) {
      const st = stockState.data;
      if (st && st.total) tiles.push(homeTile('Valeur du stock XC', eur(st.total.value), '', st.as_of ? 'au ' + fmtDate(st.as_of) : '', '', '#/xc/inventory'));
      else { if (!stockState.loading && !stockState.error) loadStock(false).then(homeRedraw); tiles.push(homeTile('Valeur du stock XC', '…', '', stockState.error || 'chargement', '', '#/xc/inventory')); }
    }
  }
  el.innerHTML = tiles.length ? `<div class="home-grid">${tiles.join('')}</div>` : '<p class="na">Aucun indicateur disponible pour vos accès. Utilisez le menu pour accéder à vos sections.</p>';
}

// ETP par BU : temps de travail (%) de chaque personne active × sa part d'imputation. Données du personnel : réservées aux administrateurs.
function homeEtp() {
  if (typeof sd === 'undefined' || !sd.loaded || sd.restricted || !sd.doc) return null;
  const r = {XC: 0, MODERN_RALLY: 0, HISTORIC_RACING: 0, HISTORIC_RALLY: 0, SHARED: 0, MANAGEMENT: 0, UNALLOC: 0, total: 0};
  sd.doc.people.filter(p => p.active).forEach(p => { const f = (+p.fte || 100) / 100, al = p.alloc || {}, used = Object.values(al).reduce((t, v) => t + (+v || 0), 0);
    r.total += f; ['XC', 'MODERN_RALLY', 'HISTORIC_RACING', 'HISTORIC_RALLY', 'SHARED', 'MANAGEMENT'].forEach(k => { r[k] += f * (+al[k] || 0) / 100; }); r.UNALLOC += f * Math.max(0, 100 - used) / 100; });
  return r;
}
let homeEtpTried = false;
const homeEtpFmt = v => (Math.round(v * 10) / 10).toString().replace('.', ',');
function homeEtpTile() {
  if (typeof sd !== 'undefined' && !sd.loaded && !homeEtpTried) { homeEtpTried = true; sdLoad().then(homeRedraw); }
  const e = homeEtp(); if (!e) return null;
  const ROWS = [['XC', 'XC Cross', 'var(--bu-xc)'], ['MODERN_RALLY', 'Modern Rally', 'var(--bu-mr-ui)'], ['HISTORIC_RACING', 'Historic Racing', 'var(--bu-hrc)'], ['HISTORIC_RALLY', 'Historic Rally', 'var(--bu-hrl)'], ['SHARED', 'Shared Services', 'var(--bu-groupe-symbole)'], ['MANAGEMENT', 'Management', 'var(--mut)'], ['UNALLOC', 'Non imputé', 'var(--border)']];
  const keys = BU_KEYS[buSel], rows = keys ? ROWS.filter(r => keys.includes(r[0])) : ROWS.filter(r => e[r[0]] > 0.005), tot = keys ? rows.reduce((t, r) => t + e[r[0]], 0) : e.total;
  const bar = rows.length > 1 ? `<div class="stack">${rows.map(r => `<div style="width:${e[r[0]] / (tot || 1) * 100}%;background:${r[2]}"></div>`).join('')}</div>` : '';
  const list = `<div class="etp-list">${rows.map(r => `<div><span class="etp-dot" style="background:${r[2]}"></span>${esc(r[1])}<b>${homeEtpFmt(e[r[0]])}</b></div>`).join('')}</div>`;
  return homeTile('Effectifs (ETP)' + (buSel !== 'all' ? ' · ' + BU_PNL_LABEL[buSel] : ''), homeEtpFmt(tot), '', 'équivalents temps plein, imputés par BU', bar + list, '#/staff/people');
}
