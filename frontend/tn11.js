// Détail XC › Contrôle des marges s/ TN11 : on dépose le PDF d'un devis ; chaque ligne vendue (marquée « x ») est comparée à Odoo :
// prix de vente propre de l'article, coût Odoo (théorique), coût réel estimé (nomenclature Odoo + achats réels + transport) et main-d'œuvre rendue visible.
// Chargé avant app.js ; utilise ses fonctions (esc, num, kpi, table, fmtDate…) au moment de l'appel.
let tn = {excl: new Set(), open: new Set(), openTop: new Set(), rep: null, loading: false, error: null, name: '', grouped: true, sort: {k: 'devis', dir: 'asc'}};
// Colonnes triables : clé -> [libellé, valeur d'une ligne, valeur d'un groupe (calculée sur ses lignes retrouvées)]
const TN_COLS = {ref: ['Réf.'], name: ['Désignation'], qty: ['Qté'], sale: ['Prix de vente théorique'], odoo: ['Coût Odoo'], real: ['Coût réel estimé'], mtheo: ['Marge théorique'], mreal: ['Marge réelle'], labour: ['Main-d’œuvre']};
const TN_SORTS = [['devis', 'Ordre du devis'], ['sale', 'Prix de vente'], ['odoo', 'Coût Odoo'], ['real', 'Coût réel estimé'], ['mtheo', 'Marge théorique'], ['mreal', 'Marge réelle'], ['gap', 'Écart entre les deux marges'], ['labour', 'Main-d’œuvre'], ['name', 'Désignation'], ['ref', 'Référence']];
const tnOn = r => r.found && !tn.excl.has(r._k);
// Chevauchements possibles : une ligne vendue dont le libellé relève du même poste (peinture, soudure, galvanisation…) qu'un composant d'une AUTRE ligne vendue.
const TN_CONCEPTS = {peinture: /powder|thermolaq|laquage|peintur|paint|coating/i, soudure: /souda|weld/i, galvanisation: /galva|zinc/i, 'découpe / cintrage': /d[ée]coupe|cintrage|cutting|bending|laser/i, assemblage: /assemblage|assembly|montage|mounting/i, 'certification': /certificat|homolog/i};
const tnConcepts = n => Object.keys(TN_CONCEPTS).filter(k => TN_CONCEPTS[k].test(n || ''));
function tnOverlaps(rep) {
  const out = {};
  const found = rep.rows.filter(r => r.found);
  found.forEach(a => {
    const ca = tnConcepts((a.name_odoo || a.name)), hits = [];
    found.forEach(b => { if (b === a) return;
      (b.parts || []).forEach(p => { if (p.ref && p.ref === a.ref) hits.push({b, p, why: 'même article'}); else { const c = tnConcepts(p.name).filter(x => ca.includes(x)); if (c.length) hits.push({b, p, why: c[0]}); } });
    });
    if (hits.length) out[a._k] = hits;
  });
  return out;
}
const tnLab = r => r.self_labour ? r.real : r.labour_cost;
const tnVal = (r, k) => !r.found ? null : ({ref: r.ref, name: (r.name_odoo || r.name).toLowerCase(), qty: r.qty, sale: r.sale_total, odoo: r.odoo, real: r.real, mtheo: r.margin.theoretical, mreal: r.margin.real, gap: r.margin.theoretical != null && r.margin.real != null ? r.margin.real - r.margin.theoretical : null, labour: tnLab(r)})[k];
const tnGroupVal = (rows, k) => { const f = rows.filter(r => r.found), s = f.reduce((a, r) => a + r.sale_total, 0), o = f.reduce((a, r) => a + r.odoo, 0), c = f.reduce((a, r) => a + r.real, 0);
  return ({sale: s, odoo: o, real: c, labour: f.reduce((a, r) => a + tnLab(r), 0), mtheo: s ? (s - o) / s * 100 : null, mreal: s ? (s - c) / s * 100 : null, gap: s ? (o - c) / s * 100 : null, qty: f.length, name: (rows[0].section || '').toLowerCase(), ref: (rows[0].section || '').toLowerCase()})[k]; };
const tnCmp = (a, b, dir) => a === null || b === null ? (a === null) - (b === null) : (dir === 'asc' ? 1 : -1) * (typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), 'fr', {numeric: true}));
const tnSortRows = rows => tn.sort.k === 'devis' ? rows : rows.slice().sort((x, y) => tnCmp(tnVal(x, tn.sort.k), tnVal(y, tn.sort.k), tn.sort.dir));

function tn11Blocks() {
  return [{static: '<section class="block" data-bid="tn11"><div class="block-head"><h3>Contrôle d’un devis TN11</h3></div><div class="block-body" id="tn11-view"><p class="na">Chargement…</p></div></section>'}];
}
const tnEur = n => n == null ? '–' : new Intl.NumberFormat(LOCALE(), {style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2}).format(n);
const tnEur0 = n => n == null ? '–' : new Intl.NumberFormat(LOCALE(), {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(n);
const tnPct = v => v == null ? '–' : (Math.round(v * 10) / 10).toFixed(1).replace('.', ',') + ' %';
const tnH = min => { if (!min) return '–'; const h = Math.floor(min / 60), m = Math.round(min % 60); return (h ? h + ' h ' : '') + (m ? String(m).padStart(2, '0') + ' min' : ''); };
const tnM = (v, rate) => `<td class="mg-${rate || 'none'}" data-v="${v == null ? '' : v}">${tnPct(v)}</td>`;

async function tnUpload(file) {
  tn.loading = true; tn.error = null; tn.name = file.name; drawTn11();
  try {
    const r = await fetch('/api/xc/tn11/check', {method: 'POST', headers: {'Content-Type': 'application/pdf', ...((typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {})}, body: await file.arrayBuffer()});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    tn.rep = j; tn.excl = new Set(); j.rows.forEach((r, i) => { r._k = i; });
  } catch (e) { tn.error = e.message; tn.rep = null; }
  tn.loading = false; drawTn11();
}

function tnLabourSection(rep) {
  const items = [];
  rep.rows.filter(tnOn).forEach(r => {
    if (r.self_labour) items.push({line: r, kind: 'Ligne vendue', label: r.name_odoo || r.name, minutes: null, cost: r.real, why: 'article de main-d’œuvre : ' + r.self_labour});
    else r.labour.forEach(l => items.push({line: r, kind: l.kind === 'operation' ? 'Opération de nomenclature' : 'Composant main-d’œuvre', label: l.label, minutes: l.minutes, cost: l.cost, why: l.reason || (l.kind === 'operation' ? 'temps de poste de travail × coût horaire' : '')}));
  });
  if (!items.length) return '<h4 class="sub">Main-d’œuvre</h4><p class="na">Aucune main-d’œuvre repérée dans ce devis ni dans les nomenclatures des articles vendus. Si c’est anormal, vérifiez les motifs de détection (' + esc((rep.labour_like || []).join(', ')) + ') ou les opérations de vos nomenclatures.</p>';
  const tot = items.reduce((t, i) => t + i.cost, 0), mins = items.reduce((t, i) => t + (i.minutes || 0), 0);
  return '<h4 class="sub">Main-d’œuvre : toutes les lignes concernées</h4>' + table(['Ligne du devis', 'Origine', 'Libellé', 'Temps', 'Coût'],
    items.map(i => `<tr><td class="prod">${esc(i.line.ref)} ${esc(i.line.name_odoo || i.line.name)}</td><td>${esc(i.kind)}<br><small class="na">${esc(i.why)}</small></td><td class="prod">${esc(i.label)}</td><td data-v="${i.minutes == null ? '' : i.minutes}">${i.minutes == null ? '–' : tnH(i.minutes)}</td><td data-v="${i.cost}">${tnEur(i.cost)}</td></tr>`)
      .concat([`<tr class="tot"><td>Total (${items.length} élément${items.length > 1 ? 's' : ''})</td><td></td><td></td><td>${tnH(mins)}</td><td>${tnEur(tot)}</td></tr>`]), 'prodtable')
    + '<small class="na">La main-d’œuvre est repérée de trois façons : (1) les opérations des nomenclatures Odoo (temps × coût horaire du poste de travail) ; (2) les composants qui sont des articles de type service ou dont le nom ou la catégorie contient un motif de main-d’œuvre (' + esc((rep.labour_like || []).slice(0, 8).join(', ')) + '…) ; (3) les lignes vendues qui sont elles-mêmes de la main-d’œuvre. Elle est déjà comprise dans le coût réel ; elle est isolée ici pour la rendre visible.</small>';
}

function tnPartRow(p, ind) {
  return `<tr class="${p.warn ? 'tn-warn' : ''}"><td>${esc(p.ref)}</td><td class="prod" style="padding-left:${ind}px">${p.labour ? '🛠 ' : ''}${esc(p.name)}</td><td>${num(p.qty)} ${esc(p.uom || '')}</td><td>${tnEur(p.odoo)}</td><td>${p.real_unit == null ? '–' : tnEur(p.real_unit)}</td><td>${tnEur(p.unit)}</td><td>${tnEur(p.cost)}</td><td>${p.warn ? '<b class="neg">⚠ ' : '<small class="na">'}${esc(p.source)}${p.purchased_qty != null ? ' · ' + num(p.purchased_qty) + ' achetés' : ''}${(p.buy_flags || []).length ? ' · ' + esc(p.buy_flags.join(', ')) : ''}${p.warn ? '</b>' : '</small>'}</td></tr>`;
}

// Détail d'une ligne vendue : une ligne par ligne de la nomenclature Odoo (premier niveau) ; les sous-ensembles (qui ont leur propre nomenclature) se déplient sur leurs composants.
function tnParts(r) {
  const groups = [];
  r.parts.forEach(p => { const t = p.top || {id: 0, ref: '', name: 'Opérations', qty: 1, uom: ''}; let g = groups.find(x => x.t.id === t.id && x.t.ref === t.ref); if (!g) groups.push(g = {t, parts: []}); g.parts.push(p); });
  const body = groups.map(g => {
    const single = g.parts.length === 1 && g.parts[0].depth <= 1, key = r.id + ':' + g.t.id, open = tn.openTop.has(key), cost = g.parts.reduce((a, p) => a + p.cost, 0);
    if (single) return tnPartRow(g.parts[0], 4);
    const warn = g.parts.some(p => p.warn);
    return `<tr class="tn-sub"><td>${esc(g.t.ref)}</td><td class="prod"><button type="button" class="tnopen" data-tnsub="${key}">${open ? '▾' : '▸'}</button> <b>${esc(g.t.name)}</b> <small class="na">sous-ensemble · ${g.parts.length} composants</small>${warn ? ' <span class="neg">⚠</span>' : ''}</td><td>${num(g.t.qty)} ${esc(g.t.uom || '')}</td><td>${tnEur(g.t.odoo)}</td><td></td><td></td><td><b>${tnEur(cost)}</b></td><td></td></tr>` + (open ? g.parts.map(p => tnPartRow(p, 18)).join('') : '');
  }).join('');
  return `<tr class="tn-detail"><td colspan="9"><table class="prodtable"><thead><tr><th>Réf.</th><th>Ligne de la nomenclature</th><th>Quantité</th><th>Coût Odoo unit.</th><th>Coût réel unit.</th><th>Retenu</th><th>Coût</th><th>Source</th></tr></thead><tbody>${body}</tbody></table>${r.components > r.parts.length ? '<small class="na">Détail limité aux ' + r.parts.length + ' premiers composants.</small>' : ''}</td></tr>`;
}

function tnOverlapSection(rep, ov) {
  const ks = Object.keys(ov);
  if (!ks.length && !tn.excl.size) return '';
  const rows = ks.map(k => { const a = rep.rows[k], hs = ov[k], bs = [...new Set(hs.map(h => h.b._k))];
    return `<tr><td>${esc(a.ref)} ${esc(a.name_odoo || a.name)}<br><small class="na">${tnEur(a.sale_total)} de vente · ${tnEur(a.real)} de coût</small></td><td><small>${bs.slice(0, 3).map(b => esc(rep.rows[b].ref + ' ' + (rep.rows[b].name_odoo || rep.rows[b].name)) + ' : ' + esc([...new Set(hs.filter(h => h.b._k === b).map(h => h.p.name))].slice(0, 2).join(', '))).join('<br>')}</small></td><td><label><input type="checkbox" class="tnx" data-tnx="${a._k}" ${tn.excl.has(a._k) ? '' : 'checked'}> compter</label></td></tr>`; });
  return '<h4 class="sub">Chevauchements possibles</h4>' + (ks.length ? table(['Ligne vendue', 'Retrouvée aussi parmi les composants de', 'Compter dans le calcul'], rows, 'prodtable') : '<p class="na">Aucun chevauchement détecté.</p>')
    + `<small class="na">Détection indicative, par mots-clés (peinture, soudure, galvanisation, découpe/cintrage, assemblage, certification) et par article identique : une ligne du devis dont le libellé correspond à un composant d’une autre ligne vendue peut être comptée deux fois. C’est à vous de juger : décochez la ligne pour l’exclure du calcul (totaux, marges, main-d’œuvre).${tn.excl.size ? ` <b>${tn.excl.size} ligne${tn.excl.size > 1 ? 's' : ''} exclue${tn.excl.size > 1 ? 's' : ''} actuellement</b> <button type="button" id="tn11-resetx">tout recompter</button>` : ''}</small>`;
}

function tnOutliers(rep) {
  const o = rep.outliers || [];
  if (!o.length) return '';
  return '<h4 class="sub">Composants à vérifier (coût réel aberrant)</h4>' + table(['Réf.', 'Composant', 'Coût Odoo', 'Coût réel calculé', 'Rapport', 'Achats', 'Lignes concernées'],
    o.map(x => `<tr><td>${esc(x.ref)}</td><td class="prod">${esc(x.name)}</td><td>${tnEur(x.odoo)}</td><td class="neg">${tnEur(x.real_unit)}</td><td>× ${num(Math.round((x.real_unit || 0) / (x.odoo || 1) * 10) / 10)}</td><td><small class="na">${x.purchased_qty != null ? num(x.purchased_qty) + ' achetés · ' : ''}${esc(x.buy_source || '')}${(x.buy_flags || []).length ? ' · ' + esc(x.buy_flags.join(', ')) : ''}</small></td><td><small>${esc([...new Set(x.lines)].join(', '))}</small></td></tr>`), 'prodtable')
    + `<small class="na">Pour ces composants, le coût réel calculé dépasse ${num(rep.outlier_factor || 3)} fois le coût Odoo : c’est le plus souvent une facture d’achat globale mal répartie ou une unité différente (pièce/mètre/heure). Le coût Odoo est conservé dans le total ; corrigez la facture, la commande ou l’unité dans Odoo.</small>`;
}

function drawTn11() {
  const el = document.getElementById('tn11-view'); if (!el) return;
  const rep = tn.rep;
  const zone = `<div class="sdbar tn11bar"><label class="btn primary" style="cursor:pointer">${tn.loading ? 'Analyse en cours…' : rep ? 'Analyser un autre devis (PDF)' : 'Choisir le PDF d’un devis'}<input type="file" id="tn11-file" accept="application/pdf,.pdf" hidden></label>`
    + `<span class="na">${tn.name ? esc(tn.name) + ' · ' : ''}Le PDF est lu par le serveur et n’est pas conservé.</span></div>`;
  if (!rep) {
    el.innerHTML = zone + (tn.error ? `<p class="neg">${esc(tn.error)}</p>` : '') + (tn.loading ? '<p class="na">Lecture du devis et des nomenclatures Odoo…</p>' : '<p class="na">Déposez un devis TN11 au format PDF (par exemple « Détail TN11 POST – Complete FIA 890 VF »). Chaque ligne marquée « x » est comparée à Odoo : prix de vente de l’article, coût Odoo, coût réel estimé d’après la nomenclature (achats réels et transport, comme dans « Contrôle des marges s/ produits ») et main-d’œuvre.</p>');
    return;
  }
  const on = rep.rows.filter(tnOn), ov = tnOverlaps(rep), sum = k => on.reduce((a, r) => a + r[k], 0), mp = (s, c) => s > 0 && c > 0 ? Math.round((s - c) / s * 10000) / 100 : null, rt = m => m == null ? null : m > 25 ? 'green' : m > 15 ? 'orange' : 'red';
  const T = {sale: sum('sale_total'), odoo: sum('odoo'), real: sum('real')}, base = rep.totals;
  const pdfBase = base.gap_pdf != null && rep.pdf_total ? rep.pdf_total : null, ref = pdfBase || T.sale;        // base des marges : prix final du devis (PDF), à défaut le prix de vente Odoo
  const t = {...base, ...T, labour_cost: on.reduce((a, r) => a + tnLab(r), 0), labour_minutes: on.reduce((a, r) => a + (r.labour_minutes || 0), 0), margin: {theoretical: mp(ref, T.odoo), real: mp(ref, T.real)}, ref}; t.rate = {theoretical: rt(t.margin.theoretical), real: rt(t.margin.real)};
  const nExcl = rep.rows.filter(r => r.found && tn.excl.has(r._k)).length, found = rep.rows.filter(r => r.found), miss = rep.rows.filter(r => !r.found), nobom = found.filter(r => !r.has_bom && !r.self_labour);
  const gap = base.gap_pdf, gapOk = gap != null && Math.abs(gap) < 1, lab = t.labour_cost;
  const row = r => !r.found ? `<tr class="tn-miss"><td>${esc(r.ref) || '–'}</td><td class="prod">${esc(r.name)}${r.option ? ' <small class="na">option</small>' : ''}</td><td data-v="${r.qty}">${num(r.qty)}</td><td colspan="6"><small class="neg">${esc(r.flags[0])}${r.ref ? '' : ' (ligne sans référence)'}</small></td><td></td></tr>`
    : `<tr class="${tn.excl.has(r._k) ? 'tn-excl' : ''}"><td>${esc(r.ref)}</td><td class="prod"><input type="checkbox" class="tnx" data-tnx="${r._k}" ${tn.excl.has(r._k) ? '' : 'checked'} title="Décocher pour exclure cette ligne du calcul (déjà comprise ailleurs)"> ${ov[r._k] ? `<span class="tnov" title="${esc('Chevauchement possible avec : ' + [...new Set(ov[r._k].map(h => h.b.ref + ' ' + (h.b.name_odoo || h.b.name) + ' (' + h.p.name + ')'))].slice(0, 4).join(' · '))}">⧉</span> ` : ''}${(r.parts || []).length ? `<button type="button" class="tnopen" data-tnopen="${r.id}" title="Voir le détail des composants">${tn.open.has(r.id) ? '▾' : '▸'}</button> ` : ''}${esc(r.name_odoo || r.name)}${(r.parts || []).some(x => x.warn) ? ' <span class="neg" title="Un composant a un coût réel aberrant">⚠</span>' : ''}${r.option ? ' <small class="na">option</small>' : ''}${r.has_bom ? ' <small class="tnbadge" title="Coût réel calculé sur la nomenclature Odoo">BOM</small>' : ''}</td><td data-v="${r.qty}">${num(r.qty)}</td>`
      + `<td data-v="${r.sale_total}">${tnEur(r.sale_total)}</td><td data-v="${r.odoo}">${tnEur(r.odoo)}</td><td data-v="${r.real}" title="${esc((r.flags || []).join(' · '))}">${tnEur(r.real)}${(r.flags || []).length ? ' <small class="na">⚑</small>' : ''}</td>`
      + tnM(r.margin.theoretical, r.rate.theoretical) + tnM(r.margin.real, r.rate.real)
      + `<td data-v="${r.self_labour ? r.real : r.labour_cost}">${r.self_labour || r.labour_cost > 0 ? `<span class="tnlab" title="${esc(r.self_labour ? 'Ligne de main-d’œuvre' : r.labour.map(l => l.label + ' : ' + tnEur(l.cost)).join('\n'))}">🛠 ${tnEur0(r.self_labour ? r.real : r.labour_cost)}${r.labour_minutes ? '<br><small>' + tnH(r.labour_minutes) + '</small>' : ''}</span>` : ''}</td></tr>` + (tn.open.has(r.id) ? tnParts(r) : '');
  let body;
  if (tn.grouped) {
    const groups = []; rep.rows.forEach(r => { const g = groups.find(x => x.s === (r.section || '(sans sous-ensemble)')) || (groups.push({s: r.section || '(sans sous-ensemble)', rows: []}), groups[groups.length - 1]); g.rows.push(r); });
    const ordered = tn.sort.k === 'devis' ? groups : groups.slice().sort((x, y) => tnCmp(tnGroupVal(x.rows, tn.sort.k), tnGroupVal(y.rows, tn.sort.k), tn.sort.dir));
    body = ordered.flatMap(g => { const f = g.rows.filter(tnOn), s = f.reduce((a, r) => a + r.sale_total, 0), c = f.reduce((a, r) => a + r.real, 0), l = f.reduce((a, r) => a + tnLab(r), 0);
      return [`<tr class="grp"><td colspan="9"><strong>${esc(g.s)}</strong> <small class="na">vente ${tnEur0(s)} · coût réel ${tnEur0(c)} · marge ${tnPct(s ? (s - c) / s * 100 : null)}${l ? ' · main-d’œuvre ' + tnEur0(l) : ''}</small></td></tr>`].concat(tnSortRows(g.rows).map(row)); });
  } else body = tnSortRows(rep.rows).map(row);
  el.innerHTML = zone
    + `<p class="${gapOk ? 'na' : 'neg'}">${gapOk ? '✔' : '⚠'} Total du devis (PDF) : <b>${tnEur(rep.pdf_total)}</b> HT · somme des prix de vente Odoo des ${found.length} lignes vendues : <b>${tnEur(base.sale)}</b>${gapOk ? ' : les prix correspondent.' : gap == null ? '' : ` : écart de ${tnEur(gap)}. Les prix du devis diffèrent des prix de vente actuels d’Odoo (ou des lignes manquent).`}</p>`
    + `<div class="kpis">${kpi('Prix de vente du devis (PDF)', tnEur0(pdfBase || t.sale), '', pdfBase ? 'prix remis au client : base des marges' : 'PDF sans total : prix Odoo utilisés')}${kpi('Prix de vente théorique (Odoo)', tnEur0(t.sale), '', `${on.length} lignes comptées${nExcl ? ' · ' + nExcl + ' exclue' + (nExcl > 1 ? 's' : '') : ''}`)}${kpi('Coût Odoo (théorique)', tnEur0(t.odoo), '', 'prix de revient des fiches')}${kpi('Coût réel estimé', tnEur0(t.real), '', 'nomenclatures, achats réels et transport')}`
    + `${kpi('Marge sur coût Odoo (théorique)', tnPct(t.margin.theoretical), t.rate.theoretical === 'red' ? 'neg' : t.rate.theoretical === 'green' ? 'pos' : '', t.margin.theoretical == null ? '' : tnEur0(t.ref - t.odoo) + ' sur le prix du devis')}${kpi('Marge sur coût réel estimé', tnPct(t.margin.real), t.rate.real === 'red' ? 'neg' : t.rate.real === 'green' ? 'pos' : '', t.margin.real == null ? '' : tnEur0(t.ref - t.real) + (t.margin.theoretical != null && t.margin.real != null ? ' · ' + (t.margin.real - t.margin.theoretical >= 0 ? '+' : '−') + Math.abs(Math.round((t.margin.real - t.margin.theoretical) * 10) / 10).toString().replace('.', ',') + ' pts vs théorique' : ''))}`
    + `${kpi('Main-d’œuvre', tnEur0(lab), '', `${t.real ? tnPct(lab / t.real * 100) + ' du coût réel' : ''}${t.labour_minutes ? ' · ' + tnH(t.labour_minutes) + ' d’opérations' : ''}`)}</div>`
    + `<small class="na">Les deux marges des indicateurs sont calculées sur le prix final du devis (PDF), qui ne change pas quand on décoche des lignes (seuls les coûts changent)${pdfBase ? '' : ' (indisponible : prix Odoo utilisés)'}, avec les coûts des lignes comptées${miss.length ? ' ; les ' + miss.length + ' lignes non retrouvées dans Odoo n’ont pas de coût, la marge est donc un peu surévaluée' : ''}. Dans le tableau, chaque ligne reste comparée à son prix de vente théorique Odoo.</small>`
    + (rep.bom_error ? `<p class="neg">Nomenclatures ou coûts réels partiellement indisponibles (${esc(rep.bom_error)}) : les coûts retombent sur les coûts Odoo.</p>` : '')
    + `<div class="sdbar tn11bar"><button type="button" id="tn11-group">${tn.grouped ? 'Afficher à plat' : 'Grouper par sous-ensemble'}</button><label class="na tnsel">Trier par <select class="sdin" id="tn11-sort" style="max-width:260px">${TN_SORTS.flatMap(([k, l]) => k === 'devis' ? [`<option value="devis:asc"${tn.sort.k === 'devis' ? ' selected' : ''}>${l}</option>`] : ['asc', 'desc'].map(d => `<option value="${k}:${d}"${tn.sort.k === k && tn.sort.dir === d ? ' selected' : ''}>${l} ${d === 'asc' ? '↑ croissant' : '↓ décroissant'}</option>`)).join('')}</select></label><span class="na">${num(found.length)} lignes comparées${miss.length ? ` · <b class="neg">${miss.length} non retrouvée${miss.length > 1 ? 's' : ''} dans Odoo</b>` : ''}${nobom.length ? ` · ${nobom.length} sans nomenclature (coût réel = achats de l’article)` : ''}</span></div>`
    + `<div class="table-wrap"><table class="prodtable mgtable tn11table"><thead><tr>${Object.entries(TN_COLS).map(([k, [l]]) => `<th data-tnk="${k}" class="tnsort${tn.sort.k === k ? ' on' : ''}" title="Cliquer pour trier">${l}${tn.sort.k === k ? (tn.sort.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>`).join('')}</tr></thead><tbody>${body.join('')}</tbody></table></div>`
    + '<small class="na">Chaque ligne marquée « x » du devis est un article Odoo vendu à son prix propre (liste de prix de la fiche article) ; son coût Odoo est le coût de la fiche. <b>Coût réel estimé</b> : si l’article a une nomenclature (BOM), somme de ses composants (récursivement) au coût d’achat réel estimé (commandes et factures, + transport au prorata du prix de vente) et des opérations de main-d’œuvre (temps × coût horaire du poste) ; sinon coût d’achat réel de l’article. ⚑ : un composant est au coût Odoo faute d’achat récent. Les lignes détaillées sous un ensemble dans le PDF (composants non marqués) ne sont pas comptées : elles sont déjà dans la nomenclature.</small>'
    + tnOverlapSection(rep, ov) + tnOutliers(rep) + tnLabourSection(rep)
    + (miss.length ? '<h4 class="sub">Lignes vendues non retrouvées dans Odoo</h4>' + table(['Réf.', 'Désignation', 'Qté', 'Sous-ensemble'], miss.map(r => `<tr><td>${esc(r.ref) || '–'}</td><td class="prod">${esc(r.name)}</td><td>${num(r.qty)}</td><td>${esc(r.section)}</td></tr>`), 'prodtable') + '<small class="na">Ces lignes ne sont pas dans le prix de vente ni dans le coût calculés. Une ligne sans référence ne peut pas être rapprochée d’Odoo automatiquement.</small>' : '');
}
document.addEventListener('change', e => { if (e.target.id === 'tn11-file' && e.target.files && e.target.files[0]) tnUpload(e.target.files[0]); });
document.addEventListener('change', e => { if (e.target.id === 'tn11-sort') { const [k, dir] = e.target.value.split(':'); tn.sort = {k, dir}; drawTn11(); } });
document.addEventListener('change', e => { const x = e.target.closest && e.target.closest('input.tnx'); if (x) { const k = +x.dataset.tnx; x.checked ? tn.excl.delete(k) : tn.excl.add(k); drawTn11(); } });
document.addEventListener('click', e => {
  if (e.target.id === 'tn11-resetx') { tn.excl = new Set(); drawTn11(); return; }
  const sb = e.target.closest('[data-tnsub]'); if (sb) { const k = sb.dataset.tnsub; tn.openTop.has(k) ? tn.openTop.delete(k) : tn.openTop.add(k); drawTn11(); return; }
  const ob = e.target.closest('[data-tnopen]'); if (ob) { const id = +ob.dataset.tnopen; tn.open.has(id) ? tn.open.delete(id) : tn.open.add(id); drawTn11(); return; }
  if (e.target.id === 'tn11-group') { tn.grouped = !tn.grouped; drawTn11(); return; }
  const th = e.target.closest('th[data-tnk]'); if (th) { const k = th.dataset.tnk; tn.sort = tn.sort.k === k ? (tn.sort.dir === 'asc' ? {k, dir: 'desc'} : {k: 'devis', dir: 'asc'}) : {k, dir: 'asc'}; drawTn11(); }
});
