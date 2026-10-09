// Vue d’ensemble › « Projections annualisées » (Chiffre d’affaires, Marge brute, Marge nette). Chargé avant app.js.
// Chiffre d’affaires : CA réalisé de chaque mois écoulé (XC, CARS, total) ; pour les mois à venir, on encode le CA espéré (XC et CARS séparément). Une case laissée vide compte pour la moyenne des mois écoulés.
// Marge brute : CA de l’année × taux de marge brute réalisé à date. Marge nette : marge brute projetée − charges imputées annualisées de façon linéaire (elles courent au fil du temps).
const pj = {prev: [], ready: false, loading: null, err: null, year: null, months: [], exp: {XC: {}, CARS: {}}, saved: null, can_save: false, dirty: false, msg: null, cur: null, days: null};
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
      pj.year = y; pj.months = j.months || []; pj.prev = j.prev_months || []; pj.can_save = !!j.can_save; pj.updated = j.updated_at ? {at: j.updated_at, by: j.updated_by} : null;
      pj.saved = {XC: {...(j.expected.XC || {})}, CARS: {...(j.expected.CARS || {})}}; pj.exp = pjClone(pj.saved); pj.dirty = false;
      pj.cur = viewData(cur); pj.err = null; pj.ready = true;
    } catch (e) { pj.err = e.message; }
    pj.loading = null; pjRedraw();
  })();
  pj.loading.catch(() => {});
}

// ---- Calcul --------------------------------------------------------------------------------------
// Par périmètre : mois écoulés = CA réalisé ; mois en cours et à venir = CA espéré encodé, à défaut la moyenne des mois écoulés.
function pjCalc(sc) {
  const {dom, dim} = pj.days, done = pj.months.filter(m => !m.partial), cur = pj.months.find(m => m.partial);
  const avg = done.length ? done.reduce((t, m) => t + m[sc].ca, 0) / done.length : cur ? cur[sc].ca * dim / Math.max(1, dom) : 0;       // en janvier : mois en cours ramené à un mois plein
  const rows = [];
  for (let m = 1; m <= 12; m++) {
    const r = pj.months.find(x => x.month === m), v = sc === 'OTHER' ? undefined : (pj.exp[sc] || {})[m], has = v !== undefined && v !== null && v !== '';
    if (r && !r.partial) rows.push({m, real: r[sc].ca, done: true, val: r[sc].ca});
    else rows.push({m, real: r ? r[sc].ca : null, partial: !!r, done: false, has, enc: has ? +v : null, val: has ? +v : avg});
  }
  return {avg, rows, n: done.length, real: pj.months.reduce((t, m) => t + m[sc].ca, 0), total: rows.reduce((t, r) => t + r.val, 0), todo: rows.filter(r => !r.done && sc !== 'OTHER' && !r.has).length};
}
const pjAll = () => { const c = {XC: pjCalc('XC'), CARS: pjCalc('CARS'), OTHER: pjCalc('OTHER')}; c.TOTAL = {total: c.XC.total + c.CARS.total + c.OTHER.total, real: c.XC.real + c.CARS.real + c.OTHER.real}; return c; };

// ---- Affichage : tableau Chiffre d’affaires ------------------------------------------------------
const pjVs = (cur, prev) => prev > 0 ? `<span class="${cur >= prev ? 'pos' : 'neg'}">${cur >= prev ? '▲ +' : '▼ '}${((cur / prev - 1) * 100).toFixed(1).replace('.', ',')} %</span>` : '–';
function pjCaHtml() {
  const c = pjAll(), {y} = pj.days;
  const prevOf = m => { const p = pj.prev.find(x => x.month === m); return p ? p.ca : null; }, prevTot = pj.prev.reduce((t, x) => t + x.ca, 0);
  const monthTot = m => c.XC.rows[m - 1].val + c.CARS.rows[m - 1].val + c.OTHER.rows[m - 1].val;
  const cell = (sc, r) => r.done ? `<td data-v="${r.real}">${eur(r.real)}</td>`
    : `<td><input class="sdin pj-in" type="number" step="1000" min="0" inputmode="numeric" data-sc="${sc}" data-m="${r.m}" value="${r.has ? r.enc : ''}" placeholder="${Math.round(c[sc].avg)}" aria-label="CA espéré ${sc} ${PJ_MONTHS[r.m - 1]}"> €${r.partial && r.real != null ? `<br><small class="na">déjà ${eur(r.real)}</small>` : ''}</td>`;
  const rows = [];
  for (let m = 1; m <= 12; m++) {
    const x = c.XC.rows[m - 1], z = c.CARS.rows[m - 1];
    rows.push(`<tr class="${x.done ? '' : 'pjfut'}"><td>${PJ_MONTHS[m - 1]}${x.partial ? ' <small class="na">en cours</small>' : x.done ? '' : ' <small class="na">à venir</small>'}</td>${cell('XC', x)}${cell('CARS', z)}<td id="pjx-TOTAL-${m}" class="${x.done ? '' : 'na'}">${eur(monthTot(m))}</td><td class="na">${prevOf(m) == null ? '–' : eur(prevOf(m))}</td></tr>`);
  }
  rows.push(`<tr class="pjavg"><td>Total ${y}</td><td id="pjt-XC">${eur(c.XC.total)}</td><td id="pjt-CARS">${eur(c.CARS.total)}</td><td id="pjt-TOTAL">${eur(c.TOTAL.total)}</td><td>${pj.prev.length ? eur(prevTot) : '–'}</td></tr>`);
  rows.push(`<tr class="pjvs"><td colspan="3" class="na">Évolution du total ${y} par rapport à ${y - 1}</td><td id="pjvs">${pjVs(c.TOTAL.total, prevTot)}</td><td></td></tr>`);
  return `<p class="na">Au ${fmtDate(pj.days.to)} : ${pj.days.elapsed} jours écoulés sur ${pj.days.len}. Les mois écoulés montrent le CA réalisé. Pour les mois à venir, encodez le CA espéré de XC et de CARS : le total de l’année se met à jour.</p>`
    + `<div class="table-wrap"><table class="prodtable pjtable"><thead><tr><th>Mois</th><th>CA XC</th><th>CA CARS</th><th>Total</th><th>Total ${y - 1}</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>` + pjBar()
    + `<small class="na">Une case laissée vide compte pour la <b>moyenne des mois écoulés</b> (XC ${eur(c.XC.avg)}, CARS ${eur(c.CARS.avg)}), affichée en grisé dans la case. Le mois en cours : encodez le CA du mois complet (le CA déjà réalisé est rappelé sous la case). Le total comprend aussi les comptes non affectés (${eur(c.OTHER.real)} réalisés à date, projetés à leur moyenne). CA = comptes 700 de l’année ${y}. Colonne « Total ${y - 1} » : CA total de chaque mois de ${y - 1}, ancien plan comptable compris ; il n’est pas réparti entre XC et CARS (le plan comptable de l’époque ne le permettait pas). Pour comparaison, projection linéaire (réalisé × ${num(Math.round(pj.days.k * 100) / 100)}) : ${eur(c.TOTAL.real * pj.days.k)}.</small>`;
}
function pjBar() {
  const upd = pj.updated ? ` · enregistré le ${new Date(pj.updated.at).toLocaleDateString(LOCALE())} par ${esc(pj.updated.by || '')}` : '';
  return `<div class="sdbar">${pj.can_save ? `<button type="button" class="primary" id="pj-save"${pj.dirty ? '' : ' disabled'}>Enregistrer</button>` : ''}<button type="button" id="pj-reset"${pj.dirty ? '' : ' disabled'}>${pj.can_save ? 'Annuler mes modifications' : 'Restaurer les valeurs par défaut'}</button><button type="button" id="pj-zero">Vider toutes les cases</button>`
    + `<span class="${pj.msg && !pj.msg.ok ? 'neg' : 'na'}">${pj.msg ? esc(pj.msg.t) : pj.dirty ? (pj.can_save ? 'Modifications non enregistrées' : 'Simulation : vos valeurs ne sont pas enregistrées') : (pj.can_save ? 'Chiffres de référence' : 'Chiffres de référence (lecture seule : vous pouvez simuler)') + upd}</span></div>`;
}
function pjHtml(kind) {
  if (pj.err) return `<p class="neg">Projection indisponible : ${esc(pj.err)}</p>`;
  if (!pj.ready) return '<p class="na">Calcul des projections (CA mensuel de l’année en cours)…</p>';
  if (kind === 'ca') return pjCaHtml();
  const c = pjAll(), k = pj.days.k, yr = pj.days.y;
  const caP = {Total: c.TOTAL.total, XC: c.XC.total, CARS: c.CARS.total}, caR = {Total: pj.cur.pnl.total.ca, XC: grp(pj.cur, 'XC').ca, CARS: grp(pj.cur, 'CARS').ca};
  const mbR = {Total: pj.cur.pnl.total.margin, XC: grp(pj.cur, 'XC').margin, CARS: grp(pj.cur, 'CARS').margin};
  const intro = `<p class="na">Au ${fmtDate(pj.days.to)} : ${pj.days.elapsed} jours écoulés sur ${pj.days.len}. La projection part du <b>CA espéré</b> encodé dans Vue d’ensemble › Chiffre d’affaires pour les mois à venir (XC et CARS séparément) ; un mois sans chiffre compte pour la moyenne des mois écoulés.</p>`;
  const link = '<p style="margin:8px 0"><small class="na"><a href="#/overview/ca">Encoder le CA espéré des mois à venir</a></small></p>';
  if (kind === 'mb') {
    const rows = ['Total', 'XC', 'CARS'].map(sc => { const rate = caR[sc] ? mbR[sc] / caR[sc] : null, proj = rate == null ? null : caP[sc] * rate;
      return `<tr><td>${sc}</td><td data-v="${mbR[sc]}">${eur(mbR[sc])}</td><td data-v="${caP[sc]}">${eur(caP[sc])}</td><td>${rate == null ? '–' : pct(rate)}</td><td data-v="${proj ?? ''}" class="${proj == null ? '' : cls(proj)}"><b>${proj == null ? 'n/d' : eur(proj)}</b></td><td data-v="${mbR[sc] * k}" class="na">${eur(mbR[sc] * k)}</td></tr>`; });
    return intro + table(['', 'Marge brute à date', 'CA espéré ' + yr, 'Taux de marge brute à date', 'Marge brute projetée', 'Pour comparaison : linéaire'], rows, 'prodtable') + link
      + '<small class="na">Marge brute projetée = CA espéré de l’année × taux de marge brute réalisé à date (hypothèse : le taux de marge reste celui observé). Les ajustements de marge brute et variations de stock suivent les options actives (MB ajustée / stock). Les montants « linéaire » = réalisé × ' + num(Math.round(k * 100) / 100) + '.</small>';
  }
  if (!nm.ready || !ex.alloc) { nmEnsure(); return intro + '<p class="na">Chargement des coûts (personnel, frais généraux, véhicules)…</p>'; }
  const cols = nmCompute(pj.cur).cols, keysOf = {Total: Object.keys(cols), XC: ['XC'], CARS: NM_CARS};
  const rows = ['Total', 'XC', 'CARS'].map(sc => { const o = nmSum(cols, keysOf[sc]), mb = o.ca - o.dc, charges = mb - nmNet(o), net = nmNet(o), rate = o.ca ? mb / o.ca : null, mbP = rate == null ? null : caP[sc] * rate, proj = mbP == null ? null : mbP - charges * k;
    return `<tr><td>${sc}</td><td data-v="${net}" class="${cls(net)}">${eur(net)}<br><small class="na">MB ${eur(mb)} − charges ${eur(charges)}</small></td><td data-v="${caP[sc]}">${eur(caP[sc])}</td><td data-v="${mbP ?? ''}">${mbP == null ? 'n/d' : eur(mbP)}</td><td data-v="${charges * k}">${eur(charges * k)}</td><td data-v="${proj ?? ''}" class="${proj == null ? '' : cls(proj)}"><b>${proj == null ? 'n/d' : eur(proj)}</b>${proj == null || !caP[sc] ? '' : `<br><small class="na">${pct(proj / caP[sc])} du CA espéré</small>`}</td><td data-v="${net * k}" class="na">${eur(net * k)}</td></tr>`; });
  return intro + table(['', 'Marge nette à date', 'CA espéré ' + yr, 'Marge brute projetée', 'Charges annualisées', 'Marge nette projetée', 'Pour comparaison : linéaire'], rows, 'prodtable') + link
    + '<small class="na">Marge nette projetée = marge brute projetée (CA espéré × taux de marge brute à date) − charges imputées à date × ' + num(Math.round(k * 100) / 100) + ' (personnel, véhicules, frais généraux, Shared Services, Management, marketing : elles courent au fil du temps). Les charges suivent les hypothèses et options de « Marge nette par BU » ci-dessus. « Total » comprend aussi les comptes non affectés et les coûts non imputés.</small>';
}
const pjRedraw = () => { document.querySelectorAll('.pj-host').forEach(h => { h.innerHTML = pjHtml(h.dataset.kind); }); if (typeof homeRedraw === 'function') homeRedraw(); };
// Mise à jour des seules cellules calculées (la saisie garde son focus)
function pjUpdateCells() {
  const c = pjAll(), set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = eur(v); };
  for (let m = 1; m <= 12; m++) set('pjx-TOTAL-' + m, c.XC.rows[m - 1].val + c.CARS.rows[m - 1].val + c.OTHER.rows[m - 1].val);
  { const e = document.getElementById('pjvs'); if (e) e.innerHTML = pjVs(c.TOTAL.total, pj.prev.reduce((t, x) => t + x.ca, 0)); }
  set('pjt-XC', c.XC.total); set('pjt-CARS', c.CARS.total); set('pjt-TOTAL', c.TOTAL.total);
  const bar = document.querySelector('.pj-host[data-kind="ca"] .sdbar'); if (bar) bar.outerHTML = pjBar();
}
const pjSame = () => JSON.stringify(pj.exp) === JSON.stringify(pj.saved);
document.addEventListener('input', e => { const t = e.target; if (!t.classList || !t.classList.contains('pj-in')) return;
  const row = pj.exp[t.dataset.sc] = pj.exp[t.dataset.sc] || {};
  if (t.value === '') delete row[t.dataset.m]; else row[t.dataset.m] = Math.max(0, +t.value || 0);
  pj.dirty = !pjSame(); pj.msg = null; pjUpdateCells(); });
document.addEventListener('click', async e => {
  if (e.target.id === 'pj-reset') { pj.exp = pjClone(pj.saved); pj.dirty = false; pj.msg = null; pjRedraw(); return; }
  if (e.target.id === 'pj-zero') { pj.exp = {XC: {}, CARS: {}}; pj.dirty = !pjSame(); pj.msg = null; pjRedraw(); return; }
  if (e.target.id === 'pj-save') {
    try {
      const r = await fetch('/api/projection', {method: 'PUT', headers: {'Content-Type': 'application/json', ...pjAuth()}, body: JSON.stringify({year: pj.year, expected: pj.exp})});
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
      pj.saved = pjClone(j.expected); pj.exp = pjClone(j.expected); pj.dirty = false; pj.updated = {at: j.updated_at, by: j.updated_by}; pj.msg = {ok: true, t: 'Enregistré'};
    } catch (err) { pj.msg = {ok: false, t: err.message}; }
    pjRedraw();
  }
});
