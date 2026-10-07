// Marge nette = marge brute − personnel − frais véhicules − frais généraux, par BU, du 1er janvier à aujourd'hui.
// Assemble des données déjà calculées ailleurs : P&L (marge brute), personnel (coût réel à ce jour et % d'imputation par personne),
// frais véhicules (% retenus) et frais généraux (clé XC / CARS). Les frais communs (Shared Services, frais généraux, véhicules non liés à une BU)
// vont à XC ou CARS selon la clé d'imputation des frais généraux, puis aux BU de CARS au prorata de leur chiffre d'affaires.
const nm = {ready: false, loading: null, d: null, err: null, gen: null, alloc: null};
const NM_BU = ['XC', 'MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'], NM_CARS = ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'];
const NM_LABEL = {XC: 'XC', MODERN_RALLY: 'Modern Rally', HISTORIC_RALLY: 'Historic Rally', HISTORIC_RACING: 'Historic Racing', CARS_OTHERS: 'CARS Others', UNASSIGNED: 'Non affecté', UNALLOC: 'Non imputé'};

async function nmEnsure() {
  if (nm.ready || nm.loading) return;
  nm.loading = (async () => {
    try {
      await Promise.all([
        sd.loaded ? 0 : sdLoad(),
        exGet(`/api/expenses/general?year=${EX_YEAR}&kind=general`).then(j => { nm.gen = j; }),
        exGet(`/api/expenses/allocation?year=${EX_YEAR}`).then(j => { nm.alloc = j; }),
        exGet(`/api/expenses/vehicles?year=${EX_YEAR}&scope=all615`).then(j => { ex.vsplit = j; }),
        exGet(`/api/vehicles/usage?year=${EX_YEAR}`).then(j => { ex.vusage = j; }).catch(() => { ex.vusage = null; }),
      ]);
      if (!sd.restricted && sd.doc) {
        await sdLoadAcc();
        await Promise.all(sd.doc.people.filter(p => p.kind === 'independant' && !sd.inv[p.id]).map(p => { sd.inv[p.id] = {list: []}; return sdLoadInvoices(p); }));
      }
      nm.err = null; nm.ready = true;
    } catch (e) { nm.err = e.message; }
    nm.loading = null; nmRedraw();
  })();
}
const nmRedraw = () => document.querySelectorAll('.nm-host').forEach(h => { h.innerHTML = nmHtml(nm.d, h.dataset.scope); });

// Calcul : une colonne par BU (+ « Non affecté » du P&L et « Non imputé »), lignes de coûts séparées pour savoir d'où vient chaque euro.
function nmCompute(d) {
  const z = () => ({ca: 0, dc: 0, staff: 0, veh: 0, shared: 0, general: 0, vehgen: 0}), cols = {};
  [...NM_BU, 'UNASSIGNED', 'UNALLOC'].forEach(k => { cols[k] = z(); });
  d.pnl.bus.forEach(b => { const c = cols[b.key] || (cols[b.key] = z()); c.ca += b.ca; c.dc += b.direct_costs; });
  // Personnel : coût réel à ce jour × % d'imputation de chaque personne ; Shared Services = frais communs ; le reste (< 100 %) = non imputé.
  let sharedStaff = 0, staffTotal = 0;
  sdViewRows(true).forEach(r => { staffTotal += r.annual; NM_BU.forEach(k => { if (r.a[k]) cols[k].staff += r.a[k]; }); sharedStaff += r.a.SHARED || 0; cols.UNALLOC.staff += r.a.UNALLOCATED || 0; });
  // Véhicules : % retenus par véhicule ; la part « frais généraux » est commune.
  const vt = exSplitTotals(ex.vsplit); NM_BU.forEach(k => { if (vt.tot[k]) cols[k].veh += vt.tot[k]; }); cols.UNALLOC.veh += vt.unalloc;
  const commons = {shared: sharedStaff, general: nm.gen.total || 0, vehgen: vt.tot.GENERAL || 0};
  const sh = (nm.alloc.shares || {})[nm.alloc.key_mode] || {}, shXC = +sh.XC || 0, shCARS = +sh.CARS || 0, shT = shXC + shCARS;
  const carsCa = NM_CARS.reduce((t, k) => t + Math.max(0, cols[k].ca), 0);
  Object.entries(commons).forEach(([row, amt]) => {
    if (shT <= 0) { cols.UNALLOC[row] += amt; return; }            // pas de clé : on le dit plutôt que de le cacher
    cols.XC[row] += amt * shXC / shT;
    const cars = amt * shCARS / shT;
    NM_CARS.forEach(k => { cols[k][row] += carsCa > 0 ? cars * Math.max(0, cols[k].ca) / carsCa : cars / NM_CARS.length; });
  });
  return {cols, sources: {staff: staffTotal, general: commons.general, veh: vt.grand}, shXC: shT ? shXC / shT : 0, shCARS: shT ? shCARS / shT : 0, mode: nm.alloc.key_mode};
}
const nmSum = (cols, keys) => keys.reduce((o, k) => { const c = cols[k] || {}; Object.keys({ca: 0, dc: 0, staff: 0, veh: 0, shared: 0, general: 0, vehgen: 0}).forEach(f => { o[f] = (o[f] || 0) + (c[f] || 0); }); return o; }, {});
const nmNet = o => (o.ca - o.dc) - o.staff - o.veh - o.shared - o.general - o.vehgen;
const NM_ROWS = [['Chiffre d’affaires', o => o.ca, 'plain'], ['− Coûts directs', o => o.dc, 'plain'], ['= Marge brute', o => o.ca - o.dc, 'sub'],
  ['− Personnel imputé', o => o.staff, 'plain'], ['− Frais véhicules imputés', o => o.veh, 'plain'], ['− Quote-part Shared Services (personnel)', o => o.shared, 'plain'],
  ['− Quote-part frais généraux', o => o.general, 'plain'], ['− Quote-part véhicules non liés à une BU', o => o.vehgen, 'plain'], ['= Marge nette', nmNet, 'tot']];
// spec = [{label, keys}] ; `pctCa` ajoute la ligne « Marge nette / CA ».
function nmTable(res, spec) {
  const vals = spec.map(s => nmSum(res.cols, s.keys)), cell = (v, kind) => `<td class="${kind === 'tot' || kind === 'sub' ? cls(v) : ''}">${v ? eur(v) : '–'}</td>`;
  return table([''].concat(spec.map(s => s.label)), NM_ROWS.map(([lab, f, kind]) => `<tr class="${kind === 'tot' ? 'tot' : kind === 'sub' ? 'subtot' : ''}"><td>${lab}</td>${vals.map(o => cell(f(o), kind)).join('')}</tr>`)
    .concat([`<tr><td>Marge nette / CA</td>${vals.map(o => `<td class="${cls(nmNet(o))}">${o.ca ? pct(nmNet(o) / o.ca) : '–'}</td>`).join('')}</tr>`]), 'prodtable nmtable');
}
const nmKpis = (o, label) => `<div class="kpis">${kpi('Marge brute ' + label, eur(o.ca - o.dc), cls(o.ca - o.dc)) + kpi('Coûts imputés', eur(o.staff + o.veh + o.shared + o.general + o.vehgen), '', 'personnel, véhicules, frais généraux') + kpi('Marge nette ' + label, eur(nmNet(o)), cls(nmNet(o)), o.ca ? pct(nmNet(o) / o.ca) + ' du CA' : '') }</div>`;

// Contrôle : tout ce qui est comptabilisé comme coût de structure se retrouve dans les colonnes.
function nmControl(res) {
  const all = nmSum(res.cols, Object.keys(res.cols)), imputed = all.staff + all.veh + all.shared + all.general + all.vehgen, src = res.sources.staff + res.sources.general + res.sources.veh, gap = src - imputed;
  const un = res.cols.UNALLOC, unT = un.staff + un.veh + un.shared + un.general + un.vehgen;
  const ok = c => `<span class="${c ? 'pos' : 'neg'}">${c ? '✔' : '⚠'}</span>`;
  return '<h4 class="sub">Contrôle : tous les coûts sont repris</h4>' + table(['Source', 'Montant', ''], [
    `<tr><td>Personnel : coût réel à ce jour (Shared Services compris)</td><td>${eur(res.sources.staff)}</td><td></td></tr>`,
    `<tr><td>Frais généraux (comptes retenus en « frais généraux »)</td><td>${eur(res.sources.general)}</td><td></td></tr>`,
    `<tr><td>Frais véhicules (classe 615 entière)</td><td>${eur(res.sources.veh)}</td><td></td></tr>`,
    `<tr class="tot"><td>Total des coûts sources</td><td>${eur(src)}</td><td></td></tr>`,
    `<tr><td>Total imputé dans le tableau</td><td>${eur(imputed)}</td><td>${ok(Math.abs(gap) < 0.5)} ${Math.abs(gap) < 0.5 ? 'rien ne manque' : 'écart : ' + eur(gap)}</td></tr>`,
    `<tr><td>dont « Non imputé » (pourcentages incomplets, clé absente)</td><td>${eur(unT)}</td><td>${ok(Math.abs(unT) < 0.5)} ${Math.abs(unT) < 0.5 ? 'tout est affecté' : 'à compléter dans « Imputation du personnel » ou « Imputation des frais véhicules »'}</td></tr>`], 'prodtable');
}
const nmNote = res => `<small class="na">Du 1er janvier à aujourd’hui. Marge brute = CA − coûts directs (comptes 602, 603, 604). Personnel : coût réel à ce jour (fiches de paie et honoraires) × pourcentage d’imputation de chaque personne. Véhicules : pourcentages retenus dans « Imputation des frais véhicules ». Frais communs (Shared Services, frais généraux et véhicules non liés à une BU) : répartis entre XC (${pct(res.shXC)}) et CARS (${pct(res.shCARS)}) selon la clé « ${res.mode === 'pct' ? '% encodé' : 'prorata du CA'} » des frais généraux, puis entre les BU de CARS au prorata de leur chiffre d’affaires. Le loyer (comptes exclus) et le marketing ne sont pas repris.</small>`;

function nmHtml(d, scope) {
  if (!d) return '<p class="na">Chargement…</p>';
  if (sd.loaded && sd.restricted) return '<p class="na">La marge nette inclut les rémunérations : elle est réservée aux administrateurs du dashboard.</p>';
  if (nm.err) return `<p class="neg">${esc(nm.err)}</p>`;
  if (!nm.ready) return '<p class="na">Chargement des coûts (personnel, frais généraux, véhicules)…</p>';
  const res = nmCompute(d), c = res.cols, tot = nmSum(c, Object.keys(c)), xc = nmSum(c, ['XC']), cars = nmSum(c, NM_CARS);
  const carsCols = NM_CARS.filter(k => c[k].ca || c[k].dc || c[k].staff || c[k].veh).map(k => ({label: NM_LABEL[k], keys: [k]}));
  if (scope === 'xc') return nmKpis(xc, 'XC') + nmTable(res, [{label: 'XC', keys: ['XC']}]) + nmNote(res);
  if (scope === 'cars') return nmKpis(cars, 'CARS') + nmTable(res, [{label: 'CARS', keys: NM_CARS}].concat(carsCols)) + nmNote(res);
  if (scope === 'carsbu') { const items = carsCols.map(s => { const o = nmSum(c, s.keys); return {label: s.label, ca: o.ca, margin: nmNet(o)}; });
    return bars(items, 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + (b.ca ? pct(b.margin / b.ca) : '–')}) + nmTable(res, carsCols.concat([{label: 'CARS', keys: NM_CARS}])) + nmNote(res); }
  const spec = [{label: 'XC', keys: ['XC']}, {label: 'CARS', keys: NM_CARS}];
  if (c.UNASSIGNED.ca || c.UNASSIGNED.dc) spec.push({label: 'Non affecté', keys: ['UNASSIGNED']});
  spec.push({label: 'Non imputé', keys: ['UNALLOC']}, {label: 'Total', keys: Object.keys(c)});
  return nmKpis(tot, '') + nmTable(res, spec) + '<h4 class="sub">Détail des BU de CARS</h4>' + nmTable(res, carsCols) + nmControl(res) + nmNote(res);
}
const NM_BLOCK = (scope, title) => B('nm-' + scope, title, d => { nm.d = d; nmEnsure(); return `<div class="nm-host" data-scope="${scope}">${nmHtml(d, scope)}</div>`; }, true);
