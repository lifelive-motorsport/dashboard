// GENERAL EXPENSES › Données source (choix des comptes) et Général (résultat). Chargé avant app.js ; utilise ses fonctions (esc, eur, num, pct, kpi, table, lineChart) à l'appel.
const EX_YEAR = new Date().getFullYear();
let ex = {src: null, gen: null, err: null, genErr: null, sel: {}, dirty: false, msg: ''};
const exAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};
const exKinds = [['', 'Laisser de côté'], ['general', 'Frais généraux'], ['vehicle', 'Véhicules de service']];
const exMonth = m => { try { return new Date(m + '-15').toLocaleDateString('fr-BE', {month: 'short'}).replace('.', ''); } catch { return m; } };
const exEur2 = n => new Intl.NumberFormat('fr-BE', {style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2}).format(n || 0);

async function exGet(url) {
  const r = await fetch(url, {headers: exAuth()});
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Erreur ' + r.status);
  return r.json();
}
async function exLoadSource() {
  try { const j = await exGet(`/api/expenses/accounts?year=${EX_YEAR}`); ex.src = j; ex.err = null;
    if (!ex.dirty) ex.sel = Object.fromEntries(j.accounts.filter(a => a.kind).map(a => [a.code, a.kind])); }
  catch (e) { ex.err = e.message; }
}
async function exLoadGeneral() {
  try { ex.gen = await exGet(`/api/expenses/general?year=${EX_YEAR}&kind=general`); ex.genErr = null; } catch (e) { ex.genErr = e.message; }
}

function expensesSourceBlocks() {
  return [{static: '<section class="block" data-bid="exp-src"><div class="block-head"><h3>Frais généraux : comptes retenus</h3></div><div class="block-body" id="exp-source"><p class="na">Chargement…</p></div></section>'}];
}
function expensesGeneralBlocks() {
  return [{static: '<section class="block" data-bid="exp-gen"><div class="block-head"><h3>Frais généraux : résultat depuis le 1er janvier</h3></div><div class="block-body" id="exp-general"><p class="na">Chargement…</p></div></section>'}];
}

function exSums() {
  const s = {general: 0, vehicle: 0, aside: 0};
  (ex.src.accounts || []).forEach(a => { const k = ex.sel[a.code]; s[k === 'general' ? 'general' : k === 'vehicle' ? 'vehicle' : 'aside'] += a.total; });
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
    <span class="na">${esc(ex.msg || (s.saved ? 'Dernier enregistrement : ' + new Date(s.updated_at).toLocaleString('fr-BE') + (s.updated_by ? ' par ' + s.updated_by : '') + '.' : 'Proposition de départ (comptes 611, 612, 614 et 640), pas encore enregistrée.'))}</span></div>`;
  el.innerHTML = bar
    + `<div class="kpis">${kpi('Frais généraux', eur(sums.general), '', 'comptes retenus, depuis le 1er janvier')}${kpi('Véhicules de service', eur(sums.vehicle), '', 'menu dédié Service Vehicles')}${kpi('Laissé de côté', eur(sums.aside), '', 'comptes non retenus')}</div>`
    + `<h4 class="sub">Comptes de charges ${EX_YEAR}</h4>` + (rows.length ? table(['Compte', 'Libellé', 'Depuis le 1er janvier', 'Mois', 'Moyenne / mois', 'Rubrique'], rows, 'prodtable sdtable') : '<p class="na">Aucun compte de charges candidat.</p>')
    + `<h4 class="sub">Traité ailleurs (non repris ici)</h4>` + table(['Famille', 'Depuis le 1er janvier', 'Où'], [
        ['Achats, sous-traitance et frais directs par BU (comptes 60x)', el2.bu, 'Overview, XC Detail et CARS Detail'],
        ['Personnel (comptes 62x, rémunération et cotisations des administrateurs 618)', el2.staff, 'STAFF costs'],
        ['Marketing (comptes ' + (s.marketing_accounts || []).join(', ') + ')', el2.marketing, 'Marketing › Dépenses marketing']].filter(r => r[1] != null).map(r => `<tr><td class="prod">${esc(r[0])}</td><td>${eur(r[1])}</td><td>${esc(r[2])}</td></tr>`), 'prodtable')
    + '<small class="na">Choisissez, pour chaque compte de charges, s’il compte dans les frais généraux, dans les véhicules de service (menu Service Vehicles) ou s’il est laissé de côté. Les comptes « old » sont ignorés. Un compte qui mélange des natures différentes (par exemple un compte 640 qui contient aussi des taxes de véhicules) se range en entier dans une seule rubrique ; dites-le-moi si un compte doit être scindé.</small>';
}

function exDrawGeneral() {
  const el = document.getElementById('exp-general'); if (!el) return;
  if (ex.genErr) { el.innerHTML = `<p class="neg">${esc(ex.genErr)}</p>`; return; }
  const g = ex.gen; if (!g) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (g.empty) { el.innerHTML = '<p class="na">Aucun compte retenu comme frais généraux : choisissez-les dans « Données source ».</p>'; return; }
  const pts = g.series.map(p => ({label: exMonth(p.month), avg: p.amount, orders: 0, month: p.month}));
  el.innerHTML = `<div class="kpis">${kpi('Frais généraux depuis le 1er janvier', eur(g.total), '', g.configured ? '' : 'proposition de départ (non enregistrée)')}${kpi('Moyenne mensuelle', eur(g.monthly_avg), '', `sur ${num(g.months)} mois`)}${kpi('Projeté sur 1 an', eur(g.projected), '', 'moyenne mensuelle × 12')}</div>`
    + '<h4 class="sub">Évolution mensuelle</h4>' + lineChart(pts, g.monthly_avg, 'Frais généraux par mois (€)', v => eur(Math.round(v)), p => `${p.month} : ${eur(p.avg)}`)
    + '<h4 class="sub">Par compte</h4>' + table(['Compte', 'Libellé', 'Depuis le 1er janvier', 'Part'], g.accounts.map(a => `<tr><td>${esc(a.code)}</td><td class="prod">${esc(a.name)}</td><td>${eur(a.total)}</td><td class="sharecell"><span class="sharebar" style="width:${Math.round(Math.max(0, a.share) * 100)}%"></span><span>${pct(a.share)}</span></td></tr>`)
        .concat([`<tr class="tot"><td></td><td>Total</td><td>${eur(g.total)}</td><td>100,0 %</td></tr>`]), 'prodtable')
    + '<h4 class="sub">Principaux fournisseurs</h4>' + (g.suppliers.length ? table(['Fournisseur', 'Depuis le 1er janvier', 'Part'], g.suppliers.map(s => `<tr><td class="prod">${esc(s.name)}</td><td>${eur(s.amount)}</td><td>${pct(s.share)}</td></tr>`), 'prodtable') : '<p class="na">Aucun fournisseur identifié sur ces écritures.</p>')
    + '<small class="na">Charges des comptes retenus dans « Données source » (débit net, depuis le 1er janvier ' + EX_YEAR + '). Les véhicules de service, le personnel, le marketing et les achats par BU sont traités dans leurs propres rubriques. La projection suppose des frais réguliers ; les charges annuelles (assurances…) la déforment en début d’année.</small>';
}

document.addEventListener('change', e => {
  const el = e.target; if (!el.dataset || el.dataset.exCode === undefined || !ex.src) return;
  if (el.value) ex.sel[el.dataset.exCode] = el.value; else delete ex.sel[el.dataset.exCode];
  ex.dirty = true; ex.msg = ''; exDrawSource();
});
document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.exSave !== undefined) {
    ex.msg = 'Enregistrement…'; exDrawSource();
    try {
      const r = await fetch('/api/expenses/config', {method: 'PUT', headers: {'Content-Type': 'application/json', ...exAuth()}, body: JSON.stringify({data: {selected: ex.sel}, base: ex.src.updated_at})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      ex.dirty = false; await exLoadSource(); ex.msg = 'Enregistré.'; ex.gen = null;
    } catch (err) { ex.msg = 'Échec de l’enregistrement : ' + err.message; }
    exDrawSource();
  }
  if (t.dataset.exReload !== undefined) { ex.dirty = false; ex.msg = ''; await exLoadSource(); exDrawSource(); }
});
window.addEventListener('beforeunload', e => { if (ex.dirty) { e.preventDefault(); e.returnValue = ''; } });
