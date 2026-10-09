// Overview › « Projections annualisées » (Chiffre d’affaires, Marge brute, Marge nette). Chargé avant app.js.
// Deux méthodes, toujours expliquées à l’écran :
//  - linéaire : réalisé à date × (jours de l’année ÷ jours écoulés) ;
//  - saisonnalité N-1 : réalisé à date × (année N-1 complète ÷ N-1 à la même date), pour tenir compte des mois forts (courses, saison de vente).
// Marge nette : « mixte » = marge brute annualisée selon la saisonnalité N-1, moins les charges imputées annualisées de façon linéaire (le personnel et les frais généraux courent au fil du temps).
const pj = {ready: false, loading: null, err: null, cur: null, same: null, full: null, days: null};
const PJ_TITLE = {ca: 'Chiffre d’affaires', mb: 'Marge brute', mn: 'Marge nette'};
function PJ_BLOCK(kind) {
  return B('pj_' + kind, 'Projections annualisées', () => { pjEnsure(); return `<div class="pj-host" data-kind="${kind}">${pjHtml(kind)}</div>`; }, true);
}
function pjDays() {
  const t = new Date(), y = t.getFullYear(), elapsed = Math.floor((new Date(y, t.getMonth(), t.getDate()) - new Date(y, 0, 1)) / 864e5) + 1;
  const len = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 366 : 365;
  return {y, elapsed, len, k: len / elapsed, to: ymd(t)};
}
async function pjEnsure() {
  if (pj.ready && pj.days && pj.days.to !== ymd(new Date())) pj.ready = false;          // nouveau jour : on recalcule
  if (pj.ready || pj.loading) return;
  pj.days = pjDays();
  const {y, to} = pj.days, mmdd = to.slice(5);
  pj.loading = (async () => {
    try {
      const [cur, same, full] = await Promise.all([getRange(`${y}-01-01`, to), getRange(`${y - 1}-01-01`, `${y - 1}-${mmdd === '02-29' ? '02-28' : mmdd}`), getRange(`${y - 1}-01-01`, `${y - 1}-12-31`)]);
      pj.cur = viewData(cur); pj.same = viewData(same); pj.full = viewData(full); pj.err = null; pj.ready = true;
    } catch (e) { pj.err = e.message; }
    pj.loading = null; pjRedraw();
  })();
  pj.loading.catch(() => {});
}
const PJ_SCOPES = [['Total', d => d.pnl.total], ['XC', d => grp(d, 'XC')], ['CARS', d => grp(d, 'CARS')]];
const pjVal = (d, scope, kind) => { const o = PJ_SCOPES.find(x => x[0] === scope)[1](d); return kind === 'ca' ? o.ca : o.margin; };
const pjSeason = (scope, kind) => { const a = pjVal(pj.same, scope, kind), b = pjVal(pj.full, scope, kind); return a > 0 && b > 0 ? b / a : null; };
const pjEur = v => v == null ? '<span class="na">n/d</span>' : eur(v);
const pjDelta = (v, ref) => v == null || !ref ? '' : `<br><small class="${v >= ref ? 'pos' : 'neg'}">${v >= ref ? '▲ +' : '▼ '}${((v / ref - 1) * 100).toFixed(1).replace('.', ',')} % vs N-1</small>`;

function pjHtml(kind) {
  if (pj.err) return `<p class="neg">Projection indisponible : ${esc(pj.err)}</p>`;
  if (!pj.ready) return '<p class="na">Calcul des projections (année en cours et année précédente)…</p>';
  const {y, elapsed, len, k} = pj.days, yr = y - 1;
  const intro = `<p class="na">Au ${fmtDate(pj.days.to)} : ${elapsed} jours écoulés sur ${len} (${(elapsed / len * 100).toFixed(0)} % de l’année).</p>`;
  const note = '<small class="na"><b>Linéaire</b> : réalisé à date × ' + num(Math.round(k * 100) / 100) + ' (jours de l’année ÷ jours écoulés) ; suppose une activité régulière toute l’année. <b>Saisonnalité ' + yr + '</b> : réalisé à date × (année ' + yr + ' complète ÷ ' + yr + ' à la même date) ; suppose que l’année se déroule comme ' + yr + ' (à privilégier quand l’activité est saisonnière, ex. courses). Ce sont des extrapolations, pas des prévisions : un gros événement à venir ou déjà facturé fausse l’une comme l’autre. Les ajustements de marge brute et variations de stock suivent les options actives (MB ajustée / stock).</small>';
  if (kind !== 'mn') {
    const rows = PJ_SCOPES.map(([sc]) => { const v = pjVal(pj.cur, sc, kind), lin = v * k, f = pjSeason(sc, kind), sea = f == null ? null : v * f, prev = pjVal(pj.full, sc, kind);
      return `<tr><td>${sc}</td><td data-v="${v}">${eur(v)}</td><td data-v="${lin}">${eur(lin)}${pjDelta(lin, prev)}</td><td data-v="${sea ?? ''}">${pjEur(sea)}${pjDelta(sea, prev)}</td><td data-v="${prev}">${eur(prev)}</td></tr>`; });
    return intro + table(['', 'Réalisé à date', 'Projection linéaire', 'Projection saisonnalité ' + yr, 'Année ' + yr + ' complète'], rows, 'prodtable') + note;
  }
  if (!nm.ready || !ex.alloc) { nmEnsure(); return intro + '<p class="na">Chargement des coûts (personnel, frais généraux, véhicules)…</p>'; }
  const cols = nmCompute(pj.cur).cols, keysOf = {Total: Object.keys(cols), XC: ['XC'], CARS: NM_CARS};
  const rows = PJ_SCOPES.map(([sc]) => { const o = nmSum(cols, keysOf[sc]), mb = o.ca - o.dc, charges = mb - nmNet(o), net = nmNet(o), lin = net * k, f = pjSeason(sc, 'mb'), mix = f == null ? null : mb * f - charges * k, caLin = o.ca * k;
    const pc = v => v == null || !caLin ? '' : `<br><small class="na">${pct(v / caLin)} du CA projeté</small>`;
    return `<tr><td>${sc}</td><td data-v="${net}" class="${cls(net)}">${eur(net)}<br><small class="na">MB ${eur(mb)} − charges ${eur(charges)}</small></td><td data-v="${lin}" class="${cls(lin)}">${eur(lin)}${pc(lin)}</td><td data-v="${mix ?? ''}" class="${mix == null ? '' : cls(mix)}">${pjEur(mix)}${pc(mix)}</td></tr>`; });
  return intro + table(['', 'Réalisé à date', 'Projection linéaire', 'Projection mixte (MB saisonnalité ' + yr + ')'], rows, 'prodtable') + note
    + '<small class="na">Marge nette : les charges imputées (personnel, véhicules, frais généraux, Shared Services, Management, marketing) suivent les hypothèses et options de la section « Marge nette par BU » ci-dessus. <b>Mixte</b> : marge brute selon la saisonnalité ' + yr + ' moins les charges annualisées de façon linéaire. « Total » comprend aussi les comptes non affectés et les coûts non imputés.</small>';
}
const pjRedraw = () => document.querySelectorAll('.pj-host').forEach(h => { h.innerHTML = pjHtml(h.dataset.kind); });
