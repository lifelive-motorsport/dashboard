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
    if (pj.ready) { const t = pjAll().TOTAL.total, prev = pj.prev.reduce((s, m) => s + m.ca, 0);
      tiles.push(homeTile('Projection du CA ' + pj.year + (buSel !== 'all' ? ' · total' : ''), eur(t), '', prev > 0 ? pjVs(t, prev) + ' vs ' + (pj.year - 1) : 'selon le CA espéré encodé', '', '#/overview/ca')); }
  }
  if (d && allowedPage('overview/mb')) { const x = grp(d, 'XC'), c = grp(d, 'CARS'), t = buScope(d);
    tiles.push(homeTile('Marge brute' + (t.scoped ? ' · ' + t.label : ''), eur(t.margin), cls(t.margin), t.ca ? pct(t.margin / t.ca) + ' du CA' : '', t.scoped ? '' : homeGauge(x.margin, c.margin, 'XC', 'CARS'), '#/overview/mb')); }
  if (d && allowedPage('overview/nm')) {
    nm.d = d; nmEnsure();
    if (nm.ready && ex.alloc) { const cols = nmCompute(d).cols, keys = BU_KEYS[buSel] || Object.keys(cols), o = nmSum(cols, keys), net = nmNet(o);
      tiles.push(homeTile('Marge nette' + (buSel !== 'all' ? ' · ' + BU_PNL_LABEL[buSel] : ''), eur(net), cls(net), o.ca ? pct(net / o.ca) + ' du CA' : '', buSel !== 'all' ? '' : homeGauge(nmNet(nmSum(cols, ['XC'])), nmNet(nmSum(cols, NM_CARS)), 'XC', 'CARS'), '#/overview/nm')); }
    else tiles.push(homeTile('Marge nette', '…', '', nm.err ? esc(nm.err) : 'calcul en cours', '', '#/overview/nm'));
  }
  if (d && !d.webshops.unavailable) [['xc/webshop_xc', w => !/goldspeed/i.test(w.name)], ['xc/webshop_gs', w => /goldspeed/i.test(w.name)]].forEach(([k, pick]) => {
    if (!allowedPage(k)) return; const w = d.webshops.find(pick);
    if (w) tiles.push(homeTile(w.name, eur(w.revenue), '', `${w.orders} commandes · panier moyen ${eur(w.avg_basket)}`, '', '#/' + k)); });
  if (d && d.events && d.events.events) [['xc/events', ['XC'], 'Événements XC'], ['cars/events', ['CARS'], 'Événements CARS']].forEach(([k, groups, title]) => {
    if (!allowedPage(k)) return; const ev = d.events.events.filter(e => groups.includes(e.group));
    if (ev.length) { const ca = ev.reduce((s, e) => s + e.ca, 0), res = ev.reduce((s, e) => s + e.result, 0);
      tiles.push(homeTile(title, `${ev.length}`, '', `CA ${eur(ca)} · résultat cash <span class="${cls(res)}">${eur(res)}</span>`, '', '#/' + k)); } });
  if (allowedPage('xc/inventory')) {
    const s = stockState.data;
    if (s && s.total) tiles.push(homeTile('Valeur du stock XC', eur(s.total.value), '', s.as_of ? 'au ' + fmtDate(s.as_of) : '', '', '#/xc/inventory'));
    else { if (!stockState.loading && !stockState.error) loadStock(false).then(homeRedraw); tiles.push(homeTile('Valeur du stock XC', '…', '', stockState.error || 'chargement', '', '#/xc/inventory')); }
  }
  el.innerHTML = tiles.length ? `<div class="home-grid">${tiles.join('')}</div>` : '<p class="na">Aucun indicateur disponible pour vos accès. Utilisez le menu pour accéder à vos sections.</p>';
}
