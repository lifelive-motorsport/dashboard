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
    if (!ex.monthSelK[kind] && g.all_months.length) await exLoadMonth(g.all_months[g.all_months.length - 1].month, kind); } catch (e) { ex.genErr = e.message; }
}

async function exLoadVehicles() {
  try { ex.veh = await exGet(`/api/expenses/vehicles?year=${EX_YEAR}`); ex.vehErr = null; } catch (e) { ex.vehErr = e.message; }
  try { ex.vusage = (await exGet(`/api/vehicles/usage?year=${EX_YEAR}`)); } catch (e) { ex.vusage = null; }
}
function vehiclesByBlocks() {
  return [{static: '<section class="block" data-bid="veh-by"><div class="block-head"><h3>Coût par véhicule de service</h3></div><div class="block-body" id="exp-vehicles"><p class="na">Chargement…</p></div></section>'}];
}
// Imputation du coût de chaque véhicule aux BU, au prorata de ses jours de déplacement dans les agendas (une réservation = une BU ; Logistics à part).
function exVehicleByBu(v) {
  const cal = ex.vusage; if (!cal || !cal.configured) return `<h4 class="sub">Imputation par BU</h4><p class="na">${esc((cal && cal.note) || 'Agenda indisponible : l’imputation par BU se base sur les réservations des véhicules.')}</p>`;
  if (cal.error) return `<h4 class="sub">Imputation par BU</h4><p class="neg">${esc(cal.error)}</p>`;
  const rows = v.vehicles.map(x => { const sh = exBuShares(exMatchUsage(cal.usage, x.vehicle)), has = Object.keys(sh).length; return {x, sh, has}; });
  const tot = k => rows.reduce((t, r) => t + (r.sh[k] ? r.x.total * r.sh[k] : 0), 0), nr = rows.reduce((t, r) => t + (r.has ? 0 : r.x.total), 0);
  return '<h4 class="sub">Imputation par BU (jours de déplacement de l’agenda)</h4>' + table(['Véhicule', 'Total'].concat(EX_BUS.map(b => b[1]), ['Sans réservation']),
    rows.map(r => `<tr><td class="prod">${esc(r.x.vehicle)}</td><td>${eur(r.x.total)}</td>${EX_BUS.map(([k]) => `<td>${r.sh[k] ? eur(r.x.total * r.sh[k]) : '–'}</td>`).join('')}<td>${r.has ? '–' : eur(r.x.total)}</td></tr>`)
      .concat([`<tr class="tot"><td>Total</td><td>${eur(v.total)}</td>${EX_BUS.map(([k]) => `<td>${eur(tot(k))}</td>`).join('')}<td>${eur(nr)}</td></tr>`]), 'prodtable')
    + exLinksEditor(v, cal)
    + `<small class="na">Le coût de chaque véhicule est réparti selon ses jours de déplacement (réservation ± ${cal.buffer_days} jours) dans l’agenda de chaque BU. « Sans réservation » : véhicule absent de l’agenda sur la période, ou dont le nom ne ressemble à aucune ressource. Logistics (transports, enlèvements) reste à répartir entre les BU.</small>`;
}
// Correspondance manuelle véhicule Odoo -> ressource de l'agenda, pour les noms que le rapprochement automatique ne reconnaît pas.
function exLinksEditor(v, cal) {
  const links = ex.links || v.links || {}, res = [...new Set((cal.usage || []).map(u => u.vehicle))].sort(), canEdit = !!v.can_edit && v.can_save !== false;
  const todo = v.vehicles.filter(x => x.vehicle !== '(non classé)').map(x => x.vehicle);
  const odooNames = todo.concat(Object.keys(links).filter(k => !todo.some(t => t.toLowerCase() === k.toLowerCase())));      // les véhicules fusionnés restent listés pour pouvoir défaire la fusion
  const GEN = new Set(['util', 'utilitaire', 'truck', 'semi', 'trailer', 'remorque', 'camion', 'vehicule']);
  const twin = n => { if (links[n]) return null; const t = exVTok(n).filter(w => w.length >= 4 && !GEN.has(w)); return todo.find(o => o !== n && exVTok(o).some(w => t.includes(w))) || null; };
  const rows = odooNames.map(n => ({vehicle: n})).map(x => { const auto = !links[x.vehicle] && exMatchUsage(cal.usage, x.vehicle), tw = !auto && twin(x.vehicle);
    return `<tr><td class="prod">${esc(x.vehicle)}</td><td>${canEdit ? `<input class="sdin" type="text" list="exp-res-names" data-ex-link="${esc(x.vehicle)}" value="${esc(links[x.vehicle] || '')}" placeholder="${esc(auto ? 'auto : ' + auto.vehicle : tw ? 'même véhicule que « ' + tw + ' » ?' : 'à associer')}">` : esc(links[x.vehicle] || (auto ? 'auto : ' + auto.vehicle : '–'))}</td></tr>`; });
  return '<h4 class="sub">Correspondance véhicule Odoo ↔ ressource de l’agenda</h4>' + `<datalist id="exp-res-names">${res.concat(todo).map(n => `<option value="${esc(n)}">`).join('')}</datalist>`
    + table(['Véhicule (compte 615)', 'Ressource de l’agenda'], rows, 'prodtable')
    + (canEdit ? `<div class="sdbar"><button type="button" class="primary" data-ex-links-save${ex.linksDirty ? '' : ' disabled'}>Enregistrer les correspondances</button><span class="na">${esc(ex.linksMsg || 'Laissez vide pour le rapprochement automatique par le nom ; choisissez une ressource quand il ne trouve pas. Pour deux comptes qui désignent le même véhicule, choisissez l’autre véhicule de la liste : leurs coûts sont additionnés.')}</span></div>` : '');
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
    + exVehicleByBu(v)
    + '<small class="na">Chaque compte de la classe 615 est un véhicule et une nature de dépense (libellé « Nature Util. Véhicule », par exemple « Carburant Util. CITAN »). Le carburant est à contrôler : voir la rubrique Carburant.</small>';
}

// Analyse des factures DKV : une requête par facture (mise en cache côté serveur), affichage progressif.
async function exParseDkv(redraw) {
  const f = ex.fuel; if (!f) return;
  const atts = f.invoices.map(i => (i.attachments.find(a => /pdf/i.test(a.mimetype + a.name)) || i.attachments[0])).filter(Boolean);
  ex.dkv = ex.dkv || {}; ex.dkvTodo = atts.length;
  for (const a of atts) {
    if (ex.dkv[a.id]) continue;
    try { ex.dkv[a.id] = await exGet(`/api/fuel/parse?att=${a.id}&year=${EX_YEAR}`); } catch (e) { ex.dkv[a.id] = {error: e.message, summary: {vehicles: []}, transactions: []}; }
    redraw();
  }
  ex.dkvTodo = 0; redraw();
}
async function exLoadFuel() {
  try { ex.fuel = await exGet(`/api/fuel?year=${EX_YEAR}`); ex.fuelErr = null; } catch (e) { ex.fuelErr = e.message; }
  try { ex.vfuel = await exGet(`/api/expenses/vehicles?year=${EX_YEAR}&scope=all615`); } catch (e) { ex.vfuel = null; }
}
function fuelBlocks() {
  return [{static: '<section class="block" data-bid="veh-fuel"><div class="block-head"><h3>Carburant : Odoo, factures de la carte carburant et agenda</h3></div><div class="block-body" id="exp-fuel"><p class="na">Chargement…</p></div></section>'}];
}
const EX_BUS = [['XC', 'XC'], ['MODERN_RALLY', 'Modern Rally'], ['HISTORIC_RALLY', 'Historic Rally'], ['HISTORIC_RACING', 'Historic Racing'], ['LOGISTICS', 'Logistics']];
const exLinks = () => (ex.veh || ex.vsplit || ex.vfuel || {}).links || {};
const EX_VSTOP = new Set(['sv', 'tr', 'llm', 'pkg', 'rent', 'to', 'hire', 'non', 'classe']);
const exVTok = n => exNorm(n).replace(/[^a-z0-9]+/g, ' ').split(' ').filter(t => t && !EX_VSTOP.has(t));
// Deux libellés désignent le même véhicule si tous les mots du plus court sont (début de) mots du plus long : « SPRINTER 1 » ≈ « (SV)-LLM-PKG-Van (Sprinter) #1 (1) ».
const exSameVeh = (a, b) => { let x = exVTok(a), y = exVTok(b); if (!x.length || !y.length) return false; if (x.length > y.length) [x, y] = [y, x];
  return x.every(t => y.some(w => w === t || (t.length >= 3 && w.startsWith(t)))); };
const exMatchUsage = (usage, veh) => { if (exNorm(veh) === '(non classe)') return undefined; const all = usage || [], lk = exLinks()[veh]; if (lk) { const f = all.find(u => u.vehicle === lk); if (f) return f; }
  const eq = all.filter(u => exNorm(u.vehicle) === exNorm(veh)); if (eq.length) return eq[0];
  const c = all.filter(u => exSameVeh(u.vehicle, veh)); if (c.length <= 1) return c[0];
  // Plusieurs ressources possibles (« TRUCK » : 3 camions) : on écarte celles que les autres véhicules Odoo identifient sans ambiguïté (« GOLD TRU. », « RALLY TRU. »).
  const peers = [...new Set([...((ex.veh || {}).vehicles || []), ...((ex.vfuel || {}).vehicles || []), ...((ex.vsplit || {}).vehicles || [])].map(v => v.vehicle))].filter(n => n && exNorm(n) !== exNorm(veh));
  const taken = new Set(); peers.forEach(n => { const m = all.filter(u => exSameVeh(u.vehicle, n)); if (m.length === 1) taken.add(m[0].vehicle); });
  let left = c.filter(u => !taken.has(u.vehicle));
  // Les ressources « (TO HIRE) … to rent » sont des véhicules à louer, pas des véhicules de service : dernier départage.
  if (left.length > 1) { const own = left.filter(u => !/\(to hire\)|to rent/i.test(u.vehicle)); if (own.length) left = own; }
  return left.length === 1 ? left[0] : undefined; };
// Liste dédoublonnée : les noms des agendas font foi ; un nom Odoo n'est ajouté que s'il ne correspond à aucun.
const exVehChoices = (odoo, cal) => { const out = [...new Set(cal)]; (odoo || []).forEach(n => { if (exLinks()[n]) return; if (!out.some(c => exNorm(c) === exNorm(n) || exSameVeh(c, n) && cal.filter(k => exSameVeh(k, n)).length === 1)) out.push(n); }); return out; };
// Part de chaque BU dans les jours de déplacement d'un véhicule (agenda) : {BU: part}, somme = 1 ; vide si le véhicule n'a aucune réservation.
const exBuShares = u => { if (!u || !u.away_days) return {}; const t = Object.values(u.away_by_bu || {}).reduce((a, b) => a + b, 0) || 1; return Object.fromEntries(Object.entries(u.away_by_bu).map(([k, v]) => [k, v / t])); };
const exNorm = t => String(t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const exPlate = p => String(p || '').replace(/[\s-]+/g, '').toUpperCase();
function exDkvSections(f, usage) {
  const parsed = Object.values(ex.dkv || {}).filter(x => !x.error);
  const done = parsed.length, total = f.invoices.filter(i => i.attachments.length).length;
  if (!total) return '';
  const head = `<h4 class="sub">4. Analyse des factures ${esc(f.supplier)} par plaque</h4>` + (done < total ? `<p class="na">Lecture des factures : ${done} sur ${total}…</p>` : '');
  const plates = {};
  parsed.forEach(x => (x.summary.vehicles || []).forEach(v => { const k = exPlate(v.vehicle), d = plates[k] || (plates[k] = {plate: k, litres: 0, fuel: 0, adblue: 0, toll: 0, other: 0, n: 0, km: []});
    d.litres += v.fuel_litres; d.fuel += v.fuel_ht; d.adblue += v.adblue_ht; d.toll += v.toll_ht; d.other += v.other_ht; d.n += v.n; d.km = d.km.concat(v.km || []); }));
  const list = Object.values(plates).sort((a, b) => b.fuel - a.fuel);
  if (!list.length) return head + '<p class="na">Aucune transaction lue dans les pièces jointes.</p>';
  const names = exVehChoices([...(ex.vfuel ? ex.vfuel.vehicles.map(v => v.vehicle) : [])].filter(x => x && x !== '(non classé)'), [...new Set([...usage.map(u => u.vehicle), ...Object.values(f.plates || {})])].filter(Boolean));
  const canEdit = !!f.can_edit, lab = p => (ex.plates || f.plates || {})[p] || '';
  const tot = k => list.reduce((t, d) => t + d[k], 0);
  const sec4 = head + `<datalist id="exp-veh-names">${names.map(n => `<option value="${esc(n)}">`).join('')}</datalist>` + table(['Plaque (ou carte)', 'Véhicule de service', 'Litres', 'Carburant HT', 'AdBlue HT', 'Péages HT', 'Frais HT', 'Transactions'],
      list.map(d => `<tr><td>${esc(d.plate)}</td><td><input class="sdin" list="exp-veh-names" data-ex-plate="${esc(d.plate)}" value="${esc(lab(d.plate))}" placeholder="à associer"${canEdit ? '' : ' disabled'}></td><td>${num(Math.round(d.litres))}</td><td>${exEur2(d.fuel)}</td><td>${exEur2(d.adblue)}</td><td>${exEur2(d.toll)}</td><td>${exEur2(d.other)}</td><td>${num(d.n)}</td></tr>`)
        .concat([`<tr class="tot"><td colspan="2">Total</td><td>${num(Math.round(tot('litres')))}</td><td>${exEur2(tot('fuel'))}</td><td>${exEur2(tot('adblue'))}</td><td>${exEur2(tot('toll'))}</td><td>${exEur2(tot('other'))}</td><td>${num(tot('n'))}</td></tr>`]), 'prodtable sdtable')
    + (canEdit ? `<div class="sdbar"><button type="button" class="primary" data-ex-plates-save${ex.platesDirty ? '' : ' disabled'}>Enregistrer les associations</button><span class="na">${esc(ex.platesMsg || 'Associez chaque plaque (ou carte) au véhicule de service correspondant : la liste propose les véhicules des comptes 615 et des agendas.')}</span></div>` : '')
    + '<small class="na">Lecture directe des PDF des factures (les montants en monnaie étrangère, les péages en détail et les lignes sans plaque sont écartés ou comptés à part). Chaque total de véhicule a été vérifié contre les totaux imprimés sur les factures.</small>';
  // 5. Contrôle croisé : DKV ↔ Odoo ↔ agenda, par véhicule associé
  const by = {};
  list.forEach(d => { const v = lab(d.plate); if (!v) return; (by[v] || (by[v] = {vehicle: v, fuel: 0, litres: 0, plates: []})); by[v].fuel += d.fuel; by[v].litres += d.litres; by[v].plates.push(d.plate); });
  const txAll = parsed.flatMap(x => x.transactions || []).filter(t => t.category === 'carburant');
  const rows5 = Object.values(by).sort((a, b) => b.fuel - a.fuel).map(v => {
    const odoo = (ex.vfuel ? ex.vfuel.vehicles : []).filter(o => o.types.Carburant && exResKey(usage, o.vehicle) === exResKey(usage, v.vehicle)).reduce((t, o) => t + o.types.Carburant, 0);
    const u = exMatchUsage(usage, v.vehicle), mine = txAll.filter(t => v.plates.includes(exPlate(t.vehicle)));
    const out = u ? mine.filter(t => !(u.away_ranges || []).some(r => t.date >= r.from && t.date <= r.to)) : [];
    return `<tr><td class="prod">${esc(v.vehicle)}<br><small class="na">${esc(v.plates.join(', '))}</small></td><td>${exEur2(v.fuel)}</td><td>${exEur2(odoo)}</td><td class="${Math.abs(v.fuel - odoo) > 50 ? 'neg' : ''}">${exEur2(v.fuel - odoo)}</td>
      <td>${u ? num(u.away_days) + ' j' : '<small class="na">pas dans l’agenda</small>'}</td><td>${u ? `${num(out.length)} / ${num(mine.length)}` : '–'}</td><td class="${out.length ? 'neg' : ''}">${u ? exEur2(out.reduce((t, x) => t + x.total_ht, 0)) : '–'}</td></tr>`; });
  const sec5 = '<h4 class="sub">5. Contrôle croisé : DKV, Odoo et agenda</h4>' + (rows5.length ? table(['Véhicule', 'Carburant DKV (HT)', 'Carburant Odoo (615)', 'Écart', 'Jours de déplacement (agenda)', 'Pleins hors déplacement', 'Montant hors déplacement'], rows5, 'prodtable')
    + '<small class="na">DKV : ce que les factures détaillent par plaque. Odoo : ce qui est imputé aux comptes « Carburant … » du véhicule. Écart en rouge au-delà de 50 €. « Pleins hors déplacement » : transactions un jour où le véhicule n’est réservé dans aucun agenda (ni la marge avant / après) : à vérifier (usage privé, véhicule non réservé, mauvaise imputation).</small>' : '<p class="na">Associez d’abord les plaques aux véhicules ci-dessus.</p>');
  // 6. Kilométrage saisi à la pompe et coût au km
  const rows6 = list.filter(d => d.km.length >= 2).map(d => { const k = d.km.slice().sort((a, b) => a.date < b.date ? -1 : 1), span = k[k.length - 1].km - k[0].km, days = k[k.length - 1].date;
    const ok = span > 0, litres = d.litres; return {d, span, n: k.length, from: k[0], to: k[k.length - 1], ok, litres}; });
  const sec6 = '<h4 class="sub">6. Kilométrage relevé à la pompe et coût au km (carburant)</h4>' + (rows6.length ? table(['Plaque', 'Relevés crédibles', 'Premier relevé', 'Dernier relevé', 'Km parcourus', 'Carburant HT', 'Litres', 'L / 100 km', 'Carburant par km'],
      rows6.map(r => `<tr><td>${esc(r.d.plate)} <small class="na">${esc(lab(r.d.plate))}</small></td><td>${num(r.n)}</td><td>${num(r.from.km)} km<br><small class="na">${fmtDate(r.from.date)}</small></td><td>${num(r.to.km)} km<br><small class="na">${fmtDate(r.to.date)}</small></td><td>${r.ok ? num(r.span) + ' km' : '–'}</td><td>${exEur2(r.d.fuel)}</td><td>${num(Math.round(r.litres))}</td><td>${r.ok ? num(Math.round(r.litres / r.span * 1000) / 10) : '–'}</td><td>${r.ok ? exEur2(r.d.fuel / r.span) : '–'}</td></tr>`), 'prodtable')
    + '<small class="na">Le kilométrage est saisi par le chauffeur au moment du plein : il est souvent vide ou faux (« 1 »). Seuls les relevés supérieurs à 100 km sont gardés. Les kilomètres parcourus = dernier relevé − premier relevé ; la consommation et le coût au km sont calculés sur la totalité des litres et du montant de la période, donc approximatifs. Une source fiable (Odoo Fleet, relevé mensuel) donnerait un vrai coût au km.</small>' : '<p class="na">Aucune plaque n’a au moins deux relevés de kilométrage crédibles.</p>');
  return sec4 + sec5;      // le kilométrage et le coût au km (sec6) sont mis de côté pour l'instant
}
// Identité d'un véhicule pour comparer deux libellés (nom Odoo ou nom d'agenda) : la ressource de l'agenda à laquelle il correspond, sinon son nom normalisé.
const exResKey = (usage, name) => { const u = exMatchUsage(usage, name); return u ? 'r:' + u.vehicle : 'n:' + exNorm(name); };
function exDrawFuel() {
  const el = document.getElementById('exp-fuel'); if (!el) return;
  if (ex.fuelErr) { el.innerHTML = `<p class="neg">${esc(ex.fuelErr)}</p>`; return; }
  const f = ex.fuel; if (!f) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  const cal = f.calendar || {}, usage = cal.usage || [];
  const match = veh => exMatchUsage(usage, veh);
  // 1. Carburant encodé dans Odoo, par véhicule, rapproché des jours de réservation de l'agenda
  const fuelBy = ex.vfuel ? ex.vfuel.vehicles.filter(v => v.types.Carburant).map(v => ({vehicle: v.vehicle, fuel: v.types.Carburant, u: match(v.vehicle)})) : [];
  const tfuel = fuelBy.reduce((t, x) => t + x.fuel, 0);
  const sec1 = '<h4 class="sub">1. Carburant tel qu’encodé dans Odoo (tous les comptes 615 « Carburant … », quelle que soit leur rubrique)</h4>' + (fuelBy.length ? table(['Véhicule', 'Carburant depuis le 1er janvier', 'Part', 'Jours de déplacement (agenda)', 'Carburant par jour de déplacement'].concat(EX_BUS.map(b => b[1])),
      fuelBy.sort((a, b) => b.fuel - a.fuel).map(x => `<tr><td class="prod">${esc(x.vehicle)}${x.u ? ` <small class="na">≈ ${esc(x.u.vehicle)}</small>` : ''}</td><td>${eur(x.fuel)}</td><td>${tfuel ? pct(x.fuel / tfuel) : '–'}</td><td>${x.u ? num(x.u.away_days) : '–'}</td><td>${x.u && x.u.away_days ? eur(x.fuel / x.u.away_days) : '–'}</td>${EX_BUS.map(([k]) => `<td>${exBuShares(x.u)[k] ? eur(x.fuel * exBuShares(x.u)[k]) : '–'}</td>`).join('')}</tr>`)
        .concat([`<tr class="tot"><td>Total</td><td>${eur(tfuel)}</td><td>100,0 %</td><td></td><td></td>${EX_BUS.map(([k]) => `<td>${eur(fuelBy.reduce((t, x) => t + x.fuel * (exBuShares(x.u)[k] || 0), 0))}</td>`).join('')}</tr>`]), 'prodtable')
      + '<small class="na">Rapprochement indicatif par ressemblance de nom entre le véhicule du compte et la ressource de l’agenda.</small>' : '<p class="na">Aucun compte 615 dont le libellé commence par « Carburant » n’a été trouvé (comptes du type « Carburant Util. CITAN »).</p>');
  // 2. Factures de la carte carburant
  const sumHt = f.invoices.reduce((t, i) => t + i.untaxed, 0), sum615 = f.invoices.reduce((t, i) => t + i.lines.reduce((u, l) => u + l.amount, 0), 0), sumOt = f.invoices.reduce((t, i) => t + (i.other || []).reduce((u, l) => u + l.amount, 0), 0);
  const sec2 = `<h4 class="sub">2. Factures ${esc(f.supplier)} ${EX_YEAR}</h4>` + (f.invoices.length ? table(['Date', 'Facture', 'HT', 'Imputé en 615', 'Imputé ailleurs', 'Écart', 'Imputation en 615 par véhicule', 'Pièce jointe', ''],
      f.invoices.map(i => { const im = i.lines.reduce((t, l) => t + l.amount, 0), ot = (i.other || []).reduce((t, l) => t + l.amount, 0), gap = Math.abs(i.untaxed - im - ot) > 1;
        return `<tr><td>${fmtDate(i.date)}</td><td>${esc(i.number)}${i.refund ? ' <small class="na">(avoir)</small>' : ''}<br><small class="na">${esc(i.ref)}</small></td><td>${exEur2(i.untaxed)}</td><td>${exEur2(im)}</td><td class="prod">${(i.other || []).map(l => `${esc(l.name)} : ${exEur2(l.amount)}`).join('<br>') || '–'}</td><td class="${gap ? 'neg' : ''}">${exEur2(i.untaxed - im - ot)}</td>
          <td class="prod">${i.lines.map(l => `${esc(l.name)} : ${exEur2(l.amount)}`).join('<br>') || '–'}</td><td>${i.attachments.length ? i.attachments.map(a => esc(a.name)).join('<br>') : '<small class="na">aucune</small>'}</td>
          <td>${i.attachments.length ? `<button type="button" data-ex-att="${i.attachments[0].id}">Texte extrait</button>` : ''}</td></tr>`; })
        .concat([`<tr class="tot"><td colspan="2">Total</td><td>${exEur2(sumHt)}</td><td>${exEur2(sum615)}</td><td>${exEur2(sumOt)}</td><td>${exEur2(sumHt - sum615 - sumOt)}</td><td colspan="3"></td></tr>`]), 'prodtable sdtable') + '<div id="exp-att"></div>'
      + '<small class="na">« Imputé en 615 » : lignes de la facture sur les comptes 615 (véhicule et nature). « Imputé ailleurs » : lignes sur les autres comptes de charges (par exemple frais des BU 602xxx). « Écart » : HT de la facture moins ces deux montants (TVA non déductible, lignes sur des comptes hors classe 6…).</small>' : '<p class="na">Aucune facture trouvée pour ce fournisseur (recherche par nom : variable FUEL_SUPPLIER_NAME).</p>');
  // 3. Agenda
  let sec3 = '<h4 class="sub">3. Réservations des véhicules dans l’agenda Google</h4>';
  if (!cal.configured) sec3 += `<p class="na">${esc(cal.note || 'Agenda non configuré.')}</p>`;
  else if (cal.error) sec3 += `<p class="neg">${esc(cal.error)}</p>`;
  else sec3 += (cal.calendars && cal.calendars.length ? `<small class="na">Agendas lus : ${cal.calendars.map(c => esc(c.label)).join(', ')}.</small>` : '') + (usage.length ? table(['Ressource (véhicule)', 'Réservations', 'Jours réservés', `Jours de déplacement (± ${cal.buffer_days} j)`].concat(EX_BUS.map(b => b[1]), ['Derniers événements']),
      usage.map(u => `<tr><td class="prod">${esc(u.vehicle)}</td><td>${num(u.events)}</td><td>${num(u.booked_days)}</td><td>${num(u.away_days)}</td>${EX_BUS.map(([k]) => `<td>${(u.away_by_bu || {})[k] ? num(u.away_by_bu[k]) : '–'}</td>`).join('')}<td class="prod"><small class="na">${u.list.slice(-3).map(e => esc(e.title) + ' (' + fmtDate(e.start) + (e.end !== e.start ? ' → ' + fmtDate(e.end) : '') + ')').join('<br>')}</small></td></tr>`), 'prodtable')
      + `<small class="na">Un véhicule est « en déplacement » de ${cal.buffer_days} jours avant à ${cal.buffer_days} jours après sa réservation : le carburant de ces jours se rattache à l’événement. </small>` : '<p class="na">Aucun événement avec une ressource véhicule trouvé sur la période.</p>');
  el.innerHTML = sec1 + sec2 + sec3 + exDkvSections(f, usage)
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
  const kindMode = el.dataset.kind || 'general', s = {...ex.src}, canEdit = !!s.can_edit && s.can_save !== false, sums = exSums(), el2 = s.elsewhere || {};
  if (kindMode === 'vehicle') s.accounts = s.accounts.filter(a => ex.sel[a.code] === 'vehicle' || (s.vehicle_prefixes || []).some(p => a.code.startsWith(p)));      // comptes 615 et comptes déjà rangés en véhicules
  const sel = a => `<select class="sdin" data-ex-code="${a.code}"${canEdit ? '' : ' disabled'}>${exKinds.map(([v, l]) => `<option value="${v}"${(ex.sel[a.code] || '') === v ? ' selected' : ''}>${l}</option>`).join('')}</select>`;
  const rows = s.accounts.map(a => `<tr><td>${esc(a.code)}</td><td class="prod">${esc(a.name)}${!s.saved && a.suggested ? ' <small class="na">(proposé)</small>' : ''}</td><td>${eur(a.total)}</td><td>${num(a.months)}</td><td>${eur((a.closed_total ?? a.total) / (s.months_elapsed || 1))}</td><td>${sel(a)}</td></tr>`);
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
    + `<h4 class="sub">Comptes de charges ${EX_YEAR}</h4>` + (rows.length ? table(['Compte', 'Libellé', 'Depuis le 1er janvier', 'Mois avec écritures', 'Moyenne / mois (lissée)', 'Rubrique'], rows, 'prodtable sdtable') : '<p class="na">Aucun compte de charges candidat.</p>')
    + byPartner
    + `<h4 class="sub">Traité ailleurs (non repris ici)</h4>` + table(['Famille', 'Depuis le 1er janvier', 'Où'], [
        ['Achats, sous-traitance et frais directs par BU (comptes 60x)', el2.bu, 'Overview, XC Detail et CARS Detail'],
        ['Personnel (comptes 62x, rémunération et cotisations des administrateurs 618)', el2.staff, 'STAFF costs'],
        ['Marketing (comptes ' + (s.marketing_accounts || []).join(', ') + ')', el2.marketing, 'Marketing › Dépenses marketing'],
        ['Loyer exclu (compte ' + (s.excluded_accounts || []).join(', ') + ')', el2.excluded, 'mentionné sous le graphique de la page Général']].filter(r => r[1] != null).map(r => `<tr><td class="prod">${esc(r[0])}</td><td>${eur(r[1])}</td><td>${esc(r[2])}</td></tr>`), 'prodtable')
    + '<small class="na">Choisissez, pour chaque compte de charges, s’il compte dans les frais généraux, dans les véhicules de service (menu Service Vehicles) ou s’il est laissé de côté. Les comptes « old » sont ignorés. Un compte qui mélange des natures différentes (par exemple un compte 640 qui contient aussi des taxes de véhicules) se range en entier dans une seule rubrique ; dites-le-moi si un compte doit être scindé.</small>';
}

// Remarque sous le graphique : comptes exclus des frais généraux (le loyer du bâtiment, mis gratuitement à disposition par les actionnaires).
function exOdNote(g) {
  const x = g.excluded; if (!x || x.error || !x.moves.length) return '';
  return `<div class="note"><b>Loyer du bâtiment exclu de ces chiffres : ${exEur2(x.total)}</b> <small class="na">(bâtiment mis gratuitement à disposition par les actionnaires)</small><ul>${x.moves.map(o => `<li>${fmtDate(o.date)} · ${esc(o.move)} · ${esc(o.code)} ${esc(o.name)} · ${esc(o.label)} : <b>${exEur2(o.amount)}</b></li>`).join('')}</ul>
    <small class="na">Écritures comptabilisées en charge mais qui ne correspondent à aucun paiement ; elles sont retirées de la courbe, des totaux et de la projection.</small></div>`;
}
// Détail d'un mois : mois choisi (par défaut le dernier, même en cours) et ses plus grosses écritures, pour expliquer un pic.
function exMonthBlock(g, kind) {
  const sel = `<select class="sdin" data-ex-month data-kind="${kind}">${g.all_months.map(p => `<option value="${p.month}"${p.month === ex.monthSelK[kind] ? ' selected' : ''}>${exMonth(p.month)} ${p.month.slice(0, 4)} : ${eur(p.amount)}</option>`).join('')}</select>`;
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
  el.innerHTML = `<div class="kpis">${kpi(name + ' depuis le 1er janvier', eur(g.total), '', g.configured ? '' : 'proposition de départ (non enregistrée)')}${kpi('Moyenne mensuelle', eur(g.monthly_avg), '', `mois clos : ${num(g.months)} (moyenne lissée)`)}${kpi('Projeté sur 1 an', eur(g.projected), '', 'moyenne mensuelle × 12')}</div>`
    + '<h4 class="sub">Évolution mensuelle</h4>' + lineChart(pts, g.monthly_avg, name + ' par mois (€)' + (g.last_closed ? ' · mois en cours non tracé (incomplet)' : ''), v => eur(Math.round(v)), p => `${p.month} : ${eur(p.avg)}`)
    + exOdNote(g)
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
    ${canEdit && a.can_save === false ? exSimBar('data-ex-restore-key') : canEdit ? `<button type="button" class="primary" data-ex-key-save${ex.keyDirty ? '' : ' disabled'}>Enregistrer</button>` : ''}<span class="na">${esc(ex.msg || (a.updated_at ? 'Dernier enregistrement : ' + new Date(a.updated_at).toLocaleString('fr-BE') + (a.updated_by ? ' par ' + a.updated_by : '') + '.' : 'Clé par défaut : prorata du CA.'))}</span></div>`;
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
  if (el.dataset && el.dataset.exPlate !== undefined && ex.fuel) {
    ex.plates = ex.plates || {...(ex.fuel.plates || {})}; const k = el.dataset.exPlate;
    if (el.value.trim()) ex.plates[k] = el.value.trim(); else delete ex.plates[k];
    ex.platesDirty = true; ex.platesMsg = ''; exDrawFuel(); return;
  }
  if (el.dataset && el.dataset.exLink !== undefined && ex.veh) {
    ex.links = ex.links || {...(ex.veh.links || {})}; const k = el.dataset.exLink;
    if (el.value.trim()) ex.links[k] = el.value.trim(); else delete ex.links[k];
    ex.linksDirty = true; ex.linksMsg = ''; exDrawVehicles(); return;
  }
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
  if (t.dataset.exPlatesSave !== undefined && ex.fuel) {
    ex.platesMsg = 'Enregistrement…'; exDrawFuel();
    try {
      const r = await fetch('/api/expenses/plates', {method: 'PUT', headers: {'Content-Type': 'application/json', ...exAuth()}, body: JSON.stringify({plates: ex.plates || ex.fuel.plates || {}, base: ex.fuel.plates_base})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      ex.fuel.plates = j.plates; ex.fuel.plates_base = j.updated_at; ex.plates = {...j.plates}; ex.platesDirty = false; ex.platesMsg = 'Enregistré.';
    } catch (err) { ex.platesMsg = 'Échec de l’enregistrement : ' + err.message; }
    exDrawFuel(); return;
  }
  if (t.dataset.exLinksSave !== undefined && ex.veh) {
    ex.linksMsg = 'Enregistrement…'; exDrawVehicles();
    try {
      const r = await fetch('/api/expenses/links', {method: 'PUT', headers: {'Content-Type': 'application/json', ...exAuth()}, body: JSON.stringify({links: ex.links || ex.veh.links || {}, base: ex.veh.links_base})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      ex.veh.links = j.links; ex.veh.links_base = j.updated_at; ex.links = {...j.links}; ex.linksDirty = false; ex.linksMsg = 'Enregistré.';
    } catch (err) { ex.linksMsg = 'Échec de l’enregistrement : ' + err.message; }
    exDrawVehicles(); return;
  }
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
window.addEventListener('beforeunload', e => { if (ex.dirty || ((ex.keyDirty || ex.splitDirty) && !exSim()) || ex.platesDirty || ex.linksDirty) { e.preventDefault(); e.returnValue = ''; } });

// ---- SERVICE VEHICLES › Imputation des frais véhicules : % indicatif (agendas) et % retenu (saisi) par véhicule, BU et frais généraux ----
const EX_SPLIT = [['XC', 'XC'], ['MODERN_RALLY', 'Modern Rally'], ['HISTORIC_RALLY', 'Historic Rally'], ['HISTORIC_RACING', 'Historic Racing'], ['GENERAL', 'Frais généraux']];
function splitBlocks() {
  return [{static: '<section class="block" data-bid="veh-split"><div class="block-head"><h3>Imputation des frais véhicules aux BU et aux frais généraux</h3></div><div class="block-body" id="exp-split"><p class="na">Chargement…</p></div></section>'}];
}
async function exLoadSplit() {
  try { ex.vsplit = await exGet(`/api/expenses/vehicles?year=${EX_YEAR}&scope=all615`); ex.splitErr = null; } catch (e) { ex.splitErr = e.message; }
  try { ex.vusage = await exGet(`/api/vehicles/usage?year=${EX_YEAR}`); } catch (e) { ex.vusage = null; }
}
// Proposition indicative : jours de déplacement de l'agenda par BU ; Logistics réparti au prorata ; sans réservation et frais non liés à un véhicule précis : frais généraux.
function exIndicative(x, cal) {
  const out = Object.fromEntries(EX_SPLIT.map(([k]) => [k, 0])), bus = EX_SPLIT.map(([k]) => k).filter(k => k !== 'GENERAL');
  const u = x.identified === false ? null : exMatchUsage((cal || {}).usage, x.vehicle), sh = exBuShares(u);
  if (!Object.keys(sh).length) { out.GENERAL = 1; return out; }
  // Logistics (transports, enlèvements) : réparti entre les 4 BU au prorata de leurs jours de déplacement sur ce véhicule, à défaut sur l'ensemble des véhicules.
  const own = bus.reduce((t, k) => t + (sh[k] || 0), 0), glob = Object.fromEntries(bus.map(k => [k, ((cal || {}).usage || []).reduce((t, y) => t + ((y.away_by_bu || {})[k] || 0), 0)])), gt = Object.values(glob).reduce((a, b) => a + b, 0);
  const lg = sh.LOGISTICS || 0;
  bus.forEach(k => { out[k] = (sh[k] || 0) + (own > 0 ? lg * (sh[k] || 0) / own : gt > 0 ? lg * glob[k] / gt : 0); });
  out.GENERAL = own > 0 || gt > 0 ? 0 : lg;
  const t = Object.values(out).reduce((a, b) => a + b, 0) || 1; Object.keys(out).forEach(k => out[k] /= t); return out;
}
// % retenu d'une ligne : ceux que vous avez saisis (case vide = 0) ; si rien n'est saisi, la proposition indicative.
function exRetained(x, ind) { const sv = (ex.split || (ex.vsplit || {}).split || {})[x.vehicle]; return sv && Object.keys(sv).length ? {src: 'saisi', p: Object.fromEntries(EX_SPLIT.map(([k]) => [k, (sv[k] || 0) / 100]))} : {src: 'indicatif', p: ind}; }
// Lignes de l'imputation des frais véhicules (indicatif, retenu, total saisi) : partagées avec le calcul de la marge nette.
// Simulation : un administrateur qui n'est pas propriétaire des hypothèses peut les modifier dans son navigateur, sans rien enregistrer.
const exSimBar = (attr, what = 'Vos modifications') => `<span class="chip bad">Simulation</span><span class="na">${what} ne sont pas enregistrées : elles disparaissent à la fermeture de la page. Les valeurs de référence sont celles de leur propriétaire.</span><button type="button" ${attr}>Restaurer les valeurs par défaut</button>`;
function exSplitRows(v) {
  const cal = ex.vusage && ex.vusage.configured && !ex.vusage.error ? ex.vusage : null;
  const gen = (ex.general || v.general_vehicles || []).map(n => n.toLowerCase());
  return v.vehicles.map(x0 => { const base = x0.identified !== false || !!x0.forced_general, forced = gen.includes(x0.vehicle.toLowerCase()), x = {...x0, base, identified: base && !forced, forced}; const ind = exIndicative(x, cal), ret = exRetained(x, ind); const sv = (ex.split || v.split || {})[x.vehicle] || {};
    const sum = EX_SPLIT.reduce((t, [k]) => t + (sv[k] || 0), 0); return {x, ind, ret, sv, sum}; });
}
// Total des frais véhicules par BU et frais généraux avec les % retenus ; `unalloc` = ce qu'une ligne saisie à moins de 100 % laisse sans imputation.
function exSplitTotals(v) {
  const rows = exSplitRows(v), tot = Object.fromEntries(EX_SPLIT.map(([k]) => [k, rows.reduce((t, r) => t + r.x.total * r.ret.p[k], 0)])), grand = rows.reduce((t, r) => t + r.x.total, 0);
  return {tot, grand, unalloc: grand - Object.values(tot).reduce((a, b) => a + b, 0)};
}
function exDrawSplit() {
  const el = document.getElementById('exp-split'); if (!el) return;
  if (ex.splitErr) { el.innerHTML = `<p class="neg">${esc(ex.splitErr)}</p>`; return; }
  const v = ex.vsplit; if (!v) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (v.empty) { el.innerHTML = '<p class="na">Aucun compte de la classe 615 : voir « Données source ».</p>'; return; }
  const cal = ex.vusage && ex.vusage.configured && !ex.vusage.error ? ex.vusage : null, canEdit = !!v.can_edit;
  const rowsAll = exSplitRows(v);
  const id = rowsAll.filter(r => r.x.identified !== false), other = rowsAll.filter(r => r.x.identified === false);
  // Doublons probables (deux comptes qui désignent sans doute le même véhicule) : fusion en un clic, la plus petite ligne rejoint la plus grosse.
  const GENW = new Set(['util', 'utilitaire', 'truck', 'semi', 'trailer', 'remorque', 'camion', 'vehicule']), linked = v.links || {}, ident = id.map(r => r.x), pairs = [];
  ident.forEach(x => { if (linked[x.vehicle]) return; const tk = exVTok(x.vehicle).filter(w => w.length >= 4 && !GENW.has(w)); const y = ident.find(o => o !== x && o.total >= x.total && !linked[o.vehicle] && exVTok(o.vehicle).some(w => tk.includes(w))); if (y && !pairs.some(p => p[0] === y.vehicle && p[1] === x.vehicle)) pairs.push([x.vehicle, y.vehicle]); });
  const twinBar = canEdit && v.can_save !== false && pairs.length ? `<div class="note nmtwin">${pairs.map(([a, b]) => `<span>Doublon probable : « ${esc(a)} » et « ${esc(b)} » sont peut-être le même véhicule. <button type="button" class="sdfill" data-ex-merge="${esc(a)}" data-into="${esc(b)}">Fusionner dans « ${esc(b)} »</button></span>`).join('<br>')}</div>` : '';
  const BUC = {XC: '#c8102e', MODERN_RALLY: '#2f80ed', HISTORIC_RALLY: '#27ae60', HISTORIC_RACING: '#f2994a', GENERAL: '#9aa0a6'};
  const ip = x => x ? Math.round(x * 100) + ' %' : '–';
  const cell = r => EX_SPLIT.map(([k]) => `<td class="sdind${r.ret.src === 'indicatif' ? ' on' : ''}" title="Proposition indicative">${ip(r.ind[k])}</td><td class="sdinp"><input class="sdin sdpct${r.sv[k] != null ? ' set' : ''}" type="text" inputmode="decimal" autocomplete="off" data-ex-split="${esc(r.x.vehicle)}" data-k="${k}" value="${r.sv[k] != null ? r.sv[k] : ''}"${canEdit ? '' : ' disabled'}></td>`).join('');
  const bar = r => `<span class="sdmini" title="Répartition retenue">${EX_SPLIT.map(([k]) => r.ret.p[k] > 0 ? `<i style="width:${(r.ret.p[k] * 100).toFixed(1)}%;background:${BUC[k]}"></i>` : '').join('')}</span>`;
  const row = r => { const bad = r.ret.src === 'saisi' && Math.abs(r.sum - 100) > 0.5, st = r.ret.src === 'saisi' ? (bad ? `<span class="chip bad">⚠ ${num(Math.round(r.sum * 10) / 10)} %</span>` : '<span class="chip ok">✔ 100 %</span>') : '<span class="chip">indicatif</span>';
    return `<tr><td class="prod sdname" title="${esc(r.x.vehicle + (r.x.merged && r.x.merged.length ? ' + ' + r.x.merged.join(', ') : ''))}">${esc(r.x.vehicle)}${r.x.merged && r.x.merged.length ? ' <small class="na">+' + r.x.merged.length + '</small>' : ''}</td><td class="sdcost">${eur(r.x.total)}</td>${cell(r)}<td class="sdtot">${st}${bar(r)}</td><td class="sdact">${canEdit && r.x.base ? `<button type="button" class="sdfill" data-ex-split-gen="${esc(r.x.vehicle)}" title="${r.x.forced ? 'C’est un véhicule : le ressortir des frais généraux' : 'Ce n’est pas un véhicule : classer en frais généraux'}">${r.x.forced ? 'Véh.' : 'FG'}</button>` : ''}${canEdit ? `<button type="button" class="sdfill" data-ex-split-fill="${esc(r.x.vehicle)}" title="Recopier la proposition indicative dans les cases">↤</button>` : ''}</td></tr>`; };
  const head = ['Véhicule', 'Coût'].map(h => `<th rowspan="2">${h}</th>`).join('') + EX_SPLIT.map(([k, l]) => `<th colspan="2" class="grp" style="border-bottom:3px solid ${BUC[k]}">${l}</th>`).join('') + '<th rowspan="2">Retenu</th><th rowspan="2"></th>';
  const sub = EX_SPLIT.map(() => '<th class="sdsub">Indic.</th><th class="sdsub">Retenu</th>').join('');
  const sect = t => `<tr class="grp"><td colspan="${EX_SPLIT.length * 2 + 4}"><strong>${t}</strong></td></tr>`;
  const tbl = twinBar + `<div class="table-wrap"><table class="prodtable sdtable sdsplit" style="width:100%;min-width:830px">${'<colgroup><col><col style="width:78px">' + EX_SPLIT.map(() => '<col style="width:38px"><col style="width:50px">').join('') + '<col style="width:98px"><col style="width:72px"></colgroup>'}<thead><tr>${head}</tr><tr>${sub}</tr></thead><tbody>${sect('Véhicules identifiés')}${id.map(row).join('')}${other.length ? sect('Frais non liés à un véhicule identifié') + other.map(row).join('') : ''}</tbody></table></div>`;
  // Résultat en € avec les % retenus (saisis, sinon indicatifs)
  const amt = r => Object.fromEntries(EX_SPLIT.map(([k]) => [k, r.x.total * r.ret.p[k]])), tot = Object.fromEntries(EX_SPLIT.map(([k]) => [k, rowsAll.reduce((t, r) => t + amt(r)[k], 0)])), grand = rowsAll.reduce((t, r) => t + r.x.total, 0);
  const res = table(['Véhicule', 'Coût'].concat(EX_SPLIT.map(b => b[1]), ['Source']),
    rowsAll.map(r => `<tr><td class="prod">${esc(r.x.vehicle)}</td><td>${eur(r.x.total)}</td>${EX_SPLIT.map(([k]) => `<td>${amt(r)[k] ? eur(amt(r)[k]) : '–'}</td>`).join('')}<td><small class="na">${r.ret.src}</small></td></tr>`)
      .concat([`<tr class="tot"><td>Total</td><td>${eur(grand)}</td>${EX_SPLIT.map(([k]) => `<td>${eur(tot[k])}</td>`).join('')}<td></td></tr>`, `<tr class="tot"><td>Part</td><td>100,0 %</td>${EX_SPLIT.map(([k]) => `<td>${grand ? pct(tot[k] / grand) : '–'}</td>`).join('')}<td></td></tr>`]), 'prodtable');
  const bad = rowsAll.filter(r => r.ret.src === 'saisi' && Math.abs(r.sum - 100) > 0.5);
  const rc = v.reconciliation, imputed = Object.values(tot).reduce((a, b) => a + b, 0), unalloc = grand - imputed;
  const ok = (c) => `<span class="${c ? 'pos' : 'neg'}">${c ? '✔' : '⚠'}</span>`, acc = l => l.map(a => `${esc(a.code)} ${esc(a.name)} (${eur(a.total)})`).join(', ');
  const control = rc ? '<h4 class="sub">Contrôle : tout ce qui est comptabilisé est imputé</h4>' + table(['Contrôle', 'Montant', ''], [
    `<tr><td>Total comptable de la classe 615 (Odoo, depuis le 1er janvier)</td><td>${eur(rc.total)}</td><td></td></tr>`,
    `<tr><td>− comptes « old » ignorés par convention${rc.old_accounts.length ? `<br><small class="na">${acc(rc.old_accounts)}</small>` : ''}</td><td>${eur(rc.old)}</td><td></td></tr>`,
    rc.other ? `<tr><td>− comptes 615 rangés ailleurs (exclus, personnel, marketing…)<br><small class="na">${acc(rc.other_accounts)}</small></td><td>${eur(rc.other)}</td><td></td></tr>` : '',
    `<tr><td>= repris dans ce tableau</td><td>${eur(rc.included)}</td><td>${ok(Math.abs(rc.gap) < 0.5)} ${Math.abs(rc.gap) < 0.5 ? 'aucun écart avec la comptabilité' : 'écart non repris : ' + eur(rc.gap)}</td></tr>`,
    `<tr><td>Imputé aux BU et aux frais généraux avec les % retenus</td><td>${eur(imputed)}</td><td>${ok(Math.abs(unalloc) < 0.5)} ${Math.abs(unalloc) < 0.5 ? 'tout est imputé' : 'non imputé : ' + eur(unalloc) + ' (une ligne saisie ne totalise pas 100 %)'}</td></tr>`,
    rc.also_general.length ? `<tr><td>Comptes 615 aussi retenus en frais généraux<br><small class="na">${acc(rc.also_general)}</small></td><td>${eur(rc.also_general.reduce((t, a) => t + a.total, 0))}</td><td>${ok(false)} risque de double comptage : à retirer de la rubrique « frais généraux » dans « Données source »</td></tr>` : ''].filter(Boolean), 'prodtable') : '';
  el.innerHTML = `<div class="kpis">${kpi('Frais véhicules depuis le 1er janvier', eur(grand), '', 'tous les comptes de la classe 615')}${kpi('Imputé aux BU', eur(grand - tot.GENERAL), '', 'avec les % retenus')}${kpi('Frais généraux', eur(tot.GENERAL))}</div>`
    + (cal ? '' : `<p class="na">Agenda indisponible : les propositions indicatives placent tout en frais généraux.</p>`)
    + control + tbl
    + (canEdit && v.can_save === false ? `<div class="sdbar sim">${exSimBar('data-ex-restore-split')}<button type="button" data-ex-split-fillall title="Recopier la proposition indicative dans toutes les lignes sans saisie">Reprendre l’indicatif partout</button></div>` : '') + (canEdit && v.can_save !== false ? `<div class="sdbar"><button type="button" class="primary" data-ex-split-save${ex.splitDirty ? '' : ' disabled'}>Enregistrer les pourcentages</button><button type="button" data-ex-split-fillall title="Recopier la proposition indicative dans toutes les lignes sans saisie">Reprendre l’indicatif partout</button><span class="${bad.length ? 'neg' : 'na'}">${esc(bad.length ? 'Total différent de 100 % : ' + bad.map(r => r.x.vehicle).join(', ') : (ex.splitMsg || 'Saisissez les % qui seront utilisés pour la marge nette ; une ligne sans saisie utilise la proposition indicative.'))}</span></div>` : '')
    + '<h4 class="sub">Résultat avec les pourcentages retenus</h4>' + res
    + `<small class="na">« Indicatif » : jours de déplacement du véhicule dans l’agenda de chaque BU (réservation ± ${cal ? cal.buffer_days : 3} jours). Les jours Logistics (transports, enlèvements) sont répartis entre les 4 BU au prorata de leurs jours de déplacement sur le véhicule (à défaut, sur l’ensemble des véhicules). Les véhicules sans réservation et les frais non liés à un véhicule précis (par exemple le carburant des véhicules loués) sont proposés en frais généraux. Dans une ligne que vous renseignez, une case vide compte pour 0 % et le total doit faire 100 %. Les montants couvrent tous les comptes de la classe 615, y compris ceux que vous auriez laissés de côté dans « Données source ».</small>`;
}
const exSplitFocus = () => { const a = document.activeElement, st = a && a.dataset && a.dataset.exSplit !== undefined ? {veh: a.dataset.exSplit, k: a.dataset.k, pos: a.selectionStart} : null;
  exDrawSplit(); if (!st) return; const n = [...document.querySelectorAll('[data-ex-split]')].find(i => i.dataset.exSplit === st.veh && i.dataset.k === st.k); if (n) { n.focus(); try { n.setSelectionRange(st.pos, st.pos); } catch {} } };
document.addEventListener('input', e => {
  const el = e.target; if (!el.dataset || el.dataset.exSplit === undefined || !ex.vsplit) return;
  ex.split = ex.split || JSON.parse(JSON.stringify(ex.vsplit.split || {})); const veh = el.dataset.exSplit, k = el.dataset.k, d = ex.split[veh] || (ex.split[veh] = {});
  const n = parseFloat(String(el.value).replace(',', '.')); if (el.value.trim() === '' || isNaN(n)) delete d[k]; else d[k] = Math.min(100, Math.max(0, n));
  if (!Object.keys(d).length) delete ex.split[veh];
  ex.splitDirty = true; ex.splitMsg = ''; exSplitFocus();
});
// Recopie la proposition indicative (arrondie à l'entier, total forcé à 100) dans une ligne.
function exFillSplit(veh) {
  const v = ex.vsplit, x = v.vehicles.find(y => y.vehicle === veh); if (!x) return; const cal = ex.vusage && ex.vusage.configured && !ex.vusage.error ? ex.vusage : null, ind = exIndicative(x, cal);
  const r = Object.fromEntries(EX_SPLIT.map(([k]) => [k, Math.round(ind[k] * 100)])), diff = 100 - Object.values(r).reduce((a, b) => a + b, 0), big = EX_SPLIT.map(([k]) => k).sort((a, b) => ind[b] - ind[a])[0];
  r[big] += diff; ex.split = ex.split || JSON.parse(JSON.stringify(v.split || {})); ex.split[veh] = Object.fromEntries(Object.entries(r).filter(([, n]) => n > 0)); ex.splitDirty = true; ex.splitMsg = '';
}
document.addEventListener('click', async e => {
  const mb = e.target.closest('button'); if (mb && mb.dataset.exMerge !== undefined && ex.vsplit) {
    ex.splitMsg = 'Fusion…'; exDrawSplit();
    try {
      const links = {...(ex.vsplit.links || {}), [mb.dataset.exMerge]: mb.dataset.into};
      const r = await fetch('/api/expenses/links', {method: 'PUT', headers: {'Content-Type': 'application/json', ...exAuth()}, body: JSON.stringify({links, base: ex.vsplit.links_base})});
      const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      ex.links = null; await exLoadSplit(); ex.splitMsg = 'Fusionné.';
    } catch (err) { ex.splitMsg = 'Échec de la fusion : ' + err.message; }
    exDrawSplit(); return;
  }
  const rb = e.target.closest('button'); if (rb && rb.dataset.exRestoreSplit !== undefined) { await exRestoreSplit(); return; } if (rb && rb.dataset.exRestoreKey !== undefined) { await exRestoreKey(); return; }
  const f = e.target.closest('button'); if (f && ex.vsplit && f.dataset.exSplitFill !== undefined) { exFillSplit(f.dataset.exSplitFill); exDrawSplit(); return; }
  if (f && ex.vsplit && f.dataset.exSplitGen !== undefined) { const n = f.dataset.exSplitGen, cur = (ex.general || ex.vsplit.general_vehicles || []).slice(), i = cur.findIndex(y => y.toLowerCase() === n.toLowerCase()); if (i >= 0) cur.splice(i, 1); else cur.push(n);
    ex.general = cur; if (ex.split && ex.split[n]) delete ex.split[n]; else if (!ex.split && (ex.vsplit.split || {})[n]) { ex.split = JSON.parse(JSON.stringify(ex.vsplit.split)); delete ex.split[n]; } ex.splitDirty = true; ex.splitMsg = ''; exDrawSplit(); return; }
  if (f && ex.vsplit && f.dataset.exSplitFillall !== undefined) { const cur = ex.split || ex.vsplit.split || {}; ex.vsplit.vehicles.forEach(x => { if (!cur[x.vehicle] || !Object.keys(cur[x.vehicle]).length) exFillSplit(x.vehicle); }); exDrawSplit(); return; }
});
document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t || t.dataset.exSplitSave === undefined || !ex.vsplit) return;
  ex.splitMsg = 'Enregistrement…'; exDrawSplit();
  try {
    const r = await fetch('/api/expenses/split', {method: 'PUT', headers: {'Content-Type': 'application/json', ...exAuth()}, body: JSON.stringify({split: ex.split || ex.vsplit.split || {}, general: ex.general || ex.vsplit.general_vehicles || [], base: ex.vsplit.links_base})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    ex.vsplit.split = j.split; ex.vsplit.general_vehicles = j.general_vehicles; ex.general = j.general_vehicles.slice(); ex.vsplit.links_base = j.updated_at; ex.split = JSON.parse(JSON.stringify(j.split)); ex.splitDirty = false; ex.splitMsg = 'Enregistré.';
  } catch (err) { ex.splitMsg = 'Échec de l’enregistrement : ' + err.message; }
  exDrawSplit();
});

// Retour aux valeurs de référence (celles enregistrées par leur propriétaire) : on jette les modifications locales et on relit le serveur.
async function exRestoreSplit() { ex.split = null; ex.general = null; ex.links = null; ex.splitDirty = false; ex.linksDirty = false; ex.splitMsg = ''; await exLoadSplit(); exDrawSplit(); }
async function exRestoreKey() { ex.keyDirty = false; ex.msg = ''; await exLoadAlloc(); exDrawRules(); }
const exSim = () => ((ex.vsplit || {}).can_save === false) || ((ex.alloc || {}).can_save === false);
