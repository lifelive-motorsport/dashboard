// Détail XC › Stock : valorisation du stock au coût moyen (top des références à code PIF, répartition par code PIF, points d'attention).
// Chargé avant app.js ; utilise ses fonctions (esc, eur, num, pct, kpi, table, NOTE…) au moment de l'appel.
let stockState = {data: null, error: null, loading: false};

async function loadStock(force) {
  stockState.loading = true; stockState.error = null; drawStock();
  try {
    const r = await fetch('/api/stock' + (force ? '?refresh=true' : ''), {headers: (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {}});
    if (!r.ok) throw new Error(r.status === 401 ? 'Connexion requise' : r.status === 502 ? 'Odoo est momentanément injoignable' : 'Erreur ' + r.status);
    stockState.data = await r.json();
  } catch (e) { stockState.error = e.message; }
  stockState.loading = false;
}

function stockBlocks() {
  return [{static: '<section class="block" data-bid="stock"><div class="block-head"><h3>Valorisation du stock XC</h3><span class="per-wrap"><small class="per-dates" id="stock-date">à date</small></span></div><div class="block-body" id="stock-view"><p class="na">Chargement…</p></div></section>'}];
}

const sNum = n => num(Math.round(n * 100) / 100);
function drawStock() {
  const el = document.getElementById('stock-view'); if (!el) return;
  const d = stockState.data;
  if (!d) { el.innerHTML = stockState.error ? `<p class="neg">${esc(stockState.error)}</p>` : '<p class="na">Chargement…</p>'; return; }
  if (d.unavailable) { el.innerHTML = `<p class="na">${esc(d.unavailable)}</p>`; return; }
  const dt = document.getElementById('stock-date'); if (dt) dt.textContent = 'Situation au ' + fmtDate(d.as_of);
  const t = d.total, a = d.attention, pifSet = !!d.pif_field;
  const sign = v => (v < 0 ? '–' : '') + eur(Math.abs(v));
  const top = d.top.map((x, i) => `<tr><td>${i + 1}</td><td>${esc(x.ref)}</td><td class="prod">${esc(x.name)}</td><td>${esc(x.pif)}</td><td>${eur(x.cost)}</td><td>${sNum(x.qty)}</td><td><b>${eur(x.value)}</b></td><td>${pct(x.cum)}</td></tr>`)
    .concat([`<tr class="tot"><td></td><td></td><td>Total top ${d.top.length}</td><td></td><td></td><td></td><td>${eur(d.top_value)}</td><td>${pct(d.top_share)}</td></tr>`]);
  const rep = d.by_pif.map(c => `<tr><td>${esc(c.code)}</td><td>${num(c.refs)}</td><td>${sign(c.value)}</td><td>${sign(c.positive)}</td><td class="neg">${sign(c.negative)}</td></tr>`);
  const sub = d.by_pif.reduce((s, c) => ({refs: s.refs + c.refs, value: s.value + c.value, positive: s.positive + c.positive, negative: s.negative + c.negative}), {refs: 0, value: 0, positive: 0, negative: 0});
  const e = d.pif_empty;
  rep.push(`<tr class="tot"><td>Sous-total PIF renseigné</td><td>${num(sub.refs)}</td><td>${sign(sub.value)}</td><td>${sign(sub.positive)}</td><td class="neg">${sign(sub.negative)}</td></tr>`,
    `<tr><td>PIF vide</td><td>${num(e.refs)}</td><td>${sign(e.value)}</td><td>${sign(e.positive)}</td><td class="neg">${sign(e.negative)}</td></tr>`,
    `<tr class="tot"><td>Total stock XC</td><td>${num(t.refs)}</td><td>${sign(t.value)}</td><td>${sign(t.positive)}</td><td class="neg">${sign(t.negative)}</td></tr>`);
  const li = (x, f) => x.map(f).join(', ');
  const pt = (title, html) => `<div class="note"><b>${title}</b><br>${html}</div>`;
  const pts = [];
  if (a.negatives.refs) pts.push(pt('Stocks négatifs', `Le total net de ${eur(t.value)} intègre ${sign(a.negatives.value)} de stocks négatifs répartis sur ${num(a.negatives.refs)} référence${a.negatives.refs > 1 ? 's' : ''}. Les principaux : ${li(a.negatives.top, x => `${esc(x.name)} [${esc(x.ref)}] à ${sNum(x.qty)} unité${Math.abs(x.qty) > 1 ? 's' : ''} (${sign(x.value)})`)}. Ces écarts proviennent en général de sorties enregistrées sans réception correspondante. Une fois corrigés, la valeur totale se rapprochera de ${eur(t.positive)}.`));
  if (a.zero_cost.refs) pts.push(pt('Articles valorisés à zéro', `${num(a.zero_cost.refs)} référence${a.zero_cost.refs > 1 ? 's ont' : ' a'} du stock en main (${sNum(a.zero_cost.units)} unités au total) mais un coût moyen nul : valorisé${a.zero_cost.refs > 1 ? 'es' : 'e'} à 0 €, ce qui peut sous-estimer la valeur réelle du stock.`));
  if (a.volumes.length) pts.push(pt('Volumes à vérifier', `${li(a.volumes, x => `${esc(x.name)} [${esc(x.ref)}] (${sNum(x.qty)} pièces)`)} figurent dans le top 10 en valeur grâce à leur volume. Un contrôle physique permettrait d’écarter une erreur d’unité ou de saisie.`));
  if (a.decimals.length) pts.push(pt('Unité de mesure', `${li(a.decimals, x => `${esc(x.name)} [${esc(x.ref)}] affiche une quantité décimale (${sNum(x.qty)})`)} alors que l’unité est « Units » : il s’agit probablement d’un article géré au mètre ou au poids, l’unité Odoo mérite d’être vérifiée.`));
  if (a.pairs.length) pts.push(pt('Cohérence des paires', `Paires gauche / droite déséquilibrées : ${li(a.pairs, p => `${esc(p.a)} (${sNum(p.a_qty)}) contre ${esc(p.b)} (${sNum(p.b_qty)})`)}.`));
  if (a.no_pif.refs) pts.push(pt('Couverture du code PIF', `${num(a.no_pif.refs)} référence${a.no_pif.refs > 1 ? 's' : ''} (${eur(a.no_pif.value)}, soit ${pct(a.no_pif.share)} de la valeur) n’${a.no_pif.refs > 1 ? 'ont' : 'a'} pas de code PIF.${a.no_pif.top.length ? ' Les plus valorisées : ' + li(a.no_pif.top, x => `${esc(x.name)} [${esc(x.ref)}] (${eur(x.value)})`) + '.' : ''}`));
  el.innerHTML = (pifSet ? '' : '<p class="neg">Champ « code PIF » introuvable dans Odoo : les classements par code PIF sont vides. Indiquez son nom technique avec la variable STOCK_PIF_FIELD.</p>')
    + `<div class="kpis">${kpi('Stock total XC', eur(t.value), '', `${num(t.refs)} références`)}${kpi('Stock à PIF renseigné', eur(d.pif.value), '', `${pct(d.pif.share)} du stock total`)}${kpi('Top ' + d.top.length + ' PIF', eur(d.top_value), '', `${pct(d.top_share)} du stock à PIF`)}</div>`
    + `<h4 class="sub">Top ${d.top.length} des références à code PIF par valeur de stock</h4>` + table(['#', 'Référence', 'Désignation', 'PIF', 'Coût moyen', 'Qté', 'Valeur', 'Cumul'], top, 'prodtable stock')
    + '<small class="na">Cumul : part cumulée de la valeur du stock à PIF renseigné. Valorisation au coût moyen Odoo (quantité en main × coût), tous emplacements internes.</small>'
    + '<h4 class="sub">Répartition de la valeur par code PIF</h4>' + table(['Code PIF', 'Nb réf.', 'Valeur nette', 'dont stock positif', 'dont stock négatif'], rep, 'prodtable')
    + (pts.length ? '<h4 class="sub">Points d’attention</h4>' + pts.join('') : '')
    + `<div class="note"><b>En synthèse</b> : selon le traitement des stocks négatifs, une valeur défendable du stock XC se situe entre ${eur(t.value)} et ${eur(t.positive)}, avant décote éventuelle des références lentes ou obsolètes.</div>`;
}
