const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const eur = n => new Intl.NumberFormat('fr-BE', {style:'currency', currency:'EUR', maximumFractionDigits:0}).format(n);
const pct = n => (n*100).toFixed(1).replace('.', ',') + ' %';
const cls = n => n < 0 ? 'neg' : 'pos';
const store = {get: k => { try { return localStorage.getItem(k); } catch { return null; } },
               set: (k, v) => { try { localStorage.setItem(k, v); } catch {} }};

// ---- Menu (id de page = « rubrique/élément ») ----------------------------------------------
const MENU = [
  ['overview', 'Overview', [['ca','CA'], ['mb','MB']]],
  ['xcvscars', 'XC vs CARS', [['ca','CA'], ['mb','MB']]],
  ['xc', 'XC Detail', [['general','Général'], ['lignes','Par ligne d’activité'], ['webshop','Par webshop'], ['events','Par événement'], ['inventory','Inventory']]],
  ['cars', 'CARS Detail', [['general','Général'], ['bu','Par BU'], ['events','Par événement'], ['vehicles','Par véhicule']]],
  ['staff', 'STAFF costs', [['general','Général'], ['xc','XC'], ['cars','CARS'], ['shared','Shared Services'], ['rules','Règles de répartition']]],
  ['expenses', 'GENERAL EXPENSES', [['general','Général'], ['xc','XC'], ['cars','CARS'], ['rules','Règles de répartition']]],
  ['vehicles', 'SERVICE VEHICLES', [['general','Général'], ['byvehicle','Par véhicule'], ['usage','Taux d’utilisation']]],
  ['racecars', 'RACE CARS', [['listing','Listing'], ['alerts','Alertes']]],
  ['others', 'Others', [['marketing','Marketing']]],
];
const LIVE = new Set(['overview/ca','overview/mb','xcvscars/ca','xcvscars/mb','xc/general','xc/lignes','xc/webshop','cars/general','cars/bu']);

// Pages en construction : ce qu'elles afficheront et ce qu'il faut pour les alimenter.
const PLAN = {
  'xc/events': ['CA, frais directs et marge par événement (course, meeting) pour XC.',
    'Savoir comment un événement est repéré dans Odoo (compte analytique, projet, étiquette sur les factures…). Les comptes « XC Events » (700014, 602014) donnent déjà le total, pas le détail.'],
  'xc/inventory': ['Valeur du stock XC dans le temps (pièces, véhicules, en-cours), par catégorie et par entrepôt, avec alertes de rupture et de surstock.',
    'Valider les entrepôts à inclure et la méthode de valorisation d’Odoo. L’analyse de septembre a montré que la valeur du stock varie fortement : une courbe mensuelle sera utile.'],
  'cars/events': ['CA, frais directs et marge par événement pour CARS (ex. Andalucia).',
    'La même règle d’identification des événements dans Odoo que pour XC.'],
  'cars/vehicles': ['Rentabilité par véhicule (voiture client ou de course).',
    'Comment le véhicule est identifié sur les factures et achats (n° de châssis, immatriculation, étiquette…).'],
  'staff/general': ['Coûts de personnel (comptes 62) : total, évolution, ventilation XC / CARS / Shared Services.',
    'Les clés de répartition (XC 60 %, clés nominatives pour CARS, Shared Services) reprises de l’analyse de septembre, à confirmer.'],
  'staff/xc': ['Part du personnel imputée à XC selon la règle de répartition.', 'La règle de répartition validée.'],
  'staff/cars': ['Part du personnel imputée à chaque BU de CARS (clés nominatives par personne).', 'Les clés nominatives validées et à jour.'],
  'staff/shared': ['Coûts des Shared Services (indépendante, polyvalent, Managing Director).', 'Décider si ces coûts sont affichés et comment ils sont répartis.'],
  'staff/rules': ['Tableau des clés de répartition du personnel, consultable par les actionnaires.',
    'Où stocker ces clés (dans l’application) et qui peut les modifier.'],
  'expenses/general': ['Frais généraux (loyer, IT, assurances, divers, véhicules) : total et évolution.',
    'Liste des comptes à inclure et à exclure (honoraires, personnel, véhicules de service).'],
  'expenses/xc': ['Part des frais généraux imputée à XC (50 % dans l’analyse de septembre).', 'La règle de répartition validée.'],
  'expenses/cars': ['Part des frais généraux imputée à CARS (au prorata du CA).', 'La règle de répartition validée.'],
  'expenses/rules': ['Tableau des clés de répartition des frais généraux.', 'Où stocker ces clés et qui peut les modifier.'],
  'vehicles/general': ['Coûts des véhicules de service (comptes 615xxx) : carburant, entretien, taxes, assurance, péages.',
    'Confirmer le périmètre des véhicules et le regroupement des comptes 615.'],
  'vehicles/byvehicle': ['Coût complet par véhicule (BMW X5, Citan, Sprinter, camions…).', 'Les comptes 615 sont déjà classés par véhicule : prêt à brancher.'],
  'vehicles/usage': ['Taux d’utilisation de chaque véhicule d’après les agendas Google des ressources.',
    'Un accès en lecture aux agendas Google des véhicules et leur convention de nommage.'],
  'racecars/listing': ['Liste des voitures de course (état, lieu, propriétaire, prochaines échéances).',
    'Où ces voitures sont gérées dans Odoo (stock, produits, flotte…) et les champs à afficher.'],
  'racecars/alerts': ['Alertes : échéances (homologation, entretien…), stock bas, etc.', 'La liste des alertes voulues et leur source.'],
  'others/marketing': ['Dépenses marketing (comptes 6120xx), éventuellement sponsoring et budget.',
    'Le périmètre exact (comptes, sponsoring) et un budget de référence.'],
};

let token = sessionStorage.getItem('idt'), data = null, tab = 'total', cfg;
const route = () => (location.hash.replace(/^#\/?/, '') || store.get('lm_page') || 'overview/ca');
const item = key => { const [g, i] = key.split('/'); const grp = MENU.find(m => m[0] === g);
  const it = grp && grp[2].find(x => x[0] === i); return grp && it ? {grp, it} : null; };

function range() {
  const t = new Date(), y = t.getFullYear(), f = d => d.toISOString().slice(0,10);
  switch ($('period').value) {
    case 'month': return [f(new Date(Date.UTC(y, t.getMonth(), 1))), f(t)];
    case 'prev': return [`${y-1}-01-01`, `${y-1}-12-31`];
    case '12m': return [f(new Date(Date.UTC(y-1, t.getMonth(), t.getDate()+1))), f(t)];
    default: return [`${y}-01-01`, f(t)];
  }
}

// ---- Composants -----------------------------------------------------------------------------
const kpi = (l, v, c='', sub='') => `<div class="card"><div class="v ${c}">${v}</div><div class="l">${esc(l)}</div>${sub ? `<div class="l">${sub}</div>` : ''}</div>`;
const note = t => `<div class="note">${t}</div>`;
const section = (t, html) => `<h3>${esc(t)}</h3>${html}`;
const margin = o => o.ca ? pct(o.margin / o.ca) : '–';

function bars(items, key, opts = {}) {
  const max = Math.max(...items.map(b => Math.abs(b[key])), 1);
  return `<div class="card">` + items.map(b => `<div class="row"><span>${esc(b.label)}</span>
    <div class="bars"><div class="bar solo ${key === 'ca' ? 'ca' : 'm' + (b[key] < 0 ? ' n' : '')}" style="width:${Math.abs(b[key]) / max * 100}%"></div></div>
    <span class="num ${key === 'margin' ? cls(b[key]) : ''}">${eur(b[key])}${opts.sub ? `<br><small class="na">${opts.sub(b)}</small>` : ''}</span></div>`).join('') + `</div>`;
}

function table(head, rows) {
  return `<div class="table-wrap"><table><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}
const lineRow = (label, o) => `<tr><td>${esc(label)}</td><td>${eur(o.ca)}</td><td>${eur(o.direct_costs)}</td>
  <td class="${cls(o.margin)}">${eur(o.margin)}</td><td class="${cls(o.margin)}">${margin(o)}</td></tr>`;
const HEAD = ['', 'CA', 'Frais directs', 'Marge brute', 'Marge %'];

function financeStrip() {
  const bs = data.balance_sheet;
  return section('Position financière', `<div class="kpis">${kpi('Trésorerie', eur(bs.cash), cls(bs.cash))
    + kpi('Créances clients', eur(bs.receivables)) + kpi('Dettes fournisseurs', eur(bs.payables))}</div>`);
}

function clients(allowed) {
  const tc = data.top_clients;
  if (tc.unavailable) return `<p class="na">${esc(tc.unavailable)}</p>`;
  const tabs = allowed.includes(tab) ? tab : allowed[0];
  const labels = {total:'Total', XC:'XC', MODERN_RALLY:'Modern Rally', HISTORIC_RALLY:'Historic Rally', HISTORIC_RACING:'Historic Racing'};
  return `<div class="tabs">${allowed.map(k => `<button data-tab="${k}" class="${k === tabs ? 'on' : ''}">${labels[k]}</button>`).join('')}</div>
    <ol>${(tc[tabs] || []).map(c => `<li><span>${esc(c.name)}</span><b>${eur(c.ca)}</b></li>`).join('')}</ol>`;
}

const bus = () => data.pnl.bus.filter(b => b.ca || b.direct_costs);
const grp = k => data.pnl.groups.find(g => g.key === k) || {ca: 0, direct_costs: 0, margin: 0};
const GROUP_LABEL = {XC: 'XC Cross Car', CARS: 'CARS', OTHER: 'Non affecté'};

// ---- Pages -------------------------------------------------------------------------------------
const PAGES = {
  'overview/ca'() {
    const t = data.pnl.total;
    return `<div class="kpis">${kpi('Chiffre d’affaires', eur(t.ca)) + kpi('CA XC', eur(grp('XC').ca)) + kpi('CA CARS', eur(grp('CARS').ca))}</div>`
      + financeStrip() + section('CA par BU', bars(bus(), 'ca', {sub: b => t.ca ? pct(b.ca / t.ca) + ' du CA' : ''}))
      + section('Hit-parade clients', clients(['total','XC','MODERN_RALLY','HISTORIC_RALLY','HISTORIC_RACING']));
  },
  'overview/mb'() {
    const t = data.pnl.total;
    return `<div class="kpis">${kpi('Marge brute', eur(t.margin), cls(t.margin)) + kpi('Marge brute / CA', pct(t.margin_pct), cls(t.margin))
      + kpi('Frais directs', eur(t.direct_costs))}</div>` + financeStrip()
      + section('Marge brute par BU', bars(bus(), 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + margin(b)}))
      + note('Marge brute = CA − frais directs (comptes 602, 603, 604). Personnel et véhicules (615) ne sont pas imputables à une BU et sont exclus.');
  },
  'xcvscars/ca'() {
    const x = grp('XC'), c = grp('CARS'), tot = x.ca + c.ca || 1;
    return `<div class="two">${kpi('XC Cross Car', eur(x.ca), '', pct(x.ca / tot) + ' du CA')}${kpi('CARS', eur(c.ca), '', pct(c.ca / tot) + ' du CA')}</div>
      <div class="stack"><div style="width:${x.ca / tot * 100}%;background:var(--red)"></div><div style="width:${c.ca / tot * 100}%;background:var(--mut)"></div></div>
      <small class="na">Rouge : XC — gris : CARS (hors « Non affecté », ${eur(grp('OTHER').ca)})</small>`;
  },
  'xcvscars/mb'() {
    const x = grp('XC'), c = grp('CARS');
    return `<div class="two">${kpi('XC Cross Car', eur(x.margin), cls(x.margin), 'Marge brute · ' + margin(x))}${kpi('CARS', eur(c.margin), cls(c.margin), 'Marge brute · ' + margin(c))}</div>`
      + section('Détail', table(HEAD, [lineRow('XC Cross Car', x), lineRow('CARS', c)]));
  },
  'xc/general'() {
    const x = grp('XC');
    return `<div class="kpis">${kpi('CA XC', eur(x.ca)) + kpi('Frais directs', eur(x.direct_costs)) + kpi('Marge brute', eur(x.margin), cls(x.margin))
      + kpi('Marge brute / CA', margin(x), cls(x.margin))}</div>`
      + note('Les lignes XC (Manufacturer, Race team, Goldspeed…) ne sont pas des activités indépendantes : les comparer entre elles peut être trompeur. Voir « Par ligne d’activité ».')
      + section('Hit-parade clients XC', clients(['XC']));
  },
  'xc/lignes'() {
    const xc = data.pnl.bus.find(b => b.key === 'XC');
    return table(HEAD, xc.lines.map(l => lineRow(l.line, l)))
      + note('Le Race Team se déplace d’abord pour soutenir les clients constructeur ; le contrat Goldspeed découle du statut de constructeur XC. Les ventes webshop sont comptabilisées sur d’autres lignes que « Webshop » (CA = 0 sur cette ligne) — à confirmer.');
  },
  'xc/webshop'() {
    const ws = data.webshops;
    if (ws.unavailable) return `<p class="na">${esc(ws.unavailable)}</p>`;
    return `<div class="two">${ws.map(w => kpi(w.name, eur(w.revenue), '', `${w.orders} commandes · panier moyen ${eur(w.avg_basket)}`)).join('')}</div>`
      + ws.map(w => section('Produits les plus vendus — ' + w.name, `<ol>${(w.top_products || []).map(p => `<li><span>${esc(p)}</span></li>`).join('')}</ol>`)).join('')
      + note('Commandes confirmées, hors taxes, hors lignes de service (livraison…). Source : commandes Odoo par site web.');
  },
  'cars/general'() {
    const c = grp('CARS');
    return `<div class="kpis">${kpi('CA CARS', eur(c.ca)) + kpi('Frais directs', eur(c.direct_costs)) + kpi('Marge brute', eur(c.margin), cls(c.margin))
      + kpi('Marge brute / CA', margin(c), cls(c.margin))}</div>`
      + section('Par BU', table(HEAD, data.pnl.bus.filter(b => b.group === 'CARS' && (b.ca || b.direct_costs)).map(b => lineRow(b.label, b))));
  },
  'cars/bu'() {
    const list = data.pnl.bus.filter(b => b.group === 'CARS' && (b.ca || b.direct_costs));
    return section('Marge brute par BU', bars(list, 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + margin(b)}))
      + section('Hit-parade clients', clients(['MODERN_RALLY','HISTORIC_RALLY','HISTORIC_RACING']))
      + note('Modern Rally : le CA est surtout de la main-d’œuvre atelier (le client achète les pièces), ce qui gonfle le taux de marge.');
  },
};

function soon(key) {
  const [what, needs] = PLAN[key] || ['Cette page.', 'À préciser ensemble.'];
  return `<div class="soon-box"><span class="tag">En construction</span>
    <h4>Ce que cette page affichera</h4><ul><li>${esc(what)}</li></ul>
    <h4>Ce qu’il faut pour la construire</h4><ul><li>${esc(needs)}</li></ul></div>`;
}

// ---- Rendu -----------------------------------------------------------------------------------
function renderNav(key) {
  const cur = key.split('/')[0];
  $('nav').innerHTML = MENU.map(([g, label, items]) => `<div class="grp ${g === cur ? 'open active' : ''}" data-g="${g}">
    <button type="button">${esc(label)}</button><ul>${items.map(([i, l]) => {
      const k = g + '/' + i, live = LIVE.has(k);
      return `<li><a href="#/${k}" class="${k === key ? 'on' : ''} ${live ? '' : 'soon'}">${esc(l)}${live ? '' : '<small>bientôt</small>'}</a></li>`; }).join('')}</ul></div>`).join('');
}

function render() {
  let key = route(); if (!item(key)) key = 'overview/ca';
  const {grp: g, it} = item(key);
  renderNav(key);
  $('page-title').innerHTML = `${esc(g[1])} <small>›</small> ${esc(it[1])}`;
  $('page').innerHTML = data ? (PAGES[key] ? PAGES[key]() : soon(key)) : '<p class="na">Chargement…</p>';
  if (data) { const d = new Date(data.generated_at);
    $('foot').textContent = `Source : ${data.source}${data.source === 'demo' ? ' (DONNÉES FICTIVES)' : ''} — période ${data.period.from} → ${data.period.to} — mis à jour ${d.toLocaleString('fr-BE')}`; }
  store.set('lm_page', key); document.body.classList.remove('nav-open'); $('menu-btn').setAttribute('aria-expanded', 'false');
  $('app').hidden = false;
}

async function load(force) {
  const [f, t] = range();
  try {
    const r = await fetch(`/api/dashboard?from=${f}&to=${t}${force ? '&refresh=true' : ''}`, {headers: token ? {Authorization: 'Bearer ' + token} : {}});
    if (r.status === 401) { sessionStorage.removeItem('idt'); token = null; return needLogin(); }
    if (!r.ok) throw new Error(r.status === 403 ? 'Accès non autorisé pour ce compte' : r.status === 502 ? 'Odoo est momentanément injoignable (erreur 502)' : 'Erreur ' + r.status);
    data = await r.json(); $('status').textContent = ''; $('status').className = ''; $('login').hidden = true; render();
  } catch (e) { $('status').textContent = e.message + (data ? ' — affichage des dernières données' : ''); $('status').className = 'err'; }
}

function needLogin() {
  $('app').hidden = true; $('login').hidden = false;
  google.accounts.id.initialize({client_id: cfg.google_client_id, hd: undefined,
    callback: r => { token = r.credential; sessionStorage.setItem('idt', token); load(); }});
  google.accounts.id.renderButton($('g_btn'), {theme: 'filled_black', size: 'large', width: 280, locale: 'fr'});
}

$('period').onchange = () => load();
$('refresh').onclick = () => load(true);
$('menu-btn').onclick = () => { const o = document.body.classList.toggle('nav-open'); $('menu-btn').setAttribute('aria-expanded', String(o)); };
$('backdrop').onclick = () => document.body.classList.remove('nav-open');
$('nav').onclick = e => { const b = e.target.closest('.grp > button'); if (b) b.parentElement.classList.toggle('open'); };
$('page').onclick = e => { if (e.target.dataset.tab) { tab = e.target.dataset.tab; render(); } };
window.addEventListener('hashchange', () => { if ($('login').hidden) render(); window.scrollTo(0, 0); });
setInterval(() => document.visibilityState === 'visible' && load(), 60000);
document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && load());

(async () => {
  cfg = await (await fetch('/api/config')).json();
  if (cfg.auth) {
    await new Promise(res => { const s = document.createElement('script'); s.src = 'https://accounts.google.com/gsi/client'; s.onload = res; document.head.append(s); });
    if (!token) return needLogin();
  }
  load();
})();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');
