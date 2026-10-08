// XC Detail › Contrôle des marges : articles à code PIF renseigné, avec prix de vente, coût renseigné, prix d'achat « worst case » et coût réel estimé.
// Chargé avant app.js ; utilise ses fonctions (esc, num, pct, kpi, table…) au moment de l'appel.
let mg = {data: null, error: null, loading: false, q: '', filter: 'all', at: null};
const MG_LABEL = {theoretical: 'Marge théorique', worst: 'Marge « worst case »', real: 'Marge réelle estimée'};

async function loadMargins(force) {
  mg.loading = true; mg.error = null; drawMargins();
  try {
    const r = await fetch('/api/xc/margins' + (force ? '?refresh=true' : ''), {headers: (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {}});
    if (!r.ok) throw new Error(r.status === 401 ? 'Connexion requise' : r.status === 502 ? 'Odoo est momentanément injoignable' : 'Erreur ' + r.status);
    mg.data = await r.json(); mg.at = new Date().toLocaleTimeString('fr-BE', {hour: '2-digit', minute: '2-digit'});
  } catch (e) { mg.error = e.message; }
  mg.loading = false; drawMargins();
}
function marginsBlocks() {
  return [{static: '<section class="block" data-bid="margins"><div class="block-head"><h3>Contrôle des marges : articles à code PIF</h3><span class="per-wrap"><small class="per-dates" id="mg-date">à date</small></span></div><div class="block-body" id="margins-view"><p class="na">Chargement…</p></div></section>'}];
}
const mgEur = n => n == null ? '–' : new Intl.NumberFormat('fr-BE', {style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2}).format(n);
const mgPct = v => v == null ? '–' : (Math.round(v * 10) / 10).toFixed(1).replace('.', ',') + ' %';
const mgCell = (v, rate) => `<td class="mg-${rate || 'none'}" data-v="${v == null ? '' : v}">${mgPct(v)}</td>`;
function drawMargins() {
  const el = document.getElementById('margins-view'); if (!el) return;
  const d = mg.data;
  if (!d) { el.innerHTML = mg.error ? `<p class="neg">${esc(mg.error)}</p>` : '<p class="na">Chargement…</p>'; return; }
  if (d.unavailable) { el.innerHTML = `<p class="na">${esc(d.unavailable)}</p>`; return; }
  const dt = document.getElementById('mg-date'); if (dt) dt.textContent = 'Situation au ' + fmtDate(d.as_of);
  const [fb, fl] = mg.filter === 'all' ? [null, null] : mg.filter.split(':'), matchFilter = r => !fb || (r.rate[fb] || 'unknown') === fl;
  const q = mg.q.trim().toLowerCase(), rows = d.rows.filter(r => (!q || (r.ref + ' ' + r.name + ' ' + r.pif).toLowerCase().includes(q)) && matchFilter(r));
  const s = d.summary, line = k => `<tr><td>${MG_LABEL[k]}</td><td class="mg-green">${num(s[k].green)}</td><td class="mg-orange">${num(s[k].orange)}</td><td class="mg-red">${num(s[k].red)}</td><td>${num(s[k].unknown)}</td></tr>`;
  const body = rows.map(r => {
    const w = r.worst, re = r.real, tiers = r.tiers.map(t => `${t.partner} ≥ ${num(t.min_qty)} : ${mgEur(t.price)}`).join('\n');
    return `<tr><td>${esc(r.ref)}</td><td class="prod">${esc(r.name)}</td><td>${esc(r.pif)}</td><td data-v="${r.sale}">${mgEur(r.sale)}</td><td data-v="${r.cost}">${mgEur(r.cost)}</td>`
      + `<td data-v="${w ? w.price : ''}" title="${esc(tiers)}">${w ? mgEur(w.price) + `<br><small class="na">${esc(w.partner)}</small>` : '<small class="na">pas de prix fournisseur</small>'}</td>`
      + `<td data-v="${re ? re.unit : ''}">${re ? mgEur(re.unit) + `<br><small class="na">${num(re.qty)} u. · ${re.source}</small>` : '<small class="na">aucun achat récent</small>'}</td>`
      + mgCell(r.margin.theoretical, r.rate.theoretical) + mgCell(r.margin.worst, r.rate.worst) + mgCell(r.margin.real, r.rate.real) + '</tr>';
  });
  const opts = (items, cur) => items.map(([v, l]) => `<option value="${v}"${cur === v ? ' selected' : ''}>${l}</option>`).join('');
  el.innerHTML = (d.real_error ? `<p class="neg">Coût réel indisponible (${esc(d.real_error)}) : seules les marges théorique et « worst case » sont calculées.</p>` : '')
    + `<div class="kpis">${kpi('Articles à code PIF', num(s.count), '', 'champ « ' + esc(d.pif_field) + ' » renseigné')}${kpi('Marge réelle estimée en rouge', num(s.real.red), s.real.red ? 'neg' : '', '≤ 15 %')}${kpi('En orange', num(s.real.orange), '', '15 à 25 %')}${kpi('En vert', num(s.real.green), 'pos', '> 25 %')}</div>`
    + '<h4 class="sub">Répartition par niveau de marge</h4>' + table(['Marge', 'Vert (> 25 %)', 'Orange (15 à 25 %)', 'Rouge (≤ 15 %)', 'Inconnue'], ['theoretical', 'worst', 'real'].map(line), 'prodtable')
    + `<div class="sdbar mgbar"><input type="search" class="sdin" id="mg-q" placeholder="Rechercher une référence, un article, un code PIF" value="${esc(mg.q)}" style="max-width:340px">`
    + `<select class="sdin" id="mg-filter" style="max-width:300px">${opts([['all', 'Tous les articles']].concat(['real', 'worst', 'theoretical'].flatMap(b => [['red', 'rouge'], ['orange', 'orange'], ['green', 'vert'], ['unknown', 'non calculable']].map(([l, n]) => [b + ':' + l, MG_LABEL[b] + ' : ' + n]))), mg.filter)}</select>`
    + `<button type="button" id="mg-refresh">${mg.loading ? 'Actualisation…' : 'Actualiser'}</button><span class="na">${num(rows.length)} article${rows.length > 1 ? 's' : ''} affiché${rows.length > 1 ? 's' : ''} sur ${num(d.rows.length)}${mg.at ? ' · données de ' + mg.at : ''}</span></div>`
    + (rows.length ? table(['Réf.', 'Désignation', 'PIF', 'Prix de vente', 'Coût Odoo', 'Achat « worst case »', 'Coût réel estimé', 'Marge théorique', 'Marge « worst case »', 'Marge réelle'], body, 'prodtable mgtable') : '<p class="na">Aucun article ne correspond.</p>')
    + `<small class="na">Prix de vente : prix de la fiche article, hors taxes. Coût Odoo : coût renseigné (standard_price). <b>Achat « worst case »</b> : 1 unité chez le fournisseur le plus cher (pour chaque fournisseur, le prix de son palier de plus petite quantité ; tarifs expirés et devises autres que l’euro écartés${d.foreign_currency_lines ? ' : ' + d.foreign_currency_lines + ' ligne(s) ignorée(s)' : ''}) ; passez la souris sur la cellule pour voir tous les paliers. <b>Coût réel estimé</b> : prix unitaire moyen pondéré des factures d’achat comptabilisées (avoirs déduits) depuis le ${fmtDate(d.since)} (${d.lookback_months} mois), à défaut des commandes d’achat confirmées. Marge = (prix de vente − coût) ÷ prix de vente. Vert &gt; 25 %, orange &gt; 15 % et ≤ 25 %, rouge ≤ 15 %. Une marge n’est pas calculable quand le coût, le prix fournisseur ou les achats récents sont absents ou à 0,00 € (elle n’est alors ni verte ni rouge). Le coût réel ne comprend pas les frais de transport ni de douane.</small>`;
}
document.addEventListener('input', e => { if (e.target.id !== 'mg-q') return; mg.q = e.target.value; const keep = e.target.selectionStart; drawMargins(); const n = document.getElementById('mg-q'); if (n) { n.focus(); try { n.setSelectionRange(keep, keep); } catch {} } });
document.addEventListener('change', e => { if (e.target.id === 'mg-filter') { mg.filter = e.target.value; drawMargins(); } });
document.addEventListener('click', e => { if (e.target.id === 'mg-refresh') loadMargins(true); });
