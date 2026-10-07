// GENERAL EXPENSES › Données source (choix des comptes) et Général (résultat). Chargé avant app.js ; utilise ses fonctions (esc, eur, num, pct, kpi, table, lineChart) à l'appel.
const EX_YEAR = new Date().getFullYear();
let ex = {alloc: null, allocErr: null, keyMode: null, keyPct: 50, keyDirty: false, src: null, gen: null, err: null, genErr: null, sel: {}, part: {}, dirty: false, msg: ''};
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
async function exLoadMonth(m) {
  ex.monthSel = m; ex.month = null;
  try { ex.month = await exGet(`/api/expenses/month?month=${m}&kind=general`); ex.monthErr = null; } catch (e) { ex.monthErr = e.message; }
}
async function exLoadGeneral() {
  try { ex.gen = await exGet(`/api/expenses/general?year=${EX_YEAR}&kind=general`); ex.genErr = null;
    if (!ex.monthSel && ex.gen.series.length) { const top = ex.gen.series.slice().sort((a, b) => b.amount - a.amount)[0]; await exLoadMonth(top.month); } } catch (e) { ex.genErr = e.message; }
}

async function exLoadAlloc() {
  try { const j = await exGet(`/api/expenses/allocation?year=${EX_YEAR}`); ex.alloc = j; ex.allocErr = null;
    if (!ex.keyDirty) { ex.keyMode = j.key_mode; ex.keyPct = j.xc_pct; } } catch (e) { ex.allocErr = e.message; }
}
function expensesRulesBlocks() {
  return [{static: '<section class="block" data-bid="exp-rules"><div class="block-head"><h3>Imputation des frais généraux entre XC et CARS</h3></div><div class="block-body" id="exp-rules"><p class="na">Chargement…</p></div></section>'}];
}
function expensesViewBlocks(view) {
  const t = view === 'xc' ? 'Frais généraux imputés à XC' : 'Frais généraux imputés à CARS';
  return [{static: `<section class="block" data-bid="exp-view-${view}"><div class="block-head"><h3>${t}</h3></div><div class="block-body" id="exp-view" data-view="${view}"><p class="na">Chargement…</p></div></section>`}];
}
function expensesSourceBlocks() {
  return [{static: '<section class="block" data-bid="exp-src"><div class="block-head"><h3>Frais généraux : comptes retenus</h3></div><div class="block-body" id="exp-source"><p class="na">Chargement…</p></div></section>'}];
}
function expensesGeneralBlocks() {
  return [{static: '<section class="block" data-bid="exp-gen"><div class="block-head"><h3>Frais généraux : résultat depuis le 1er janvier</h3></div><div class="block-body" id="exp-general"><p class="na">Chargement…</p></div></section>'}];
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
  const s = ex.src, canEdit = !!s.can_edit, sums = exSums(), el2 = s.elsewhere || {};
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
function exMonthBlock(g) {
  const sel = `<select class="sdin" data-ex-month>${g.series.map(p => `<option value="${p.month}"${p.month === ex.monthSel ? ' selected' : ''}>${exMonth(p.month)} ${p.month.slice(0, 4)} : ${eur(p.amount)}</option>`).join('')}</select>`;
  const m = ex.month;
  const body = ex.monthErr ? `<p class="neg">${esc(ex.monthErr)}</p>` : !m ? '<p class="na">Chargement…</p>' : m.lines.length ? table(['Date', 'Pièce', 'Fournisseur', 'Compte', 'Libellé', 'Montant'], m.lines.map(l => `<tr><td>${fmtDate(l.date)}</td><td>${esc(l.move)}</td><td class="prod">${esc(l.partner)}</td><td>${esc(l.code)} <small class="na">${esc(l.name)}</small></td><td class="prod">${esc(l.label)}</td><td>${exEur2(l.amount)}</td></tr>`)
      .concat([`<tr class="tot"><td colspan="5">Total du mois (${num(m.count)} écritures, dont les ${num(m.lines.length)} plus grosses ci-dessus)</td><td>${exEur2(m.total)}</td></tr>`]), 'prodtable sdtable') : '<p class="na">Aucune écriture ce mois-ci.</p>';
  return `<h4 class="sub">Détail d’un mois ${sel}</h4>${body}`;
}
function exDrawGeneral() {
  const el = document.getElementById('exp-general'); if (!el) return;
  if (ex.genErr) { el.innerHTML = `<p class="neg">${esc(ex.genErr)}</p>`; return; }
  const g = ex.gen; if (!g) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (g.empty) { el.innerHTML = '<p class="na">Aucun compte retenu comme frais généraux : choisissez-les dans « Données source ».</p>'; return; }
  const pts = g.series.map(p => ({label: exMonth(p.month), avg: p.amount, orders: 0, month: p.month}));
  el.innerHTML = `<div class="kpis">${kpi('Frais généraux depuis le 1er janvier', eur(g.total), '', g.configured ? '' : 'proposition de départ (non enregistrée)')}${kpi('Moyenne mensuelle', eur(g.monthly_avg), '', `sur ${num(g.months)} mois`)}${kpi('Projeté sur 1 an', eur(g.projected), '', 'moyenne mensuelle × 12')}</div>`
    + '<h4 class="sub">Évolution mensuelle</h4>' + lineChart(pts, g.monthly_avg, 'Frais généraux par mois (€)', v => eur(Math.round(v)), p => `${p.month} : ${eur(p.avg)}`)
    + exMonthBlock(g)
    + '<h4 class="sub">Par compte</h4>' + table(['Compte', 'Libellé', 'Depuis le 1er janvier', 'Part'], g.accounts.map(a => `<tr><td>${esc(a.code)}</td><td class="prod">${esc(a.name)}</td><td>${eur(a.total)}</td><td class="sharecell"><span class="sharebar" style="width:${Math.round(Math.max(0, a.share) * 100)}%"></span><span>${pct(a.share)}</span></td></tr>`)
        .concat([`<tr class="tot"><td></td><td>Total</td><td>${eur(g.total)}</td><td>100,0 %</td></tr>`]), 'prodtable')
    + '<h4 class="sub">Principaux fournisseurs</h4>' + (g.suppliers.length ? table(['Fournisseur', 'Depuis le 1er janvier', 'Part'], g.suppliers.map(s => `<tr><td class="prod">${esc(s.name)}</td><td>${eur(s.amount)}</td><td>${pct(s.share)}</td></tr>`), 'prodtable') : '<p class="na">Aucun fournisseur identifié sur ces écritures.</p>')
    + '<small class="na">Charges des comptes retenus dans « Données source » (débit net, depuis le 1er janvier ' + EX_YEAR + '). Les véhicules de service, le personnel, le marketing et les achats par BU sont traités dans leurs propres rubriques. La projection suppose des frais réguliers ; les charges annuelles (assurances…) la déforment en début d’année.</small>';
}

const exShare = (a, mode, g) => (a.shares[mode] || {})[g] || 0;
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
    + `<small class="na">Prorata du CA : part de chaque famille dans le chiffre d’affaires XC + CARS depuis le 1er janvier ${EX_YEAR} (hors « Others »). % encodé : la part XC saisie ici, CARS recevant le reste. La clé choisie (colonne en évidence) s’applique aux pages XC et CARS de GENERAL EXPENSES ; elle est appliquée au total depuis le 1er janvier et à chaque mois de la même façon.</small>`;
}
function exDrawView() {
  const el = document.getElementById('exp-view'); if (!el) return;
  if (ex.allocErr) { el.innerHTML = `<p class="neg">${esc(ex.allocErr)}</p>`; return; }
  const a = ex.alloc; if (!a) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  const g = el.dataset.view === 'xc' ? 'XC' : 'CARS', mode = a.key_mode, share = a.shares[mode][g];
  if (a.empty) { el.innerHTML = '<p class="na">Aucun compte retenu comme frais généraux : voir « Données source ».</p>'; return; }
  const pts = a.series.map(p => ({label: exMonth(p.month), avg: p.amount * share, orders: 0, month: p.month}));
  el.innerHTML = `<div class="kpis">${kpi('Imputé depuis le 1er janvier', eur(a.total * share), '', pct(share) + ' des frais généraux')}${kpi('Moyenne mensuelle', eur(a.monthly_avg * share), '', `sur ${num(a.months)} mois`)}${kpi('Projeté sur 1 an', eur(a.projected * share), '', 'moyenne mensuelle × 12')}${kpi('Clé appliquée', mode === 'revenue' ? 'Prorata du CA' : '% encodé', '', mode === 'revenue' ? `CA ${g} ${eur(a.ca[g])}` : `${pct(share)} pour ${g}`)}</div>`
    + '<h4 class="sub">Évolution mensuelle</h4>' + lineChart(pts, a.monthly_avg * share, `Frais généraux imputés à ${g} par mois (€)`, v => eur(Math.round(v)), p => `${p.month} : ${eur(p.avg)}`)
    + '<h4 class="sub">Par compte</h4>' + table(['Compte', 'Libellé', 'Frais généraux', 'Imputé à ' + g], a.accounts.map(x => `<tr><td>${esc(x.code)}</td><td class="prod">${esc(x.name)}</td><td>${eur(x.total)}</td><td>${eur(x.total * share)}</td></tr>`)
        .concat([`<tr class="tot"><td></td><td>Total</td><td>${eur(a.total)}</td><td>${eur(a.total * share)}</td></tr>`]), 'prodtable')
    + '<small class="na">Le montant de chaque compte est multiplié par la part de ' + g + ' (clé choisie dans « Imputation des frais généraux »).</small>';
}

document.addEventListener('input', e => {
  const el = e.target; if (!el.dataset || el.dataset.exXcpct === undefined || !ex.alloc) return;
  ex.keyPct = Math.min(100, Math.max(0, parseFloat(el.value) || 0)); ex.keyDirty = true; ex.msg = '';
  const keep = el.selectionStart; exDrawRules(); const n = document.querySelector('[data-ex-xcpct]'); if (n) { n.focus(); try { n.setSelectionRange(keep, keep); } catch {} }
});
document.addEventListener('change', async e => {
  const el = e.target;
  if (el.dataset && el.dataset.exMonth !== undefined) { await exLoadMonth(el.value); exDrawGeneral(); return; }
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
      ex.dirty = false; await exLoadSource(); ex.msg = 'Enregistré.'; ex.gen = null;
    } catch (err) { ex.msg = 'Échec de l’enregistrement : ' + err.message; }
    exDrawSource();
  }
  if (t.dataset.exReload !== undefined) { ex.dirty = false; ex.msg = ''; await exLoadSource(); exDrawSource(); }
});
window.addEventListener('beforeunload', e => { if (ex.dirty || ex.keyDirty) { e.preventDefault(); e.returnValue = ''; } });
