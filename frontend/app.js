const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const eur = n => new Intl.NumberFormat(LOCALE(), {style:'currency', currency:'EUR', maximumFractionDigits:0}).format(n);
const num = n => new Intl.NumberFormat(LOCALE(), {maximumFractionDigits: 2}).format(n);
const decFmt = v => LANG === 'en' ? v : v.replace('.', ',');
const pct = n => LANG === 'en' ? (n*100).toFixed(1) + '%' : (n*100).toFixed(1).replace('.', ',') + ' %';
const cls = n => n < 0 ? 'neg' : 'pos';
const store = {get: k => { try { return localStorage.getItem(k); } catch { return null; } },
               set: (k, v) => { try { localStorage.setItem(k, v); } catch {} }};

// Catégorie « XC » (adresses de XC_ONLY_EMAILS côté serveur) : uniquement ces pages ; le serveur refuse tout le reste
let role = 'full', superUser = false, pagesList = null;       // pagesList : pages de la catégorie de l'utilisateur (null = toutes)
const allowedPage = k => k === 'home/welcome' || ((k !== 'others/users' || superUser) && (!pagesList || pagesList.has(k)));
const homePage = () => 'home/welcome';
const needsAdj = () => !pagesList || ['overview/mb', 'overview/nm', 'overview/xcvscars', 'overview/adjustments', 'xc/general', 'xc/lignes', 'cars/general', 'cars/bu'].some(k => pagesList.has(k));
const setSession = sj => { me = {name: sj.name || '', first: sj.first || '', profile: sj.profile || '', email: sj.email || ''}; role = sj.role || 'full'; superUser = !!sj.super; pagesList = sj.pages ? new Set(sj.pages) : null; };

// ---- Menu (id de page = « rubrique/élément ») ----------------------------------------------
const MENU = [
  ['home', 'Accueil', [['welcome','Accueil']]],
  ['overview', 'Vue d’ensemble', [['ca','Chiffre d’affaires'], ['mb','Marge brute'], ['nm','Marge nette'], ['xcvscars','XC vs CARS'], ['clients','Clients'], ['suppliers','Fournisseurs'], ['adjustments','Ajustements MB']]],
  ['xc', 'Détail XC', [['general','Général'], ['lignes','Par ligne d’activité'], ['webshop_xc','XC Webshop'], ['webshop_gs','Goldspeed EAX Webshop'], ['events','Par événement'], ['inventory','Stock'], ['margins','Contrôle des marges s/ produits'], ['tn11','Contrôle des marges s/ TN11']]],
  ['cars', 'Détail CARS', [['general','Général'], ['bu','Par BU'], ['events','Par événement'], ['vehicles','Par véhicule']]],
  ['staff', 'Coûts du personnel', [['source','Données source'], ['people','Imputation du personnel'], ['general','Général'], ['xc','XC'], ['cars','CARS'], ['shared','Shared Services'], ['management','Management']]],
  ['expenses', 'Frais généraux', [['source','Données source'], ['general','Général'], ['rules','Imputation des frais généraux']]],
  ['vehicles', 'Véhicules de service', [['source','Données source'], ['general','Général'], ['byvehicle','Par véhicule'], ['fuel','Carburant'], ['usage','Imputation des frais véhicules']]],
  ['marketing', 'Marketing', [['site','Site internet'], ['expenses','Dépenses marketing']]],
  ['planifier', 'Planifier', [['events','Événements'], ['resources','Ressources']]],
  ['consigner', 'Consigner', [['timesheets','Pointages'], ['rides','Roulages'], ['consumables','Consommables']]],
  ['others', 'Administrer', [['tags','Tags Odoo'], ['users','Utilisateurs']]],
];
const LIVE = new Set(['home/welcome','xc/events','cars/events','cars/vehicles','overview/ca','overview/mb','overview/nm','overview/clients','overview/suppliers','overview/xcvscars','overview/adjustments','xc/inventory','xc/margins','xc/tn11','marketing/site','marketing/expenses','others/tags','others/users','expenses/source','expenses/general','expenses/rules','vehicles/source','vehicles/general','vehicles/byvehicle','vehicles/fuel','staff/source','staff/people','staff/general','staff/xc','staff/cars','staff/shared','staff/management','xc/general','xc/lignes','xc/webshop_xc','xc/webshop_gs','cars/general','cars/bu','vehicles/usage']);

// Pages en construction : ce qu'elles afficheront et ce qu'il faut pour les alimenter.
const PLAN = {
  'planifier/events': ['Courses, essais et roulages clients : création et mise à jour des événements dans les agendas Google partagés, avec la couleur de la BU.', 'Valider les agendas à utiliser et donner au compte de service un droit d’écriture sur ces agendas.'],
  'planifier/resources': ['Allocation du personnel, des voitures, des camions et du matériel à chaque événement, avec les conflits de réservation.', 'Lister les ressources (agendas de ressources Google, fiches Odoo) et les règles d’allocation.'],
  'consigner/timesheets': ['Fiches de pointage de l’atelier : heures par job, par voiture et par technicien, saisies depuis un téléphone.', 'Décider si les heures se saisissent dans Odoo (feuilles de temps, clé API en écriture) ou dans Logbook.'],
  'consigner/rides': ['Suivi des meetings : rapports de roulage, réglages, remarques du pilote, séance par séance (données propres à Logbook).', 'Définir le modèle d’un rapport de roulage (champs, réglages, pièces jointes) avec les mécaniciens et ingénieurs.'],
  'consigner/consumables': ['Stocks de pneus et de carburant, mouvements par événement et par voiture.', 'Choisir les emplacements et articles de stock Odoo à suivre et qui encode les mouvements.'],
  'xc/events': ['CA, coûts directs et marge par événement (course, meeting) pour XC.',
    'Savoir comment un événement est repéré dans Odoo (compte analytique, projet, étiquette sur les factures…). Les comptes « XC Events » (700014, 602014) donnent déjà le total, pas le détail.'],
  'xc/inventory': ['Valeur du stock XC dans le temps (pièces, véhicules, en-cours), par catégorie et par entrepôt, avec alertes de rupture et de surstock.',
    'Valider les entrepôts à inclure et la méthode de valorisation d’Odoo. L’analyse de septembre a montré que la valeur du stock varie fortement : une courbe mensuelle sera utile.'],
  'cars/events': ['CA, coûts directs et marge par événement pour CARS (ex. Andalucia).',
    'La même règle d’identification des événements dans Odoo que pour XC.'],
  'staff/general': ['Coûts de personnel (comptes 62) : total, évolution, ventilation XC / CARS / Shared Services.',
    'Les clés de répartition (XC 60 %, clés nominatives pour CARS, Shared Services) reprises de l’analyse de septembre, à confirmer.'],
  'staff/xc': ['Part du personnel imputée à XC selon la règle de répartition.', 'La règle de répartition validée.'],
  'staff/cars': ['Part du personnel imputée à chaque BU de CARS (clés nominatives par personne).', 'Les clés nominatives validées et à jour.'],
  'staff/shared': ['Coûts des Shared Services (indépendante, polyvalent, Managing Director).', 'Décider si ces coûts sont affichés et comment ils sont répartis.'],
  'expenses/general': ['Frais généraux (loyer, IT, assurances, divers, véhicules) : total et évolution.',
    'Liste des comptes à inclure et à exclure (honoraires, personnel, véhicules de service).'],
  'expenses/rules': ['Tableau des clés de répartition des frais généraux.', 'Où stocker ces clés et qui peut les modifier.'],
  'vehicles/usage': ['Imputation indicative des frais de chaque véhicule aux BU et aux frais généraux, d’après les agendas Google des ressources.',
    'Les pourcentages retenus, saisis par un administrateur.'],
};

let token = sessionStorage.getItem('idt'), tab = 'total', tabS = 'total', cfg;
const route = () => (location.hash.replace(/^#\/?/, '') || 'home/welcome').replace(/^xc\/webshop$/, 'xc/webshop_xc').replace(/^xcvscars(\/.*)?$/, 'overview/xcvscars').replace(/^others\/marketing$/, 'marketing/site').replace(/^expenses\/(xc|cars)$/, 'expenses/rules');   // ancienne adresse
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
const getData = (p, force) => getRange(...periodRange(p), force);
async function getRange(f, t, force) {
  const key = f + '|' + t, hit = cache.get(key);
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
const latestData = () => [...cache.values()].map(h => h.data).sort((x, y) => (y.generated_at > x.generated_at) - (y.generated_at < x.generated_at))[0] || null;
function renderFooter() {
  const d = latestData(); if (!d) return;
  const f = $('foot'); f.textContent = `Source : ${d.source}${d.source === 'demo' ? ' (DONNÉES FICTIVES)' : ''} — mis à jour ${new Date(d.generated_at).toLocaleString(LOCALE())}`;
  if (cfg && cfg.auth) { const a = document.createElement('a'); a.href = '#'; a.id = 'logout'; a.textContent = 'Se déconnecter'; f.append(' — ', a); }
}
document.addEventListener('click', async e => {
  if (e.target.id !== 'logout') return; e.preventDefault();
  try { await fetch('/api/session', {method: 'DELETE'}); } catch {}
  sessionStorage.removeItem('idt'); token = null; location.reload();
});

// ---- Composants (tous reçoivent les données `d` de LA période du bloc) -----------------------
const kpi = (l, v, c='', sub='', ls='') => `<div class="card"><div class="v ${c}">${v}</div><div class="l">${esc(l)}${ls ? ` <small class="na">${ls}</small>` : ''}</div>${sub ? `<div class="l">${sub}</div>` : ''}</div>`;
// Variation par rapport à la même période un an plus tôt (cur, prev : montants ; label : année comparée)
const vsPrev = (cur, prev, yr) => prev > 0 ? `<span class="${cur >= prev ? 'pos' : 'neg'}">${cur >= prev ? '▲ +' : '▼ '}${decFmt(((cur / prev - 1) * 100).toFixed(1))} %</span> vs ${yr}` : `<span class="na">vs ${yr} : n/d</span>`;
const margin = o => o.ca ? pct(o.margin / o.ca) : '–';
const grp = (d, k) => d.pnl.groups.find(g => g.key === k) || {ca: 0, direct_costs: 0, margin: 0};
const busOf = d => d.pnl.bus.filter(b => b.ca || b.direct_costs);
const CARS_KEYS = ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'];
// BU avec CARS en entité propre (total du groupe) suivie de ses sous-BU en retrait ; les autres BU (XC, non affecté) restent au niveau principal
function busTree(d) {
  const bs = busOf(d), cars = grp(d, 'CARS'), out = [];
  const keep = b => b.key === 'CARS_OTHERS' ? ['all', 'cars'].includes(buSel) : buMatchesFilter(buOfKey(b.key), buSel);
  bs.filter(b => !CARS_KEYS.includes(b.key)).forEach(b => { if (b.key !== 'OTHER' && b.key !== 'NON_AFFECTE' && !/non affect/i.test(b.label)) out.push(b); });
  const cb = bs.filter(b => CARS_KEYS.includes(b.key));
  if (cb.length) { out.push({...cars, key: 'CARS', label: 'CARS', group: true}); cb.forEach(b => out.push({...b, indent: true})); }
  bs.filter(b => !CARS_KEYS.includes(b.key) && !out.includes(b)).forEach(b => out.push(b));
  return buSel === 'all' ? out : out.filter(keep);
}

function bars(items, key, opts = {}) {
  const max = Math.max(...items.map(b => Math.abs(b[key])), 1);
  return `<div class="card">` + items.map(b => `<div class="row${b.group ? ' grp-row' : ''}"><span${b.indent ? ' style="padding-left:1.1em" class="na"' : b.group ? ' style="font-weight:600"' : ''}>${b.indent ? '↳ ' : ''}${esc(b.label)}</span>
    <div class="bars"><div class="bar solo ${key === 'ca' ? 'ca' : 'm' + (b[key] < 0 ? ' n' : '')}" style="width:${Math.abs(b[key]) / max * 100}%"></div></div>
    <span class="num ${key === 'margin' ? cls(b[key]) : ''}">${eur(b[key])}${opts.sub ? `<br><small class="na">${opts.sub(b)}</small>` : ''}</span></div>`).join('') + `</div>`;
}
const table = (head, rows, cl = '') => `<div class="table-wrap"><table class="${cl}"><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const lineRow = (label, o) => `<tr><td>${esc(label)}</td><td>${eur(o.ca)}</td><td>${eur(o.direct_costs)}</td>
  <td class="${cls(o.margin)}">${eur(o.margin)}</td><td class="${cls(o.margin)}">${margin(o)}</td></tr>`;
const HEAD = ['', 'CA', 'Coûts directs', 'Marge brute', 'Marge %'];
const NOTE = t => ({static: `<div class="note">${t}</div>`});

// Événements (axe analytique « MEETING ») : une ligne par événement dont le groupe BU figure dans `groups`.
let evSort = {k: 'ca', dir: -1};                                   // tri des tableaux d'événements (défaut : CA décroissant)
const evVal = (e, k) => k === 'margin' ? (e.ca ? e.result / e.ca : -Infinity) : k === 'client' ? (e.client || '') : k === 'bu' ? (e.bus || []).map(b => b.bu).join(' ') : e[k];
// Véhicules : pas de colonne « Investis » ; le détail (investi, amorti, durée) est dans l'infobulle du résultat cash.
function resultCell(e) {
  if (!e.capex) return eur(e.result);
  const dur = e.amort_months ? ` sur ≈ ${e.amort_months} mois (≈ ${eur(e.amort_monthly)} / mois)` : '';
  const tip = `Résultat cash après ${eur(e.capex)} investis (immobilisés puis amortis${dur}). Déjà amorti sur la période : ${eur(e.amort || 0)} (non compté). Résultat comptable : ${eur(e.result_accounting)}.`;
  return `<span title="${esc(tip)}">${eur(e.result)} <small class="na">ⓘ</small></span>`;
}
function capexCell(e) {
  if (!e.capex) return eur(0);
  const dur = e.amort_months ? ` sur ≈ ${e.amort_months} mois (≈ ${eur(e.amort_monthly)} / mois)` : '';
  const tip = `${eur(e.capex)} investis, comptabilisés en immobilisations et amortis${dur}. Déjà amorti sur la période : ${eur(e.amort || 0)} (non compté dans le résultat cash). Résultat comptable : ${eur(e.result_accounting)}.`;
  return `<span title="${esc(tip)}">${eur(e.capex)} <small class="na">ⓘ</small></span>`;
}
// Libellé d'un événement / véhicule : lien vers son compte analytique dans Odoo (nouvel onglet) quand l'adresse d'Odoo est connue.
const nameLink = e => (cfg && cfg.analytic_link && e.id)
  ? `<a class="olink" href="${esc(cfg.analytic_link.replace('{id}', encodeURIComponent(e.id)))}" target="_blank" rel="noopener noreferrer" title="Ouvrir dans Odoo">${esc(e.name)}</a>` : esc(e.name);
function eventsTable(d, groups, showBu = false, veh = false) {
  const ev = veh ? d.vehicles : d.events, U = veh ? 'véhicule' : 'événement';
  if (!ev || ev.unavailable) return `<p class="na">${esc(ev ? ev.unavailable : 'Indisponible pour le moment.')}</p>`;
  const list = (veh ? ev.vehicles : ev.events).filter(e => groups.includes(e.group));
  const note = `<small class="na">${veh ? 'Véhicules' : 'Événements'} : axe ${esc((ev.plans || []).join(', '))}. Rattachement : axe ${esc(ev.bu_axis || 'BU')}.</small>`
    + (ev.bu_missing ? `<br><small class="neg">${ev.bu_missing} regroupement(s) de lignes analytiques sans compte sur l’axe ${esc(ev.bu_axis || 'BU')} : à corriger dans Odoo (l’axe est censé être obligatoire).</small>`
      + (ev.bu_missing_detail || []).map(m => `<br><small class="neg">→ ${esc(m.item)} · compte ${esc(m.account)} · ${eur(m.amount)} (${m.lines} ligne${m.lines > 1 ? 's' : ''})</small>`).join('') : '')
    + (ev.bu_unmapped && ev.bu_unmapped.length ? `<br><small class="neg">Comptes de l’axe BU non reconnus : ${esc(ev.bu_unmapped.join(', '))}.</small>` : '');
  if (!list.length) return `<p class="na">Aucun ${U} sur la période.</p>` + note;
  const sum = k => list.reduce((s, e) => s + e[k], 0);
  const buText = e => (e.bus || []).filter(b => b.share >= .005).map((b, i, all) => all.length > 1 ? `${b.bu} ${Math.round(b.share * 100)} %` : b.bu).join(' · ');
  const refText = e => { const r = e.reference || ''; return r.includes('/') ? r.split('/').slice(1).join('/').trim() : /^(modern rally|historic rally|historic racing)$/i.test(r.trim()) ? '' : r; };   // la BU a sa colonne
  const row = (e, cl = '') => `<tr class="${cl}"><td>${nameLink(e)}${veh && refText(e) ? ` <small class="na">${esc(refText(e))}</small>` : ''}${e.mixed ? ' <small class="na" title="Une part notable de cet événement relève d’un autre groupe (XC / CARS / Others)">(mixte)</small>' : ''}</td>
    ${veh ? `<td class="client">${esc(e.client || '')}</td>` : ''}${showBu ? `<td class="bu">${esc(buText(e))}</td>` : ''}<td>${eur(e.ca)}</td><td>${eur(e.direct_costs)}</td><td>${eur(e.other_costs)}</td>${veh ? '' : `<td>${capexCell(e)}</td>`}
    <td class="${cls(e.result)}">${veh ? resultCell(e) : eur(e.result)}</td><td class="${cls(e.result)}">${e.ca ? pct(e.result / e.ca) : '–'}</td></tr>`;
  const total = {name: `Total (${list.length} ${U}${list.length > 1 ? 's' : ''})`, ca: sum('ca'), direct_costs: sum('direct_costs'), other_costs: sum('other_costs'), capex: sum('capex'), amort: sum('amort'), result: sum('result')};
  const cols = [['name', veh ? 'Véhicule' : 'Événement']].concat(veh ? [['client', 'Client']] : [], showBu ? [['bu', 'BU']] : [], [['ca', 'CA'], ['direct_costs', 'Coûts directs'], ['other_costs', 'Autres charges']].concat(veh ? [] : [['capex', 'Investis*']], [['result', 'Résultat cash'], ['margin', 'Marge %']]));
  const sorted = list.slice().sort((a, b) => {
    const x = evVal(a, evSort.k), y = evVal(b, evSort.k);
    return (typeof x === 'string' ? x.localeCompare(y, 'fr') : x - y) * evSort.dir || a.name.localeCompare(b.name, 'fr');
  });
  const th = ([k, l]) => `<th class="sortable${evSort.k === k ? ' sorted' : ''}" data-sort="${k}" role="button" tabindex="0" aria-sort="${evSort.k === k ? (evSort.dir > 0 ? 'ascending' : 'descending') : 'none'}">${esc(l)}<span class="arrow">${evSort.k === k ? (evSort.dir > 0 ? ' ▲' : ' ▼') : ''}</span></th>`;
  return `<div class="table-wrap"><table class="prodtable"><thead><tr>${cols.map(th).join('')}</tr></thead><tbody>${sorted.map(e => row(e)).concat([row(total, 'tot')]).join('')}</tbody></table></div>` + note;
}
const CARS_MARGIN_WARN = {static: '<div class="note warn"><b>⚠ Marge brute, pas une marge nette.</b> Le résultat et la marge de cette vue sont une marge brute (produits − coûts directs − autres charges), <b>hors</b> coûts de personnel interne, <b>hors</b> coûts liés aux véhicules de service, <b>hors</b> contribution aux frais généraux (dont assurances, marketing, etc.) et <b>hors</b> amortissements (infrastructures, outillage, véhicules de service, etc.). La marge nette par BU se trouve dans Vue d’ensemble › Marge nette.</div>'};
const EVENT_NOTE = NOTE('Résultat cash = produits (comptes 7xx) − coûts directs (602, 603, 604) − autres charges (autres comptes 6xx hors dotations aux amortissements : déplacements, hôtels, carburant, véhicules…) − investissements. *Investis = dépenses de l’événement immobilisées (comptes INVEST 24x) puis amorties sur plusieurs mois ; la dotation d’amortissement (630) n’est pas comptée, pour éviter le double comptage. Survolez le ⓘ pour le montant investi, la durée d’amortissement et le résultat comptable. Montants d’après la ventilation analytique des factures sur l’axe MEETING. Un événement est rattaché d’après l’axe analytique BU renseigné sur ses lignes : XC, CARS (Modern Rally, Historic Rally, Historic Racing — la colonne BU donne la répartition si plusieurs) ou Others ; « mixte » signale un événement dont un autre groupe pèse au moins 10 % ; les comptes « OLD » de l’axe sont ignorés. Les montants non ventilés analytiquement n’apparaissent pas ici.');

const CLIENT_TABS = {total:'Total', XC:'XC', CARS:'CARS', MODERN_RALLY:'Modern Rally', HISTORIC_RALLY:'Historic Rally', HISTORIC_RACING:'Historic Racing', CARS_OTHERS:'CARS Others'};
const SUPPLIER_TABS = {total:'Général', XC:'XC', CARS:'CARS', MODERN_RALLY:'Modern Rally', HISTORIC_RALLY:'Historic Rally', HISTORIC_RACING:'Historic Racing', CARS_OTHERS:'CARS Others', HORS_BU:'Hors BU'};
const ALL_SUPPLIERS = Object.keys(SUPPLIER_TABS);

// Classement clients (kind 'c') ou fournisseurs (kind 's') : mêmes colonnes, mêmes totaux.
function ranking(d, kind, allowed, opts = {}) {
  const sup = kind === 's', tc = sup ? d.top_suppliers : d.top_clients, labels = sup ? SUPPLIER_TABS : CLIENT_TABS;
  if (!tc || tc.unavailable) return `<p class="na">${esc(tc ? tc.unavailable : 'Indisponible pour le moment.')}</p>`;
  const sel = opts.force || (sup ? tabS : tab), cur = allowed.includes(sel) ? sel : allowed[0];
  const scope = sup ? ((tc._totals || {})[cur] || 0)                                   // achats HT du périmètre
    : cur === 'total' ? d.pnl.total.ca : cur === 'CARS' ? grp(d, 'CARS').ca : (d.pnl.bus.find(b => b.key === cur) || {ca: 0}).ca;   // CA du périmètre
  const share = v => scope > 0 ? pct(v / scope) : '–';
  const list = tc[cur] || [], shown = list.reduce((s, c) => s + c.ca, 0), other = scope - shown;
  const hasOpen = !!(tc._meta && tc._meta.open), sumOpen = list.reduce((s, c) => s + (c.open || 0), 0);
  const scopeOpen = hasOpen ? ((tc._open_totals || {})[cur] || 0) : 0;
  const hasInv = list.some(c => c.invoices != null), st = (tc._stats || {})[cur] || null;
  const topInv = list.reduce((s, c) => s + (c.invoices || 0), 0), topAmt = list.reduce((s, c) => s + (c.invoices || 0) * (c.avg || 0), 0);
  const hasMix = sup && list.some(c => c.mix), MIXN = {'604': 'Achats de marchandises', '603': 'Sous-traitance', '602': 'Frais', autres: 'Autres charges'};
  const mx = m => { if (!hasMix) return ''; if (!m) return '<td></td>';
    const keys = ['604', '603', '602', 'autres'], pos = keys.reduce((t, k) => t + Math.max(0, m[k] || 0), 0); if (!pos) return '<td>–</td>';
    const tip = keys.filter(k => m[k]).map(k => `${MIXN[k]} : ${eur(m[k])} (${pct(Math.max(0, m[k]) / pos)})`).join(' · ');
    return `<td class="mixcell" title="${esc(tip)}"><span class="mixbar">${keys.map(k => `<i class="m${k}" style="width:${Math.max(0, m[k] || 0) / pos * 100}%"></i>`).join('')}</span></td>`; };
  const inv = (n, avg) => hasInv ? `<td>${n == null ? '–' : num(n)}</td><td>${avg != null && n ? eur(avg) : '–'}</td>` : '';
  const op = v => hasOpen ? `<td class="open">${v ? eur(v) : '–'}</td>` : '';
  const T = sup ? {one: 'fournisseurs', other: 'Autres fournisseurs', scope: 'Total des achats du périmètre', head: ['#', 'Fournisseur', 'Achats HT', '% des achats'], open: 'Reste à payer'}
                : {one: 'clients', other: 'Autres clients et ventes sans client identifié', scope: 'Total du périmètre', head: ['#', 'Client', 'CA', '% du CA'], open: 'Solde ouvert'};
  const rows = list.map((c, i) => `<tr><td>${i + 1}</td><td>${esc(c.name)}</td><td>${eur(c.ca)}</td><td>${share(c.ca)}</td>${inv(c.invoices, c.avg)}${mx(c.mix)}${op(c.open || 0)}</tr>`);
  if (list.length) rows.push(`<tr class="tot"><td></td><td>Total des ${list.length} premiers ${T.one}</td><td>${eur(shown)}</td><td>${share(shown)}</td>${inv(topInv, topInv ? topAmt / topInv : null)}${mx(null)}${op(sumOpen)}</tr>`,
    `<tr><td></td><td>${T.other}</td><td>${eur(other)}</td><td>${share(other)}</td>${inv(st ? Math.max(0, st.invoices - topInv) : null, null)}${mx(null)}${op(scopeOpen - sumOpen)}</tr>`,
    `<tr class="tot"><td></td><td>${T.scope}</td><td>${eur(scope)}</td><td>100,0 %</td>${inv(st ? st.invoices : null, st ? st.avg : null)}${mx((tc._mix || {})[cur])}${op(scopeOpen)}</tr>`);
  const m = tc._meta, tag = sup ? 'regroup_fournisseur=' : 'regroup_client=';
  const info = !m ? '' : m.grouping
    ? `<small class="na">Regroupements d’après les étiquettes Odoo « ${tag} » : ${m.groups} appliqué${m.groups > 1 ? 's' : ''}. `
      + (sup ? 'Achats HT = lignes de factures fournisseurs (avoirs déduits), rattachées à une BU d’après le compte comptable de chaque ligne (602, 603, 604) ; « Hors BU » = frais généraux, véhicules, honoraires… <i>Reste à payer</i> = reste dû TTC des factures de la période non soldées.'
             : 'Le « % » est la part du CA du périmètre sélectionné (comptes 700). <i>Solde ouvert</i> = reste dû TTC des factures de la période non soldées, avoirs déduits.') + '</small>'
    : `<small class="neg">Regroupement indisponible : les noms sont affichés tels que saisis dans Odoo.</small>`;
  const infoInv = hasInv ? `<br><small class="na">${sup ? 'Achat moyen' : 'Panier moyen'} = montant HT moyen des ${sup ? 'factures fournisseurs' : 'factures clients'} de la période (les avoirs ne comptent pas comme factures) ; une facture répartie sur plusieurs BU n’est comptée qu’une fois dans le total.</small>` : '';
  // Rapprochement avec les coûts directs du P&L (fournisseurs, périmètres BU / XC / CARS) : explique l'écart par les écritures hors factures
  let infoRecon = '';
  const pnlScope = !sup || d._adj ? null : cur === 'XC' || cur === 'CARS' ? grp(d, cur).direct_costs : (d.pnl.bus.find(b => b.key === cur) || {}).direct_costs;
  if (pnlScope != null && Math.abs(pnlScope - scope) >= 1) {
    const rc = (tc._recon || {})[cur] || {amount: 0, journals: []}, gap = pnlScope - scope;
    infoRecon = `<div class="note"><b>Écart avec les coûts directs du P&amp;L</b> : ${eur(pnlScope)} (coûts directs) − ${eur(scope)} (achats de ce tableau) = <b>${eur(gap)}</b>.<br>`
      + `Cet écart vient d’écritures sur les comptes 602, 603 et 604 qui ne sont pas des lignes de factures fournisseurs rattachées à un tiers : écritures diverses, provisions ou factures à recevoir, notes de frais, paiements directs, lignes sans fournisseur.`
      + (rc.amount ? ` Identifié : ${eur(rc.amount)}${rc.journals.length ? ' — ' + rc.journals.map(j => `${esc(j.name)} (${eur(j.amount)})`).join(', ') : ''}.` : '')
      + `</div>`;
  }
  const infoOpen = m && !m.open ? `<br><small class="neg">${T.open} indisponible pour le moment.</small>` : '';
  const legend = hasMix ? `<div class="legend mixlegend">${['604', '603', '602', 'autres'].map(k => `<span><i class="sw m${k}"></i>${MIXN[k]}${k === 'autres' ? '' : ' (' + k + ')'}</span>`).join('')}</div>` : '';
  return `${opts.hideTabs ? '' : `<div class="tabs">${allowed.map(k => `<button data-tab="${k}" data-kind="${kind}" class="${k === cur ? 'on' : ''}">${labels[k]}</button>`).join('')}</div>`}
    ${list.length ? legend + table(T.head.concat(hasInv ? ['Factures', sup ? 'Achat moyen' : 'Panier moyen'] : [], hasMix ? ['Répartition'] : [], hasOpen ? [T.open] : []), rows, 'prodtable') : '<p class="na">Aucune ligne sur la période.</p>'}${info}${infoInv}${infoOpen}${infoRecon}`;
}
const clients = (d, allowed, opts) => ranking(d, 'c', allowed, opts);
const suppliers = (d, allowed, opts) => ranking(d, 's', allowed, opts);

// Un bloc = un tableau/graphique avec son sélecteur de période. `fixed` = chiffre à date (pas de période).
const B = (id, title, render, fixed = false) => ({id, title, render, fixed});
const BU_TAB = {all: 'total', xc: 'XC', cars: 'CARS', mr: 'MODERN_RALLY', hrc: 'HISTORIC_RACING', hrl: 'HISTORIC_RALLY'};          // onglets des classements clients / fournisseurs
const buSyncTabs = () => { tab = tabS = BU_TAB[buSel] || 'total'; };
// Page « XC vs CARS » : quand une BU CARS précise est choisie, on compare XC à cette BU (sinon XC à l'ensemble CARS)
const xvcSide = d => buIsCars(buSel) && buSel !== 'cars' ? buScope(d) : {...grp(d, 'CARS'), label: 'CARS'};
const BU_OPEN_KEY = {xc: 'XC', cars: 'CARS', mr: 'MODERN_RALLY', hrc: 'HISTORIC_RACING', hrl: 'HISTORIC_RALLY'};
const FINANCE = B('finance', 'Position financière (à date)', d => {
  if (buSel !== 'all') {              // par BU : la trésorerie (comptes bancaires) n'est pas ventilable ; créances et dettes = encours des factures de l'année, répartis par BU
    const yd = cached('ytd') || d, sc = BU_OPEN_KEY[buSel], c = yd.top_clients, f = yd.top_suppliers;
    const ok = t => t && !t.unavailable && t._meta && t._meta.open, rec = ok(c) ? (c._open_totals || {})[sc] || 0 : null, pay = ok(f) ? (f._open_totals || {})[sc] || 0 : null;
    if (rec == null && pay == null) return `<p class="na">Créances et dettes par BU indisponibles pour le moment.</p>`;
    return `<div class="kpis">${rec == null ? '' : kpi('Créances clients · ' + BU_PNL_LABEL[buSel], eur(rec), '', 'à encaisser (TTC)')}${pay == null ? '' : kpi('Dettes fournisseurs · ' + BU_PNL_LABEL[buSel], eur(pay), '', 'à payer (TTC)')}`
      + `${rec != null && pay != null ? kpi('Encours net', eur(rec - pay), cls(rec - pay), 'clients − fournisseurs') : ''}</div>`
      + `<small class="na">Filtre BU actif : ${esc(BU_PNL_LABEL[buSel])}. Encours = reste dû TTC des factures de l’année en cours non encore soldées (avoirs déduits), réparti entre BU au prorata des lignes de facture. La trésorerie est celle de la société et ne se ventile pas par BU : elle n’est affichée que pour « Toutes ».</small>`; }
  const yd = cached('ytd') || d, oc = yd.top_clients, of = yd.top_suppliers, okO = t => t && !t.unavailable && t._meta && t._meta.open;
  const bank = d.balance_sheet, split = okO(oc) && okO(of) ? [['XC', 'XC Cross'], ['MODERN_RALLY', 'Modern Rally'], ['HISTORIC_RACING', 'Historic Racing'], ['HISTORIC_RALLY', 'Historic Rally'], ['CARS_OTHERS', 'CARS Others']].map(([k, l]) => [l, (oc._open_totals || {})[k] || 0, (of._open_totals || {})[k] || 0]).filter(r => r[1] || r[2]) : null;
  let bu = '';
  if (split) { const sr = split.reduce((t, r) => t + r[1], 0), sp = split.reduce((t, r) => t + r[2], 0), gr = bank.receivables - sr, gp = bank.payables - sp;
    bu = '<h4 class="sub">Créances et dettes par BU</h4>' + table(['', 'Créances clients', 'Dettes fournisseurs', 'Encours net'], split.map(r => `<tr><td>${esc(r[0])}</td><td>${eur(r[1])}</td><td>${eur(r[2])}</td><td class="${cls(r[1] - r[2])}">${eur(r[1] - r[2])}</td></tr>`)
      .concat([`<tr><td>Non ventilé par BU</td><td>${eur(gr)}</td><td>${eur(gp)}</td><td class="${cls(gr - gp)}">${eur(gr - gp)}</td></tr>`, `<tr class="tot"><td>Total (société)</td><td>${eur(bank.receivables)}</td><td>${eur(bank.payables)}</td><td class="${cls(bank.receivables - bank.payables)}">${eur(bank.receivables - bank.payables)}</td></tr>`]), 'prodtable')
      + '<small class="na">Les lignes par BU sont celles qu’affiche le filtre BU. « Non ventilé » = écart entre le total de la société et la somme des BU : factures dont aucune ligne n’est rattachée à une BU (frais généraux, immobilisations…) ou sans tiers. Les BU et cet écart totalisent exactement les chiffres du haut.</small>'; }
  return `<div class="kpis">${kpi('Trésorerie', eur(d.balance_sheet.cash), cls(d.balance_sheet.cash))
  + kpi('Créances clients', eur(d.balance_sheet.receivables)) + kpi('Dettes fournisseurs', eur(d.balance_sheet.payables))}</div>
  <small class="na">Créances et dettes : montant restant dû des factures validées, non payées ou partiellement payées, dont la date comptable est en ${esc(d.balance_sheet.year)} (critères de « Vendor bills to pay » dans Odoo ; avoirs déduits ; brouillons exclus). Les factures ouvertes d’années antérieures ne sont pas comptées. Trésorerie : solde à date.</small>` + bu; }, true);

const ALL_CLIENTS = ['total','XC','CARS','MODERN_RALLY','HISTORIC_RALLY','HISTORIC_RACING','CARS_OTHERS'];
const GROUP_LABEL = {XC: 'XC Cross Car', CARS: 'CARS', OTHER: 'Non affecté'};

// ---- Pages = listes de blocs --------------------------------------------------------------------
// Encours d'un périmètre (XC, CARS) : reste dû TTC des factures de la période non soldées, clients et fournisseurs (mêmes chiffres que les colonnes « Solde ouvert » / « Reste à payer »).
function encoursCards(d, scope) {
  const ok = t => t && !t.unavailable && t._meta && t._meta.open, c = d.top_clients, f = d.top_suppliers;
  const rec = ok(c) ? (c._open_totals || {})[scope] || 0 : null, pay = ok(f) ? (f._open_totals || {})[scope] || 0 : null;
  if (rec == null && pay == null) return '';
  return `<div class="kpis">${rec == null ? '' : kpi('Encours clients', eur(rec), '', 'à encaisser (TTC)')}${pay == null ? '' : kpi('Encours fournisseurs', eur(pay), '', 'à payer (TTC)')}`
    + `${rec != null && pay != null ? kpi('Encours net', eur(rec - pay), cls(rec - pay), 'clients − fournisseurs') : ''}</div>`
    + '<small class="na">Encours = reste dû TTC des factures de la période non encore soldées (avoirs déduits), réparti entre BU au prorata des lignes de facture.</small>';
}

// Décomposition d'un périmètre : CA d'un côté ; de l'autre achats de marchandises (604), sous-traitance (603) et frais (602) ; une colonne par entité.
function decompTable(d, cols) {
  cols = cols.filter(c => c.o && (c.o.ca || c.o.direct_costs || Object.values(c.o.costs || {}).some(Boolean)));
  if (!cols.length) return '<p class="na">Aucune donnée sur la période.</p>';
  const cell = (v, ca, extra = '') => `<td${extra}>${eur(v)}${ca > 0 ? `<br><small class="na">${pct(v / ca)} du CA</small>` : ''}</td>`;
  const sum = o => ['604', '603', '602'].reduce((t, k) => t + ((o.costs || {})[k] || 0), 0);
  const row = (label, fn, cl = '', pctOn = true) => `<tr class="${cl}"><td class="prod">${label}</td>${cols.map(c => { const v = fn(c.o); return pctOn ? cell(v, c.o.ca, v < 0 && cl === 'tot' ? ' class="neg"' : '') : `<td>${eur(v)}</td>`; }).join('')}</tr>`;
  const adj = cols.some(c => Math.abs(sum(c.o) - c.o.direct_costs) >= 1);
  return table([''].concat(cols.map(c => c.label)), [
    row('<b>Chiffre d’affaires</b> (comptes 700)', o => o.ca, 'tot', false),
    row('Achats de marchandises (604)', o => (o.costs || {})['604'] || 0),
    row('Sous-traitance (603)', o => (o.costs || {})['603'] || 0),
    row('Frais (602)', o => (o.costs || {})['602'] || 0),
    row('<b>Total des coûts directs</b>', o => sum(o), 'tot'),
    adj ? row('Ajustements de MB', o => sum(o) - o.direct_costs, '') : '',
    `<tr class="tot"><td class="prod">Marge brute</td>${cols.map(c => `<td class="${cls(c.o.margin)}">${eur(c.o.margin)}<br><small>${c.o.ca ? pct(c.o.margin / c.o.ca) : '–'}</small></td>`).join('')}</tr>`,
  ].filter(Boolean), 'prodtable decomp') + '<small class="na">Les pourcentages sont rapportés au CA de chaque colonne. Coûts directs = achats de marchandises (604), sous-traitance (603) et frais (602) rattachés à la BU ; le personnel et les véhicules (615) sont exclus.</small>';
}

// Courbe d'évolution (une seule série, SVG adaptatif) : points = [{label, avg (ou null), orders}], ref = valeur de référence en pointillé.
// Retire le mois en cours (incomplet) d'une série mensuelle : sinon la courbe semble descendre alors que les données ne sont pas complètes.
const MOIS_COURTS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.'];
function closedMonths(points, granularity) {
  if (granularity === 'week' && points && points.length >= 3 && new Date().getDay() !== 0) {          // la semaine en cours (lundi → dimanche) n'est pas terminée : points incomplets écartés
    const out = points.slice(0, -1); out.trimmed = 'semaine du ' + points[points.length - 1].label; out.trimmedKind = 'semaine'; return out;
  }
  if (granularity !== 'month' || !points || points.length < 3) return points;
  const t = new Date(), last = points[points.length - 1], m = /^(\S+)\s+(\d{4})$/.exec(last.label || '');
  if (!m || +m[2] !== t.getFullYear() || MOIS_COURTS.indexOf(m[1]) !== t.getMonth()) return points;
  if (t.getDate() === new Date(t.getFullYear(), t.getMonth() + 1, 0).getDate()) return points;       // dernier jour du mois : le mois est complet
  const out = points.slice(0, -1); out.trimmed = last.label; return out;
}
function lineChart(points, ref, unit, fmt = v => eur(Math.round(v)), tip = p => `${p.label} : ${eur(p.avg)} (${p.orders} commande${p.orders > 1 ? 's' : ''})`, refLabel = 'moyenne') {
  const pts = points.map((p, i) => ({...p, i})), vals = pts.filter(p => p.avg != null);
  if (vals.length < 2) return '<p class="na">Pas assez de commandes sur la période pour tracer une évolution.</p>';
  const W = 640, H = 240, L = 52, R = 14, T = 14, B = 34;
  const lo0 = Math.min(...vals.map(p => p.avg), ref || Infinity), hi0 = Math.max(...vals.map(p => p.avg), ref || 0);
  const span = (hi0 - lo0) || hi0 || 1, lo = Math.max(0, lo0 - span * .15), hi = hi0 + span * .15;
  const x = i => L + (W - L - R) * (pts.length > 1 ? i / (pts.length - 1) : .5), y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const ticks = [0, 1, 2, 3].map(k => lo + (hi - lo) * k / 3);
  const every = Math.ceil(pts.length / 8), path = pts.filter(p => p.avg != null).map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.avg).toFixed(1)}`).join('');
  return `<div class="linechart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Évolution">
    ${ticks.map(t => `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text class="ax" x="${L - 6}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`).join('')}
    ${ref ? `<line class="ref" x1="${L}" x2="${W - R}" y1="${y(ref)}" y2="${y(ref)}"/><text class="ax" x="${L + 6}" y="${y(ref) - 5}" text-anchor="start">${refLabel} ${fmt(ref)}</text>` : ''}
    <path class="ln" d="${path}"/>
    ${pts.map(p => p.avg == null ? '' : `<circle class="dot" cx="${x(p.i).toFixed(1)}" cy="${y(p.avg).toFixed(1)}" r="4"><title>${esc(tip(p))}</title></circle>
      <circle class="hit" cx="${x(p.i).toFixed(1)}" cy="${y(p.avg).toFixed(1)}" r="12"><title>${esc(tip(p))}</title></circle>`).join('')}
    ${pts.map(p => p.i % every === 0 ? `<text class="ax" x="${x(p.i).toFixed(1)}" y="${H - 12}" text-anchor="middle">${esc(p.label)}</text>` : '').join('')}
  </svg><small class="na">${unit}${points.trimmed ? ' · ' + esc(points.trimmed) + ' (' + (points.trimmedKind || 'mois') + ' en cours, incomplet' + (points.trimmedKind === 'semaine' ? 'e' : '') + ') non tracé' + (points.trimmedKind === 'semaine' ? 'e' : '') : ''}</small></div>`;
}

// Répartition par mode (paiement, livraison) : tableau avec part en % et barre.
function modeTable(rows, head, countLabel, note, err) {
  if (!rows) return `<p class="na">Indisponible pour le moment.</p>${err ? `<small class="neg">Motif renvoyé par Odoo : ${esc(err)}</small>` : ''}`;
  if (!rows.length) return '<p class="na">Aucune donnée sur la période.</p>';
  const tot = rows.reduce((a, r) => a + r.count, 0), amt = rows.reduce((a, r) => a + r.amount, 0);
  return table([head, countLabel, '%', 'Montant HT'], rows.map(r => `<tr><td>${esc(r.name)}</td><td>${num(r.count)}</td>
    <td class="sharecell"><span class="sharebar" style="width:${Math.round(r.share * 100)}%"></span><span>${pct(r.share)}</span></td><td>${eur(r.amount)}</td></tr>`)
    .concat([`<tr class="tot"><td>Total</td><td>${num(tot)}</td><td>100,0 %</td><td>${eur(amt)}</td></tr>`]), 'prodtable') + `<small class="na">${note}</small>`;
}
// Courbes multiples sur UN SEUL axe (points = [{label, ...valeurs}], series = [{key, label, cls}]) ; légende + infobulle par point.
function multiLineChart(points, series, tip, note, H = 250) {
  if (!points.some(p => series.some(s => p[s.key] > 0))) return '<p class="na">Aucune donnée sur la période.</p>';
  const W = 640, L = 46, R = 14, T = 14, B = 34, hi = Math.max(...points.flatMap(p => series.map(s => p[s.key] || 0))) * 1.12 || 1;
  const x = i => L + (W - L - R) * (points.length > 1 ? i / (points.length - 1) : .5), y = v => T + (H - T - B) * (1 - v / hi);
  const ticks = [0, 1, 2, 3].map(k => hi * k / 3), every = Math.ceil(points.length / 8);
  const path = s => points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[s.key] || 0).toFixed(1)}`).join('');
  return `<div class="linechart"><div class="legend">${series.map(s => `<span><i class="sw ${s.cls}"></i>${esc(s.label)}</span>`).join('')}</div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map(s => s.label).join(' et '))}">
    ${ticks.map(t => `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text class="ax" x="${L - 6}" y="${y(t) + 4}" text-anchor="end">${num(Math.round(t))}</text>`).join('')}
    ${series.map(s => `<path class="ln ${s.cls}" d="${path(s)}"/>`).join('')}
    ${points.map((p, i) => series.map(s => `<circle class="dot ${s.cls}" cx="${x(i).toFixed(1)}" cy="${y(p[s.key] || 0).toFixed(1)}" r="4"><title>${esc(tip(p))}</title></circle>`).join('')
      + `<rect class="hit" x="${(x(i) - 10).toFixed(1)}" y="${T}" width="20" height="${H - T - B}"><title>${esc(tip(p))}</title></rect>`).join('')}
    ${points.map((p, i) => i % every === 0 ? `<text class="ax" x="${x(i).toFixed(1)}" y="${H - 12}" text-anchor="middle">${esc(p.label)}</text>` : '').join('')}
  </svg><small class="na">${note}${points.trimmed ? ' ' + esc(points.trimmed) + ' (' + (points.trimmedKind || 'mois') + ' en cours, incomplet' + (points.trimmedKind === 'semaine' ? 'e' : '') + ') non tracé.' : ''}</small></div>`;
}

// Page d'un webshop : « pick » choisit le webshop concerné parmi ceux renvoyés par l'API.
let pickScope = 'web';
function webshopPage(pick, {topPages = true, customers = false, picking = false, gaKey = ''} = {}) {
  const shop = d => (d.webshops.unavailable ? null : d.webshops.find(pick));
  const miss = d => d.webshops.unavailable ? `<p class="na">${esc(d.webshops.unavailable)}</p>` : '<p class="na">Aucune vente sur ce webshop pour la période.</p>';
  return [
    B('shops', 'Ventes du webshop', d => { const w = shop(d); return w ? `<div class="two">${kpi(w.name, eur(w.revenue), '', `${w.orders} commandes · panier moyen ${eur(w.avg_basket)}`)}</div>` : miss(d); }),
    B('basket', 'Évolution du panier moyen', d => {
      const w = shop(d); if (!w) return miss(d);
      const bs = w.basket_series;
      return bs ? lineChart(closedMonths(bs.points, bs.granularity), w.avg_basket, `Panier moyen HT par ${bs.granularity === 'week' ? 'semaine' : 'mois'} (commandes confirmées) ; le pointillé = moyenne de la période. Survolez un point pour le détail.`)
        : '<p class="na">Évolution indisponible pour le moment.</p>';
    }),
    B('picking', 'Commandes préparées par semaine', d => {
      const w = shop(d); if (!w) return miss(d);
      const pk = w.pickings; if (!pk || pk.unavailable) return `<p class="na">Commandes préparées indisponibles pour le moment.</p>${(w.errors || {}).pickings ? `<small class="neg">Motif renvoyé par Odoo : ${esc(w.errors.pickings)}</small>` : ''}`;
      const sc = pk[pickScope] || pk.web, tabs = `<div class="tabs">${[['web', 'Commandes du webshop'], ['all', 'Tous les bons de livraison (hors Goldspeed)']].map(([k, l]) => `<button data-pickscope="${k}" class="${k === pickScope ? 'on' : ''}">${l}</button>`).join('')}</div>`;
      const pts = sc.points || [], lastFull = pts.length > 1 ? pts[pts.length - 2] : null, per = n => sc.weeks ? num(Math.round(n / sc.weeks * 10) / 10) + ' par semaine' : '';
      const tipFn = p => `Semaine du ${p.label} : ${p.orders} commande${p.orders > 1 ? 's' : ''}, ${num(p.units)} produit${p.units > 1 ? 's' : ''}${p.per_order == null ? '' : ' (' + num(p.per_order) + ' par commande)'}`;
      return `<div class="pickwrap">${tabs}<div class="kpis">${kpi('Commandes préparées · ' + sc.weeks + ' semaines', num(sc.orders), '', per(sc.orders) + (lastFull ? ' · dernière semaine complète : ' + num(lastFull.orders) : ''))}${kpi('Produits expédiés · ' + sc.weeks + ' semaines', num(sc.units), '', per(sc.units))}${kpi('Produits par commande', sc.per_order == null ? '–' : num(sc.per_order), '', 'moyenne sur ' + sc.weeks + ' semaines')}</div>`
        + `<div><h4 class="sub">Commandes préparées par semaine</h4>${multiLineChart(pts, [{key: 'orders', label: 'Commandes préparées', cls: 's1'}], tipFn, '', 190)}</div>`
        + `<div><h4 class="sub">Produits expédiés par semaine</h4>${multiLineChart(pts, [{key: 'units', label: 'Produits expédiés', cls: 's2'}], tipFn, `Les ${sc.weeks} dernières semaines. Une commande est comptée comme préparée quand son bon de livraison est validé (date de validation, semaines commençant le lundi, semaine en cours comprise : elle est incomplète). Les livraisons du webshop Goldspeed sont exclues : elles sont faites sur les courses par le Race Team. Produits = quantités expédiées. Survolez une semaine pour le détail : moins de commandes mais plus de produits par commande explique souvent une semaine plus calme.`, 190)}</div></div>`;
    }, true),
    B('products', 'Top 15 des produits vendus', d => {
      const w = shop(d); if (!w) return miss(d);
      const t = w.products_total || {value: 0, units: 0, count: 0};
      return `<h4 class="sub">${esc(w.name)} <small class="na">— ${t.count} références vendues</small></h4>` + table(['#', 'Produit', 'Valeur HT', 'Unités', '% du total'],
        (w.products || []).map((p, i) => `<tr><td>${i + 1}</td><td class="prod">${esc(p.name)}</td><td>${eur(p.value)}</td><td>${num(p.units)}</td><td>${pct(p.share)}</td></tr>`)
        .concat([`<tr class="tot"><td></td><td>Total des produits vendus</td><td>${eur(t.value)}</td><td>${num(t.units)}</td><td>100,0 %</td></tr>`]), 'prodtable');
    }),
    B('customers', 'Top 15 des meilleurs clients', d => {
      const w = shop(d); if (!w) return miss(d);
      const c = w.customers; if (!c) return `<p class="na">Meilleurs clients indisponibles pour le moment.</p>${(w.errors || {}).customers ? `<small class="neg">Motif renvoyé par Odoo : ${esc(w.errors.customers)}</small>` : ''}`;
      if (!c.customers.length) return '<p class="na">Aucune commande sur la période.</p>';
      const top = c.customers, mix = l => (l || []).map((x, i, a) => esc(x.name) + (a.length > 1 || x.count > 1 ? ` <small class="na">×${x.count}</small>` : '')).join('<br>') || '–';
      const rows = top.map((x, i) => `<tr><td>${i + 1}</td><td class="prod">${esc(x.name)}${x.country ? `<br><small class="na">${esc(x.country)}</small>` : ''}</td><td>${eur(x.ca)}</td><td>${pct(x.share)}</td>
        <td>${num(x.orders)}</td><td>${eur(x.avg_basket)}</td><td class="mix">${mix(x.payments)}</td><td class="mix">${mix(x.deliveries)}</td><td>${x.last_order ? fmtDate(x.last_order) : '–'}</td></tr>`);
      const other = c.total_ca - c.top_ca;
      rows.push(`<tr class="tot"><td></td><td>Total des ${top.length} premiers clients</td><td>${eur(c.top_ca)}</td><td>${pct(c.total_ca ? c.top_ca / c.total_ca : 0)}</td><td colspan="5"></td></tr>`,
        `<tr><td></td><td>Autres clients</td><td>${eur(other)}</td><td>${pct(c.total_ca ? other / c.total_ca : 0)}</td><td colspan="5"></td></tr>`,
        `<tr class="tot"><td></td><td>Total du webshop</td><td>${eur(c.total_ca)}</td><td>100,0 %</td><td>${num(c.total_orders)}</td><td>${c.total_orders ? eur(c.total_ca / c.total_orders) : '–'}</td><td colspan="3"></td></tr>`);
      return `<div class="kpis">${kpi('Clients distincts', num(c.count))}${kpi('Clients récurrents', pct(c.count ? c.repeat / c.count : 0), '', `${num(c.repeat)} avec 2 commandes ou plus`)}${kpi('Part du top 15', pct(c.total_ca ? c.top_ca / c.total_ca : 0), '', 'du CA HT du webshop')}</div>`
        + table(['#', 'Client', 'CA HT', '% du CA', 'Cmd', 'Panier moyen', 'Paiement', 'Livraison', 'Dernière cmd'], rows, 'prodtable')
        + '<small class="na">Commandes confirmées, hors taxes ; contacts d’une même société fusionnés (et étiquettes « regroup_client= » appliquées). Paiement et livraison : modes les plus utilisés par le client (×nombre de commandes).</small>';
    }),
    B('payments', 'Méthodes de paiement', d => { const w = shop(d); return w ? modeTable(w.payments, 'Méthode', 'Paiements', 'Transactions des commandes confirmées (réussies, autorisées ou en attente, ex. virement) ; % = part du nombre de paiements.', (w.errors || {}).payments) : miss(d); }),
    B('delivery', 'Modes de livraison', d => { const w = shop(d); return w ? modeTable(w.deliveries, 'Mode', 'Commandes', 'Transporteur choisi sur les commandes confirmées ; « sans livraison » = retrait, services ou produits virtuels.', (w.errors || {}).deliveries) : miss(d); }),
    B('abandon', 'Abandons de panier', d => {
      const w = shop(d); if (!w) return miss(d);
      const a = w.abandoned; if (!a) return `<p class="na">Abandons de panier indisponibles pour le moment.</p>${(w.errors || {}).abandoned ? `<small class="neg">Motif renvoyé par Odoo : ${esc(w.errors.abandoned)}</small>` : ''}`;
      const bs = a.series, per = bs.granularity === 'week' ? 'semaine' : 'mois';
      return (a.incomplete ? `<p class="neg">Historique incomplet avant le ${fmtDate(a.complete_from)} : Odoo ne conserve pas les anciens paniers non confirmés. Le taux d’abandon n’est calculé qu’à partir du ${fmtDate(a.rate_from || a.complete_from)} ; les mois précédents ne sont pas tracés.</p>` : '')
        + `<div class="kpis">${kpi('Paniers abandonnés', num(a.count), '', `dont ${num(a.identified)} avec client identifié (menu Odoo « Abandoned Carts ») et ${num(a.anonymous)} visiteurs non connectés`)}${kpi('Valeur HT non convertie', eur(a.amount))}${kpi('Taux d’abandon', pct(a.rate), a.rate > .7 ? 'neg' : '', a.incomplete ? `depuis le ${fmtDate(a.rate_from || a.complete_from)} (historique partiel)` : 'abandonnés ÷ (abandonnés + commandes)')}</div>`
        + lineChart(closedMonths(bs.points, bs.granularity), a.rate, `Taux d’abandon par ${per} = paniers abandonnés ÷ (paniers abandonnés + commandes confirmées). Un panier abandonné = devis du site web non confirmé, avec au moins un article, après le délai d’abandon d’Odoo (visiteurs non connectés compris). Survolez un point pour le détail.`,
          v => pct(v), p => `${p.label} : ${pct(p.avg)} — ${p.abandoned} abandonné${p.abandoned > 1 ? 's' : ''} dont ${p.identified} identifié${p.identified > 1 ? 's' : ''} (${eur(p.amount)}) pour ${p.orders} commande${p.orders > 1 ? 's' : ''}`, 'moyenne');
    }),
    B('visits', 'Évolution des visites — 50 derniers jours', d => {
      const w = shop(d); if (!w) return miss(d);
      const v = w.visits; if (!v) return `<p class="na">Visites indisponibles pour le moment.</p>${(w.errors || {}).visits ? `<small class="neg">Motif renvoyé par Odoo : ${esc(w.errors.visits)}</small>` : ''}`;
      const conv = v.visitors && !v.incomplete ? (v.orders || 0) / v.visitors : null;       // faux si l'historique de visites est tronqué
      return (v.incomplete ? `<p class="neg">Historique incomplet avant le ${fmtDate(v.complete_from)} : Odoo supprime les visiteurs anonymes inactifs après environ 60 jours, et leurs pages vues avec. Les périodes antérieures ne sont pas tracées, et les totaux ci-dessous sont sous-estimés.</p>` : '')
        + `<div class="kpis">${kpi('Pages vues', num(v.views))}${kpi('Visiteurs uniques', v.visitors == null ? '–' : num(v.visitors))}${kpi('Taux de conversion', conv == null ? '–' : pct(conv), '', v.incomplete ? 'indisponible : historique de visites incomplet' : 'commandes ÷ visiteurs uniques')}</div>`
        + lineChart(closedMonths(v.points, v.granularity), null, `Pages vues par ${v.granularity === 'week' ? 'semaine' : 'mois'}, limitées aux pages « ${esc(v.path)} » suivies par Odoo. Survolez un point pour le détail. Odoo ne suit que certaines pages (produits, pages marquées « suivre ») et exclut une partie des robots : ce sont des ordres de grandeur, à comparer plutôt qu’à lire en valeur absolue.`,
          x => num(Math.round(x)), p => `${p.label} : ${num(p.views)} pages vues${p.visitors == null ? '' : ', ' + num(p.visitors) + ' visiteurs'}`, '');
    }, true),
    B('toppages', 'Pages les plus visitées — 50 derniers jours', d => {
      const w = shop(d); if (!w) return miss(d);
      const t = w.top_pages; if (!t || t.unavailable) return `<p class="na">Pages les plus visitées indisponibles pour le moment.</p>${(w.errors || {}).top_pages ? `<small class="neg">Motif renvoyé par Odoo : ${esc(w.errors.top_pages)}</small>` : ''}`;
      if (!t.length) return '<p class="na">Aucune page suivie sur la période.</p>';
      return table(['#', 'Page', 'Vues', '% des vues'], t.map((p, i) => `<tr><td>${i + 1}</td><td class="prod">${pageLink(cfg && cfg.hosts && cfg.hosts.xc, p.path, p.label)}<br><small class="na">${esc(p.path)}</small></td><td>${num(p.views)}</td><td>${pct(p.share)}</td></tr>`), 'prodtable')
        + '<small class="na">Pages du webshop suivies par Odoo, adresses regroupées sans leurs paramètres ; le % est la part dans les vues de ces pages (hors visites des pages non suivies).</small>';
    }, true),
    NOTE('Commandes confirmées, hors taxes. Le classement porte sur les produits (hors livraison et autres services) ; le « % du total » est la part dans la valeur de ces produits pour le webshop. Noms de produits en français quand Odoo les traduit. Source : commandes Odoo par site web.'),
  ].concat(gaKey ? gaBlocks(gaKey, {shop: true, pages: topPages}) : []).filter(b => (!(cfg && cfg.ga && gaKey) || (b.id !== 'visits' && b.id !== 'toppages')) && (topPages || b.id !== 'toppages') && (customers || b.id !== 'customers') && (picking || b.id !== 'picking'));
}
const PAGES = {
  'overview/ca': () => [
    BU_BAR(),
    B('kpi', 'Chiffre d’affaires', d => {
      if (buSel !== 'all') { const sc = buScope(d), t = d.pnl.total.ca;
        return `<div class="kpis">${kpi('Chiffre d’affaires · ' + sc.label, eur(sc.ca), '', t > 0 ? pct(sc.ca / t) + ' du CA total' : '')}</div><small class="na">Filtre BU actif : ${esc(sc.label)}. La comparaison avec l’année précédente n’existe que pour le total (le plan comptable de 2025 ne distinguait pas les BU).</small>`; }
      const tot = d.pnl.total.ca, pv = d.pnl_prev, yr = pv && pv.period ? pv.period.from.slice(0, 4) : '';
      const share = k => tot > 0 ? pct(grp(d, k).ca / tot) + ' du CA' : '';
      const cmp = (cur, prev) => pv ? vsPrev(cur, prev, yr) : '';
      return `<div class="kpis">${kpi('Chiffre d’affaires', eur(tot), '', cmp(tot, pv && pv.total.ca)) + kpi('CA XC', eur(grp(d,'XC').ca), '', '', share('XC'))
        + kpi('CA CARS', eur(grp(d,'CARS').ca), '', '', share('CARS'))}</div>`
        + (pv ? `<small class="na">Variation du CA total par rapport à la même période en ${yr} (${fmtDate(pv.period.from)} → ${fmtDate(pv.period.to)}) : ${eur(pv.total.ca)}${pv.old_plan_ca ? ` (dont ${eur(pv.old_plan_ca)} sur l’ancien plan comptable, comptes « OLD »)` : ''}. Pas de comparaison XC / CARS : la structure des comptes de ${yr} ne permet pas la répartition par BU. Part du CA : par rapport au CA total, « Non affecté » compris.</small>` : '');
    }),
    FINANCE,
    B('bu', 'CA par BU', d => bars(busTree(d), 'ca', {sub: b => d.pnl.total.ca ? pct(b.ca / d.pnl.total.ca) + ' du CA' : ''})),
    PJ_BLOCK('ca'),
  ],
  'overview/clients': () => [
    BU_BAR(),
    B('kpi', 'Clients', d => { const c = d.top_clients || {}, key = BU_TAB[buSel], list = c[key] || [], ca = buScope(d).ca, top = list.reduce((x, y) => x + y.ca, 0);
      return c.unavailable ? `<p class="na">${esc(c.unavailable)}</p>`
        : `<div class="kpis">${kpi('CA facturé', eur(ca)) + kpi('Part des ' + list.length + ' premiers clients', pct(ca > 0 ? top / ca : 0), '', eur(top))
          + (c._stats && c._stats[key] && c._stats[key].invoices ? kpi('Factures émises', num(c._stats[key].invoices), '', 'panier moyen ' + eur(c._stats[key].avg || 0)) : '')
          + (c._meta && c._meta.open ? kpi('Solde ouvert (période)', eur((c._open_totals || {})[key] || 0)) : '')}</div>` + (buSel !== 'all' ? `<small class="na">Filtre BU actif : ${esc(BU_PNL_LABEL[buSel])}.</small>` : ''); }),
    B('clients', 'Hit-parade clients' + (buSel !== 'all' ? ' · ' + BU_PNL_LABEL[buSel] : ''), d => clients(d, ALL_CLIENTS, {hideTabs: true})),
    ...(buSel === 'cars' ? [B('clients_oth', 'Hit-parade clients · CARS Others', d => clients(d, ALL_CLIENTS, {hideTabs: true, force: 'CARS_OTHERS'}))] : []),
  ],
  'overview/mb': () => [
    BU_BAR(),
    B('kpi', 'Marge brute', d => { const t = buScope(d); if (t.scoped) return `<div class="kpis">${kpi('Marge brute · ' + t.label, eur(t.margin), cls(t.margin)) + kpi('Marge brute / CA', t.ca ? pct(t.margin / t.ca) : '–', cls(t.margin)) + kpi('Coûts directs', eur(t.direct_costs))}</div>`; return `<div class="kpis">${kpi('Marge brute', eur(t.margin), cls(t.margin)) + kpi('Marge brute / CA', pct(t.margin_pct), cls(t.margin)) + kpi('Coûts directs', eur(t.direct_costs))}</div>`; }),
    FINANCE,
    B('bu', 'Marge brute par BU', d => bars(busTree(d), 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + margin(b)})),
    NOTE('Marge brute = CA − coûts directs (comptes 602, 603, 604). Personnel et véhicules (615) ne sont pas imputables à une BU et sont exclus.'),
    PJ_BLOCK('mb'),
  ],
  'overview/nm': () => [BU_BAR(), NM_BLOCK('all', 'Marge nette par BU'), PJ_BLOCK('mn')],
  'overview/suppliers': () => [
    BU_BAR(),
    B('kpi', 'Achats fournisseurs', d => { const s = d.top_suppliers || {}, t = s._totals || {}, key = BU_TAB[buSel], bu = ['XC', 'MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'].reduce((x, k) => x + (t[k] || 0), 0);   // sans la vue CARS (déjà comprise)
      if (!(s.unavailable || !s._totals) && buSel !== 'all') return `<div class="kpis">${kpi('Achats HT · ' + BU_PNL_LABEL[buSel], eur(t[key] || 0), '', t.total ? pct((t[key] || 0) / t.total) + ' des achats totaux' : '')
          + (s._stats && s._stats[key] && s._stats[key].invoices ? kpi('Factures reçues', num(s._stats[key].invoices), '', 'achat moyen ' + eur(s._stats[key].avg || 0)) : '')
          + (s._meta && s._meta.open ? kpi('Reste à payer (période)', eur((s._open_totals || {})[key] || 0)) : '')}</div><small class="na">Filtre BU actif : ${esc(BU_PNL_LABEL[buSel])}.</small>`;
      return s.unavailable || !s._totals ? `<p class="na">${esc(s.unavailable || 'Indisponible pour le moment.')}</p>`
        : `<div class="kpis">${kpi('Achats HT', eur(t.total || 0)) + kpi('Rattachés à une BU', eur(bu), '', pct(t.total ? bu / t.total : 0))
          + (s._stats && s._stats.total && s._stats.total.invoices ? kpi('Factures reçues', num(s._stats.total.invoices), '', 'achat moyen ' + eur(s._stats.total.avg || 0)) : '')
          + kpi('Hors BU (frais généraux…)', eur(t.HORS_BU || 0), '', pct(t.total ? (t.HORS_BU || 0) / t.total : 0))
          + (s._meta && s._meta.open ? kpi('Reste à payer (période)', eur((s._open_totals || {}).total || 0)) : '')}</div>`; }),
    B('suppliers', 'Hit-parade fournisseurs' + (buSel !== 'all' ? ' · ' + BU_PNL_LABEL[buSel] : ''), d => suppliers(d, ALL_SUPPLIERS, {hideTabs: true})),
    ...(buSel === 'cars' ? [B('suppliers_oth', 'Hit-parade fournisseurs · CARS Others', d => suppliers(d, ALL_SUPPLIERS, {hideTabs: true, force: 'CARS_OTHERS'}))] : []),
  ],
  'overview/adjustments': () => adjPageBlocks(),
  'xc/inventory': () => stockBlocks().concat(stockVarBlocks()),
  'xc/margins': () => marginsBlocks(),
  'xc/tn11': () => tn11Blocks(),
  'marketing/expenses': () => marketingBlocks(),
  'home/welcome': () => homeBlocks(),
  'others/tags': () => tagsBlocks(),
  'others/users': () => usersBlocks(),
  'expenses/source': () => expensesSourceBlocks(),
  'expenses/general': () => expensesGeneralBlocks(),
  'expenses/rules': () => expensesRulesBlocks(),
  'vehicles/source': () => expensesSourceBlocks('vehicle'),
  'vehicles/general': () => expensesGeneralBlocks('vehicle'),
  'vehicles/byvehicle': () => vehiclesByBlocks(),
  'vehicles/fuel': () => fuelBlocks(),
  'vehicles/usage': () => splitBlocks(),
  'staff/source': () => staffSourceBlocks(),
  'staff/people': () => staffPeopleBlocks(),
  'staff/general': () => staffViewBlocks('general'),
  'staff/xc': () => staffViewBlocks('xc'),
  'staff/cars': () => staffViewBlocks('cars'),
  'staff/shared': () => staffViewBlocks('shared'),
  'staff/management': () => staffViewBlocks('management'),
  'marketing/site': () => gaBlocks('site', {pages: true, geo: true}).concat([NOTE('Trafic du site vitrine lifelive-motorsport.com (toutes les pages, boutique comprise) d’après Google Analytics. Les visiteurs qui refusent les cookies ne sont pas comptés ; les chiffres sont fiables pour comparer des périodes entre elles. Les webshops XC et Goldspeed ont leur propre analyse dans Détail XC.')]),
  'overview/xcvscars': () => [BU_BAR(), ...PAGES['xcvscars/ca'](), ...PAGES['xcvscars/mb']()],
  'xcvscars/ca': () => [
    B('cmp', 'CA : XC vs CARS', d => { const x = grp(d,'XC'), c = xvcSide(d), tot = x.ca + c.ca || 1;
      return `<div class="two">${kpi('XC Cross Car', eur(x.ca), '', pct(x.ca / tot) + ' du CA')}${kpi(c.label, eur(c.ca), '', pct(c.ca / tot) + ' du CA')}</div>
      <div class="stack"><div style="width:${x.ca / tot * 100}%;background:var(--red)"></div><div style="width:${c.ca / tot * 100}%;background:var(--mut)"></div></div>
      <small class="na">Rouge : XC — gris : ${esc(c.label)} (hors « Non affecté », ${eur(grp(d,'OTHER').ca)})</small>`; }),
  ],
  'xcvscars/mb': () => [
    B('cmpm', 'Marge brute : XC vs CARS', d => { const x = grp(d,'XC'), c = xvcSide(d);
      return `<div class="two">${kpi('XC Cross Car', eur(x.margin), cls(x.margin), 'Marge brute · ' + margin(x))}${kpi(c.label, eur(c.margin), cls(c.margin), 'Marge brute · ' + margin(c))}</div>`
      + signedGauge([{v: x.margin, label: 'XC', color: 'var(--red)'}, {v: c.margin, label: c.label, color: 'var(--mut)'}]) + `<small class="na">Parts de la marge brute XC + CARS, hors « Non affecté » (${eur(grp(d,'OTHER').margin)}).</small>`; }),
    B('detailxc', 'Détail', d => table(HEAD, [lineRow('XC Cross Car', grp(d,'XC')), lineRow(xvcSide(d).label, xvcSide(d))])),
  ],
  'xc/general': () => [
    B('kpi', 'XC — synthèse', d => { const x = grp(d,'XC'); return `<div class="kpis">${kpi('CA XC', eur(x.ca)) + kpi('Coûts directs', eur(x.direct_costs)) + kpi('Marge brute', eur(x.margin), cls(x.margin)) + kpi('Marge brute / CA', margin(x), cls(x.margin))}</div>` + encoursCards(d, 'XC'); }),
    NM_BLOCK('xc', 'XC — marge nette'),
    B('decomp', 'XC — CA et coûts directs en détail', d => decompTable(d, [{label: 'XC', o: grp(d, 'XC')}])),
    NOTE('Les lignes XC (Manufacturer, Race team, Goldspeed…) ne sont pas des activités indépendantes : les comparer entre elles peut être trompeur. Voir « Par ligne d’activité ».'),
    B('suppliers', 'Hit-parade fournisseurs XC', d => suppliers(d, ['XC'])),
    B('clients', 'Hit-parade clients XC', d => clients(d, ['XC'])),
  ],
  'xc/lignes': () => [
    B('lines', 'XC — par ligne d’activité', d => table(HEAD, d.pnl.bus.find(b => b.key === 'XC').lines.map(l => lineRow(l.line, l)))),
    NOTE('Le Race Team se déplace d’abord pour soutenir les clients constructeur ; le contrat Goldspeed découle du statut de constructeur XC. Les ventes webshop sont comptabilisées sur d’autres lignes que « Webshop » (CA = 0 sur cette ligne) — à confirmer.'),
  ],
  'xc/webshop_xc': () => webshopPage(w => !/goldspeed/i.test(w.name), {customers: true, picking: true, gaKey: 'xc'}),
  'xc/webshop_gs': () => webshopPage(w => /goldspeed/i.test(w.name), {topPages: false, gaKey: 'gs'}),      // 2 produits seulement : un classement de pages n'a pas de sens
  'xc/events': () => [
    B('events', 'Événements XC', d => eventsTable(d, ['XC'])),
    B('none', 'Autres événements (BU « Others » ou sans BU identifiable)', d => eventsTable(d, ['OTHERS', 'NONE'], true)),
    EVENT_NOTE,
  ],
  'cars/events': () => [
    CARS_MARGIN_WARN,
    B('events', 'Événements CARS', d => eventsTable(d, ['CARS'], true)),
    B('none', 'Autres événements (BU « Others » ou sans BU identifiable)', d => eventsTable(d, ['OTHERS', 'NONE'], true)),
    EVENT_NOTE,
  ],
  'cars/vehicles': () => [
    CARS_MARGIN_WARN,
    B('vehicles', 'Véhicules CARS', d => eventsTable(d, ['CARS'], true, true)),
    NOTE('Un véhicule = un compte de l’axe analytique CARS ; il est rattaché à une BU d’après l’axe BU renseigné sur ses lignes (Modern Rally, Historic Rally, Historic Racing). Client et catégorie viennent de la fiche du compte analytique. Résultat cash = produits − coûts directs − autres charges (hors dotations aux amortissements) − investissements (dépenses immobilisées sur les comptes INVEST, amorties ensuite) ; survolez le ⓘ à côté du résultat pour le montant investi, la durée d’amortissement et le résultat comptable. Les montants non ventilés analytiquement n’apparaissent pas ici ; les comptes « OLD » de l’axe BU sont ignorés.'),
  ],
  'cars/general': () => [
    B('kpi', 'CARS — synthèse', d => { const c = grp(d,'CARS'); return `<div class="kpis">${kpi('CA CARS', eur(c.ca)) + kpi('Coûts directs', eur(c.direct_costs)) + kpi('Marge brute', eur(c.margin), cls(c.margin)) + kpi('Marge brute / CA', margin(c), cls(c.margin))}</div>` + encoursCards(d, 'CARS'); }),
    NM_BLOCK('cars', 'CARS — marge nette'),
    B('decomp', 'CARS et ses BU — CA et coûts directs en détail', d => decompTable(d, [{label: 'CARS', o: grp(d, 'CARS')}].concat(d.pnl.bus.filter(b => b.group === 'CARS').map(b => ({label: b.label, o: b}))))),
    B('bu', 'Par BU', d => table(HEAD, d.pnl.bus.filter(b => b.group === 'CARS' && (b.ca || b.direct_costs)).map(b => lineRow(b.label, b)))),
    B('suppliers', 'Hit-parade fournisseurs CARS', d => suppliers(d, ['CARS'])),
    B('clients', 'Hit-parade clients CARS', d => clients(d, ['CARS'])),
  ],
  'cars/bu': () => [
    B('bu', 'Marge brute par BU', d => bars(d.pnl.bus.filter(b => b.group === 'CARS' && (b.ca || b.direct_costs)), 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + margin(b)})),
    NM_BLOCK('carsbu', 'Marge nette par BU'),
    B('suppliers', 'Hit-parade fournisseurs', d => suppliers(d, ['CARS','MODERN_RALLY','HISTORIC_RALLY','HISTORIC_RACING','CARS_OTHERS'])),
    B('clients', 'Hit-parade clients', d => clients(d, ['CARS','MODERN_RALLY','HISTORIC_RALLY','HISTORIC_RACING','CARS_OTHERS'])),
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
let navClosed = new Set();           // modules repliés à la main
function renderNav(key) {
  const mo = moduleOf(key), curG = key.split('/')[0];
  const grpHtml = g => { const m = MENU.find(x => x[0] === g), items = m ? m[2].filter(([i]) => allowedPage(g + '/' + i)) : []; if (!items.length) return '';
    return `<div class="grp ${g === curG ? 'open active' : ''}" data-g="${g}"><button type="button">${esc(m[1])}</button><ul>${items.map(([i, l]) => { const k = g + '/' + i, live = LIVE.has(k);
      return `<li><a href="#/${k}" class="${k === key ? 'on' : ''} ${live ? '' : 'soon'}">${esc(l)}${live ? '' : '<small>bientôt</small>'}</a></li>`; }).join('')}</ul></div>`; };
  const link = (k, label, soon) => `<a class="navmod ${k === key ? 'on' : ''} ${soon ? 'soon' : ''}" href="#/${k}">${esc(label)}${soon ? '<small>bientôt</small>' : ''}</a>`;
  const modHtml = m => {
    const pages = modulePages(m).filter(p => allowedPage(p[0])); if (!pages.length) return '';
    if (m.groups) { const open = !navClosed.has(m.id) || (mo && mo.module.id === m.id);
      return `<div class="sec ${open ? 'open' : ''}" data-mod="${m.id}"><button type="button" class="sec-h">${esc(m.label)}</button><div class="sec-body">${m.groups.map(grpHtml).join('')}</div></div>`; }
    return pages.map(p => link(p[0], pages.length === 1 ? m.label : p[1], !LIVE.has(p[0]))).join('');
  };
  $('nav').innerHTML = `<a class="navhome ${key === 'home/welcome' ? 'on' : ''}" href="#/home/welcome">Accueil</a>`
    + CHAPTERS.map(c => { const h = c.modules.map(modHtml).join(''); return h ? `<div class="chap"><div class="chap-h"><span>${c.n}</span>${esc(c.label)}</div>${h}</div>` : ''; }).join('');
}

let current = {key: null, blocks: []};
const bkey = b => current.key + ':' + b.id;
const selectHTML = (b, p) => `<select class="per" data-bid="${b.id}" aria-label="Période — ${esc(b.title)}">${PERIODS.map(([v, l]) => `<option value="${v}"${v === p ? ' selected' : ''}>${l}</option>`).join('')}</select>`;

function blockHTML(b) {
  if (b.static) return b.static;
  const p = periodOf(bkey(b)), [f, t] = periodRange(p);
  let d = b.fixed ? (anyData() || cached('ytd')) : cached(p);
  if (d && !b.raw) d = viewData(d);          // MB ajustée (sauf sur le bloc de rapprochement, qui compare les deux)
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
  if ($('adj-editor')) drawAdjEditor();                    // les listes d'événements / véhicules viennent d'arriver
  renderFooter();
}

function render(force) {
  let key = route(); if (!item(key) || !allowedPage(key)) key = homePage();
  const {grp: g, it} = item(key);
  renderNav(key); buLogo(pageBu(key));
  $('page-title').innerHTML = pageTitle(key);
  const blocks = PAGES[key] ? PAGES[key]() : [];
  const bar = adjBar(key); if (bar) blocks.unshift(bar);
  current = {key, blocks};
  $('page').innerHTML = PAGES[key] ? blocks.map(blockHTML).join('') : soon(key);
  blocks.forEach(b => { if (!b.static && (force || !fresh(b.fixed ? 'ytd' : periodOf(bkey(b))))) fillBlock(b, force); });  // données périmées : affichées, puis rafraîchies
  if (key === 'overview/adjustments') drawAdjEditor();
  if (key === 'xc/inventory') { drawStockVar(); loadStock(!!force).then(drawStock); }
  if (key === 'home/welcome') homeDraw();
  if (key === 'xc/tn11') drawTn11();
  if (key === 'xc/margins') { drawMargins(); if (!mg.data || force) loadMargins(!!force); }
  if (/^staff\/(source|people|general|xc|cars|shared|management)$/.test(key)) { sdDraw(); sdLoad().then(sdDraw); }
  if (key === 'expenses/source') { exDrawSource(); exLoadSource().then(exDrawSource); }
  if (key === 'expenses/rules') { exDrawRules(); exLoadAlloc().then(exDrawRules); }
  if (key === 'vehicles/source') { exDrawSource(); exLoadSource().then(exDrawSource); }
  if (key === 'vehicles/general') { exDrawGeneral(); exLoadGeneral('vehicle').then(exDrawGeneral); }
  if (key === 'vehicles/fuel') { exDrawFuel(); exLoadFuel().then(() => { exDrawFuel(); exParseDkv(exDrawFuel); }); }
  if (key === 'vehicles/usage') { exDrawSplit(); exLoadSplit().then(exDrawSplit); }
  if (key === 'vehicles/byvehicle') { exDrawVehicles(); exLoadVehicles().then(exDrawVehicles); }
  if (key === 'expenses/general') { exDrawGeneral(); exLoadGeneral().then(exDrawGeneral); }
  if (key === 'others/tags') { drawTags(); loadTags().then(drawTags); }
  if (key === 'others/users') { drawUsers(); loadUsers().then(drawUsers); }
  renderFooter(); store.set('lm_page', key); document.body.classList.remove('nav-open'); $('menu-btn').setAttribute('aria-expanded', 'false');
  $('app').hidden = false; $('login').hidden = true;
}

function needLogin() {
  $('app').hidden = true; $('login').hidden = false;
  google.accounts.id.initialize({client_id: cfg.google_client_id, hd: undefined,
    callback: async r => { token = r.credential; sessionStorage.setItem('idt', token);
      try { const sr = await fetch('/api/session', {method: 'POST', headers: {Authorization: 'Bearer ' + token}}); setSession(await sr.json()); } catch {}      // cookie de session du dashboard (durée longue)
      Promise.all([loadAdj(), loadStockVar()]).then(() => render()); }});
  google.accounts.id.renderButton($('g_btn'), {theme: 'outline', size: 'large', width: 280, locale: 'en'});
}

// ---- Export PDF : impression navigateur avec feuille de style dédiée ------------------------------
function exportPdf() {
  const {grp: g, it} = item(current.key) || {grp: ['', ''], it: ['', '']};
  const stamp = new Date().toLocaleString(LOCALE());
  $('print-title').textContent = `${g[1]} › ${it[1]}`;
  $('print-meta').textContent = `Rapport généré le ${stamp}`;
  const old = document.title; document.title = `Lifelive – ${g[1]} – ${it[1]} – ${ymd(new Date())}`;
  const restore = () => { document.title = old; window.removeEventListener('afterprint', restore); };
  window.addEventListener('afterprint', restore); window.print();
}

$('home').onclick = e => {                    // le logo ramène à l'accueil (Vue d’ensemble › CA)
  e.preventDefault(); document.body.classList.remove('nav-open');
  if (route() === homePage()) window.scrollTo({top: 0}); else location.hash = '#/' + homePage();
};

let statusTimer;
function flash(text, kind = 'ok') {            // message temporaire sous l'en-tête
  $('status').textContent = text; $('status').className = kind; clearTimeout(statusTimer);
  statusTimer = setTimeout(() => { if ($('status').textContent === text) { $('status').textContent = ''; $('status').className = ''; } }, 6000);
}
async function refresh() {
  const btn = $('refresh'); if (btn.disabled) return;
  btn.disabled = true; btn.classList.add('spin'); flash('Actualisation en cours…', '');
  const periodsUsed = [...new Set(current.blocks.filter(b => !b.static).map(b => b.fixed ? 'ytd' : periodOf(bkey(b))))];
  const before = new Set([...cache.values()].map(h => h.data.generated_at));
  try {
    await Promise.all(periodsUsed.map(p => getData(p, true)));   // une seule demande par période
    render();
    const fresh = periodsUsed.some(p => !before.has((cached(p) || {}).generated_at));
    const at = new Date().toLocaleTimeString(LOCALE());
    if (fresh) flash(`Données actualisées à ${at}.`);
    else { const last = new Date(Math.max(...periodsUsed.map(p => +new Date((cached(p) || {}).generated_at || 0)))).toLocaleTimeString(LOCALE());
           flash(`Déjà à jour : Odoo a été lu à ${last} (nouvelle lecture possible après 30 secondes).`); }
  } catch (e) { if (e.message !== 'Connexion requise') flash(e.message, 'err'); }
  finally { btn.disabled = false; btn.classList.remove('spin'); }
}
$('refresh').onclick = refresh;
$('pdf').onclick = exportPdf;
$('menu-btn').onclick = () => { const o = document.body.classList.toggle('nav-open'); $('menu-btn').setAttribute('aria-expanded', String(o)); };
$('backdrop').onclick = () => document.body.classList.remove('nav-open');
$('nav').onclick = e => { const h = e.target.closest('.sec-h'); if (h) { const id = h.parentElement.dataset.mod, open = !h.parentElement.classList.contains('open'); open ? navClosed.delete(id) : navClosed.add(id); h.parentElement.classList.toggle('open'); return; } const b = e.target.closest('.grp > button'); if (b) b.parentElement.classList.toggle('open'); };
const sortBy = e => { const h = e.target.closest('th[data-sort]'); if (!h) return false;
  const k = h.dataset.sort; evSort = {k, dir: evSort.k === k ? -evSort.dir : (k === 'name' || k === 'bu' || k === 'client' ? 1 : -1)};     // 2ᵉ clic : inverse
  current.blocks.filter(b => !b.static).forEach(updateBlock); return true; };
$('page').onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && sortBy(e)) e.preventDefault(); };
$('page').onclick = e => { if (e.target.dataset.pickscope) { pickScope = e.target.dataset.pickscope; current.blocks.filter(b => !b.static).forEach(updateBlock); return; } if (sortBy(e)) return; if (e.target.dataset.tab) { if (e.target.dataset.kind === 's') tabS = e.target.dataset.tab; else tab = e.target.dataset.tab; current.blocks.filter(b => !b.static).forEach(updateBlock); } };
$('page').onchange = e => {
  const bid = e.target.dataset.bid; if (!bid || !e.target.classList.contains('per')) return;
  const b = current.blocks.find(x => x.id === bid); periods[bkey(b)] = e.target.value; store.set('lm_periods', JSON.stringify(periods));
  updateBlock(b); fillBlock(b);
};
window.addEventListener('hashchange', () => { if ($('login').hidden) { render(); window.scrollTo(0, 0); } });
const tick = () => { if (document.visibilityState === 'visible' && $('login').hidden) Promise.all([loadAdj(), loadStockVar()]).finally(() => render()); };
setInterval(tick, 5 * 60000);   // l'API met déjà ses réponses en cache 5 min
document.addEventListener('visibilitychange', tick);

buSyncTabs(); if (typeof buLogo === 'function') buLogo();
(async () => {
  cfg = await (await fetch('/api/config')).json();
  if (cfg.auth) {
    await new Promise(res => { const s = document.createElement('script'); s.src = 'https://accounts.google.com/gsi/client?hl=en'; s.onload = res; document.head.append(s); });
    let ok = false;
    try { const sr = await fetch('/api/session', {headers: token ? {Authorization: 'Bearer ' + token} : {}}); ok = sr.ok; if (ok) setSession(await sr.json()); } catch {}      // cookie de session valide, ou jeton Google encore valable
    if (!ok) { token = null; sessionStorage.removeItem('idt'); return needLogin(); }
  }
  else { try { const sr = await fetch('/api/session'); if (sr.ok) setSession(await sr.json()); } catch {} }
  await Promise.all([loadAdj(), loadStockVar()]);
  render();
})();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');

