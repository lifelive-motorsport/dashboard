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

let token = sessionStorage.getItem('idt'), tab = 'total', cfg;
const route = () => (location.hash.replace(/^#\/?/, '') || store.get('lm_page') || 'overview/ca');
const item = key => { const [g, i] = key.split('/'); const grp = MENU.find(m => m[0] === g);
  const it = grp && grp[2].find(x => x[0] === i); return grp && it ? {grp, it} : null; };

// ---- Périodes : chaque tableau a la sienne ---------------------------------------------------
const PERIODS = [['ytd','Année en cours'], ['6m','6 derniers mois'], ['3m','3 derniers mois'], ['lm','Mois dernier']];
const ymd = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
function monthsAgo(t, n) {           // même jour il y a n mois (ramené à la fin du mois si besoin)
  const d = new Date(t.getFullYear(), t.getMonth() - n, 1);
  d.setDate(Math.min(t.getDate(), new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate())); return d;
}
function periodRange(p) {
  const t = new Date();
  if (p === 'lm') return [ymd(new Date(t.getFullYear(), t.getMonth() - 1, 1)), ymd(new Date(t.getFullYear(), t.getMonth(), 0))];
  if (p === '6' || p === '6m' || p === '3m') { const d = monthsAgo(t, p === '3m' ? 3 : 6); d.setDate(d.getDate() + 1); return [ymd(d), ymd(t)]; }
  return [`${t.getFullYear()}-01-01`, ymd(t)];                       // ytd
}
const fmtDate = s => s.split('-').reverse().join('/');
let periods = {}; try { periods = JSON.parse(store.get('lm_periods') || '{}'); } catch {}
const periodOf = bid => PERIODS.some(p => p[0] === periods[bid]) ? periods[bid] : 'ytd';

// Données par période (clé = dates réelles, donc renouvelée chaque jour)
const cache = new Map();   // "from|to" -> {data, at}
const inflight = new Map();
async function getData(p, force) {
  const [f, t] = periodRange(p), key = f + '|' + t, hit = cache.get(key);
  if (hit && !force && Date.now() - hit.at < 60000) return hit.data;
  if (inflight.has(key) && !force) return inflight.get(key);
  const job = (async () => {
    const r = await fetch(`/api/dashboard?from=${f}&to=${t}${force ? '&refresh=true' : ''}`, {headers: token ? {Authorization: 'Bearer ' + token} : {}});
    if (r.status === 401) { sessionStorage.removeItem('idt'); token = null; needLogin(); throw new Error('Connexion requise'); }
    if (!r.ok) throw new Error(r.status === 403 ? 'Accès non autorisé pour ce compte' : r.status === 502 ? 'Odoo est momentanément injoignable (erreur 502)' : 'Erreur ' + r.status);
    const data = await r.json(); cache.set(key, {data, at: Date.now()}); return data;
  })().finally(() => inflight.delete(key));
  inflight.set(key, job); return job;
}
const entry = p => { const [f, t] = periodRange(p); return cache.get(f + '|' + t); };
const cached = p => { const h = entry(p); return h && h.data; };
const fresh = p => { const h = entry(p); return !!h && Date.now() - h.at < 60000; };
const anyData = () => { for (const h of cache.values()) return h.data; return null; };

// ---- Composants (tous reçoivent les données `d` de LA période du bloc) -----------------------
const kpi = (l, v, c='', sub='') => `<div class="card"><div class="v ${c}">${v}</div><div class="l">${esc(l)}</div>${sub ? `<div class="l">${sub}</div>` : ''}</div>`;
const margin = o => o.ca ? pct(o.margin / o.ca) : '–';
const grp = (d, k) => d.pnl.groups.find(g => g.key === k) || {ca: 0, direct_costs: 0, margin: 0};
const busOf = d => d.pnl.bus.filter(b => b.ca || b.direct_costs);

function bars(items, key, opts = {}) {
  const max = Math.max(...items.map(b => Math.abs(b[key])), 1);
  return `<div class="card">` + items.map(b => `<div class="row"><span>${esc(b.label)}</span>
    <div class="bars"><div class="bar solo ${key === 'ca' ? 'ca' : 'm' + (b[key] < 0 ? ' n' : '')}" style="width:${Math.abs(b[key]) / max * 100}%"></div></div>
    <span class="num ${key === 'margin' ? cls(b[key]) : ''}">${eur(b[key])}${opts.sub ? `<br><small class="na">${opts.sub(b)}</small>` : ''}</span></div>`).join('') + `</div>`;
}
const table = (head, rows) => `<div class="table-wrap"><table><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const lineRow = (label, o) => `<tr><td>${esc(label)}</td><td>${eur(o.ca)}</td><td>${eur(o.direct_costs)}</td>
  <td class="${cls(o.margin)}">${eur(o.margin)}</td><td class="${cls(o.margin)}">${margin(o)}</td></tr>`;
const HEAD = ['', 'CA', 'Frais directs', 'Marge brute', 'Marge %'];
const NOTE = t => ({static: `<div class="note">${t}</div>`});

function clients(d, allowed) {
  const tc = d.top_clients;
  if (tc.unavailable) return `<p class="na">${esc(tc.unavailable)}</p>`;
  const cur = allowed.includes(tab) ? tab : allowed[0];
  const labels = {total:'Total', XC:'XC', MODERN_RALLY:'Modern Rally', HISTORIC_RALLY:'Historic Rally', HISTORIC_RACING:'Historic Racing'};
  const m = tc._meta, info = !m ? '' : m.grouping
    ? `<small class="na">Regroupements d’après les étiquettes Odoo « regroup_client= » : ${m.groups} appliqué${m.groups > 1 ? 's' : ''}.</small>`
    : `<small class="neg">Regroupement indisponible : les clients sont affichés tels que saisis dans Odoo.</small>`;
  return `<div class="tabs">${allowed.map(k => `<button data-tab="${k}" class="${k === cur ? 'on' : ''}">${labels[k]}</button>`).join('')}</div>
    <ol>${(tc[cur] || []).map(c => `<li><span>${esc(c.name)}</span><b>${eur(c.ca)}</b></li>`).join('')}</ol>${info}`;
}

// Un bloc = un tableau/graphique avec son sélecteur de période. `fixed` = chiffre à date (pas de période).
const B = (id, title, render, fixed = false) => ({id, title, render, fixed});
const FINANCE = B('finance', 'Position financière (à date)', d => `<div class="kpis">${kpi('Trésorerie', eur(d.balance_sheet.cash), cls(d.balance_sheet.cash))
  + kpi('Créances clients', eur(d.balance_sheet.receivables)) + kpi('Dettes fournisseurs', eur(d.balance_sheet.payables))}</div>`, true);

const ALL_CLIENTS = ['total','XC','MODERN_RALLY','HISTORIC_RALLY','HISTORIC_RACING'];
const GROUP_LABEL = {XC: 'XC Cross Car', CARS: 'CARS', OTHER: 'Non affecté'};

// ---- Pages = listes de blocs --------------------------------------------------------------------
const PAGES = {
  'overview/ca': () => [
    B('kpi', 'Chiffre d’affaires', d => `<div class="kpis">${kpi('Chiffre d’affaires', eur(d.pnl.total.ca)) + kpi('CA XC', eur(grp(d,'XC').ca)) + kpi('CA CARS', eur(grp(d,'CARS').ca))}</div>`),
    FINANCE,
    B('bu', 'CA par BU', d => bars(busOf(d), 'ca', {sub: b => d.pnl.total.ca ? pct(b.ca / d.pnl.total.ca) + ' du CA' : ''})),
    B('clients', 'Hit-parade clients', d => clients(d, ALL_CLIENTS)),
  ],
  'overview/mb': () => [
    B('kpi', 'Marge brute', d => { const t = d.pnl.total; return `<div class="kpis">${kpi('Marge brute', eur(t.margin), cls(t.margin)) + kpi('Marge brute / CA', pct(t.margin_pct), cls(t.margin)) + kpi('Frais directs', eur(t.direct_costs))}</div>`; }),
    FINANCE,
    B('bu', 'Marge brute par BU', d => bars(busOf(d), 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + margin(b)})),
    NOTE('Marge brute = CA − frais directs (comptes 602, 603, 604). Personnel et véhicules (615) ne sont pas imputables à une BU et sont exclus.'),
  ],
  'xcvscars/ca': () => [
    B('cmp', 'CA : XC vs CARS', d => { const x = grp(d,'XC'), c = grp(d,'CARS'), tot = x.ca + c.ca || 1;
      return `<div class="two">${kpi('XC Cross Car', eur(x.ca), '', pct(x.ca / tot) + ' du CA')}${kpi('CARS', eur(c.ca), '', pct(c.ca / tot) + ' du CA')}</div>
      <div class="stack"><div style="width:${x.ca / tot * 100}%;background:var(--red)"></div><div style="width:${c.ca / tot * 100}%;background:var(--mut)"></div></div>
      <small class="na">Rouge : XC — gris : CARS (hors « Non affecté », ${eur(grp(d,'OTHER').ca)})</small>`; }),
  ],
  'xcvscars/mb': () => [
    B('cmp', 'Marge brute : XC vs CARS', d => { const x = grp(d,'XC'), c = grp(d,'CARS');
      return `<div class="two">${kpi('XC Cross Car', eur(x.margin), cls(x.margin), 'Marge brute · ' + margin(x))}${kpi('CARS', eur(c.margin), cls(c.margin), 'Marge brute · ' + margin(c))}</div>`; }),
    B('detail', 'Détail', d => table(HEAD, [lineRow('XC Cross Car', grp(d,'XC')), lineRow('CARS', grp(d,'CARS'))])),
  ],
  'xc/general': () => [
    B('kpi', 'XC — synthèse', d => { const x = grp(d,'XC'); return `<div class="kpis">${kpi('CA XC', eur(x.ca)) + kpi('Frais directs', eur(x.direct_costs)) + kpi('Marge brute', eur(x.margin), cls(x.margin)) + kpi('Marge brute / CA', margin(x), cls(x.margin))}</div>`; }),
    NOTE('Les lignes XC (Manufacturer, Race team, Goldspeed…) ne sont pas des activités indépendantes : les comparer entre elles peut être trompeur. Voir « Par ligne d’activité ».'),
    B('clients', 'Hit-parade clients XC', d => clients(d, ['XC'])),
  ],
  'xc/lignes': () => [
    B('lines', 'XC — par ligne d’activité', d => table(HEAD, d.pnl.bus.find(b => b.key === 'XC').lines.map(l => lineRow(l.line, l)))),
    NOTE('Le Race Team se déplace d’abord pour soutenir les clients constructeur ; le contrat Goldspeed découle du statut de constructeur XC. Les ventes webshop sont comptabilisées sur d’autres lignes que « Webshop » (CA = 0 sur cette ligne) — à confirmer.'),
  ],
  'xc/webshop': () => [
    B('shops', 'Ventes des webshops', d => d.webshops.unavailable ? `<p class="na">${esc(d.webshops.unavailable)}</p>`
      : `<div class="two">${d.webshops.map(w => kpi(w.name, eur(w.revenue), '', `${w.orders} commandes · panier moyen ${eur(w.avg_basket)}`)).join('')}</div>`),
    B('products', 'Produits les plus vendus', d => d.webshops.unavailable ? '' : d.webshops.map(w =>
      `<h4 class="sub">${esc(w.name)}</h4><ol>${(w.top_products || []).map(p => `<li><span>${esc(p)}</span></li>`).join('')}</ol>`).join('')),
    NOTE('Commandes confirmées, hors taxes, hors lignes de service (livraison…). Source : commandes Odoo par site web.'),
  ],
  'cars/general': () => [
    B('kpi', 'CARS — synthèse', d => { const c = grp(d,'CARS'); return `<div class="kpis">${kpi('CA CARS', eur(c.ca)) + kpi('Frais directs', eur(c.direct_costs)) + kpi('Marge brute', eur(c.margin), cls(c.margin)) + kpi('Marge brute / CA', margin(c), cls(c.margin))}</div>`; }),
    B('bu', 'Par BU', d => table(HEAD, d.pnl.bus.filter(b => b.group === 'CARS' && (b.ca || b.direct_costs)).map(b => lineRow(b.label, b)))),
  ],
  'cars/bu': () => [
    B('bu', 'Marge brute par BU', d => bars(d.pnl.bus.filter(b => b.group === 'CARS' && (b.ca || b.direct_costs)), 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + margin(b)})),
    B('clients', 'Hit-parade clients', d => clients(d, ['MODERN_RALLY','HISTORIC_RALLY','HISTORIC_RACING'])),
    NOTE('Modern Rally : le CA est surtout de la main-d’œuvre atelier (le client achète les pièces), ce qui gonfle le taux de marge.'),
  ],
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

let current = {key: null, blocks: []};
const bkey = b => current.key + ':' + b.id;
const selectHTML = (b, p) => `<select class="per" data-bid="${b.id}" aria-label="Période — ${esc(b.title)}">${PERIODS.map(([v, l]) => `<option value="${v}"${v === p ? ' selected' : ''}>${l}</option>`).join('')}</select>`;

function blockHTML(b) {
  if (b.static) return b.static;
  const p = periodOf(bkey(b)), d = b.fixed ? (anyData() || cached('ytd')) : cached(p), [f, t] = periodRange(p);
  const dates = b.fixed ? 'à date' : `${fmtDate(f)} → ${fmtDate(t)}`;
  return `<section class="block" data-bid="${b.id}"><div class="block-head"><h3>${esc(b.title)}</h3>
    <span class="per-wrap">${b.fixed ? '' : selectHTML(b, p)}<small class="per-dates">${dates}</small></span></div>
    <div class="block-body">${d ? b.render(d) : '<p class="na">Chargement…</p>'}</div></section>`;
}

function updateBlock(b) {   // ne redessine que ce bloc (conserve le défilement)
  const el = $('page').querySelector(`.block[data-bid="${b.id}"]`); if (!el) return;
  el.outerHTML = blockHTML(b);
}

async function fillBlock(b, force) {
  if (b.static) return;
  const p = b.fixed ? 'ytd' : periodOf(bkey(b));
  try { await getData(p, force); $('status').textContent = ''; $('status').className = ''; $('login').hidden = true; }
  catch (e) { if (e.message === 'Connexion requise') return;
    $('status').textContent = e.message + (anyData() ? ' — affichage des dernières données' : ''); $('status').className = 'err'; return; }
  if (current.blocks.includes(b)) updateBlock(b);
  const d = anyData(); if (d) $('foot').textContent = `Source : ${d.source}${d.source === 'demo' ? ' (DONNÉES FICTIVES)' : ''} — mis à jour ${new Date(d.generated_at).toLocaleString('fr-BE')}`;
}

function render(force) {
  let key = route(); if (!item(key)) key = 'overview/ca';
  const {grp: g, it} = item(key);
  renderNav(key);
  $('page-title').innerHTML = `${esc(g[1])} <small>›</small> ${esc(it[1])}`;
  const blocks = PAGES[key] ? PAGES[key]() : [];
  current = {key, blocks};
  $('page').innerHTML = PAGES[key] ? blocks.map(blockHTML).join('') : soon(key);
  blocks.forEach(b => { if (!b.static && (force || !fresh(b.fixed ? 'ytd' : periodOf(bkey(b))))) fillBlock(b, force); });  // données périmées : affichées, puis rafraîchies
  store.set('lm_page', key); document.body.classList.remove('nav-open'); $('menu-btn').setAttribute('aria-expanded', 'false');
  $('app').hidden = false; $('login').hidden = true;
}

function needLogin() {
  $('app').hidden = true; $('login').hidden = false;
  google.accounts.id.initialize({client_id: cfg.google_client_id, hd: undefined,
    callback: r => { token = r.credential; sessionStorage.setItem('idt', token); render(); }});
  google.accounts.id.renderButton($('g_btn'), {theme: 'filled_black', size: 'large', width: 280, locale: 'fr'});
}

// ---- Export PDF : impression navigateur avec feuille de style dédiée ------------------------------
function exportPdf() {
  const {grp: g, it} = item(current.key) || {grp: ['', ''], it: ['', '']};
  const stamp = new Date().toLocaleString('fr-BE');
  $('print-title').textContent = `${g[1]} › ${it[1]}`;
  $('print-meta').textContent = `Rapport généré le ${stamp}`;
  const old = document.title; document.title = `Lifelive – ${g[1]} – ${it[1]} – ${ymd(new Date())}`;
  const restore = () => { document.title = old; window.removeEventListener('afterprint', restore); };
  window.addEventListener('afterprint', restore); window.print();
}

$('refresh').onclick = () => render(true);
$('pdf').onclick = exportPdf;
$('menu-btn').onclick = () => { const o = document.body.classList.toggle('nav-open'); $('menu-btn').setAttribute('aria-expanded', String(o)); };
$('backdrop').onclick = () => document.body.classList.remove('nav-open');
$('nav').onclick = e => { const b = e.target.closest('.grp > button'); if (b) b.parentElement.classList.toggle('open'); };
$('page').onclick = e => { if (e.target.dataset.tab) { tab = e.target.dataset.tab; current.blocks.filter(b => !b.static).forEach(updateBlock); } };
$('page').onchange = e => {
  const bid = e.target.dataset.bid; if (!bid || !e.target.classList.contains('per')) return;
  const b = current.blocks.find(x => x.id === bid); periods[bkey(b)] = e.target.value; store.set('lm_periods', JSON.stringify(periods));
  updateBlock(b); fillBlock(b);
};
window.addEventListener('hashchange', () => { if ($('login').hidden) { render(); window.scrollTo(0, 0); } });
const tick = () => { if (document.visibilityState === 'visible' && $('login').hidden) render(); };
setInterval(tick, 5 * 60000);   // l'API met déjà ses réponses en cache 5 min
document.addEventListener('visibilitychange', tick);

(async () => {
  cfg = await (await fetch('/api/config')).json();
  if (cfg.auth) {
    await new Promise(res => { const s = document.createElement('script'); s.src = 'https://accounts.google.com/gsi/client'; s.onload = res; document.head.append(s); });
    if (!token) return needLogin();
  }
  render();
})();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');
