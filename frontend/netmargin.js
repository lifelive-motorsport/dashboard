// Marge nette = marge brute − personnel − frais véhicules − frais généraux, par BU, du 1er janvier à aujourd'hui.
// Assemble des données déjà calculées ailleurs : P&L (marge brute), personnel (coût réel à ce jour et % d'imputation par personne),
// frais véhicules (% retenus) et frais généraux (clé XC / CARS). Les frais communs (Shared Services, frais généraux, véhicules non liés à une BU)
// vont à XC ou CARS selon la clé d'imputation des frais généraux, puis aux BU de CARS au prorata de leur chiffre d'affaires.
const nm = {ready: false, loading: null, d: null, err: null, gen: null, alloc: null, withMgmt: (() => { try { return localStorage.getItem('lm_nm_mgmt') !== '0'; } catch { return true; } })(), withShared: (() => { try { return localStorage.getItem('lm_nm_shared') !== '0'; } catch { return true; } })()};
const NM_BU = ['XC', 'MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'], NM_CARS = ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'];
const NM_LABEL = {XC: 'XC', MODERN_RALLY: 'Modern Rally', HISTORIC_RALLY: 'Historic Rally', HISTORIC_RACING: 'Historic Racing', CARS_OTHERS: 'CARS Others', UNASSIGNED: 'Non affecté', UNALLOC: 'Non imputé'};

async function nmEnsure() {
  if (nm.ready || nm.loading) return;
  nm.loading = (async () => {
    try {
      await Promise.all([
        sd.loaded ? 0 : sdLoad(),
        exGet(`/api/expenses/general?year=${EX_YEAR}&kind=general`).then(j => { nm.gen = j; }),
        exLoadAlloc(),
        exGet(`/api/expenses/marketing?year=${EX_YEAR}`).then(j => { nm.mk = j; }),
        exGet(`/api/pnl/unassigned?year=${EX_YEAR}`).then(j => { nm.una = j; }).catch(() => { nm.una = null; }),
        exGet(`/api/expenses/vehicles?year=${EX_YEAR}&scope=all615`).then(j => { ex.vsplit = j; }),
        exGet(`/api/vehicles/usage?year=${EX_YEAR}`).then(j => { ex.vusage = j; }).catch(() => { ex.vusage = null; }),
      ]);
      if (!sd.restricted && sd.doc) {
        await sdLoadAcc();
        await nmLoadInvoices();
      }
      nm.err = null; nm.ready = true;
    } catch (e) { nm.err = e.message; }
    nm.loading = null; nmRedraw();
  })();
}
const nmLoadInvoices = () => Promise.all(sd.doc.people.filter(p => p.kind === 'independant' && !sd.inv[p.id]).map(p => { sd.inv[p.id] = {list: []}; return sdLoadInvoices(p); }));
const nmRedraw = () => { document.querySelectorAll('.nm-host').forEach(h => { h.innerHTML = nmHtml(nm.d, h.dataset.scope); }); if (typeof pjRedraw === 'function') pjRedraw(); if (typeof homeRedraw === 'function') homeRedraw(); };

// Calcul : une colonne par BU (+ « Non affecté » du P&L et « Non imputé »), lignes de coûts séparées pour savoir d'où vient chaque euro.
function nmCompute(d) {
  const z = () => ({ca: 0, dc: 0, staff: 0, veh: 0, shared: 0, mgmt: 0, general: 0, vehgen: 0, mkt: 0}), cols = {};
  [...NM_BU, 'UNASSIGNED', 'UNALLOC'].forEach(k => { cols[k] = z(); });
  d.pnl.bus.forEach(b => { const c = cols[b.key] || (cols[b.key] = z()); c.ca += b.ca; c.dc += b.direct_costs; });
  // Personnel : coût réel à ce jour × % d'imputation de chaque personne ; Shared Services = frais communs ; le reste (< 100 %) = non imputé.
  let sharedStaff = 0, mgmtStaff = 0, mgmtOut = 0, sharedOut = 0, staffTotal = 0;
  const BU4 = NM_BU.slice(0, 4);
  sdViewRows(true).forEach(r => { staffTotal += r.annual; NM_BU.forEach(k => { if (r.a[k]) cols[k].staff += r.a[k]; }); cols.UNALLOC.staff += r.a.UNALLOCATED || 0;
    // Part Shared Services / Management : répartition propre à la personne sur les 4 BU si elle est renseignée (le solde est « non imputé »), sinon clé générale des frais communs.
    const cs = r.p.common_split || {}, used = BU4.reduce((t, k) => t + (+cs[k] || 0), 0), sh = nm.withShared ? (r.a.SHARED || 0) : 0, mg = nm.withMgmt ? (r.a.MANAGEMENT || 0) : 0;
    if (!nm.withMgmt) mgmtOut += r.a.MANAGEMENT || 0;
    if (!nm.withShared) sharedOut += r.a.SHARED || 0;
    if (used > 0) { BU4.forEach(k => { cols[k].shared += sh * (+cs[k] || 0) / 100; cols[k].mgmt += mg * (+cs[k] || 0) / 100; }); cols.UNALLOC.shared += sh * (100 - used) / 100; cols.UNALLOC.mgmt += mg * (100 - used) / 100; }
    else { sharedStaff += sh; mgmtStaff += mg; } });
  // Véhicules : % retenus par véhicule ; la part « frais généraux » est commune.
  const vt = exSplitTotals(ex.vsplit); NM_BU.forEach(k => { if (vt.tot[k]) cols[k].veh += vt.tot[k]; }); cols.UNALLOC.veh += vt.unalloc;
  const commons = {shared: sharedStaff, mgmt: mgmtStaff, general: nm.gen.total || 0, vehgen: vt.tot.GENERAL || 0, mkt: (nm.mk || {}).common || 0};
  const al = ex.alloc || nm.alloc, mode = ex.keyMode || al.key_mode, xcp = Math.min(100, Math.max(0, +ex.keyPct || 0)) / 100, sh = mode === 'pct' ? {XC: xcp, CARS: 1 - xcp} : ((al.shares || {}).revenue || {}), shXC = +sh.XC || 0, shCARS = +sh.CARS || 0, shT = shXC + shCARS;
  const carsCa = NM_CARS.reduce((t, k) => t + Math.max(0, cols[k].ca), 0);
  Object.entries(commons).forEach(([row, amt]) => {
    if (shT <= 0) { cols.UNALLOC[row] += amt; return; }            // pas de clé : on le dit plutôt que de le cacher
    cols.XC[row] += amt * shXC / shT;
    const cars = amt * shCARS / shT;
    NM_CARS.forEach(k => { cols[k][row] += carsCa > 0 ? cars * Math.max(0, cols[k].ca) / carsCa : cars / NM_CARS.length; });
  });
  return {cols, sources: {staff: staffTotal - mgmtOut - sharedOut, mgmtOut, sharedOut, general: commons.general, veh: vt.grand, mkt: commons.mkt}, shXC: shT ? shXC / shT : 0, shCARS: shT ? shCARS / shT : 0, mode};
}
const nmSum = (cols, keys) => keys.reduce((o, k) => { const c = cols[k] || {}; ['ca', 'dc', 'staff', 'veh', 'shared', 'mgmt', 'general', 'vehgen', 'mkt'].forEach(f => { o[f] = (o[f] || 0) + (c[f] || 0); }); return o; }, {});
const nmNet = o => (o.ca - o.dc) - o.staff - o.veh - o.shared - o.mgmt - o.general - o.vehgen - o.mkt;
const NM_ROWS = [['Chiffre d’affaires', o => o.ca, 'plain'], ['− Coûts directs', o => o.dc, 'plain'], ['= Marge brute', o => o.ca - o.dc, 'sub'],
  ['− Personnel imputé', o => o.staff, 'plain'], ['− Frais véhicules imputés', o => o.veh, 'plain'], ['− Quote-part Shared Services (personnel)', o => o.shared, 'plain'], ['− Quote-part Management', o => o.mgmt, 'plain'],
  ['− Quote-part frais généraux', o => o.general, 'plain'], ['− Quote-part véhicules non liés à une BU', o => o.vehgen, 'plain'], ['− Quote-part marketing commun', o => o.mkt, 'plain'], ['= Marge nette', nmNet, 'tot']];
// spec = [{label, keys}] ; `pctCa` ajoute la ligne « Marge nette / CA ».
function nmTable(res, spec) {
  const vals = spec.map(s => nmSum(res.cols, s.keys)), cell = (v0, kind) => { const v = Math.abs(v0) < 0.5 ? 0 : v0; return `<td class="${kind === 'tot' || kind === 'sub' ? cls(v) : ''}">${v ? eur(v) : '–'}</td>`; };
  return table([''].concat(spec.map(s => s.label)), NM_ROWS.map(([lab, f, kind]) => `<tr class="${kind === 'tot' ? 'tot' : kind === 'sub' ? 'subtot' : ''}"><td>${lab}</td>${vals.map(o => cell(f(o), kind)).join('')}</tr>`)
    .concat([`<tr><td>Marge nette / CA</td>${vals.map(o => `<td class="${cls(nmNet(o))}">${o.ca ? pct(nmNet(o) / o.ca) : '–'}</td>`).join('')}</tr>`]), 'prodtable nmtable');
}
const nmKpis = (o, label) => `<div class="kpis">${kpi('Marge brute ' + label, eur(o.ca - o.dc), cls(o.ca - o.dc)) + kpi('Coûts imputés', eur(o.staff + o.veh + o.shared + o.mgmt + o.general + o.vehgen + o.mkt), '', 'personnel, véhicules, frais généraux, marketing') + kpi('Marge nette ' + label, eur(nmNet(o)), cls(nmNet(o)), o.ca ? pct(nmNet(o) / o.ca) + ' du CA' : '') }</div>`;

// Contrôle : tout ce qui est comptabilisé comme coût de structure se retrouve dans les colonnes.
function nmControl(res) {
  const all = nmSum(res.cols, Object.keys(res.cols)), imputed = all.staff + all.veh + all.shared + all.mgmt + all.general + all.vehgen + all.mkt, src = res.sources.staff + res.sources.general + res.sources.veh + res.sources.mkt, gap = src - imputed;
  const un = res.cols.UNALLOC, unT = un.staff + un.veh + un.shared + un.mgmt + un.general + un.vehgen + un.mkt;
  const ok = c => `<span class="${c ? 'pos' : 'neg'}">${c ? '✔' : '⚠'}</span>`;
  return '<h4 class="sub">Contrôle : tous les coûts sont repris</h4>' + table(['Source', 'Montant', ''], [
    `<tr><td>Personnel : coût réel à ce jour (${[nm.withShared ? 'Shared Services' : '', nm.withMgmt ? 'Management' : ''].filter(Boolean).join(' et ') || 'sans Shared Services ni Management'}${nm.withShared || nm.withMgmt ? ' compris' : ''})</td><td>${eur(res.sources.staff)}</td><td></td></tr>`,
    res.sources.mgmtOut ? `<tr><td>Management : coût réel à ce jour, <b>exclu</b> de la marge nette (bouton ci-dessus)</td><td>${eur(res.sources.mgmtOut)}</td><td></td></tr>` : '',
    res.sources.sharedOut ? `<tr><td>Shared Services : coût réel à ce jour, <b>exclu</b> de la marge nette (bouton ci-dessus)</td><td>${eur(res.sources.sharedOut)}</td><td></td></tr>` : '',
    `<tr><td>Frais généraux (comptes retenus en « frais généraux »)</td><td>${eur(res.sources.general)}</td><td></td></tr>`,
    `<tr><td>Frais véhicules (classe 615 entière)</td><td>${eur(res.sources.veh)}</td><td></td></tr>`,
    `<tr><td>Marketing commun (comptes marketing sans BU)</td><td>${eur(res.sources.mkt)}</td><td></td></tr>`,
    `<tr class="tot"><td>Total des coûts sources</td><td>${eur(src)}</td><td></td></tr>`,
    `<tr><td>Total imputé dans le tableau</td><td>${eur(imputed)}</td><td>${ok(Math.abs(gap) < 0.5)} ${Math.abs(gap) < 0.5 ? 'rien ne manque' : 'écart : ' + eur(gap)}</td></tr>`,
    `<tr><td>dont « Non imputé » (pourcentages incomplets, clé absente)</td><td>${eur(unT)}</td><td>${ok(Math.abs(unT) < 0.5)} ${Math.abs(unT) < 0.5 ? 'tout est affecté' : 'à compléter dans « Imputation du personnel » ou « Imputation des frais véhicules »'}</td></tr>`], 'prodtable');
}
const nmNote = res => `<small class="na">Du 1er janvier à aujourd’hui. Marge brute = CA − coûts directs (comptes 602, 603, 604). Personnel : coût réel à ce jour (fiches de paie et honoraires) × pourcentage d’imputation de chaque personne. Véhicules : pourcentages retenus dans « Imputation des frais véhicules ». Frais communs (Shared Services, frais généraux, véhicules non liés à une BU et marketing commun) : répartis entre XC (${pct(res.shXC)}) et CARS (${pct(res.shCARS)}) selon la clé « ${res.mode === 'pct' ? '% encodé' : 'prorata du CA'} » des frais généraux, puis entre les BU de CARS au prorata de leur chiffre d’affaires. Le marketing rattaché à une BU (comptes 602019, 602059) est déjà dans les coûts directs ; seul le marketing commun (ex. 612050) est ajouté ici. Le loyer (comptes exclus) et l’amortissement des investissements marketing ne sont pas repris.</small>`;

// Comptes de la colonne « Non affecté » : à corriger dans Odoo (suffixe de BU) ou à rattacher à une BU.
function nmUnassigned(c) {
  if (!(c.UNASSIGNED.ca || c.UNASSIGNED.dc)) return '';
  const u = nm.una; if (!u || !u.accounts || !u.accounts.length) return '<small class="na">« Non affecté » : écritures des comptes 700, 602, 603 et 604 dont le suffixe ne correspond à aucune BU. Le détail des comptes n’est pas disponible pour le moment.</small>';
  return '<h4 class="sub">Comptes « Non affecté » : à rattacher à une BU</h4>' + table(['Compte', 'Libellé', 'Nature', 'Montant'], u.accounts.map(a => `<tr><td>${esc(a.code)}</td><td class="prod">${esc(a.name)}</td><td>${a.kind === 'revenue' ? 'Chiffre d’affaires' : 'Coûts directs'}</td><td>${eur(a.amount)}</td></tr>`)
    .concat([`<tr class="tot"><td></td><td>Chiffre d’affaires ${eur(u.revenue)} · coûts directs ${eur(u.costs)}</td><td></td><td>${eur(u.revenue - u.costs)}</td></tr>`]), 'prodtable')
    + '<small class="na">Le plan comptable encode la BU dans les trois derniers chiffres du compte (010-016, 019 : XC ; 020 : Modern Rally ; 030 : Historic Rally ; 040 : Historic Racing ; 050, 059 : CARS Others). Un compte avec un autre suffixe n’est rattaché à aucune BU : ni coûts de personnel, ni frais communs ne lui sont imputés, et son chiffre d’affaires manque à XC et CARS.</small>';
}
const nmSimulating = () => sd.canSave === false || (ex.vsplit || {}).can_save === false || (ex.alloc || {}).can_save === false;
const nmDirty = () => !!(sd.dirty || ex.splitDirty || ex.keyDirty);
// Bascule « avec / sans management » + mode simulation (hypothèses modifiées sans être enregistrées) avec retour aux valeurs de référence.
const nmAdj = () => typeof adjOn !== 'undefined' && adjOn;
// Rappel (lecture seule) de la marge brute de départ : MB comptable ou ajustée, avec ou sans variation de stock ; réglage dans Overview › Marge brute et XC / CARS Detail.
const nmBasisNote = () => `<small class="na">Marge brute de départ : <b>${nmAdj() ? 'MB ajustée' : 'MB comptable'}</b>, <b>${typeof stockOn !== 'undefined' && stockOn ? 'avec' : 'sans'} variation de stock</b>. Ces deux options se règlent dans <a href="#/overview/mb">Overview › Marge brute</a>.</small>`;
const nmControls = () => `<div class="sdbar nmbar"><span class="na">Management :</span><button type="button" data-nm-mgmt="1" class="${nm.withMgmt ? 'primary' : ''}">Avec le coût du management</button><button type="button" data-nm-mgmt="0" class="${nm.withMgmt ? '' : 'primary'}">Sans le coût du management</button></div><div class="sdbar nmbar"><span class="na">Shared Services :</span><button type="button" data-nm-shared="1" class="${nm.withShared ? 'primary' : ''}">Avec le coût des Shared Services</button><button type="button" data-nm-shared="0" class="${nm.withShared ? '' : 'primary'}">Sans le coût des Shared Services</button></div>`
  + (nmSimulating() ? `<div class="sdbar sim">${exSimBar('data-nm-restore', 'Vos hypothèses')}</div><small class="na">${nmDirty() ? 'Simulation en cours : ce tableau utilise vos hypothèses modifiées.' : 'Ce tableau utilise les valeurs de référence.'} Modifiez les imputations dans STAFF costs › Imputation du personnel, SERVICE VEHICLES › Imputation des frais véhicules et GENERAL EXPENSES › Imputation des frais généraux : le résultat se recalcule ici. L’export PDF reprend ce que vous voyez.</small>` : '');
document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.nmShared !== undefined) { nm.withShared = t.dataset.nmShared === '1'; try { localStorage.setItem('lm_nm_shared', nm.withShared ? '1' : '0'); } catch {} nmRedraw(); return; }
  if (t.dataset.nmMgmt !== undefined) { nm.withMgmt = t.dataset.nmMgmt === '1'; try { localStorage.setItem('lm_nm_mgmt', nm.withMgmt ? '1' : '0'); } catch {} nmRedraw(); return; }
  if (t.dataset.nmRestore !== undefined) {
    sd.dirty = false; sd.msg = ''; await sdLoad(); sd.inv = {}; if (!sd.restricted && sd.doc) await nmLoadInvoices();
    await exRestoreSplit(); await exRestoreKey(); nmRedraw(); sdDraw();
  }
});
// Hypothèses d'imputation : ce sur quoi repose le résultat, avec les valeurs en vigueur (référence ou simulation) et les points d'attention.
function nmAssumptions(res) {
  const c = res.cols, li = a => '<ul>' + a.filter(Boolean).map(x => `<li>${x}</li>`).join('') + '</ul>';
  const blk = (title, how, watch) => `<details class="nmhyp"><summary>${title}</summary><div><b>Méthode</b>${li(how)}<b>Points d’attention</b>${li(watch)}</div></details>`;
  const rows = sdViewRows(true), people = rows.filter(r => r.annual > 0), unalloc = people.filter(r => (r.a.UNALLOCATED || 0) > 1), withSplit = people.filter(r => Object.values(r.p.common_split || {}).some(v => v > 0)), inactive = people.filter(r => !r.p.active);
  const vrows = exSplitRows(ex.vsplit), saisi = vrows.filter(r => r.ret.src === 'saisi'), forced = vrows.filter(r => r.x.forced), fgVeh = vrows.reduce((t, r) => t + r.x.total * r.ret.p.GENERAL, 0);
  const gen = nm.gen || {}, mk = nm.mk || {}, un = c.UNASSIGNED, key = res.mode === 'pct' ? '% encodé' : 'prorata du CA';
  const adj = nmAdj();
  return '<h4 class="sub">Hypothèses d’imputation</h4><p class="na">Ce résultat repose sur les hypothèses ci-dessous. Elles sont modifiables dans STAFF costs, SERVICE VEHICLES et GENERAL EXPENSES' + (nmSimulating() ? ' (vos modifications sont une simulation)' : '') + '.</p>'
    + blk('Période et périmètre',
      ['Du 1er janvier à aujourd’hui, comptabilité Odoo (écritures comptabilisées). Les comptes dont le libellé commence par « old » sont ignorés.', 'Marge nette = marge brute − personnel − frais véhicules − frais généraux − marketing commun.', adj ? '<b>Les ajustements de marge brute sont activés</b> : la marge brute en tient compte.' : 'Marge brute comptable, sans ajustement (voir « Ajustements MB »).',
      typeof stockOn !== 'undefined' && stockOn ? '<b>Les variations de stock sont incluses</b> dans la marge brute de XC (voir XC Detail › Inventory).' : 'Variations de stock non incluses.'],
      ['Le résultat comptable de l’exercice contient aussi les amortissements, les comptes « old », les frais financiers et le loyer : voir « Éléments hors marge nette ».', 'Les montants sont à date : un mois en cours est partiel.'])
    + blk('Marge brute (CA et coûts directs)',
      ['Chaque compte 700 (CA) et 602, 603, 604 (coûts directs) est rattaché à une BU par ses trois derniers chiffres : 010-016 et 019 XC, 020 Modern Rally, 030 Historic Rally, 040 Historic Racing, 050 et 059 CARS Others.'],
      [`Les comptes sans BU reconnue (« Non affecté ») pèsent ${eur(un.ca)} de CA et ${eur(un.dc)} de coûts : ils ne reçoivent aucun coût de structure.`, 'Le marketing rattaché à une BU (602019, 602059) est déjà dans ses coûts directs.'])
    + blk('Personnel : part directe des BU',
      ['Coût réel à ce jour de chaque personne : fiches de paie (brut + cotisations patronales, primes et pécule compris), coûts récurrents, et honoraires facturés pour les indépendants (comptes 613, hors frais avancés).', 'Multiplié par le pourcentage d’imputation que vous avez saisi pour chaque personne sur XC, Modern Rally, Historic Rally et Historic Racing.'],
      [`${people.length} personnes comptées${inactive.length ? `, dont ${inactive.length} inactive${inactive.length > 1 ? 's' : ''} (sorties ou ponctuelles)` : ''}.`, unalloc.length ? `<b class="neg">${unalloc.length} personne${unalloc.length > 1 ? 's' : ''} ${unalloc.length > 1 ? 'ont' : 'a'} moins de 100 % imputés</b> : le solde est « non imputé » (${unalloc.map(r => esc(r.p.name)).join(', ')}).` : 'Toutes les personnes sont imputées à 100 %.', 'Le coût réel dépend des fiches saisies : un mois sans fiche n’est pas compté.', 'Le coût des BU de CARS Others est nul : le personnel ne s’impute pas sur cette BU.'])
    + blk('Shared Services et Management',
      ['Part du coût de chaque personne imputée à ces deux catégories (frais communs).', 'Si un découpage sur les 4 BU est saisi pour la personne, il s’applique directement ; sinon la part suit la clé générale des frais communs (voir plus bas).', 'Les boutons « avec / sans » permettent d’exclure l’une ou l’autre catégorie du résultat.'],
      [`Découpage propre à la personne pour ${withSplit.length} personne${withSplit.length > 1 ? 's' : ''} ; clé générale pour les autres.`, `Management : ${nm.withMgmt ? 'inclus' : '<b>exclu</b>'} ; Shared Services : ${nm.withShared ? 'inclus' : '<b>exclu</b>'}.`, 'Un découpage de moins de 100 % laisse un solde « non imputé ».'])
    + blk('Frais véhicules (classe 615)',
      ['Chaque compte est un véhicule et une nature (carburant, entretien, assurance…). Le coût de chaque véhicule est réparti sur les 4 BU et les frais généraux selon vos pourcentages retenus.', 'Sans saisie, la proposition indicative se base sur les jours de déplacement du véhicule dans les agendas Google (réservation ± quelques jours) ; Logistics est réparti au prorata des jours des BU.'],
      [`${saisi.length} ligne${saisi.length > 1 ? 's' : ''} saisie${saisi.length > 1 ? 's' : ''} sur ${vrows.length} ; les autres suivent la proposition indicative.`, `${eur(fgVeh)} de frais véhicules vont en frais généraux${forced.length ? ` (dont ${forced.map(r => esc(r.x.vehicle)).join(', ')} classé${forced.length > 1 ? 's' : ''} ainsi)` : ''}, répartis par la clé générale.`, 'Les véhicules sans réservation et les frais non liés à un véhicule précis (par exemple les véhicules loués) vont en frais généraux.', 'Les comptes « old » (renting BMW X5…) ne sont pas repris.'])
    + blk('Frais généraux',
      [`Comptes retenus en « frais généraux » dans GENERAL EXPENSES › Données source (loyers et charges, bureau, IT, assurances, divers, honoraires de l’expert-comptable et de l’IT…) : ${eur(gen.total || 0)} depuis le 1er janvier.`, 'Ils vont à XC ou CARS selon la clé choisie, puis aux BU de CARS au prorata de leur chiffre d’affaires.'],
      ['Le loyer (compte 611010, écritures non payées) est exclu.', 'Un compte non retenu dans « Données source » n’est pas dans le résultat : le contrôle ci-dessus compare le total aux sources.', 'Les comptes 616000 et 618300 (formation) ne sont pas proposés par défaut.'])
    + blk('Marketing commun',
      [`Comptes marketing sans BU dans leur numéro (ex. 612050) : ${eur(mk.common || 0)}.`, 'Répartis comme les autres frais communs.'],
      ['Les investissements marketing immobilisés (compte 240050) et leur amortissement ne sont pas repris.'])
    + blk('Clé de répartition des frais communs',
      [`XC contre CARS : clé « ${key} » (XC ${pct(res.shXC)}, CARS ${pct(res.shCARS)}).`, 'Prorata du CA : part de chaque famille dans le CA XC + CARS depuis le 1er janvier ; % encodé : la part XC saisie dans GENERAL EXPENSES › Imputation des frais généraux.', 'Puis, entre les BU de CARS : au prorata de leur chiffre d’affaires.'],
      ['Le prorata du CA favorise les BU qui facturent beaucoup, indépendamment du support qu’elles consomment.', 'Une clé en % par BU de CARS serait plus fine : elle n’existe pas encore.', 'Le CA de CARS Others (comptes 050, 059) compte dans la clé.'])
    + blk('Éléments hors marge nette',
      ['Amortissements (comptes 63), frais et produits financiers, comptes « old », loyer exclu, autres produits d’exploitation sans compte détaillé.'],
      ['Ils figurent dans le résultat comptable d’Odoo mais pas ici : la marge nette est avant amortissements et avant éléments financiers.', 'Voir le rapprochement avec le P&L d’Odoo pour les montants.']);
}
function nmHtml(d, scope) {
  if (!d) return '<p class="na">Chargement…</p>';
  if (sd.loaded && sd.restricted) return '<p class="na">La marge nette inclut les rémunérations : elle est réservée aux administrateurs du dashboard.</p>';
  if (nm.err) return `<p class="neg">${esc(nm.err)}</p>`;
  if (!nm.ready) return '<p class="na">Chargement des coûts (personnel, frais généraux, véhicules)…</p>';
  if (!ex.alloc) return `<p class="neg">Clé d’imputation des frais généraux indisponible${ex.allocErr ? ' : ' + esc(ex.allocErr) : ''}.</p>`;
  const res = nmCompute(d), c = res.cols, tot = nmSum(c, Object.keys(c)), xc = nmSum(c, ['XC']), cars = nmSum(c, NM_CARS);
  const carsCols = NM_CARS.filter(k => c[k].ca || c[k].dc || c[k].staff || c[k].veh).map(k => ({label: NM_LABEL[k], keys: [k]}));
  const ctl = nmControls();
  if (scope === 'xc') return ctl + nmKpis(xc, 'XC') + nmTable(res, [{label: 'XC', keys: ['XC']}]) + nmNote(res);
  if (scope === 'cars') return ctl + nmKpis(cars, 'CARS') + nmTable(res, [{label: 'CARS', keys: NM_CARS}].concat(carsCols)) + nmNote(res);
  if (scope === 'carsbu') { const items = carsCols.map(s => { const o = nmSum(c, s.keys); return {label: s.label, ca: o.ca, margin: nmNet(o)}; });
    return ctl + bars(items, 'margin', {sub: b => 'sur ' + eur(b.ca) + ' de CA · ' + (b.ca ? pct(b.margin / b.ca) : '–')}) + nmTable(res, carsCols.concat([{label: 'CARS', keys: NM_CARS}])) + nmNote(res); }
  const spec = [{label: 'XC', keys: ['XC']}, {label: 'CARS', keys: NM_CARS}];
  const na = c.UNASSIGNED.ca || c.UNASSIGNED.dc ? `<small class="na">Le total comprend les comptes « Non affecté » (${eur(c.UNASSIGNED.ca)} de CA, ${eur(c.UNASSIGNED.dc)} de coûts directs), détaillés ci-dessous.</small>` : '';
  const un = nmSum(c, ['UNALLOC']); if (Math.abs(un.staff + un.veh + un.shared + un.mgmt + un.general + un.vehgen + un.mkt) >= 0.5) spec.push({label: 'Non imputé', keys: ['UNALLOC']});      // masqué quand tout est imputé
  spec.push({label: 'Total', keys: Object.keys(c)});
  return ctl + nmBasisNote() + nmKpis(tot, '') + nmTable(res, spec) + na + nmUnassigned(c) + '<h4 class="sub">Marge nette par BU</h4>' + nmTable(res, [{label: 'XC', keys: ['XC']}].concat(carsCols)) + nmControl(res) + nmAssumptions(res) + nmNote(res);
}
const NM_BLOCK = (scope, title) => B('nm-' + scope, title, d => { nm.d = d; nmEnsure(); return `<div class="nm-host" data-scope="${scope}">${nmHtml(d, scope)}</div>`; }, true);
