// Détail XC › Contrôle des marges : articles à code PIF renseigné ; marge théorique (prix de vente − coût Odoo) contre marge réelle estimée (coût d'après les achats réels),
// avec une illustration de l'écart. Chargé avant app.js ; utilise ses fonctions (esc, num, kpi, table…) au moment de l'appel.
let mg = {data: null, error: null, loading: false, q: '', filter: 'all', at: null};
const MG_LEVELS = [['red', 'rouge'], ['orange', 'orange'], ['green', 'vert'], ['unknown', 'non calculable']];

async function loadMargins(force) {
  mg.loading = true; mg.error = null; drawMargins();
  try {
    const r = await fetch('/api/xc/margins' + (force ? '?refresh=true' : ''), {headers: (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {}});
    if (!r.ok) throw new Error(r.status === 401 ? 'Connexion requise' : r.status === 502 ? 'Odoo est momentanément injoignable' : 'Erreur ' + r.status);
    mg.data = await r.json(); mg.at = new Date().toLocaleTimeString(LOCALE(), {hour: '2-digit', minute: '2-digit'});
  } catch (e) { mg.error = e.message; }
  mg.loading = false; drawMargins();
}
function marginsBlocks() {
  return [{static: '<section class="block" data-bid="margins"><div class="block-head"><h3>Contrôle des marges s/ produits : articles à code PIF</h3><span class="per-wrap"><small class="per-dates" id="mg-date">à date</small></span></div><div class="block-body" id="margins-view"><p class="na">Chargement…</p></div></section>'}];
}
const mgEur = n => n == null ? '–' : new Intl.NumberFormat(LOCALE(), {style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2}).format(n);
const mgPct = v => v == null ? '–' : (Math.round(v * 10) / 10).toFixed(1).replace('.', ',') + ' %';
const mgPts = v => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(Math.round(v * 10) / 10).toFixed(1).replace('.', LANG === 'en' ? '.' : ',') + ' pts';

// Illustration de l'écart : sur une échelle de marge (−20 % à 80 %) avec les zones rouge (≤ 15 %), orange et verte (> 25 %), le rond creux marque la marge théorique,
// le rond plein la marge réelle, et le trait entre les deux l'écart (rouge s'il y a perte de marge, vert sinon).
const MG_LO = -20, MG_HI = 80, mgX = v => Math.min(100, Math.max(0, (v - MG_LO) / (MG_HI - MG_LO) * 100));
function mgDumbbell(theo, real, rt, big = false) {
  if (theo == null && real == null) return '<span class="na">–</span>';
  const a = theo != null ? mgX(theo) : null, b = real != null ? mgX(real) : null;
  const line = a != null && b != null ? `<i class="mgl ${real < theo ? 'loss' : 'gain'}" style="left:${Math.min(a, b)}%;width:${Math.abs(a - b)}%"></i>` : '';
  const tip = `Théorique ${mgPct(theo)} → réelle ${mgPct(real)}${theo != null && real != null ? ' (' + mgPts(real - theo) + ')' : ''}`;
  return `<span class="mgdb${big ? ' big' : ''}" title="${esc(tip)}"><span class="mgz"><i class="r" style="width:${mgX(15)}%"></i><i class="o" style="left:${mgX(15)}%;width:${mgX(25) - mgX(15)}%"></i><i class="g" style="left:${mgX(25)}%;width:${100 - mgX(25)}%"></i></span>`
    + line + (a != null ? `<i class="mgp theo" style="left:${a}%"></i>` : '') + (b != null ? `<i class="mgp real mg-bg-${rt || 'none'}" style="left:${b}%"></i>` : '') + '</span>';
}
const mgCell = (v, rate) => `<td class="mg-${rate || 'none'}" data-v="${v == null ? '' : v}">${mgPct(v)}</td>`;

function drawMargins() {
  const el = document.getElementById('margins-view'); if (!el) return;
  const d = mg.data;
  if (!d) { el.innerHTML = mg.error ? `<p class="neg">${esc(mg.error)}</p>` : '<p class="na">Chargement…</p>'; return; }
  if (d.unavailable) { el.innerHTML = `<p class="na">${esc(d.unavailable)}</p>`; return; }
  const dt = document.getElementById('mg-date'); if (dt) dt.textContent = 'Situation au ' + fmtDate(d.as_of);
  const s = d.summary, q = mg.q.trim().toLowerCase(), [fk, fv] = mg.filter === 'all' ? [null, null] : mg.filter.split(':');
  const match = r => !fk || (fk === 'gap' ? r.gap != null && r.gap <= -(+fv) : (r.rate[fk] || 'unknown') === fv);
  const rows = d.rows.filter(r => (!q || (r.ref + ' ' + r.name + ' ' + r.pif).toLowerCase().includes(q)) && match(r));
  const maxB = Math.max(1, ...s.buckets.map(b => b.count)), bcol = ['#ff5a5f', '#ff8a5c', '#f5a623', '#9aa0a6', '#2ecc71'];
  const hist = s.buckets.map((b, i) => `<div class="row"><span>${esc(b.label)}</span><div class="bars"><div class="bar solo" style="width:${b.count / maxB * 100}%;background:${bcol[i]}"></div></div><span class="num">${num(b.count)}</span></div>`).join('');
  // Colonnes selon le filtre : filtre sur la marge réelle -> seulement la marge réelle ; sur la marge théorique -> seulement la théorique ; sinon les deux et l'écart.
  const mode = fk === 'real' ? 'real' : fk === 'theoretical' ? 'theo' : 'both';
  const cell = {
    ref: [r => `<td>${esc(r.ref)}<br><small class="na">PIF ${esc(r.pif)}</small></td>`, 'Réf.'],
    name: [r => `<td class="prod">${esc(r.name)}</td>`, 'Désignation'],
    sale: [r => `<td data-v="${r.sale}">${mgEur(r.sale)}</td>`, 'Prix de vente'],
    price: [r => `<td data-v="${r.sale}">${mgEur(r.sale)}<br><small class="na">coût Odoo ${r.cost > 0 ? mgEur(r.cost) : 'non renseigné'}</small></td>`, 'Prix de vente / coût Odoo'],
    cost: [r => `<td data-v="${r.cost > 0 ? r.cost : ''}">${r.cost > 0 ? mgEur(r.cost) : '<small class="na">non renseigné</small>'}</td>`, 'Coût Odoo'],
    real: [r => { const re = r.real; return `<td data-v="${re ? re.unit : ''}" title="${re ? esc(`Achat ${mgEur(re.buy)} + transport ${mgEur(re.freight)} · ${num(re.qty)} unités · ${re.source}${(re.flags || []).length ? ' · facture globale répartie' : ''}`) : ''}">${re ? mgEur(re.unit) + `<br><small class="na">dont transport ${mgEur(re.freight)} · ${num(re.qty)} u.${(re.flags || []).length ? ' · globale' : ''}</small>` : '<small class="na">aucun achat récent</small>'}</td>`; }, 'Coût réel estimé'],
    mtheo: [r => mgCell(r.margin.theoretical, r.rate.theoretical), 'Marge théorique'],
    mreal: [r => mgCell(r.margin.real, r.rate.real), 'Marge réelle'],
    gap: [r => `<td data-v="${r.gap == null ? '' : r.gap}" class="mggap"><span class="${r.gap == null ? '' : r.gap < -0.05 ? 'mg-red' : 'mg-green'}">${mgPts(r.gap)}</span>${mgDumbbell(r.margin.theoretical, r.margin.real, r.rate.real)}</td>`, 'Théorique → réelle'],
  };
  const order = mode === 'real' ? ['ref', 'name', 'sale', 'real', 'mreal'] : mode === 'theo' ? ['ref', 'name', 'sale', 'cost', 'mtheo'] : ['ref', 'name', 'price', 'real', 'mtheo', 'mreal', 'gap'];
  const body = rows.map(r => `<tr>${order.map(c => cell[c][0](r)).join('')}</tr>`);
  const opts = (items, cur) => items.map(([v, l]) => `<option value="${v}"${cur === v ? ' selected' : ''}>${l}</option>`).join('');
  const fopts = [['all', 'Tous les articles'], ['gap:10', 'Écart de 10 pts ou plus en dessous'], ['gap:5', 'Écart de 5 pts ou plus en dessous']]
    .concat(['real', 'theoretical'].flatMap(b => MG_LEVELS.filter(([l]) => l !== 'unknown').map(([l, n]) => [b + ':' + l, (b === 'real' ? 'Marge réelle : ' : 'Marge théorique : ') + n])));
  const cmp = s.avg_real != null && s.avg_theoretical != null ? s.avg_real - s.avg_theoretical : null;
  el.innerHTML = (d.real_error ? `<p class="neg">Coût réel indisponible (${esc(d.real_error)}) : seule la marge théorique est calculée.</p>` : '')
    + `<div class="kpis">${kpi('Articles à code PIF', num(s.count), '', `${num(s.compared)} comparables (coût Odoo et achats récents connus)`)}`
    + `${kpi('Transport réparti', d.freight && d.freight.pool ? '+' + mgPct(d.freight.rate * 100) : '–', '', d.freight && d.freight.pool ? 'du prix de vente, soit ' + mgEur(d.freight.pool) + ' (compte ' + esc(d.freight.accounts) + ')' : 'aucun compte de transport')}`
    + `${kpi('Marge théorique moyenne', mgPct(s.avg_theoretical), '', 'prix de vente − coût Odoo')}${kpi('Marge réelle moyenne', mgPct(s.avg_real), cmp != null && cmp < -0.05 ? 'neg' : '', cmp != null ? mgPts(cmp) + ' par rapport à la théorie' : '')}`
    + `${kpi('Marge réelle en rouge', num(s.real.red), s.real.red ? 'neg' : '', `≤ 15 % · théorique : ${num(s.theoretical.red)}`)}</div>`
    + '<h4 class="sub">Ampleur de l’écart entre marge théorique et marge réelle</h4>'
    + `<div class="card mghist">${hist}</div><small class="na">Écart = marge réelle − marge théorique, en points de marge, sur les ${num(s.compared)} articles dont le coût Odoo et les achats récents sont connus. Un écart négatif signifie que l’article rapporte moins que son coût Odoo ne le laisse croire.</small>`
    + '<h4 class="sub">Tous les articles</h4>'
    + `<div class="sdbar mgbar"><input type="search" class="sdin" id="mg-q" placeholder="Rechercher une référence, un article, un code PIF" value="${esc(mg.q)}" style="max-width:340px">`
    + `<select class="sdin" id="mg-filter" style="max-width:300px">${opts(fopts, mg.filter)}</select><button type="button" id="mg-refresh">${mg.loading ? 'Actualisation…' : 'Actualiser'}</button>`
    + `<span class="na">${num(rows.length)} article${rows.length > 1 ? 's' : ''} affiché${rows.length > 1 ? 's' : ''} sur ${num(d.rows.length)}${mg.at ? ' · données de ' + mg.at : ''}</span></div>`
    + (rows.length ? table(order.map(c => cell[c][1]), body, 'prodtable mgtable') : '<p class="na">Aucun article ne correspond.</p>')
    + `<small class="na">Prix de vente : prix de la fiche article, hors taxes. Coût Odoo : coût renseigné (standard_price). <b>Coût réel estimé</b> = coût d’achat + transport. <i>Coût d’achat</i> : d’après les commandes d’achat et leurs factures comptabilisées depuis le ${fmtDate(d.since)} (${d.lookback_months} mois) : une facture cohérente avec la commande donne le prix facturé ; une facture « globale » (par exemple 1 pièce facturée pour 30 reçues, ou qui couvre aussi d’autres lignes de la commande) est ramenée à la quantité reçue, chaque ligne reçoit au plus son prix de commande et l’excédent est réparti sur les autres lignes reçues non encore facturées de la même commande ; à défaut de facture, prix des commandes confirmées. <i>Transport</i> : solde des comptes ${esc(d.freight ? d.freight.accounts : '')} sur la même période, réparti au prorata du prix de vente des unités achetées (soit +${d.freight ? mgPct(d.freight.rate * 100) : '–'} du prix de vente de chaque article). Marge = (prix de vente − coût) ÷ prix de vente ; vert &gt; 25 %, orange &gt; 15 % et ≤ 25 %, rouge ≤ 15 %. Une marge n’est pas calculable quand le coût Odoo est à 0,00 € ou qu’aucun achat récent n’existe. Les droits de douane ne sont pas pris en compte. Les colonnes se trient d’un clic.</small>`;
}
document.addEventListener('input', e => { if (e.target.id !== 'mg-q') return; mg.q = e.target.value; const keep = e.target.selectionStart; drawMargins(); const n = document.getElementById('mg-q'); if (n) { n.focus(); try { n.setSelectionRange(keep, keep); } catch {} } });
document.addEventListener('change', e => { if (e.target.id === 'mg-filter') { mg.filter = e.target.value; drawMargins(); } });
document.addEventListener('click', e => { if (e.target.id === 'mg-refresh') loadMargins(true); });
