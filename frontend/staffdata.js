// STAFF costs › Données source (salariés, indépendants) et Imputation du personnel. Données sensibles : visibles et modifiables par les administrateurs seulement.
// Chargé après staffcalc.js et avant app.js ; utilise ses fonctions (esc, eur, num, pct, kpi, table, token…) au moment de l'appel.
const SD_YEAR = new Date().getFullYear();
let sd = {loaded: false, restricted: false, error: null, doc: null, base: null, canEdit: false, upload: false, dirty: false, msg: '',
          tab: 'salarie', sel: {salarie: null, independant: null}, acc: null, inv: {}, q: '', results: null};
const SD_KINDS = {vehicule: 'Véhicule', carte_essence: 'Carte essence', telephone: 'Abonnement téléphone', autre: 'Autre avantage'};
const SD_SHARES = [['XC', 'XC'], ['MODERN_RALLY', 'Modern Rally'], ['HISTORIC_RALLY', 'Historic Rally'], ['HISTORIC_RACING', 'Historic Racing'], ['SHARED', 'Shared Services']];
const sdAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};
const sdId = () => 'x' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const sdPeople = k => (sd.doc ? sd.doc.people.filter(p => p.kind === k) : []);
const sdPerson = id => sd.doc && sd.doc.people.find(p => p.id === id);
const sdNum = v => { const n = parseFloat(String(v).replace(',', '.')); return isFinite(n) ? n : 0; };
const sdEur2 = n => new Intl.NumberFormat('fr-BE', {style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2}).format(n || 0);
const sdMonthsElapsed = () => new Date().getMonth() + 1;
const sdPlural = (n, w) => `${n} ${w}${n > 1 ? 's' : ''}`;

async function sdLoad() {
  try {
    const r = await fetch('/api/staff', {headers: sdAuth()});
    if (!r.ok) throw new Error('Erreur ' + r.status);
    const j = await r.json();
    sd.loaded = true; sd.error = null; sd.restricted = !!j.restricted;
    if (!j.restricted && !sd.dirty) { sd.doc = j.data; sd.base = j.updated_at; sd.updatedBy = j.updated_by; sd.canEdit = !!j.can_edit; sd.upload = !!j.upload; }
  } catch (e) { sd.loaded = true; sd.error = e.message; }
}

async function sdSave() {
  sd.msg = 'Enregistrement…'; sdDraw();
  try {
    const r = await fetch('/api/staff', {method: 'PUT', headers: {'Content-Type': 'application/json', ...sdAuth()}, body: JSON.stringify({data: sd.doc, base: sd.base})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Données refusées (vérifiez les champs, ex. imputation ≤ 100 %).');
    sd.base = j.updated_at; sd.updatedBy = j.updated_by; sd.dirty = false; sd.msg = 'Enregistré.';
  } catch (e) { sd.msg = 'Échec de l’enregistrement : ' + e.message; }
  sdDraw();
}

const sdTouch = () => { sd.dirty = true; sd.msg = ''; const b = document.querySelector('[data-sd-save]'); if (b) b.disabled = false; };
window.addEventListener('beforeunload', e => { if (sd.dirty) { e.preventDefault(); e.returnValue = ''; } });

// ---- Pages -------------------------------------------------------------------------------------------------------
function staffSourceBlocks() {
  return [{static: '<section class="block" data-bid="staff-src"><div class="block-head"><h3>Données source du personnel</h3></div><div class="block-body" id="staff-source"><p class="na">Chargement…</p></div></section>'}];
}
function staffPeopleBlocks() {
  return [{static: '<section class="block" data-bid="staff-ppl"><div class="block-head"><h3>Imputation du personnel sur les BU et Shared Services</h3></div><div class="block-body" id="staff-people"><p class="na">Chargement…</p></div></section>'}];
}

function sdGate() {
  if (!sd.loaded) return '<p class="na">Chargement…</p>';
  if (sd.error) return `<p class="neg">${esc(sd.error)}</p>`;
  if (sd.restricted) return '<p class="na">Ces données (rémunérations, coûts par personne) sont réservées aux administrateurs du dashboard.</p>';
  return '';
}
const sdBar = () => `<div class="sdbar"><button type="button" class="primary" data-sd-save${sd.dirty ? '' : ' disabled'}>Enregistrer</button>
  <button type="button" data-sd-reload>Annuler les modifications</button>${sd.canEdit ? ' <label class="btn" title="Archive ZIP préparée pour le premier remplissage (staff.json + fiches PDF)">Importer (ZIP)<input type="file" accept=".zip,application/zip" data-sd-import hidden></label>' : ''}<span class="na">${esc(sd.msg || (sd.base ? 'Dernier enregistrement : ' + new Date(sd.base).toLocaleString('fr-BE') + (sd.updatedBy ? ' par ' + sd.updatedBy : '') + '.' : 'Rien d’enregistré pour le moment.'))}</span></div>`;

const sdIn = (field, val, o = {}) => `<input class="sdin" ${o.type === 'text' ? 'type="text"' : 'type="number" step="' + (o.step || '0.01') + '"'} data-f="${field}"${o.pid ? ` data-pid="${o.pid}"` : ''}${o.i != null ? ` data-i="${o.i}"` : ''}${o.sub ? ` data-sub="${o.sub}"` : ''} value="${esc(val ?? '')}"${sd.canEdit ? '' : ' disabled'}${o.ph ? ` placeholder="${esc(o.ph)}"` : ''}>`;
const sdField = (label, html, hint = '') => `<label class="sdfield"><span>${esc(label)}</span>${html}${hint ? `<small class="na">${esc(hint)}</small>` : ''}</label>`;

// Cotisations sociales d'un gérant (hors 620/621) : moyenne mensuelle comptabilisée en 618001 depuis le début de l'année.
function sdSocial(p) {
  const d = sd.acc && sd.acc.director; if (!d || p.in_payroll !== false) return 0;
  return Object.values(d.social_by_month || {}).reduce((t, v) => t + v, 0) / Math.max(1, sdMonthsElapsed());
}
function sdCalcCards(p) {
  const params = sd.doc.params;
  if (p.kind === 'salarie') {
    const c = SC.employeeCosts(p, params, sdSocial(p));
    return `<div class="kpis">${kpi('Coût société annualisé', eur(c.annual), '', `(${sdEur2(c.brut)} + ${sdEur2(c.patronal)}) × ${num(c.factor)}`)}${kpi('Coût société mensuel', eur(c.monthly))}${kpi('Coût société journalier', sdEur2(c.daily), '', `${num(params.days_per_year * p.fte / 100)} jours / an`)}${kpi('Coût société horaire', sdEur2(c.hourly), '', `${num(p.hours_week / 5)} h / jour`)}${kpi('Coût société horaire ajusté', sdEur2(c.hourlyAdj), c.adjFactor === 1 ? '' : 'adj', `facturable ${num(p.billable_pct ?? 100)} % · temps presté ${num(p.hours_pct ?? 100)} %`)}</div>`
      + `<small class="na">Rémunération annualisée : ${eur(c.remunAnnual)} · autres coûts récurrents (×12) : ${eur(c.recurringAnnual)} · hors salaire (×12) : ${eur(c.extrasAnnual)}.</small>`;
  }
  const inv = sd.inv[p.id], tot = inv ? inv.list.reduce((t, x) => t + x.untaxed, 0) : 0, c = SC.independentCosts(p, params, tot, sdMonthsElapsed());
  return `<div class="kpis">${kpi('Facturé ' + SD_YEAR + ' (HT)', eur(tot), '', inv ? sdPlural(inv.list.length, 'facture') : 'à charger')}${kpi('Coût annualisé', eur(c.annual), '', `moyenne ${eur(c.invoicedMonthlyAvg)} / mois × 12 + hors facture`)}${kpi('Coût mensuel', eur(c.monthly))}${kpi('Coût journalier', sdEur2(c.daily))}${kpi('Coût horaire', sdEur2(c.hourly))}${kpi('Coût horaire ajusté', sdEur2(c.hourlyAdj), c.adjFactor === 1 ? '' : 'adj', `facturable ${num(p.billable_pct ?? 100)} % · temps presté ${num(p.hours_pct ?? 100)} %`)}</div>`;
}

function sdExtras(p) {
  const rows = (p.extras || []).map((e, i) => `<tr><td>${sdIn('label', e.label, {type: 'text', pid: p.id, i, sub: 'extra', ph: 'Libellé'})}</td>
    <td><select class="sdin" data-f="kind" data-pid="${p.id}" data-i="${i}" data-sub="extra"${sd.canEdit ? '' : ' disabled'}>${Object.entries(SD_KINDS).map(([k, l]) => `<option value="${k}"${e.kind === k ? ' selected' : ''}>${l}</option>`).join('')}</select></td>
    <td>${sdIn('monthly', e.monthly, {pid: p.id, i, sub: 'extra'})}</td><td>${sdIn('note', e.note, {type: 'text', pid: p.id, i, sub: 'extra', ph: 'Note'})}</td>
    <td>${sd.canEdit ? `<button type="button" class="mini" data-sd-del-extra data-pid="${p.id}" data-i="${i}">✕</button>` : ''}</td></tr>`);
  return `<h4 class="sub">${p.kind === 'salarie' ? 'Coûts hors salaire' : 'Coûts hors facture'}</h4>`
    + (rows.length ? table(['Libellé', 'Type', '€ / mois', 'Note', ''], rows, 'prodtable sdtable') : '<p class="na">Aucun : véhicule, carte essence, abonnement téléphone ou autre avantage mis à disposition.</p>')
    + (sd.canEdit ? `<button type="button" data-sd-add-extra data-pid="${p.id}">+ Ajouter un coût</button>` : '');
}

function sdPayslips(p) {
  const slips = SC.sortedSlips(p);
  const rows = slips.map(s => { const i = p.payslips.indexOf(s);
    const file = s.file ? `<a href="#" data-sd-open data-pid="${p.id}" data-month="${s.month}">${esc(s.file.name)}</a>` : (sd.canEdit && sd.upload ? `<input type="file" accept="application/pdf" data-sd-upload data-pid="${p.id}" data-month="${s.month}">` : '–');
    return `<tr><td><b>${esc(s.month)}</b></td><td>${sdIn('brut', s.brut, {pid: p.id, i, sub: 'slip'})}</td><td>${sdIn('patronal', s.patronal, {pid: p.id, i, sub: 'slip', ph: 'estimé'})}</td><td>${sdIn('net', s.net, {pid: p.id, i, sub: 'slip'})}</td>
      <td>${sdIn('other', s.other, {pid: p.id, i, sub: 'slip'})}</td><td>${file}</td><td>${sd.canEdit ? `<button type="button" class="mini" data-sd-del-slip data-pid="${p.id}" data-i="${i}">✕</button>` : ''}</td></tr>`; });
  const next = slips.length ? (() => { const [y, m] = slips[slips.length - 1].month.split('-').map(Number); return m === 12 ? `${y + 1}-01` : `${y}-${String(m + 1).padStart(2, '0')}`; })() : `${SD_YEAR}-01`;
  return '<h4 class="sub">Fiches de paie</h4>'
    + (rows.length ? table(['Mois', 'Brut', 'Cotisations patronales', 'Net', 'Autres coûts société', 'Fiche (PDF)', ''], rows, 'prodtable sdtable') : '<p class="na">Aucune fiche saisie.</p>')
    + (sd.canEdit ? `<div class="sdadd"><input type="month" id="sd-newmonth" value="${next}"> <button type="button" data-sd-add-slip data-pid="${p.id}">+ Ajouter ce mois</button>${sd.upload ? '' : ' <small class="na">Dépôt de PDF indisponible : bucket de stockage non configuré (les chiffres se saisissent à la main).</small>'}</div>` : '')
    + '<small class="na">Brut de référence = dernier mois saisi (ou le brut de référence ci-dessus). Cotisations patronales : celles de la fiche si renseignées, sinon estimées au taux ci-dessus.</small>';
}

function sdPersonPanel(p) {
  const emp = p.kind === 'salarie';
  const base = `<div class="sdgrid">${sdField('Nom', sdIn('name', p.name, {type: 'text', pid: p.id}))}${sdField('Fonction', sdIn('function', p.function, {type: 'text', pid: p.id}))}
    ${emp ? sdField('Temps de travail (%)', sdIn('fte', p.fte, {pid: p.id, step: '1'}), '100 = temps plein') + sdField('Heures / semaine (temps plein)', sdIn('hours_week', p.hours_week, {pid: p.id, step: '0.5'}))
          + sdField('Cotisations patronales estimées (%)', sdIn('patronal_pct', p.patronal_pct, {pid: p.id}), 'si absentes de la fiche') + sdField('Coefficient d’annualisation', sdIn('factor', p.factor, {pid: p.id, ph: num(sd.doc.params.annual_factor)}), '13,92 employé (13e mois + double pécule) · 12 ouvrier / gérant') + sdField('Brut mensuel de référence (€)', sdIn('brut_override', p.brut_override, {pid: p.id, ph: 'dernière fiche'}), 'facultatif')
          + sdField('Autres coûts société récurrents (€ / mois)', sdIn('monthly_other', p.monthly_other, {pid: p.id}), 'chèques-repas, assurance groupe…')
        : sdField('Temps (jours facturables) (%)', sdIn('fte', p.fte, {pid: p.id, step: '1'}), '100 = temps plein') + sdField('Heures / semaine', sdIn('hours_week', p.hours_week, {pid: p.id, step: '0.5'}))}
    ${sdField('Taux facturable (%)', sdIn('billable_pct', p.billable_pct ?? 100, {pid: p.id, step: '1'}), 'part des heures facturables à des clients externes (50 = la moitié) : sert au coût ajusté')}${sdField('Temps presté / horaire de base (%)', sdIn('hours_pct', p.hours_pct ?? 100, {pid: p.id, step: '1'}), '120 = preste en moyenne 20 % de plus que l’horaire de base')}
    ${emp ? sdField('Rémunération en 620/621', `<input type="checkbox" class="sdin" data-f="in_payroll" data-pid="${p.id}"${p.in_payroll !== false ? ' checked' : ''}${sd.canEdit ? '' : ' disabled'}>`, 'à décocher pour le gérant (payé via un autre compte)') : ''}${sdField('Actif', `<input type="checkbox" class="sdin" data-f="active" data-pid="${p.id}"${p.active ? ' checked' : ''}${sd.canEdit ? '' : ' disabled'}>`)}${sdField('Note', sdIn('note', p.note, {type: 'text', pid: p.id}))}</div>`;
  let body = base + `<div id="sd-kpi">${sdCalcCards(p)}</div>`;
  if (emp) body += sdPayslips(p);
  else body += sdIndependentCompanies(p);
  body += sdExtras(p);
  if (sd.canEdit) body += `<p><button type="button" class="danger" data-sd-del-person data-pid="${p.id}">Supprimer ${emp ? 'ce salarié' : 'cet indépendant'}</button></p>`;
  return `<div class="adjcard">${body}</div>`;
}

function sdIndependentCompanies(p) {
  const chips = (p.partners || []).map(x => `<span class="tagchip">${esc(x.name)} ${sd.canEdit ? `<button type="button" class="mini" data-sd-del-partner data-pid="${p.id}" data-id="${x.id}">✕</button>` : ''}</span>`).join(' ');
  const res = sd.results ? (sd.results.length ? sd.results.map(r => `<div class="sdres"><span>${esc(r.name)} <small class="na">${esc([r.vat, r.city].filter(Boolean).join(' · '))}</small></span> <button type="button" data-sd-add-partner data-pid="${p.id}" data-id="${r.id}" data-name="${esc(r.name)}">Ajouter</button></div>`).join('') : '<small class="na">Aucune société trouvée.</small>') : '';
  const inv = sd.inv[p.id];
  const list = !(p.partners || []).length ? '<p class="na">Rattachez une ou plusieurs sociétés Odoo pour faire remonter les factures de cet indépendant.</p>'
    : !inv ? '<p class="na">Chargement des factures…</p>'
    : inv.error ? `<p class="neg">${esc(inv.error)}</p>`
    : inv.list.length ? table(['Date', 'Facture', 'Référence', 'Société', 'HT', 'TTC', 'Payée'], inv.list.map(x => `<tr><td>${fmtDate(x.date)}</td><td>${esc(x.number)}${x.refund ? ' <small class="na">(avoir)</small>' : ''}</td><td>${esc(x.ref)}</td><td>${esc(x.partner)}</td><td>${sdEur2(x.untaxed)}</td><td>${sdEur2(x.total)}</td><td>${x.paid ? '✓' : '–'}</td></tr>`)
        .concat([`<tr class="tot"><td colspan="4">Total ${SD_YEAR}</td><td>${sdEur2(inv.list.reduce((t, x) => t + x.untaxed, 0))}</td><td>${sdEur2(inv.list.reduce((t, x) => t + x.total, 0))}</td><td></td></tr>`]), 'prodtable sdtable')
      : `<p class="na">Aucune facture comptabilisée en ${SD_YEAR}.</p>`;
  return `<h4 class="sub">Sociétés et factures</h4><div>${chips || '<small class="na">Aucune société rattachée.</small>'}</div>`
    + (sd.canEdit ? `<div class="sdadd"><input type="text" id="sd-q" placeholder="Rechercher une société Odoo" value="${esc(sd.q)}"> <button type="button" data-sd-search data-pid="${p.id}">Rechercher</button></div>${res}` : '') + list;
}

async function sdLoadInvoices(p) {
  const ids = (p.partners || []).map(x => x.id);
  if (!ids.length) { sd.inv[p.id] = {list: []}; return; }
  try {
    const r = await fetch(`/api/staff/invoices?ids=${ids.join(',')}&year=${SD_YEAR}`, {headers: sdAuth()});
    const j = await r.json();
    sd.inv[p.id] = j.unavailable ? {list: [], error: j.unavailable} : {list: j.invoices || []};
  } catch (e) { sd.inv[p.id] = {list: [], error: 'Factures indisponibles.'}; }
}

// Rapprochement mois par mois fiches de paie / comptabilité. Les écritures de paie sont parfois passées le mois suivant : pour chaque mois on retient,
// parmi le mois et le suivant (non encore utilisé), l'écriture la plus proche de la fiche. Le mois en cours n'est pas comparé.
function sdMatchRows(pay, accM) {
  const cur = new Date().toISOString().slice(0, 7), all = Array.from({length: 12}, (_, i) => `${SD_YEAR}-${String(i + 1).padStart(2, '0')}`), next = m => all[all.indexOf(m) + 1];
  const used = new Set(); let tp = 0, ta = 0;
  const rows = all.filter(m => m < cur).map(m => {
    const mine = pay[m] || 0; let am = m;
    if (mine) { const n = next(m), dn = n && !used.has(n) && accM[n] ? Math.abs(mine - accM[n]) : Infinity, d0 = used.has(m) ? Infinity : Math.abs(mine - (accM[m] || 0));
      if (dn <= mine * 0.02 && d0 > mine * 0.02) am = n; }      // décalage seulement si le mois ne colle pas (> 2 %) et que le suivant colle (≤ 2 %)
    else if (used.has(m)) return '';
    const acc = used.has(am) ? 0 : (accM[am] || 0); if (!mine && !acc) return ''; used.add(am); tp += mine; ta += acc;
    const diff = mine - acc;
    return `<tr><td>${m}${am !== m ? ` <small class="na">(écritures de ${am})</small>` : ''}</td><td>${sdEur2(mine)}</td><td>${sdEur2(acc)}</td><td class="${Math.abs(diff) < 1 ? '' : 'neg'}">${sdEur2(diff)}</td></tr>`; }).filter(Boolean);
  return {rows, tp, ta};
}
function sdControl() {
  const a = sd.acc;
  if (!a) return '<p class="na">Chargement des données comptables…</p>';
  if (a.unavailable) return `<p class="na">${esc(a.unavailable)}</p>`;
  const m = sdMatchRows(SC.payrollByMonth(sd.doc.people), a.pay_by_month || {});
  const tbl = (r, label) => r.rows.length ? table(['Mois', 'Fiches de paie (brut + patronal)', label, 'Écart'], r.rows.concat([`<tr class="tot"><td>Total</td><td>${sdEur2(r.tp)}</td><td>${sdEur2(r.ta)}</td><td>${sdEur2(r.tp - r.ta)}</td></tr>`]), 'prodtable sdtable') : '<p class="na">Aucune donnée à comparer pour ' + SD_YEAR + '.</p>';
  let out = tbl(m, `Comptabilité (comptes ${esc((a.pay_prefixes || []).join(', '))})`);
  const d = a.director, outside = SC.payrollByMonth(sd.doc.people, true);
  if (d && Object.keys(outside).length) {
    const g = sdMatchRows(outside, d.pay_by_month || {}), soc = Object.values(d.social_by_month || {}).reduce((t, v) => t + v, 0);
    out += `<h4 class="sub">Gérant / administrateur</h4>` + tbl(g, `Comptabilité (comptes ${esc((d.pay_accounts || []).join(', '))})`)
      + `<small class="na">Cotisations sociales de l’administrateur payées par la société (comptes ${esc((d.social_accounts || []).join(', '))}) : ${sdEur2(soc)} depuis le 1er janvier, ajoutées à son coût annualisé (moyenne mensuelle × 12).</small>`;
  }
  return out + `<small class="na">Compare, mois par mois, la rémunération des fiches de paie saisies (salariés) avec les écritures comptables des comptes de rémunération. Le mois en cours n'est pas comparé ; une paie dont les écritures sont datées du mois suivant est rapprochée de celles-ci (mention « écritures de … »). Les personnes dont la rémunération n'est pas en 620/621 (case décochée dans leur fiche, ex. le gérant) sont comparées à part. Un écart peut venir d'un pécule ou d'une prime comptabilisés autrement, ou d'une fiche manquante. Autres charges de personnel en comptabilité (hors rémunération) : ${sdEur2(Object.values(a.other_by_month || {}).reduce((t, v) => t + v, 0))}.</small>`;
}

function sdDrawSource() {
  const el = document.getElementById('staff-source'); if (!el) return;
  const gate = sdGate(); if (gate) { el.innerHTML = gate; return; }
  const k = sd.tab, list = sdPeople(k);
  if (!list.find(p => p.id === sd.sel[k])) sd.sel[k] = list.length ? list[0].id : null;
  const cur = list.find(p => p.id === sd.sel[k]);
  const params = sd.doc.params;
  el.innerHTML = sdBar()
    + `<div class="tabs"><button type="button" data-sd-tab="salarie" class="${k === 'salarie' ? 'on' : ''}">Salariés</button><button type="button" data-sd-tab="independant" class="${k === 'independant' ? 'on' : ''}">Indépendants</button></div>`
    + (k === 'salarie' ? `<div class="sdparams">${sdField('Facteur d’annualisation', sdIn('annual_factor', params.annual_factor, {pid: '_', sub: 'params', step: '0.01'}), '12 mois + 13e mois + double pécule = 13,92')}${sdField('Jours prestés par an (temps plein)', sdIn('days_per_year', params.days_per_year, {pid: '_', sub: 'params', step: '1'}), 'pour le coût journalier')}</div>` : '')
    + `<div class="tabs sdpeople">${list.map(p => `<button type="button" data-sd-sel="${p.id}" class="${p.id === sd.sel[k] ? 'on' : ''}">${esc(p.name || '(sans nom)')}</button>`).join('')}${sd.canEdit ? `<button type="button" data-sd-add-person="${k}">+ ${k === 'salarie' ? 'Salarié' : 'Indépendant'}</button>` : ''}</div>`
    + (cur ? sdPersonPanel(cur) : `<p class="na">Aucun ${k === 'salarie' ? 'salarié' : 'indépendant'} pour le moment.</p>`)
    + (k === 'salarie' ? `<h4 class="sub">Contrôle avec la comptabilité (${SD_YEAR})</h4><div id="sd-control">${sdControl()}</div>` : '');
  if (k === 'independant' && cur && !sd.inv[cur.id]) sdLoadInvoices(cur).then(sdDrawSource);
  if (k === 'salarie' && !sd.acc) sdLoadAcc();
}

async function sdLoadAcc() {
  if (sd.accLoading) return sd.accLoading;
  sd.accLoading = (async () => {
    try { sd.acc = await (await fetch(`/api/staff/accounting?year=${SD_YEAR}`, {headers: sdAuth()})).json(); } catch { sd.acc = {unavailable: 'Données comptables indisponibles.'}; }
    sd.accLoading = null; sdDraw();                       // coûts du gérant (cotisations en 618001) et tableau de contrôle
  })();
  return sd.accLoading;
}

function sdPersonAnnual(p) {
  if (p.kind === 'salarie') return SC.employeeCosts(p, sd.doc.params, sdSocial(p)).annual;
  const inv = sd.inv[p.id], tot = inv ? inv.list.reduce((t, x) => t + x.untaxed, 0) : 0;
  return SC.independentCosts(p, sd.doc.params, tot, sdMonthsElapsed()).annual;
}

function sdDrawPeople() {
  const el = document.getElementById('staff-people'); if (!el) return;
  const gate = sdGate(); if (gate) { el.innerHTML = gate; return; }
  if (!sd.acc) sdLoadAcc();
  const people = sd.doc.people.filter(p => p.active);
  people.filter(p => p.kind === 'independant' && !sd.inv[p.id]).forEach(p => sdLoadInvoices(p).then(() => { const t = document.getElementById('sd-alloc-tot'); if (t) t.innerHTML = sdAllocTotals(); }));
  const rows = people.map(p => { const a = p.alloc || {}, used = SD_SHARES.reduce((t, [k]) => t + (+a[k] || 0), 0);
    return `<tr data-row="${p.id}"><td class="prod">${esc(p.name)}<br><small class="na">${p.kind === 'salarie' ? 'Salarié' : 'Indépendant'}${p.function ? ' · ' + esc(p.function) : ''}</small></td><td data-annual="${p.id}">${eur(sdPersonAnnual(p))}</td>`
      + SD_SHARES.map(([k]) => `<td>${sdIn('alloc:' + k, a[k], {pid: p.id, sub: 'alloc', step: '1'})}</td>`).join('') + `<td data-pct="${p.id}" class="${used > 100.0001 ? 'neg' : used < 99.9999 ? 'na' : ''}">${num(used)} %</td></tr>`; });
  el.innerHTML = sdBar()
    + (rows.length ? table(['Personne', 'Coût annualisé'].concat(SD_SHARES.map(s => s[1] + ' (%)'), ['Total']), rows, 'prodtable sdtable sdalloc') : '<p class="na">Aucune personne : créez d’abord les salariés et indépendants dans « Données source ».</p>')
    + '<h4 class="sub">Coût imputé</h4><div id="sd-alloc-tot">' + sdAllocTotals() + '</div>'
    + '<small class="na">Pour chaque personne, indiquez le pourcentage de son coût imputé sur chacune des 4 BU et sur Shared Services (fonctions de support et de management). Le total ne doit pas dépasser 100 % ; ce qui n’est pas imputé apparaît en « non imputé ». Seuls les membres actifs sont listés.</small>';
}

function sdAllocTotals() {
  const tot = {XC: 0, MODERN_RALLY: 0, HISTORIC_RALLY: 0, HISTORIC_RACING: 0, SHARED: 0, UNALLOCATED: 0}; let all = 0;
  sd.doc.people.filter(p => p.active).forEach(p => { const annual = sdPersonAnnual(p), a = SC.allocate(annual, p.alloc); all += annual; Object.keys(tot).forEach(k => { tot[k] += a[k] || 0; }); });
  return `<div class="kpis">${SD_SHARES.map(([k, l]) => kpi(l, eur(tot[k]), '', all ? pct(tot[k] / all) + ' du coût du personnel' : '')).join('')}${tot.UNALLOCATED > 1 ? kpi('Non imputé', eur(tot.UNALLOCATED), 'neg', 'à répartir') : ''}</div>`;
}

function sdDraw() { sdDrawSource(); sdDrawPeople(); sdDrawView(); }

// ---- Événements ----------------------------------------------------------------------------------------------------
function sdParse(el) {
  if (el.type === 'checkbox') return el.checked;
  if (el.type === 'text' || el.tagName === 'SELECT' || el.type === 'month') return el.value;
  return el.value === '' ? null : sdNum(el.value);
}
document.addEventListener('change', e => {
  const el = e.target;
  if (el.dataset && el.dataset.sdUpload !== undefined && el.files && el.files[0]) { sdUpload(el); return; }
  if (el.dataset && el.dataset.sdImport !== undefined && el.files && el.files[0]) { sdImport(el); return; }
  if (!el.dataset || !el.dataset.f || !sd.doc || !sd.canEdit) return;
  const f = el.dataset.f, pid = el.dataset.pid, sub = el.dataset.sub, v = sdParse(el), i = el.dataset.i != null ? +el.dataset.i : null;
  if (sub === 'params') sd.doc.params[f] = v == null ? sd.doc.params[f] : v;
  else {
    const p = sdPerson(pid); if (!p) return;
    if (sub === 'alloc') { const k = f.split(':')[1]; if (v == null || v === 0) delete p.alloc[k]; else p.alloc[k] = v; }
    else if (sub === 'extra') p.extras[i][f] = (f === 'monthly') ? (v || 0) : v;
    else if (sub === 'slip') p.payslips[i][f] = (f === 'brut' || f === 'other') ? (v || 0) : v;
    else if (f === 'fte' || f === 'hours_week' || f === 'patronal_pct' || f === 'monthly_other') p[f] = v == null ? 0 : v;
    else if (f === 'billable_pct' || f === 'hours_pct') p[f] = v > 0 ? v : 100;
    else if (f === 'factor') p.factor = v;
    else p[f] = (f === 'brut_override') ? v : v;
  }
  sdTouch();
  const k = document.getElementById('sd-kpi'), cur = pid && pid !== '_' ? sdPerson(pid) : null;
  if (k && cur) k.innerHTML = sdCalcCards(cur);
  const ctl = document.getElementById('sd-control'); if (ctl && sd.acc) ctl.innerHTML = sdControl();
  if (sub === 'alloc' && cur) {                       // total des pourcentages, coût imputé
    const used = SD_SHARES.reduce((t, [kk]) => t + (+cur.alloc[kk] || 0), 0), c = document.querySelector(`[data-pct="${pid}"]`);
    if (c) { c.textContent = num(used) + ' %'; c.className = used > 100.0001 ? 'neg' : used < 99.9999 ? 'na' : ''; }
    const t = document.getElementById('sd-alloc-tot'); if (t) t.innerHTML = sdAllocTotals();
  }
  if (f === 'name' || sub === 'params' || f === 'kind') { if (f === 'name') document.querySelectorAll('[data-sd-sel="' + pid + '"]').forEach(b => { b.textContent = v || '(sans nom)'; }); }
});

document.addEventListener('click', async e => {
  const t = e.target.closest('button, a'); if (!t || !sd.doc) return;
  const d = t.dataset, redraw = () => { sdTouch(); sdDraw(); };
  if (d.sdSave !== undefined) { sdSave(); return; }
  if (d.sdReload !== undefined) { sd.dirty = false; sd.msg = ''; await sdLoad(); sd.inv = {}; sd.results = null; sdDraw(); return; }
  if (d.sdTab) { sd.tab = d.sdTab; sd.results = null; sdDraw(); return; }
  if (d.sdSel) { sd.sel[sd.tab] = d.sdSel; sd.results = null; sdDraw(); return; }
  if (!sd.canEdit && d.sdOpen === undefined) return;
  if (d.sdAddPerson) { const p = {id: sdId(), name: '', kind: d.sdAddPerson, function: '', active: true, start: null, end: null, fte: 100, hours_week: 38, patronal_pct: 25, brut_override: null, monthly_other: 0, payslips: [], extras: [], partners: [], alloc: {}, note: ''};
    sd.doc.people.push(p); sd.sel[p.kind] = p.id; redraw(); return; }
  if (d.sdDelPerson !== undefined) { const p = sdPerson(d.pid); if (p && confirm(`Supprimer ${p.name || 'cette personne'} et toutes ses données ?`)) { sd.doc.people = sd.doc.people.filter(x => x.id !== d.pid); redraw(); } return; }
  if (d.sdAddSlip !== undefined) { const m = (document.getElementById('sd-newmonth') || {}).value, p = sdPerson(d.pid);
    if (m && p && !p.payslips.find(s => s.month === m)) { p.payslips.push({month: m, brut: 0, patronal: null, net: null, other: 0, note: '', file: null}); redraw(); } return; }
  if (d.sdDelSlip !== undefined) { sdPerson(d.pid).payslips.splice(+d.i, 1); redraw(); return; }
  if (d.sdAddExtra !== undefined) { sdPerson(d.pid).extras.push({id: sdId(), label: '', kind: 'autre', monthly: 0, note: ''}); redraw(); return; }
  if (d.sdDelExtra !== undefined) { sdPerson(d.pid).extras.splice(+d.i, 1); redraw(); return; }
  if (d.sdSearch !== undefined) { const q = (document.getElementById('sd-q') || {}).value || ''; sd.q = q; if (q.trim().length < 2) return;
    try { const j = await (await fetch('/api/staff/partners?q=' + encodeURIComponent(q.trim()), {headers: sdAuth()})).json(); sd.results = j.partners || []; } catch { sd.results = []; } sdDraw(); return; }
  if (d.sdAddPartner !== undefined) { const p = sdPerson(d.pid); if (!p.partners.find(x => x.id === +d.id)) p.partners.push({id: +d.id, name: d.name}); delete sd.inv[p.id]; sd.results = null; redraw(); return; }
  if (d.sdDelPartner !== undefined) { const p = sdPerson(d.pid); p.partners = p.partners.filter(x => x.id !== +d.id); delete sd.inv[p.id]; redraw(); return; }
  if (d.sdOpen !== undefined) { e.preventDefault();
    try { const r = await fetch(`/api/staff/payslip?person=${encodeURIComponent(d.pid)}&month=${encodeURIComponent(d.month)}`, {headers: sdAuth()}); if (!r.ok) throw new Error(r.status);
      window.open(URL.createObjectURL(await r.blob()), '_blank', 'noopener'); } catch { alert('Fiche introuvable ou inaccessible.'); } }
});

async function sdUpload(el) {
  const f = el.files[0], p = sdPerson(el.dataset.pid), m = el.dataset.month; if (!p) return;
  if (f.size > 8 * 1024 * 1024) { alert('Fichier trop volumineux (8 Mo maximum).'); return; }
  try {
    const r = await fetch(`/api/staff/payslip?person=${encodeURIComponent(p.id)}&month=${encodeURIComponent(m)}`, {method: 'PUT', headers: {'Content-Type': 'application/pdf', ...sdAuth()}, body: f});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    p.payslips.find(s => s.month === m).file = {name: f.name.slice(0, 200), size: j.size, uploaded_at: j.uploaded_at};
    sdTouch(); sdDraw();
  } catch (err) { alert('Échec du dépôt : ' + err.message); }
}

async function sdImport(el) {
  const f = el.files[0]; el.value = '';
  if (sd.dirty && !confirm('Des modifications non enregistrées seront perdues. Continuer ?')) return;
  if (!confirm(`Importer « ${f.name} » ? Les nouvelles personnes sont ajoutées ; pour les personnes déjà présentes, seules les fiches sont fusionnées.`)) return;
  sd.msg = 'Import en cours…'; sdDraw();
  try {
    const r = await fetch('/api/staff/import', {method: 'POST', headers: {'Content-Type': 'application/zip', ...sdAuth()}, body: f});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    sd.dirty = false; await sdLoad(); sd.inv = {};
    sd.msg = `Import terminé : ${sdPlural(j.added.length, 'personne')} ajoutée${j.added.length > 1 ? 's' : ''}, ${sdPlural(j.merged.length, 'personne')} fusionnée${j.merged.length > 1 ? 's' : ''}, ${sdPlural(j.pdfs, 'PDF')} déposé${j.pdfs > 1 ? 's' : ''}.`;
  } catch (err) { sd.msg = 'Échec de l’import : ' + err.message; }
  sdDraw();
}

// ---- Affichage des coûts du personnel (Général, XC, CARS, Shared Services) -------------------------------------------
const SD_VIEWS = {
  general: {title: 'Coûts du personnel : vue générale', scope: null},
  xc: {title: 'Coûts du personnel imputés à XC', scope: ['XC']},
  cars: {title: 'Coûts du personnel imputés à CARS', scope: ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING']},
  shared: {title: 'Coûts du personnel des Shared Services', scope: ['SHARED']},
};
function staffViewBlocks(view) {
  return [{static: `<section class="block" data-bid="staff-view-${view}"><div class="block-head"><h3>${esc(SD_VIEWS[view].title)}</h3></div><div class="block-body" id="staff-view" data-view="${view}"><p class="na">Chargement…</p></div></section>`}];
}
const sdLabel = k => (SD_SHARES.find(x => x[0] === k) || [k, k])[1];
function sdViewRows() {
  return sd.doc.people.filter(p => p.active).map(p => { const annual = sdPersonAnnual(p), a = SC.allocate(annual, p.alloc); return {p, annual, a}; });
}
function sdDrawView() {
  const el = document.getElementById('staff-view'); if (!el) return;
  const gate = sdGate(); if (gate) { el.innerHTML = gate; return; }
  if (!sd.acc) sdLoadAcc();
  const v = SD_VIEWS[el.dataset.view], rows = sdViewRows(), total = rows.reduce((t, r) => t + r.annual, 0), sum = (r, ks) => ks.reduce((t, k) => t + (r.a[k] || 0), 0);
  const people = (list, n = rows.length) => `${sdPlural(list.filter(r => r.p.kind === 'salarie').length, 'salarié')} · ${sdPlural(list.filter(r => r.p.kind === 'independant').length, 'indépendant')}`;
  if (!rows.length) { el.innerHTML = '<p class="na">Aucune personne active : renseignez d’abord « Données source » puis « Imputation du personnel ».</p>'; return; }
  const note = '<small class="na">Coût annualisé : voir « Données source » (rémunération × coefficient d’annualisation + coûts récurrents et hors salaire ; indépendants : facturé depuis le 1er janvier ramené sur 12 mois). L’imputation provient de « Imputation du personnel ». Attention : les avantages hors salaire (véhicule, carte essence) peuvent aussi figurer dans les pages Service Vehicles ; ne pas les compter deux fois en cumulant les vues.</small>';
  if (!v.scope) {
    const groups = [['XC', ['XC']], ['CARS', ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING']], ['Shared Services', ['SHARED']], ['Non imputé', ['UNALLOCATED']]];
    const gt = groups.map(([l, ks]) => [l, rows.reduce((t, r) => t + sum(r, ks), 0)]);
    const acc = sd.acc && !sd.acc.unavailable ? Object.values(sd.acc.pay_by_month || {}).concat(Object.values((sd.acc.director || {}).pay_by_month || {}), Object.values((sd.acc.director || {}).social_by_month || {})).reduce((t, x) => t + x, 0) : null;
    const bu = SD_SHARES.map(([k, l]) => { const amt = rows.reduce((t, r) => t + (r.a[k] || 0), 0), who = rows.filter(r => (r.a[k] || 0) > 0);
      return `<tr><td>${esc(l)}</td><td>${eur(amt)}</td><td>${total ? pct(amt / total) : '–'}</td><td><small class="na">${who.length ? people(who) : '–'}</small></td></tr>`; });
    const un = rows.reduce((t, r) => t + r.a.UNALLOCATED, 0);
    el.innerHTML = `<div class="kpis">${kpi('Coût annualisé du personnel', eur(total), '', people(rows))}${gt.filter(([l, x]) => l !== 'Non imputé' || x > 1).map(([l, x]) => kpi(l, eur(x), l === 'Non imputé' ? 'neg' : '', total ? pct(x / total) : '')).join('')}${acc != null ? kpi('Réalisé en comptabilité ' + SD_YEAR, eur(acc), '', 'comptes 620/621 + 618000/618001, depuis le 1er janvier') : ''}</div>`
      + '<h4 class="sub">Répartition par BU</h4>' + table(['Entité', 'Coût annualisé imputé', 'Part', 'Personnes concernées'], bu.concat(un > 1 ? [`<tr><td>Non imputé</td><td class="neg">${eur(un)}</td><td>${pct(un / total)}</td><td><small class="na">à répartir dans « Imputation du personnel »</small></td></tr>`] : []), 'prodtable')
      + '<h4 class="sub">Par personne</h4>' + table(['Personne', 'Type', 'Coût annualisé', 'XC', 'CARS', 'Shared Services', 'Non imputé'], rows.sort((x, y) => y.annual - x.annual).map(r =>
          `<tr><td class="prod">${esc(r.p.name)}<br><small class="na">${esc(r.p.function || '')}</small></td><td>${r.p.kind === 'salarie' ? 'Salarié' : 'Indépendant'}</td><td>${eur(r.annual)}</td><td>${eur(r.a.XC)}</td><td>${eur(sum(r, ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING']))}</td><td>${eur(r.a.SHARED)}</td><td class="${r.a.UNALLOCATED > 1 ? 'neg' : ''}">${eur(r.a.UNALLOCATED)}</td></tr>`).concat([`<tr class="tot"><td>Total</td><td></td><td>${eur(total)}</td><td>${eur(gt[0][1])}</td><td>${eur(gt[1][1])}</td><td>${eur(gt[2][1])}</td><td>${eur(gt[3][1])}</td></tr>`]), 'prodtable') + note;
    return;
  }
  const mine = rows.filter(r => sum(r, v.scope) > 0).sort((x, y) => sum(y, v.scope) - sum(x, v.scope)), amt = mine.reduce((t, r) => t + sum(r, v.scope), 0);
  const fte = mine.reduce((t, r) => t + v.scope.reduce((u, k) => u + (+r.p.alloc[k] || 0), 0) / 100, 0);
  const multi = v.scope.length > 1, head = ['Personne', 'Type'].concat(multi ? v.scope.map(k => sdLabel(k) + ' (%)') : [], ['Imputé (%)', 'Coût annualisé imputé']);
  const body = mine.map(r => { const pc = v.scope.reduce((u, k) => u + (+r.p.alloc[k] || 0), 0);
    return `<tr><td class="prod">${esc(r.p.name)}<br><small class="na">${esc(r.p.function || '')}</small></td><td>${r.p.kind === 'salarie' ? 'Salarié' : 'Indépendant'}</td>${multi ? v.scope.map(k => `<td>${num(+r.p.alloc[k] || 0)} %</td>`).join('') : ''}<td>${num(pc)} %</td><td>${eur(sum(r, v.scope))}</td></tr>`; });
  const tail = `<tr class="tot"><td>Total</td><td></td>${multi ? v.scope.map(k => `<td>${num(mine.reduce((t, r) => t + (+r.p.alloc[k] || 0) / 100, 0))} ETP</td>`).join('') : ''}<td>${num(fte)} ETP</td><td>${eur(amt)}</td></tr>`;
  const split = multi ? '<h4 class="sub">Par BU</h4><div class="kpis">' + v.scope.map(k => { const x = rows.reduce((t, r) => t + (r.a[k] || 0), 0); return kpi(sdLabel(k), eur(x), '', amt ? pct(x / amt) + ' de CARS' : ''); }).join('') + '</div>' : '';
  el.innerHTML = `<div class="kpis">${kpi('Coût annualisé imputé', eur(amt), '', total ? pct(amt / total) + ' du coût du personnel' : '')}${kpi('Équivalents temps plein imputés', num(fte), '', sdPlural(mine.length, 'personne'))}${kpi('Coût moyen par ETP', fte ? eur(amt / fte) : '–')}</div>`
    + split + (mine.length ? table(head, body.concat([tail]), 'prodtable') : '<p class="na">Personne n’est imputé ici pour le moment : voir « Imputation du personnel ».</p>') + note;
}
