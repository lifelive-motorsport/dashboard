// XC Detail › Contrôle des marges s/ TN11 : on dépose le PDF d'un devis ; chaque ligne vendue (marquée « x ») est comparée à Odoo :
// prix de vente propre de l'article, coût Odoo (théorique), coût réel estimé (nomenclature Odoo + achats réels + transport) et main-d'œuvre rendue visible.
// Chargé avant app.js ; utilise ses fonctions (esc, num, kpi, table, fmtDate…) au moment de l'appel.
let tn = {rep: null, loading: false, error: null, name: '', grouped: true};

function tn11Blocks() {
  return [{static: '<section class="block" data-bid="tn11"><div class="block-head"><h3>Contrôle d’un devis TN11</h3></div><div class="block-body" id="tn11-view"><p class="na">Chargement…</p></div></section>'}];
}
const tnEur = n => n == null ? '–' : new Intl.NumberFormat('fr-BE', {style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2}).format(n);
const tnEur0 = n => n == null ? '–' : new Intl.NumberFormat('fr-BE', {style: 'currency', currency: 'EUR', maximumFractionDigits: 0}).format(n);
const tnPct = v => v == null ? '–' : (Math.round(v * 10) / 10).toFixed(1).replace('.', ',') + ' %';
const tnH = min => { if (!min) return '–'; const h = Math.floor(min / 60), m = Math.round(min % 60); return (h ? h + ' h ' : '') + (m ? String(m).padStart(2, '0') + ' min' : ''); };
const tnM = (v, rate) => `<td class="mg-${rate || 'none'}" data-v="${v == null ? '' : v}">${tnPct(v)}</td>`;

async function tnUpload(file) {
  tn.loading = true; tn.error = null; tn.name = file.name; drawTn11();
  try {
    const r = await fetch('/api/xc/tn11/check', {method: 'POST', headers: {'Content-Type': 'application/pdf', ...((typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {})}, body: await file.arrayBuffer()});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    tn.rep = j;
  } catch (e) { tn.error = e.message; tn.rep = null; }
  tn.loading = false; drawTn11();
}

function tnLabourSection(rep) {
  const items = [];
  rep.rows.filter(r => r.found).forEach(r => {
    if (r.self_labour) items.push({line: r, kind: 'Ligne vendue', label: r.name_odoo || r.name, minutes: null, cost: r.real, why: 'article de main-d’œuvre : ' + r.self_labour});
    else r.labour.forEach(l => items.push({line: r, kind: l.kind === 'operation' ? 'Opération de nomenclature' : 'Composant main-d’œuvre', label: l.label, minutes: l.minutes, cost: l.cost, why: l.reason || 'temps de poste de travail × coût horaire'}));
  });
  if (!items.length) return '<h4 class="sub">Main-d’œuvre</h4><p class="na">Aucune main-d’œuvre repérée dans ce devis ni dans les nomenclatures des articles vendus. Si c’est anormal, vérifiez les motifs de détection (' + esc((rep.labour_like || []).join(', ')) + ') ou les opérations de vos nomenclatures.</p>';
  const tot = items.reduce((t, i) => t + i.cost, 0), mins = items.reduce((t, i) => t + (i.minutes || 0), 0);
  return '<h4 class="sub">Main-d’œuvre : toutes les lignes concernées</h4>' + table(['Ligne du devis', 'Origine', 'Libellé', 'Temps', 'Coût'],
    items.map(i => `<tr><td class="prod">${esc(i.line.ref)} ${esc(i.line.name_odoo || i.line.name)}</td><td>${esc(i.kind)}<br><small class="na">${esc(i.why)}</small></td><td class="prod">${esc(i.label)}</td><td data-v="${i.minutes == null ? '' : i.minutes}">${i.minutes == null ? '–' : tnH(i.minutes)}</td><td data-v="${i.cost}">${tnEur(i.cost)}</td></tr>`)
      .concat([`<tr class="tot"><td>Total (${items.length} élément${items.length > 1 ? 's' : ''})</td><td></td><td></td><td>${tnH(mins)}</td><td>${tnEur(tot)}</td></tr>`]), 'prodtable')
    + '<small class="na">La main-d’œuvre est repérée de trois façons : (1) les opérations des nomenclatures Odoo (temps × coût horaire du poste de travail) ; (2) les composants qui sont des articles de type service ou dont le nom ou la catégorie contient un motif de main-d’œuvre (' + esc((rep.labour_like || []).slice(0, 8).join(', ')) + '…) ; (3) les lignes vendues qui sont elles-mêmes de la main-d’œuvre. Elle est déjà comprise dans le coût réel ; elle est isolée ici pour la rendre visible.</small>';
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
  const t = rep.totals, found = rep.rows.filter(r => r.found), miss = rep.rows.filter(r => !r.found), nobom = found.filter(r => !r.has_bom && !r.self_labour);
  const gap = t.gap_pdf, gapOk = gap != null && Math.abs(gap) < 1, lab = t.labour_cost;
  const row = r => !r.found ? `<tr class="tn-miss"><td>${esc(r.ref) || '–'}</td><td class="prod">${esc(r.name)}${r.option ? ' <small class="na">option</small>' : ''}</td><td data-v="${r.qty}">${num(r.qty)}</td><td colspan="6"><small class="neg">${esc(r.flags[0])}${r.ref ? '' : ' (ligne sans référence)'}</small></td><td></td></tr>`
    : `<tr><td>${esc(r.ref)}</td><td class="prod">${esc(r.name_odoo || r.name)}${r.option ? ' <small class="na">option</small>' : ''}${r.has_bom ? ' <small class="tnbadge" title="Coût réel calculé sur la nomenclature Odoo">BOM</small>' : ''}</td><td data-v="${r.qty}">${num(r.qty)}</td>`
      + `<td data-v="${r.sale_total}">${tnEur(r.sale_total)}</td><td data-v="${r.odoo}">${tnEur(r.odoo)}</td><td data-v="${r.real}" title="${esc((r.flags || []).join(' · '))}">${tnEur(r.real)}${(r.flags || []).length ? ' <small class="na">⚑</small>' : ''}</td>`
      + tnM(r.margin.theoretical, r.rate.theoretical) + tnM(r.margin.real, r.rate.real)
      + `<td data-v="${r.self_labour ? r.real : r.labour_cost}">${r.self_labour || r.labour_cost > 0 ? `<span class="tnlab" title="${esc(r.self_labour ? 'Ligne de main-d’œuvre' : r.labour.map(l => l.label + ' : ' + tnEur(l.cost)).join('\n'))}">🛠 ${tnEur0(r.self_labour ? r.real : r.labour_cost)}${r.labour_minutes ? '<br><small>' + tnH(r.labour_minutes) + '</small>' : ''}</span>` : ''}</td></tr>`;
  const head = ['Réf.', 'Désignation', 'Qté', 'Prix de vente', 'Coût Odoo', 'Coût réel estimé', 'Marge théorique', 'Marge réelle', 'Main-d’œuvre'];
  let body;
  if (tn.grouped) {
    const groups = []; rep.rows.forEach(r => { const g = groups.find(x => x.s === (r.section || '(sans sous-ensemble)')) || (groups.push({s: r.section || '(sans sous-ensemble)', rows: []}), groups[groups.length - 1]); g.rows.push(r); });
    body = groups.flatMap(g => { const f = g.rows.filter(r => r.found), s = f.reduce((a, r) => a + r.sale_total, 0), c = f.reduce((a, r) => a + r.real, 0), l = f.reduce((a, r) => a + (r.self_labour ? r.real : r.labour_cost), 0);
      return [`<tr class="grp"><td colspan="9"><strong>${esc(g.s)}</strong> <small class="na">vente ${tnEur0(s)} · coût réel ${tnEur0(c)} · marge ${tnPct(s ? (s - c) / s * 100 : null)}${l ? ' · main-d’œuvre ' + tnEur0(l) : ''}</small></td></tr>`].concat(g.rows.map(row)); });
  } else body = rep.rows.map(row);
  el.innerHTML = zone
    + `<p class="${gapOk ? 'na' : 'neg'}">${gapOk ? '✔' : '⚠'} Total du devis (PDF) : <b>${tnEur(rep.pdf_total)}</b> HT · somme des prix de vente Odoo des ${found.length} lignes vendues : <b>${tnEur(t.sale)}</b>${gapOk ? ' : les prix correspondent.' : gap == null ? '' : ` : écart de ${tnEur(gap)}. Les prix du devis diffèrent des prix de vente actuels d’Odoo (ou des lignes manquent).`}</p>`
    + `<div class="kpis">${kpi('Prix de vente (Odoo)', tnEur0(t.sale), '', `${found.length} lignes vendues`)}${kpi('Coût Odoo (théorique)', tnEur0(t.odoo), '', 'prix de revient des fiches')}${kpi('Coût réel estimé', tnEur0(t.real), '', 'nomenclatures, achats réels et transport')}`
    + `${kpi('Marge théorique', tnPct(t.margin.theoretical), t.rate.theoretical === 'red' ? 'neg' : t.rate.theoretical === 'green' ? 'pos' : '', t.margin.theoretical == null ? '' : tnEur0(t.sale - t.odoo))}${kpi('Marge réelle estimée', tnPct(t.margin.real), t.rate.real === 'red' ? 'neg' : t.rate.real === 'green' ? 'pos' : '', t.margin.real == null ? '' : tnEur0(t.sale - t.real) + (t.margin.theoretical != null && t.margin.real != null ? ' · ' + (t.margin.real - t.margin.theoretical > 0 ? '+' : '−') + Math.abs(Math.round((t.margin.real - t.margin.theoretical) * 10) / 10).toString().replace('.', ',') + ' pts' : ''))}`
    + `${kpi('Main-d’œuvre', tnEur0(lab), '', `${t.real ? tnPct(lab / t.real * 100) + ' du coût réel' : ''}${t.labour_minutes ? ' · ' + tnH(t.labour_minutes) + ' d’opérations' : ''}`)}</div>`
    + (rep.bom_error ? `<p class="neg">Nomenclatures ou coûts réels partiellement indisponibles (${esc(rep.bom_error)}) : les coûts retombent sur les coûts Odoo.</p>` : '')
    + `<div class="sdbar tn11bar"><button type="button" id="tn11-group">${tn.grouped ? 'Afficher à plat (tri par colonne)' : 'Grouper par sous-ensemble'}</button><span class="na">${num(found.length)} lignes comparées${miss.length ? ` · <b class="neg">${miss.length} non retrouvée${miss.length > 1 ? 's' : ''} dans Odoo</b>` : ''}${nobom.length ? ` · ${nobom.length} sans nomenclature (coût réel = achats de l’article)` : ''}</span></div>`
    + table(head, body, 'prodtable mgtable tn11table')
    + '<small class="na">Chaque ligne marquée « x » du devis est un article Odoo vendu à son prix propre (liste de prix de la fiche article) ; son coût Odoo est le coût de la fiche. <b>Coût réel estimé</b> : si l’article a une nomenclature (BOM), somme de ses composants (récursivement) au coût d’achat réel estimé (commandes et factures, + transport au prorata du prix de vente) et des opérations de main-d’œuvre (temps × coût horaire du poste) ; sinon coût d’achat réel de l’article. ⚑ : un composant est au coût Odoo faute d’achat récent. Les lignes détaillées sous un ensemble dans le PDF (composants non marqués) ne sont pas comptées : elles sont déjà dans la nomenclature.</small>'
    + tnLabourSection(rep)
    + (miss.length ? '<h4 class="sub">Lignes vendues non retrouvées dans Odoo</h4>' + table(['Réf.', 'Désignation', 'Qté', 'Sous-ensemble'], miss.map(r => `<tr><td>${esc(r.ref) || '–'}</td><td class="prod">${esc(r.name)}</td><td>${num(r.qty)}</td><td>${esc(r.section)}</td></tr>`), 'prodtable') + '<small class="na">Ces lignes ne sont pas dans le prix de vente ni dans le coût calculés. Une ligne sans référence ne peut pas être rapprochée d’Odoo automatiquement.</small>' : '');
}
document.addEventListener('change', e => { if (e.target.id === 'tn11-file' && e.target.files && e.target.files[0]) tnUpload(e.target.files[0]); });
document.addEventListener('click', e => { if (e.target.id === 'tn11-group') { tn.grouped = !tn.grouped; drawTn11(); } });
