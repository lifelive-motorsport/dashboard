// GENERAL EXPENSES › Données source (choix des comptes) et Général (résultat). Chargé avant app.js ; utilise ses fonctions (esc, eur, num, pct, kpi, table, lineChart) à l'appel.
const EX_YEAR = new Date().getFullYear();
let ex = {genK: {}, monthK: {}, monthSelK: {}, alloc: null, allocErr: null, keyMode: null, keyPct: 50, keyDirty: false, src: null, gen: null, err: null, genErr: null, sel: {}, part: {}, dirty: false, msg: ''};
const exAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};
const exKinds = [['', 'Laisser de côté'], ['general', 'Frais généraux'], ['vehicle', 'Véhicules de service'], ['partners', 'Selon le fournisseur']];
const exPartKinds = [['', 'Laisser de côté'], ['general', 'Frais généraux'], ['vehicle', 'Véhicules de service']];
const exMonth = m => { try { return new Date(m + '-15').toLocaleDateString('fr-BE', {month: 'short'}).replace('.', ''); } catch { return m; } };
const exEur2 = n => new Intl.NumberFormat('fr-BE', {style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2}).format(n || 0);

async function exGet(url) {
  const r = await fetch(url, {headers: exAuth()});
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Erreur ' + r.status);
  return r.json();
}
async function exLoadSource() {
  try { const j = await exGet(`/api/expenses/accounts?year=${EX_YEAR}`); ex.src = j; ex.err = null;
    if (!ex.dirty) { ex.sel = Object.fromEntries(j.accounts.filter(a => a.kind).map(a => [a.code, a.kind])); ex.part = JSON.parse(JSON.stringify(j.partner_rules || {})); } }
  catch (e) { ex.err = e.message; }
}
async function exLoadMonth(m, kind) {
  ex.monthSelK[kind] = m; ex.monthK[kind] = null;
  try { ex.monthK[kind] = await exGet(`/api/expenses/month?month=${m}&kind=${kind}`); ex.monthErr = null; } catch (e) { ex.monthErr = e.message; }
}
async function exLoadGeneral(kind = 'general') {
  try { const g = ex.genK[kind] = await exGet(`/api/expenses/general?year=${EX_YEAR}&kind=${kind}`); ex.genErr = null;
    if (!ex.monthSelK[kind] && g.series.length) { const top = g.series.slice().sort((x, y) => y.amount - x.amount)[0]; await exLoadMonth(top.month, kind); } } catch (e) { ex.genErr = e.message; }
}

async function exLoadVehicles() {
  try { ex.veh = await exGet(`/api/expenses/vehicles?year=${EX_YEAR}`); ex.vehErr = null; } catch (e) { ex.vehErr = e.message; }
}
function vehiclesByBlocks() {
  return [{static: '<section class="block" data-bid="veh-by"><div class="block-head"><h3>Coût par véhicule de service</h3></div><div class="block-body" id="exp-vehicles"><p class="na">Chargement…</p></div></section>'}];
}
function exDrawVehicles() {
  const el = document.getElementById('exp-vehicles'); if (!el) return;
  if (ex.vehErr) { el.innerHTML = `<p class="neg">${esc(ex.vehErr)}</p>`; return; }
  const v = ex.veh; if (!v) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (v.empty) { el.innerHTML = '<p class="na">Aucun compte retenu comme véhicule de service : voir « Données source ».</p>'; return; }
  const rows = v.vehicles.map(x => `<tr><td class="prod">${esc(x.vehicle)}${x.vehicle === '(non classé)' ? ' <small class="na" title="Libellé de compte sans le motif « Nature Util. Véhicule »">comptes ' + esc(x.accounts.join(', ')) + '</small>' : ''}</td>${v.types.map(t => `<td>${x.types[t] ? eur(x.types[t]) : '–'}</td>`).join('')}<td>${eur(x.total)}</td>
    <td class="sharecell"><span class="sharebar" style="width:${Math.round(Math.max(0, x.share) * 100)}%"></span><span>${pct(x.share)}</span></td></tr>`);
  el.innerHTML = `<div class="kpis">${kpi('Véhicules de service depuis le 1er janvier', eur(v.total), '', v.configured ? '' : 'proposition de départ (non enregistrée)')}${kpi('Véhicules', num(v.vehicles.filter(x => x.vehicle !== '(non classé)').length), '', 'avec au moins une charge')}</div>`
    + table(['Véhicule'].concat(v.types, ['Total', 'Part']), rows.concat([`<tr class="tot"><td>Total</td>${v.types.map(t => `<td>${eur(v.type_totals[t])}</td>`).join('')}<td>${eur(v.total)}</td><td>100,0 %</td></tr>`]), 'prodtable')
    + '<small class="na">Chaque compte de la classe 615 est un véhicule et une nature de dépense (libellé « Nature Util. Véhicule », par exemple « Carburant Util. CITAN »). Le carburant est à contrôler : voir la rubrique Carburant.</small>';
}

async function exLoadFuel() {
  try { ex.fuel = await exGet(`/api/fuel?year=${EX_YEAR}`); ex.fuelErr = null; } catch (e) { ex.fuelErr = e.message; }
  try { if (!ex.veh) ex.veh = await exGet(`/api/expenses/vehicles?year=${EX_YEAR}`); } catch (e) { /* le reste de la page fonctionne sans */ }
}
function fuelBlocks() {
  return [{static: '<section class="block" data-bid="veh-fuel"><div class="block-head"><h3>Carburant : Odoo, factures de la carte carburant et agenda</h3></div><div class="block-body" id="exp-fuel"><p class="na">Chargement…</p></div></section>'}];
}
const exNorm = t => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
function exDrawFuel() {
  const el = document.getElementById('exp-fuel'); if (!el) return;
  if (ex.fuelErr) { el.innerHTML = `<p class="neg">${esc(ex.fuelErr)}</p>`; return; }
  const f = ex.fuel; if (!f) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  const cal = f.calendar || {}, usage = cal.usage || [];
  const match = veh => usage.find(u => { const a = exNorm(u.vehicle), b = exNorm(veh); return b !== '(non classe)' && (a.includes(b) || b.includes(a)); });
  // 1. Carburant encodé dans Odoo, par véhicule, rapproché des jours de réservation de l'agenda
  const fuelBy = ex.veh ? ex.veh.vehicles.filter(v => v.types.Carburant).map(v => ({vehicle: v.vehicle, fuel: v.types.Carburant, u: match(v.vehicle)})) : [];
  const tfuel = fuelBy.reduce((t, x) => t + x.fuel, 0);
  const sec1 = '<h4 class="sub">1. Carburant tel qu’encodé dans Odoo (comptes 615, nature « Carburant »)</h4>' + (fuelBy.length ? table(['Véhicule', 'Carburant depuis le 1er janvier', 'Part', 'Jours de déplacement (agenda)', 'Carburant par jour de déplacement'],
      fuelBy.sort((a, b) => b.fuel - a.fuel).map(x => `<tr><td class="prod">${esc(x.vehicle)}${x.u ? ` <small class="na">≈ ${esc(x.u.vehicle)}</small>` : ''}</td><td>${eur(x.fuel)}</td><td>${tfuel ? pct(x.fuel / tfuel) : '–'}</td><td>${x.u ? num(x.u.away_days) : '–'}</td><td>${x.u && x.u.away_days ? eur(x.fuel / x.u.away_days) : '–'}</td></tr>`)
        .concat([`<tr class="tot"><td>Total</td><td>${eur(tfuel)}</td><td>100,0 %</td><td></td><td></td></tr>`]), 'prodtable')
      + '<small class="na">Rapprochement indicatif par ressemblance de nom entre le véhicule du compte et la ressource de l’agenda.</small>' : '<p class="na">Aucun compte de nature « Carburant » parmi les véhicules de service (voir « Par véhicule »).</p>');
  // 2. Factures de la carte carburant
  const sumHt = f.invoices.reduce((t, i) => t + i.untaxed, 0), sum615 = f.invoices.reduce((t, i) => t + i.lines.reduce((u, l) => u + l.amount, 0), 0);
  const sec2 = `<h4 class="sub">2. Factures ${esc(f.supplier)} ${EX_YEAR}</h4>` + (f.invoices.length ? table(['Date', 'Facture', 'HT', 'Imputé en 615', 'Imputation par véhicule', 'Pièce jointe', ''],
      f.invoices.map(i => { const im = i.lines.reduce((t, l) => t + l.amount, 0), gap = Math.abs(i.untaxed - im) > 1;
        return `<tr><td>${fmtDate(i.date)}</td><td>${esc(i.number)}${i.refund ? ' <small class="na">(avoir)</small>' : ''}<br><small class="na">${esc(i.ref)}</small></td><td>${exEur2(i.untaxed)}</td><td class="${gap ? 'neg' : ''}">${exEur2(im)}</td>
          <td class="prod">${i.lines.map(l => `${esc(l.name)} : ${exEur2(l.amount)}`).join('<br>') || '–'}</td><td>${i.attachments.length ? i.attachments.map(a => esc(a.name)).join('<br>') : '<small class="na">aucune</small>'}</td>
          <td>${i.attachments.length ? `<button type="button" data-ex-att="${i.attachments[0].id}">Texte extrait</button>` : ''}</td></tr>`; })
        .concat([`<tr class="tot"><td colspan="2">Total</td><td>${exEur2(sumHt)}</td><td>${exEur2(sum615)}</td><td colspan="3"></td></tr>`]), 'prodtable sdtable') + '<div id="exp-att"></div>'
      + '<small class="na">« Imputé en 615 » = lignes de la facture sur les comptes 615 : en rouge, un écart avec le HT de la facture (partie imputée ailleurs, ou carburant non ventilé).</small>' : '<p class="na">Aucune facture trouvée pour ce fournisseur (recherche par nom : variable FUEL_SUPPLIER_NAME).</p>');
  // 3. Agenda
  let sec3 = '<h4 class="sub">3. Réservations des véhicules dans l’agenda Google</h4>';
  if (!cal.configured) sec3 += `<p class="na">${esc(cal.note || 'Agenda non configuré.')}</p>`;
  else if (cal.error) sec3 += `<p class="neg">${esc(cal.error)}</p>`;
  else sec3 += usage.length ? table(['Ressource (véhicule)', 'Réservations', 'Jours réservés', `Jours de déplacement (± ${cal.buffer_days} j)`, 'Derniers événements'],
      usage.map(u => `<tr><td class="prod">${esc(u.vehicle)}</td><td>${num(u.events)}</td><td>${num(u.booked_days)}</td><td>${num(u.away_days)}</td><td class="prod"><small class="na">${u.list.slice(-3).map(e => esc(e.title) + ' (' + fmtDate(e.start) + (e.end !== e.start ? ' → ' + fmtDate(e.end) : '') + ')').join('<br>')}</small></td></tr>`), 'prodtable')
      + `<small class="na">Un véhicule est « en déplacement » de ${cal.buffer_days} jours avant à ${cal.buffer_days} jours après sa réservation : le carburant de ces jours se rattache à l’événement. </small>` : '<p class="na">Aucun événement avec une ressource véhicule trouvé sur la période.</p>';
  el.innerHTML = sec1 + sec2 + sec3
    + '<small class="na">Le contrôle croisé (carburant DKV par carte ou plaque, véhicule réservé à la date) se branche une fois l’analyse des lignes de transaction calibrée sur une facture réelle : utilisez « Texte extrait » pour vérifier ce que l’application lit dans la pièce jointe.</small>';
}

async function exLoadAlloc() {
  try { const j = await exGet(`/api/expenses/allocation?year=${EX_YEAR}`); ex.alloc = j; ex.allocErr = null;
    if (!ex.keyDirty) { ex.keyMode = j.key_mode; ex.keyPct = j.xc_pct; } } catch (e) { ex.allocErr = e.message; }
}
function expensesRulesBlocks() {
  return [{static: '<section class="block" data-bid="exp-rules"><div class="block-head"><h3>Imputation des frais généraux entre XC et CARS</h3></div><div class="block-body" id="exp-rules"><p class="na">Chargement…</p></div></section>'}];
}
const EX_NAMES = {general: 'Frais généraux', vehicle: 'Véhicules de service'};
function expensesSourceBlocks(kind = 'general') {
  return [{static: `<section class="block" data-bid="exp-src-${kind}"><div class="block-head"><h3>${EX_NAMES[kind]} : comptes retenus</h3></div><div class="block-body" id="exp-source" data-kind="${kind}"><p class="na">Chargement…</p></div></section>`}];
}
function expensesGeneralBlocks(kind = 'general') {
  return [{static: `<section class="block" data-bid="exp-gen-${kind}"><div class="block-head"><h3>${EX_NAMES[kind]} : résultat depuis le 1er janvier</h3></div><div class="block-body" id="exp-general" data-kind="${kind}"><p class="na">Chargement…</p></div></section>`}];
}

function exSums() {
  const s = {general: 0, vehicle: 0, aside: 0};
  (ex.src.accounts || []).forEach(a => { const k = ex.sel[a.code];
    if (k === 'partners') { (a.partners || []).forEach(p => { const pk = (ex.part[a.code] || {})[p.id]; s[pk === 'general' ? 'general' : pk === 'vehicle' ? 'vehicle' : 'aside'] += p.total; });
      s.aside += a.total - (a.partners || []).reduce((t, p) => t + p.total, 0); }
    else s[k === 'general' ? 'general' : k === 'vehicle' ? 'vehicle' : 'aside'] += a.total; });
  return s;
}
function exDrawSource() {
  const el = document.getElementById('exp-source'); if (!el) return;
  if (ex.err) { el.innerHTML = `<p class="neg">${esc(ex.err)}</p>`; return; }
  if (!ex.src) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  const kindMode = el.dataset.kind || 'general', s = {...ex.src}, canEdit = !!s.can_edit, sums = exSums(), el2 = s.elsewhere || {};
  if (kindMode === 'vehicle') s.accounts = s.accounts.filter(a => ex.sel[a.code] === 'vehicle' || (s.vehicle_prefixes || []).some(p => a.code.startsWith(p)));      // comptes 615 et comptes déjà rangés en véhicules
  const sel = a => `<select class="sdin" data-ex-code="${a.code}"${canEdit ? '' : ' disabled'}>${exKinds.map(([v, l]) => `<option value="${v}"${(ex.sel[a.code] || '') === v ? ' selected' : ''}>${l}</option>`).join('')}</select>`;
  const rows = s.accounts.map(a => `<tr><td>${esc(a.code)}</td><td class="prod">${esc(a.name)}${!s.saved && a.suggested ? ' <small class="na">(proposé)</small>' : ''}</td><td>${eur(a.total)}</td><td>${num(a.months)}</td><td>${eur(a.months ? a.total / a.months : 0)}</td><td>${sel(a)}</td></tr>`);
  const bar = `<div class="sdbar">${canEdit ? `<button type="button" class="primary" data-ex-save${ex.dirty ? '' : ' disabled'}>Enregistrer</button> <button type="button" data-ex-reload>Annuler les modifications</button>` : ''}
    <span class="na">${esc(ex.msg || (s.saved ? 'Dernier enregistrement : ' + new Date(s.updated_at).toLocaleString('fr-BE') + (s.updated_by ? ' par ' + s.updated_by : '') + '.' : 'Proposition de départ (comptes 611, 612, 614 et 64x), pas encore enregistrée.'))}</span></div>`;
  const psel = (code, p) => `<select class="sdin" data-ex-part="${code}" data-pid="${esc(p.id)}"${canEdit ? '' : ' disabled'}>${exPartKinds.map(([v, l]) => `<option value="${v}"${((ex.part[code] || {})[p.id] || '') === v ? ' selected' : ''}>${l}</option>`).join('')}</select>`;
  const byPartner = s.accounts.filter(a => ex.sel[a.code] === 'partners').map(a => {
    const list = a.partners || [], hasData = list.length > 0;
    return `<h4 class="sub">Fournisseurs du compte ${esc(a.code)} ${esc(a.name)}</h4>` + (hasData ? table(['Fournisseur', 'Depuis le 1er janvier', 'Rubrique'], list.map(p => `<tr><td class="prod">${esc(p.name)}</td><td>${eur(p.total)}</td><td>${psel(a.code, p)}</td></tr>`), 'prodtable sdtable')
      + '<small class="na">Seuls les fournisseurs rangés en « Frais généraux » ou « Véhicules de service » sont repris ; les autres (par exemple les honoraires d’indépendants, déjà dans STAFF costs) restent de côté.</small>' : '<p class="na">Aucune écriture sur ce compte.</p>');
  }).join('');
  el.innerHTML = bar
    + `<div class="kpis">${kpi('Frais généraux', eur(sums.general), '', 'comptes retenus, depuis le 1er janvier')}${kpi('Véhicules de service', eur(sums.vehicle), '', 'menu dédié Service Vehicles')}${kpi('Laissé de côté', eur(sums.aside), '', 'comptes non retenus')}</div>`
    + `<h4 class="sub">Comptes de charges ${EX_YEAR}</h4>` + (rows.length ? table(['Compte', 'Libellé', 'Depuis le 1er janvier', 'Mois', 'Moyenne / mois', 'Rubrique'], rows, 'prodtable sdtable') : '<p class="na">Aucun compte de charges candidat.</p>')
    + byPartner
    + `<h4 class="sub">Traité ailleurs (non repris ici)</h4>` + table(['Famille', 'Depuis le 1er janvier', 'Où'], [
        ['Achats, sous-traitance et frais directs par BU (comptes 60x)', el2.bu, 'Overview, XC Detail et CARS Detail'],
        ['Personnel (comptes 62x, rémunération et cotisations des administrateurs 618)', el2.staff, 'STAFF costs'],
        ['Marketing (comptes ' + (s.marketing_accounts || []).join(', ') + ')', el2.marketing, 'Marketing › Dépenses marketing']].filter(r => r[1] != null).map(r => `<tr><td class="prod">${esc(r[0])}</td><td>${eur(r[1])}</td><td>${esc(r[2])}</td></tr>`), 'prodtable')
    + '<small class="na">Choisissez, pour chaque compte de charges, s’il compte dans les frais généraux, dans les véhicules de service (menu Service Vehicles) ou s’il est laissé de côté. Les comptes « old » sont ignorés. Un compte qui mélange des natures différentes (par exemple un compte 640 qui contient aussi des taxes de véhicules) se range en entier dans une seule rubrique ; dites-le-moi si un compte doit être scindé.</small>';
}

// Détail d'un mois : mois choisi (par défaut le plus élevé) et ses plus grosses écritures, pour expliquer un pic.
function exMonthBlock(g, kind) {
  const sel = `<select class="sdin" data-ex-month data-kind="${kind}">${g.series.map(p => `<option value="${p.month}"${p.month === ex.monthSelK[kind] ? ' selected' : ''}>${exMonth(p.month)} ${p.month.slice(0, 4)} : ${eur(p.amount)}</option>`).join('')}</select>`;
  const m = ex.monthK[kind];
  const body = ex.monthErr ? `<p class="neg">${esc(ex.monthErr)}</p>` : !m ? '<p class="na">Chargement…</p>' : m.lines.length ? table(['Date', 'Pièce', 'Fournisseur', 'Compte', 'Libellé', 'Montant'], m.lines.map(l => `<tr><td>${fmtDate(l.date)}</td><td>${esc(l.move)}</td><td class="prod">${esc(l.partner)}</td><td>${esc(l.code)} <small class="na">${esc(l.name)}</small></td><td class="prod">${esc(l.label)}</td><td>${exEur2(l.amount)}</td></tr>`)
      .concat([`<tr class="tot"><td colspan="5">Total du mois (${num(m.count)} écritures, dont les ${num(m.lines.length)} plus grosses ci-dessus)</td><td>${exEur2(m.total)}</td></tr>`]), 'prodtable sdtable') : '<p class="na">Aucune écriture ce mois-ci.</p>';
  return `<h4 class="sub">Détail d’un mois ${sel}</h4>${body}`;
}
function exDrawGeneral() {
  const el = document.getElementById('exp-general'); if (!el) return;
  if (ex.genErr) { el.innerHTML = `<p class="neg">${esc(ex.genErr)}</p>`; return; }
  const kind = el.dataset.kind || 'general', name = EX_NAMES[kind], g = ex.genK[kind]; if (!g) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (g.empty) { el.innerHTML = '<p class="na">Aucun compte retenu comme ' + name.toLowerCase() + ' : choisissez-les dans « Données source ».</p>'; return; }
  const pts = g.series.map(p => ({label: exMonth(p.month), avg: p.amount, orders: 0, month: p.month}));
  el.innerHTML = `<div class="kpis">${kpi(name + ' depuis le 1er janvier', eur(g.total), '', g.configured ? '' : 'proposition de départ (non enregistrée)')}${kpi('Moyenne mensuelle', eur(g.monthly_avg), '', `sur ${num(g.months)} mois`)}${kpi('Projeté sur 1 an', eur(g.projected), '', 'moyenne mensuelle × 12')}</div>`
    + '<h4 class="sub">Évolution mensuelle</h4>' + lineChart(pts, g.monthly_avg, name + ' par mois (€)', v => eur(Math.round(v)), p => `${p.month} : ${eur(p.avg)}`)
    + exMonthBlock(g, kind)
    + '<h4 class="sub">Par compte</h4>' + table(['Compte', 'Libellé', 'Depuis le 1er janvier', 'Part'], g.accounts.map(a => `<tr><td>${esc(a.code)}</td><td class="prod">${esc(a.name)}</td><td>${eur(a.total)}</td><td class="sharecell"><span class="sharebar" style="width:${Math.round(Math.max(0, a.share) * 100)}%"></span><span>${pct(a.share)}</span></td></tr>`)
        .concat([`<tr class="tot"><td></td><td>Total</td><td>${eur(g.total)}</td><td>100,0 %</td></tr>`]), 'prodtable')
    + '<h4 class="sub">Principaux fournisseurs</h4>' + (g.suppliers.length ? table(['Fournisseur', 'Depuis le 1er janvier', 'Part'], g.suppliers.map(s => `<tr><td class="prod">${esc(s.name)}</td><td>${eur(s.amount)}</td><td>${pct(s.share)}</td></tr>`), 'prodtable') : '<p class="na">Aucun fournisseur identifié sur ces écritures.</p>')
    + '<small class="na">Charges des comptes retenus dans « Données source » (débit net, depuis le 1er janvier ' + EX_YEAR + '). Les véhicules de service, le personnel, le marketing et les achats par BU sont traités dans leurs propres rubriques. La projection suppose des frais réguliers ; les charges annuelles (assurances…) la déforment en début d’année.</small>';
}

function exDrawRules() {
  const el = document.getElementById('exp-rules'); if (!el) return;
  if (ex.allocErr) { el.innerHTML = `<p class="neg">${esc(ex.allocErr)}</p>`; return; }
  const a = ex.alloc; if (!a) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  const mode = ex.keyMode || a.key_mode, canEdit = !!a.can_edit, pctXc = Math.min(100, Math.max(0, +ex.keyPct || 0));
  const shares = {revenue: a.shares.revenue, pct: {XC: pctXc / 100, CARS: 1 - pctXc / 100}};
  const amt = (m, g) => a.total * shares[m][g];
  const bar = `<div class="sdbar exkey"><button type="button" data-ex-key="revenue" class="${mode === 'revenue' ? 'primary' : ''}"${canEdit ? '' : ' disabled'}>Clé sur le CA, au prorata</button><button type="button" data-ex-key="pct" class="${mode === 'pct' ? 'primary' : ''}"${canEdit ? '' : ' disabled'}>Clé sur base d’un % encodé</button>
    ${canEdit ? `<button type="button" class="primary" data-ex-key-save${ex.keyDirty ? '' : ' disabled'}>Enregistrer</button>` : ''}<span class="na">${esc(ex.msg || (a.updated_at ? 'Dernier enregistrement : ' + new Date(a.updated_at).toLocaleString('fr-BE') + (a.updated_by ? ' par ' + a.updated_by : '') + '.' : 'Clé par défaut : prorata du CA.'))}</span></div>`;
  const cell = (m, g) => `<td class="${mode === m ? 'exactive' : ''}">${pct(shares[m][g])}</td><td class="${mode === m ? 'exactive' : ''}">${eur(amt(m, g))}</td>`;
  el.innerHTML = bar
    + (mode === 'pct' ? `<div class="sdgrid exkeyin"><label class="sdfield"><span>Part XC (%)</span><input class="sdin" type="number" step="1" min="0" max="100" data-ex-xcpct value="${esc(pctXc)}"${canEdit ? '' : ' disabled'}></label><label class="sdfield"><span>Part CARS (%)</span><input class="sdin" type="number" value="${esc(100 - pctXc)}" disabled></label></div>` : '')
    + `<div class="kpis">${kpi('Frais généraux depuis le 1er janvier', eur(a.total), '', a.configured ? 'comptes retenus dans « Données source »' : 'proposition de départ (non enregistrée)')}${kpi('Imputé à XC', eur(amt(mode, 'XC')), '', pct(shares[mode].XC))}${kpi('Imputé à CARS', eur(amt(mode, 'CARS')), '', pct(shares[mode].CARS))}</div>`
    + '<h4 class="sub">Les deux clés côte à côte</h4>' + table(['', 'Prorata du CA : part', 'Montant', '% encodé : part', 'Montant'], ['XC', 'CARS'].map(g => `<tr><td class="prod">${g === 'XC' ? 'XC' : 'CARS'} <small class="na">CA ${eur(a.ca[g])}</small></td>${cell('revenue', g)}${cell('pct', g)}</tr>`)
        .concat([`<tr class="tot"><td>Total</td><td>100,0 %</td><td>${eur(a.total)}</td><td>100,0 %</td><td>${eur(a.total)}</td></tr>`]), 'prodtable sdtable')
    + `<small class="na">Prorata du CA : part de chaque famille dans le chiffre d’affaires XC + CARS depuis le 1er janvier ${EX_YEAR} (hors « Others »). % encodé : la part XC saisie ici, CARS recevant le reste. La clé choisie est la colonne en évidence. Elle sert à imputer les frais généraux à XC et à CARS dans les analyses de rentabilité.</small>`;
}
document.addEventListener('input', e => {
  const el = e.target; if (!el.dataset || el.dataset.exXcpct === undefined || !ex.alloc) return;
  ex.keyPct = Math.min(100, Math.max(0, parseFloat(el.value) || 0)); ex.keyDirty = true; ex.msg = '';
  const keep = el.selectionStart; exDrawRules(); const n = document.querySelector('[data-ex-xcpct]'); if (n) { n.focus(); try { n.setSelectionRange(keep, keep); } catch {} }
});
document.addEventListener('change', async e => {
  const el = e.target;
  if (el.dataset && el.dataset.exMonth !== undefined) { await exLoadMonth(el.value, el.dataset.kind || 'general'); exDrawGeneral(); return; }
  if (el.dataset && el.dataset.exPart !== undefined && ex.src) {
    const code = el.dataset.exPart, m = ex.part[code] || (ex.part[code] = {});
    if (el.value) m[el.dataset.pid] = el.value; else delete m[el.dataset.pid];
    ex.dirty = true; ex.msg = ''; exDrawSource(); return;
  }
  if (!el.dataset || el.dataset.exCode === undefined || !ex.src) return;
  if (el.value) ex.sel[el.dataset.exCode] = el.value; else delete ex.sel[el.dataset.exCode];
  ex.dirty = true; ex.msg = ''; exDrawSource();
});
document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.exAtt !== undefined) {
    const box = document.getElementById('exp-att'); if (!box) return; box.innerHTML = '<p class="na">Lecture de la pièce jointe…</p>';
    try { const j = await exGet(`/api/fuel/attachment?att=${t.dataset.exAtt}&year=${EX_YEAR}`);
      box.innerHTML = `<h4 class="sub">${esc(j.name)} : ${num(j.chars)} caractères lus, ${num(j.candidate_lines.length)} lignes avec date et montant</h4>` + (j.chars ? `<pre class="exatt">${esc(j.text.slice(0, 6000))}</pre>` : '<p class="na">Aucun texte lisible (PDF scanné ou format non reconnu).</p>');
    } catch (err) { box.innerHTML = `<p class="neg">${esc(err.message)}</p>`; }
    return;
  }
  if (t.dataset.exKey !== undefined && ex.alloc) { ex.keyMode = t.dataset.exKey; ex.keyDirty = true; ex.msg = ''; exDrawRules(); return; }
  if (t.dataset.exKeySave !== undefined) {
    ex.msg = 'Enregistrement…'; exDrawRules();
    try {
      const r = await fetch('/api/expenses/key', {method: 'PUT', headers: {'Content-Type': 'application/json', ...exAuth()}, body: JSON.stringify({key_mode: ex.keyMode, xc_pct: +ex.keyPct || 0, base: ex.alloc.updated_at})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      ex.keyDirty = false; await exLoadAlloc(); ex.msg = 'Enregistré.';
    } catch (err) { ex.msg = 'Échec de l’enregistrement : ' + err.message; }
    exDrawRules(); return;
  }
  if (t.dataset.exSave !== undefined) {
    ex.msg = 'Enregistrement…'; exDrawSource();
    try {
      const r = await fetch('/api/expenses/config', {method: 'PUT', headers: {'Content-Type': 'application/json', ...exAuth()}, body: JSON.stringify({data: {selected: ex.sel, partners: Object.fromEntries(Object.entries(ex.part).filter(([c]) => ex.sel[c] === 'partners'))}, base: ex.src.updated_at})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      ex.dirty = false; await exLoadSource(); ex.msg = 'Enregistré.'; ex.genK = {}; ex.monthK = {}; ex.monthSelK = {};
    } catch (err) { ex.msg = 'Échec de l’enregistrement : ' + err.message; }
    exDrawSource();
  }
  if (t.dataset.exReload !== undefined) { ex.dirty = false; ex.msg = ''; await exLoadSource(); exDrawSource(); }
});
window.addEventListener('beforeunload', e => { if (ex.dirty || ex.keyDirty) { e.preventDefault(); e.returnValue = ''; } });
