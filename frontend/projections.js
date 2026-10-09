// Overview › « Projections annualisées » (Chiffre d’affaires, Marge brute, Marge nette). Chargé avant app.js.
// Outil de projection : CA mensuel réalisé (XC et CARS séparément), moyenne des mois écoulés, puis pour chaque mois restant une variation en % de cette moyenne → CA attendu.
// Marge brute : CA projeté × taux de marge brute réalisé à date. Marge nette : marge brute projetée − charges imputées annualisées de façon linéaire (elles courent au fil du temps).
const pj = {ready: false, loading: null, err: null, year: null, months: [], inputs: {XC: {}, CARS: {}}, saved: null, can_save: false, dirty: false, msg: null, cur: null, days: null};
const PJ_MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
const pjClone = o => JSON.parse(JSON.stringify(o));
const pjAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};
function PJ_BLOCK(kind) {
  return B('pj_' + kind, 'Projections annualisées', () => { pjEnsure(); return `<div class="pj-host" data-kind="${kind}">${pjHtml(kind)}</div>`; }, true);
}
function pjDays() {
  const t = new Date(), y = t.getFullYear(), elapsed = Math.floor((new Date(y, t.getMonth(), t.getDate()) - new Date(y, 0, 1)) / 864e5) + 1;
  const len = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 366 : 365;
  return {y, elapsed, len, k: len / elapsed, to: ymd(t), month: t.getMonth() + 1, dom: t.getDate(), dim: new Date(y, t.getMonth() + 1, 0).getDate()};
}
async function pjEnsure() {
  if (pj.ready && pj.days && pj.days.to !== ymd(new Date())) pj.ready = false;          // nouveau jour : on recalcule
  if (pj.ready || pj.loading) return;
  pj.days = pjDays();
  const {y, to} = pj.days;
  pj.loading = (async () => {
    try {
      const [r, cur] = await Promise.all([fetch('/api/projection?year=' + y, {headers: pjAuth()}), getRange(`${y}-01-01`, to)]);
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      pj.year = y; pj.months = j.months || []; pj.can_save = !!j.can_save; pj.updated = j.updated_at ? {at: j.updated_at, by: j.updated_by} : null;
      pj.saved = {XC: {...(j.inputs.XC || {})}, CARS: {...(j.inputs.CARS || {})}}; pj.inputs = pjClone(pj.saved); pj.dirty = false;
      pj.cur = viewData(cur); pj.err = null; pj.ready = true;
    } catch (e) { pj.err = e.message; }
    pj.loading = null; pjRedraw();
  })();
  pj.loading.catch(() => {});
}

// ---- Calcul --------------------------------------------------------------------------------------
function pjCalc(sc) {
  const {month, dom, dim} = pj.days, done = pj.months.filter(m => !m.partial), cur = pj.months.find(m => m.partial);
  const avg = done.length ? done.reduce((t, m) => t + m[sc].ca, 0) / done.length : cur ? cur[sc].ca * dim / Math.max(1, dom) : 0;       // en janvier : mois en cours ramené à un mois plein
  const rows = [];
  for (let m = 1; m <= 12; m++) {
    const r = pj.months.find(x => x.month === m), pct = sc === 'OTHER' ? 0 : +(pj.inputs[sc] || {})[m] || 0;
    if (r && !r.partial) rows.push({m, real: r[sc].ca, pct: avg ? (r[sc].ca / avg - 1) * 100 : null, done: true});
    else rows.push({m, real: r ? r[sc].ca : null, pct, exp: avg * (1 + pct / 100), partial: !!r, done: false});
  }
  const total = rows.reduce((t, r) => t + (r.done ? r.real : r.exp), 0), real = pj.months.reduce((t, m) => t + m[sc].ca, 0);
  return {avg, rows, total, real, n: done.length};
}
const pjAll = () => { const c = {XC: pjCalc('XC'), CARS: pjCalc('CARS'), OTHER: pjCalc('OTHER')}; c.TOTAL = {total: c.XC.total + c.CARS.total + c.OTHER.total, real: c.XC.real + c.CARS.real + c.OTHER.real}; return c; };
const pjPct = v => v == null ? '–' : (v > 0 ? '+' : '') + (Math.round(v * 10) / 10).toString().replace('.', ',') + ' %';

// ---- Affichage -----------------------------------------------------------------------------------
function pjCaHtml() {
  const c = pjAll(), {y, k, month} = pj.days;
  const head = '<tr><th rowspan="2">Mois</th><th colspan="3" class="pjg">XC</th><th colspan="3" class="pjg">CARS</th><th rowspan="2" class="pjg">Total</th></tr><tr class="pjsub"><th>Réalisé</th><th>Variation</th><th>CA attendu</th><th>Réalisé</th><th>Variation</th><th>CA attendu</th></tr>';
  const cell = (sc, r) => {
    if (r.done) return `<td data-v="${r.real}">${eur(r.real)}</td><td class="na">${pjPct(r.pct)}</td><td>${eur(r.real)}</td>`;
    const v = (pj.inputs[sc] || {})[r.m];
    return `<td class="na" data-v="${r.real ?? ''}">${r.real == null ? '–' : eur(r.real) + '<br><small>à date</small>'}</td><td><input class="sdin pj-in" type="number" step="0.5" min="-100" inputmode="decimal" data-sc="${sc}" data-m="${r.m}" value="${v ? v : ''}" placeholder="0" aria-label="Variation ${sc} ${PJ_MONTHS[r.m - 1]} en %"> %</td><td id="pjx-${sc}-${r.m}" class="pjexp">${eur(r.exp)}</td>`;
  };
  const rows = [], lastDone = Math.max(0, ...pj.months.filter(q => !q.partial).map(q => q.month)), avgRow = () => `<tr class="pjavg"><td>Moyenne des ${c.XC.n} mois écoulés</td><td colspan="2"></td><td id="pjavg-XC">${eur(c.XC.avg)}</td><td colspan="2"></td><td id="pjavg-CARS">${eur(c.CARS.avg)}</td><td></td></tr>`;
  if (!lastDone) rows.push(avgRow());
  for (let m = 1; m <= 12; m++) {
    const x = c.XC.rows[m - 1], z = c.CARS.rows[m - 1], o = c.OTHER.rows[m - 1], tot = (x.done ? x.real : x.exp) + (z.done ? z.real : z.exp) + (o.done ? o.real : o.exp);
    rows.push(`<tr class="${x.done ? '' : x.partial ? 'pjcur' : 'pjfut'}"><td>${PJ_MONTHS[m - 1]}${x.partial ? ' <small class="na">en cours</small>' : ''}</td>${cell('XC', x)}${cell('CARS', z)}<td id="pjx-TOTAL-${m}">${eur(tot)}</td></tr>`);
    if (m === lastDone) rows.push(avgRow());
  }
  rows.push(`<tr class="tot"><td>Total ${y}</td><td colspan="2" class="na">à date ${eur(c.XC.real)}</td><td id="pjt-XC">${eur(c.XC.total)}</td><td colspan="2" class="na">à date ${eur(c.CARS.real)}</td><td id="pjt-CARS">${eur(c.CARS.total)}</td><td id="pjt-TOTAL">${eur(c.TOTAL.total)}</td></tr>`);
  const o = c.OTHER;
  return `<p class="na">Au ${fmtDate(pj.days.to)} : ${pj.days.elapsed} jours écoulés sur ${pj.days.len}. Indiquez, pour chaque mois restant, la variation attendue (positive ou négative) par rapport à la <b>moyenne mensuelle des mois écoulés</b> : le CA attendu s’affiche et le total de l’année se met à jour. XC et CARS se règlent séparément.</p>`
    + `<div class="table-wrap"><table class="prodtable pjtable"><thead>${head}</thead><tbody>${rows.join('')}</tbody></table></div>` + pjBar()
    + `<small class="na">CA = comptes 700 de l’année en cours, par mois (le mois en cours est partiel : le CA attendu est celui du mois complet, d’après la moyenne et la variation saisies). La colonne Total comprend aussi les comptes non affectés (${eur(o.real)} réalisés à date, projetés à leur moyenne mensuelle). Pour comparaison, projection linéaire (réalisé × ${num(Math.round(k * 100) / 100)}) : XC ${eur(c.XC.real * k)}, CARS ${eur(c.CARS.real * k)}, total ${eur(c.TOTAL.real * k)}. Le CA de l’année précédente n’est pas utilisé : le plan comptable de 2025 ne distinguait pas XC et CARS.</small>`;
}
function pjBar() {
  const upd = pj.updated ? ` · hypothèses enregistrées le ${new Date(pj.updated.at).toLocaleDateString('fr-BE')} par ${esc(pj.updated.by || '')}` : '';
  return `<div class="sdbar">${pj.can_save ? `<button type="button" class="primary" id="pj-save"${pj.dirty ? '' : ' disabled'}>Enregistrer les hypothèses</button>` : ''}<button type="button" id="pj-reset"${pj.dirty ? '' : ' disabled'}>${pj.can_save ? 'Annuler mes modifications' : 'Restaurer les valeurs par défaut'}</button><button type="button" id="pj-zero">Tout remettre à 0 %</button>`
    + `<span class="${pj.msg && !pj.msg.ok ? 'neg' : 'na'}">${pj.msg ? esc(pj.msg.t) : pj.dirty ? (pj.can_save ? 'Modifications non enregistrées' : 'Simulation : vos valeurs ne sont pas enregistrées') : (pj.can_save ? 'Hypothèses de référence' : 'Hypothèses de référence (lecture seule : vous pouvez simuler)') + upd}</span></div>`;
}
function pjHtml(kind) {
  if (pj.err) return `<p class="neg">Projection indisponible : ${esc(pj.err)}</p>`;
  if (!pj.ready) return '<p class="na">Calcul des projections (CA mensuel de l’année en cours)…</p>';
  if (kind === 'ca') return pjCaHtml();
  const c = pjAll(), k = pj.days.k, yr = pj.days.y;
  const caP = {Total: c.TOTAL.total, XC: c.XC.total, CARS: c.CARS.total}, caR = {Total: pj.cur.pnl.total.ca, XC: grp(pj.cur, 'XC').ca, CARS: grp(pj.cur, 'CARS').ca};
  const mbR = {Total: pj.cur.pnl.total.margin, XC: grp(pj.cur, 'XC').margin, CARS: grp(pj.cur, 'CARS').margin};
  const intro = `<p class="na">Au ${fmtDate(pj.days.to)} : ${pj.days.elapsed} jours écoulés sur ${pj.days.len}. La projection part du <b>CA attendu</b> saisi dans Overview › Chiffre d’affaires (variations des mois restants, XC et CARS séparément) ; les montants sont mis à jour ici dès que vous les modifiez.</p>`;
  const link = '<small class="na"><a href="#/overview/ca">Modifier les hypothèses de CA</a>.</small>';
  if (kind === 'mb') {
    const rows = ['Total', 'XC', 'CARS'].map(sc => { const rate = caR[sc] ? mbR[sc] / caR[sc] : null, proj = rate == null ? null : caP[sc] * rate;
      return `<tr><td>${sc}</td><td data-v="${mbR[sc]}">${eur(mbR[sc])}</td><td data-v="${caP[sc]}">${eur(caP[sc])}</td><td>${rate == null ? '–' : pct(rate)}</td><td data-v="${proj ?? ''}" class="${proj == null ? '' : cls(proj)}"><b>${proj == null ? 'n/d' : eur(proj)}</b></td><td data-v="${mbR[sc] * k}" class="na">${eur(mbR[sc] * k)}</td></tr>`; });
    return intro + table(['', 'Marge brute à date', 'CA attendu ' + yr, 'Taux de marge brute à date', 'Marge brute projetée', 'Pour comparaison : linéaire'], rows, 'prodtable') + link
      + '<small class="na">Marge brute projetée = CA attendu de l’année × taux de marge brute réalisé à date (hypothèse : le taux de marge reste celui observé). Les ajustements de marge brute et variations de stock suivent les options actives (MB ajustée / stock). Les montants « linéaire » = réalisé × ' + num(Math.round(k * 100) / 100) + '.</small>';
  }
  if (!nm.ready || !ex.alloc) { nmEnsure(); return intro + '<p class="na">Chargement des coûts (personnel, frais généraux, véhicules)…</p>'; }
  const cols = nmCompute(pj.cur).cols, keysOf = {Total: Object.keys(cols), XC: ['XC'], CARS: NM_CARS};
  const rows = ['Total', 'XC', 'CARS'].map(sc => { const o = nmSum(cols, keysOf[sc]), mb = o.ca - o.dc, charges = mb - nmNet(o), net = nmNet(o), rate = o.ca ? mb / o.ca : null, mbP = rate == null ? null : caP[sc] * rate, proj = mbP == null ? null : mbP - charges * k;
    return `<tr><td>${sc}</td><td data-v="${net}" class="${cls(net)}">${eur(net)}<br><small class="na">MB ${eur(mb)} − charges ${eur(charges)}</small></td><td data-v="${caP[sc]}">${eur(caP[sc])}</td><td data-v="${mbP ?? ''}">${mbP == null ? 'n/d' : eur(mbP)}</td><td data-v="${charges * k}">${eur(charges * k)}</td><td data-v="${proj ?? ''}" class="${proj == null ? '' : cls(proj)}"><b>${proj == null ? 'n/d' : eur(proj)}</b>${proj == null || !caP[sc] ? '' : `<br><small class="na">${pct(proj / caP[sc])} du CA attendu</small>`}</td><td data-v="${net * k}" class="na">${eur(net * k)}</td></tr>`; });
  return intro + table(['', 'Marge nette à date', 'CA attendu ' + yr, 'Marge brute projetée', 'Charges annualisées', 'Marge nette projetée', 'Pour comparaison : linéaire'], rows, 'prodtable') + link
    + '<small class="na">Marge nette projetée = marge brute projetée (CA attendu × taux de marge brute à date) − charges imputées à date × ' + num(Math.round(k * 100) / 100) + ' (personnel, véhicules, frais généraux, Shared Services, Management, marketing : elles courent au fil du temps). Les charges suivent les hypothèses et options de « Marge nette par BU » ci-dessus. « Total » comprend aussi les comptes non affectés et les coûts non imputés.</small>';
}
const pjRedraw = () => document.querySelectorAll('.pj-host').forEach(h => { h.innerHTML = pjHtml(h.dataset.kind); });
// Mise à jour des seules cellules calculées (la saisie garde son focus)
function pjUpdateCells() {
  const c = pjAll(), set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = eur(v); };
  for (let m = 1; m <= 12; m++) { ['XC', 'CARS'].forEach(sc => { const r = c[sc].rows[m - 1]; if (!r.done) set(`pjx-${sc}-${m}`, r.exp); });
    const t = ['XC', 'CARS', 'OTHER'].reduce((s, sc) => { const r = c[sc].rows[m - 1]; return s + (r.done ? r.real : r.exp); }, 0); set('pjx-TOTAL-' + m, t); }
  set('pjt-XC', c.XC.total); set('pjt-CARS', c.CARS.total); set('pjt-TOTAL', c.TOTAL.total);
  const bar = document.querySelector('.pj-host[data-kind="ca"] .sdbar'); if (bar) bar.outerHTML = pjBar();
}
document.addEventListener('input', e => { const t = e.target; if (!t.classList || !t.classList.contains('pj-in')) return;
  const v = t.value === '' ? 0 : Math.max(-100, Math.min(1000, +t.value || 0)); (pj.inputs[t.dataset.sc] = pj.inputs[t.dataset.sc] || {})[t.dataset.m] = v;
  pj.dirty = JSON.stringify(pj.inputs) !== JSON.stringify(pj.saved); pj.msg = null; pjUpdateCells(); });
document.addEventListener('click', async e => {
  if (e.target.id === 'pj-reset') { pj.inputs = pjClone(pj.saved); pj.dirty = false; pj.msg = null; pjRedraw(); return; }
  if (e.target.id === 'pj-zero') { pj.inputs = {XC: {}, CARS: {}}; pj.dirty = JSON.stringify(pj.inputs) !== JSON.stringify(pj.saved); pj.msg = null; pjRedraw(); return; }
  if (e.target.id === 'pj-save') {
    try {
      const r = await fetch('/api/projection', {method: 'PUT', headers: {'Content-Type': 'application/json', ...pjAuth()}, body: JSON.stringify({year: pj.year, inputs: pj.inputs})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      pj.saved = pjClone(j.inputs); pj.inputs = pjClone(j.inputs); pj.dirty = false; pj.updated = {at: j.updated_at, by: j.updated_by}; pj.msg = {ok: true, t: 'Enregistré'};
    } catch (err) { pj.msg = {ok: false, t: err.message}; }
    pjRedraw();
  }
});
