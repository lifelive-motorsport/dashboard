// Vue d'ensemble › Analyse : synthèse de la situation comptable, calculée par des règles à chaque ouverture de la page (aucun texte figé, aucun chiffre inventé) :
// tendance générale, tendance par BU, points d'attention. Comparaison avec 2025 limitée au CA de la société (le plan comptable de 2025 ne se répartit pas par BU) ;
// la tendance par BU compare les 3 derniers mois aux 3 mois précédents (2026 seulement). Données = celles des autres pages (getRange, bilan, hit-parade clients, marge nette).
const an = {loading: false, busy: false, html: '', at: 0};
const AN_BU = ['XC', 'MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS'];
const AN_LABEL = {XC: 'XC', MODERN_RALLY: 'Modern Rally', HISTORIC_RALLY: 'Historic Rally', HISTORIC_RACING: 'Historic Racing', CARS_OTHERS: 'CARS Others'};
const AN = {warnCa: -0.10, badCa: -0.20, buDrop: -0.20, buDropBad: -0.35, lowMargin: 0.05, rateDrop: 0.05, dso: 60, concTop1: 0.25, concTop3: 0.50, gapShare: 0.10, directRatio: 0.92};
const anT = (fr, en) => LANG === 'en' ? en : fr;
const anDelta = v => `${v > 0 ? '+' : ''}${(v * 100).toFixed(1).replace('.', LANG === 'en' ? '.' : ',')} %`;
const anPts = v => `${v > 0 ? '+' : ''}${(v * 100).toFixed(1).replace('.', LANG === 'en' ? '.' : ',')} ${anT('pt', 'pt')}`;
const anIcon = v => v > 0.02 ? '▲' : v < -0.02 ? '▼' : '▬';
const anCls = v => v > 0.02 ? 'pos' : v < -0.02 ? 'neg' : '';

function analysisBlocks() {
  return [{static: '<section class="block" data-bid="analysis"><div class="block-head"><h3>Analyse de la situation</h3></div><div class="block-body" id="an-view"><p class="na loading">Chargement…</p></div></section>'}];
}

const anBu = (d, k) => (d && d.pnl && d.pnl.bus || []).find(b => b.key === k) || {ca: 0, direct_costs: 0, margin: 0};
const anRate = o => o.ca > 0 ? o.margin / o.ca : null;

async function anLoad(force) {
  const el = document.getElementById('an-view'); if (!el) return;
  if (an.busy) return; an.busy = true;
  if (!an.html || force) el.innerHTML = `<p class="na loading">${esc(tx('Chargement…'))}</p>`;
  try {
    const t = new Date(), jan1 = `${t.getFullYear()}-01-01`;
    const [f3, t3] = periodRange('3m');
    const prevEnd = new Date(monthsAgo(t, 3).getTime()), prevStart = monthsAgo(t, 6); prevStart.setDate(prevStart.getDate() + 1);
    const canTrend = ymd(prevStart) >= jan1;                                             // les 3 mois précédents doivent être sur le nouveau plan comptable (2026)
    const [ytd, cur3, prev3] = await Promise.all([getRange(...periodRange('ytd'), force), getRange(f3, t3, force), canTrend ? getRange(ymd(prevStart), ymd(prevEnd), force) : null]);
    let netCols = null;
    try {
      if (typeof nmEnsure === 'function') { nm.d = ytd; await nmEnsure(); if (nm.loading) await nm.loading; if (nm.ready && !(sd.loaded && sd.restricted) && ex.alloc) netCols = nmCompute(ytd).cols; }
    } catch { netCols = null; }
    let adjInfo = null;
    try { if (typeof adj !== 'undefined' && adj.loaded && (adj.items || []).some(a => a.enabled)) { const ad = adjustedData(ytd); adjInfo = {margin: ad.pnl.total.margin, effect: ad.pnl.total.margin - ytd.pnl.total.margin}; } } catch { adjInfo = null; }
    an.html = anRender({ytd, cur3, prev3, canTrend, netCols, adjInfo});
    an.at = Date.now();
  } catch (e) { an.html = `<p class="neg">${esc(e.message || String(e))}</p>`; }
  an.busy = false; anDraw();
}

function anDraw() {
  const el = document.getElementById('an-view'); if (!el) return;
  el.innerHTML = an.html || `<p class="na loading">${esc(tx('Chargement…'))}</p>`;
}

function anRender({ytd, cur3, prev3, canTrend, netCols, adjInfo}) {
  const tot = ytd.pnl.total, ca = tot.ca, mg = tot.margin, rate = ca > 0 ? mg / ca : null;
  const prevCa = ytd.pnl_prev && ytd.pnl_prev.total ? ytd.pnl_prev.total.ca : null, caVs = prevCa > 0 ? ca / prevCa - 1 : null;
  const days = Math.max(1, Math.round((new Date() - new Date(new Date().getFullYear(), 0, 1)) / 86400000) + 1);
  const general = [], attention = [];
  const add = (list, kind, text) => list.push({kind, text});
  const bus = AN_BU.filter(k => anBu(ytd, k).ca || anBu(ytd, k).direct_costs);
  // ---- Tendance générale ----------------------------------------------------------------------------------------
  if (caVs != null) add(general, caVs <= AN.badCa ? 'bad' : caVs <= AN.warnCa ? 'warn' : caVs >= 0.02 ? 'good' : 'info',
    anT(`Chiffre d’affaires de ${eur(ca)} à date, soit ${anDelta(caVs)} par rapport à la même période de 2025 (${eur(prevCa)}).`, `Revenue of ${eur(ca)} year to date, ${anDelta(caVs)} versus the same period of 2025 (${eur(prevCa)}).`));
  else add(general, 'info', anT(`Chiffre d’affaires de ${eur(ca)} à date (comparaison avec 2025 indisponible).`, `Revenue of ${eur(ca)} year to date (comparison with 2025 unavailable).`));
  if (rate != null) add(general, rate < 0 ? 'bad' : rate < AN.lowMargin ? 'warn' : 'info', anT(`Marge brute de ${eur(mg)} (${pct(rate)} du CA ; coûts directs : ${pct(tot.direct_costs / ca)} du CA).`, `Gross margin of ${eur(mg)} (${pct(rate)} of revenue; direct costs: ${pct(tot.direct_costs / ca)} of revenue).`));
  if (canTrend && cur3 && prev3) {
    const c = cur3.pnl.total, p = prev3.pnl.total, dCa = p.ca > 0 ? c.ca / p.ca - 1 : null, dMg = p.margin > 0 ? c.margin / p.margin - 1 : null, r1 = c.ca > 0 ? c.margin / c.ca : null, r0 = p.ca > 0 ? p.margin / p.ca : null;
    if (dCa != null) add(general, dCa <= AN.buDropBad ? 'bad' : dCa <= AN.buDrop ? 'warn' : dCa >= 0.05 ? 'good' : 'info',
      anT(`Dynamique récente : sur les 3 derniers mois, CA ${eur(c.ca)} (${anDelta(dCa)} vs les 3 mois précédents)${dMg != null ? `, marge brute ${eur(c.margin)} (${anDelta(dMg)})` : ''}${r1 != null && r0 != null ? `, taux de marge ${pct(r1)} (${anPts(r1 - r0)})` : ''}.`,
          `Recent momentum: over the last 3 months, revenue ${eur(c.ca)} (${anDelta(dCa)} vs the previous 3 months)${dMg != null ? `, gross margin ${eur(c.margin)} (${anDelta(dMg)})` : ''}${r1 != null && r0 != null ? `, margin rate ${pct(r1)} (${anPts(r1 - r0)})` : ''}.`));
  } else add(general, 'info', anT('Dynamique récente (3 derniers mois vs 3 mois précédents) indisponible : pas assez d’historique sur le plan comptable de 2026.', 'Recent momentum (last 3 months vs previous 3 months) unavailable: not enough history on the 2026 chart of accounts.'));
  if (adjInfo) add(general, 'info', anT(`Marge brute ajustée (ajustements actifs) : ${eur(adjInfo.margin)}, soit ${adjInfo.effect >= 0 ? '+' : ''}${eur(adjInfo.effect)} par rapport à la marge comptable.`, `Adjusted gross margin (active adjustments): ${eur(adjInfo.margin)}, i.e. ${adjInfo.effect >= 0 ? '+' : ''}${eur(adjInfo.effect)} versus the accounting margin.`));
  let netTot = null; const netBu = {};
  if (netCols) {
    const all = nmSum(netCols, Object.keys(netCols)); netTot = nmNet(all);
    AN_BU.forEach(k => { if (netCols[k]) netBu[k] = nmNet(nmSum(netCols, [k])); });
    add(general, netTot < 0 ? 'bad' : 'info', anT(`Marge nette à date : ${eur(netTot)}${ca > 0 ? ` (${pct(netTot / ca)} du CA)` : ''}, après personnel, véhicules et frais généraux.`, `Net margin year to date: ${eur(netTot)}${ca > 0 ? ` (${pct(netTot / ca)} of revenue)` : ''}, after staff, vehicles and overheads.`));
  }
  // ---- Tendance par BU ---------------------------------------------------------------------------------------------
  const rows = bus.map(k => {
    const y = anBu(ytd, k), c = canTrend && cur3 ? anBu(cur3, k) : null, p = canTrend && prev3 ? anBu(prev3, k) : null;
    const dCa = c && p && p.ca > 0 ? c.ca / p.ca - 1 : null, r1 = c ? anRate(c) : null, r0 = p ? anRate(p) : null, dRate = r1 != null && r0 != null ? r1 - r0 : null;
    return {k, label: AN_LABEL[k], y, rate: anRate(y), share: ca > 0 ? y.ca / ca : 0, dCa, dRate, net: netBu[k]};
  });
  const trendCell = (v, fmtv) => v == null ? '–' : `<span class="${anCls(v)}">${anIcon(v)} ${fmtv(v)}</span>`;
  const table_ = rows.length ? table([anT('BU', 'BU'), anT('CA à date', 'Revenue YTD'), anT('Part du CA', 'Share'), anT('Marge brute', 'Gross margin'), anT('Taux', 'Rate'), anT('CA · 3 mois', 'Revenue · 3 mo.'), anT('Taux · 3 mois', 'Rate · 3 mo.')].concat(netCols ? [anT('Marge nette', 'Net margin')] : []),
    rows.map(r => `<tr><td class="prod">${esc(r.label)}</td><td>${eur(r.y.ca)}</td><td>${pct(r.share)}</td><td class="${cls(r.y.margin)}">${eur(r.y.margin)}</td><td>${r.rate == null ? '–' : pct(r.rate)}</td><td>${trendCell(r.dCa, anDelta)}</td><td>${trendCell(r.dRate, anPts)}</td>${netCols ? `<td class="${cls(r.net || 0)}">${r.net == null ? '–' : eur(r.net)}</td>` : ''}</tr>`)) : `<p class="na">${esc(anT('Aucune donnée par BU sur la période.', 'No BU data for the period.'))}</p>`;
  // ---- Points d'attention -------------------------------------------------------------------------------------------
  rows.forEach(r => {
    if (r.y.ca > 0 && r.y.margin < 0) add(attention, 'bad', anT(`${r.label} : marge brute négative (${eur(r.y.margin)} pour ${eur(r.y.ca)} de CA).`, `${r.label}: negative gross margin (${eur(r.y.margin)} on ${eur(r.y.ca)} of revenue).`));
    else if (r.rate != null && r.rate < AN.lowMargin && r.share >= 0.03) add(attention, 'warn', anT(`${r.label} : taux de marge brute faible (${pct(r.rate)}) sur ${eur(r.y.ca)} de CA.`, `${r.label}: low gross margin rate (${pct(r.rate)}) on ${eur(r.y.ca)} of revenue.`));
    if (r.dCa != null && r.dCa <= AN.buDrop && r.share >= 0.03) add(attention, r.dCa <= AN.buDropBad ? 'bad' : 'warn', anT(`${r.label} : CA en recul de ${anDelta(r.dCa).replace('-', '')} sur les 3 derniers mois par rapport aux 3 précédents.`, `${r.label}: revenue down ${anDelta(r.dCa).replace('-', '')} over the last 3 months versus the previous 3.`));
    if (r.dRate != null && r.dRate <= -AN.rateDrop && r.share >= 0.03) add(attention, 'warn', anT(`${r.label} : taux de marge en baisse de ${anPts(r.dRate).replace('-', '')} sur le dernier trimestre.`, `${r.label}: margin rate down ${anPts(r.dRate).replace('-', '')} over the last quarter.`));
    if (r.net != null && r.net < 0 && r.y.ca > 0) add(attention, 'bad', anT(`${r.label} : marge nette négative (${eur(r.net)}) après imputation des coûts communs.`, `${r.label}: negative net margin (${eur(r.net)}) after common costs.`));
  });
  if (caVs != null && caVs <= AN.warnCa) add(attention, caVs <= AN.badCa ? 'bad' : 'warn', anT(`CA de la société en recul de ${anDelta(caVs).replace('-', '')} par rapport à 2025 à la même date.`, `Company revenue down ${anDelta(caVs).replace('-', '')} versus 2025 at the same date.`));
  if (ca > 0 && tot.direct_costs / ca > AN.directRatio) add(attention, 'warn', anT(`Les coûts directs absorbent ${pct(tot.direct_costs / ca)} du CA : peu de marge de manœuvre.`, `Direct costs absorb ${pct(tot.direct_costs / ca)} of revenue: little room for manoeuvre.`));
  const bs = ytd.balance_sheet;
  if (bs) {
    if (ca > 0 && bs.receivables > 0) { const dso = bs.receivables / ca * days; if (dso > AN.dso) add(attention, 'warn', anT(`Créances clients : ${eur(bs.receivables)}, soit environ ${Math.round(dso)} jours de CA à encaisser.`, `Customer receivables: ${eur(bs.receivables)}, about ${Math.round(dso)} days of revenue still to collect.`)); }
    const liquid = bs.cash + bs.receivables;
    if (bs.payables > liquid && bs.payables > 0) add(attention, 'bad', anT(`Dettes fournisseurs (${eur(bs.payables)}) supérieures à la trésorerie et aux créances réunies (${eur(liquid)}) : tension de liquidité possible.`, `Supplier payables (${eur(bs.payables)}) exceed cash plus receivables (${eur(liquid)}): possible liquidity strain.`));
    else if (bs.payables > 0 && bs.cash < bs.payables * 0.15) add(attention, 'warn', anT(`Trésorerie de ${eur(bs.cash)} pour ${eur(bs.payables)} de dettes fournisseurs (couverture ${pct(bs.cash / bs.payables)}).`, `Cash of ${eur(bs.cash)} for ${eur(bs.payables)} of supplier payables (coverage ${pct(bs.cash / bs.payables)}).`));
    const oc = ytd.top_clients && ytd.top_clients._open_totals;
    if (oc && bs.receivables > 0) { const sumBu = AN_BU.reduce((s, k) => s + (oc[k] || 0), 0), gap = bs.receivables - sumBu;
      if (gap > 5000 && gap / bs.receivables > AN.gapShare) add(attention, 'warn', anT(`${eur(gap)} de créances clients (${pct(gap / bs.receivables)}) ne sont rattachés à aucune BU : voir le détail dans Chiffre d’affaires › Créances et dettes par BU.`, `${eur(gap)} of customer receivables (${pct(gap / bs.receivables)}) are not assigned to any BU: see the detail in Revenue › Receivables and payables by BU.`)); }
  }
  const top = (ytd.top_clients && ytd.top_clients.total || []).slice().sort((a, b) => b.ca - a.ca);
  if (top.length && ca > 0) {
    const s1 = top[0].ca / ca, s3 = top.slice(0, 3).reduce((s, c) => s + c.ca, 0) / ca;
    if (s1 >= AN.concTop1) add(attention, 'warn', anT(`Concentration : ${top[0].name} représente ${pct(s1)} du CA.`, `Concentration: ${top[0].name} accounts for ${pct(s1)} of revenue.`));
    else if (s3 >= AN.concTop3) add(attention, 'info', anT(`Concentration : les 3 premiers clients représentent ${pct(s3)} du CA.`, `Concentration: the top 3 customers account for ${pct(s3)} of revenue.`));
  }
  if (netTot != null && netTot < 0) add(attention, 'bad', anT(`Marge nette de la société négative (${eur(netTot)}) : les marges brutes ne couvrent pas personnel, véhicules et frais généraux.`, `Company net margin is negative (${eur(netTot)}): gross margins do not cover staff, vehicles and overheads.`));
  if (adjInfo && mg !== 0 && Math.abs(adjInfo.effect) / Math.abs(mg) > 0.3) add(attention, 'info', anT(`La marge ajustée dépend à ${pct(Math.abs(adjInfo.effect) / Math.abs(mg))} des ajustements de MB : à relire avec la comptabilité.`, `The adjusted margin depends ${pct(Math.abs(adjInfo.effect) / Math.abs(mg))} on GM adjustments: worth re-reading with accounting.`));
  const order = {bad: 0, warn: 1, info: 2, good: 3};
  attention.sort((a, b) => order[a.kind] - order[b.kind]);
  const ICON = {bad: '⛔', warn: '⚠', info: 'ℹ', good: '✔'};
  const li = x => `<li class="an-${x.kind}"><span class="an-ic">${ICON[x.kind]}</span> ${esc(x.text)}</li>`;
  const when = new Date(an.at || Date.now()).toLocaleString(LOCALE());
  return `<h4 class="sub">${esc(anT('Tendance générale', 'Overall trend'))}</h4><ul class="an-list">${general.map(li).join('')}</ul>
    <h4 class="sub">${esc(anT('Tendance par BU', 'Trend by BU'))}</h4>${table_}
    <small class="na">${esc(anT('La comparaison avec 2025 se limite au CA de la société : le plan comptable de 2025 ne se répartit pas par BU. La tendance par BU compare les 3 derniers mois aux 3 mois précédents.', 'The comparison with 2025 is limited to company revenue: the 2025 chart of accounts cannot be split by BU. The BU trend compares the last 3 months with the previous 3 months.'))}</small>
    <h4 class="sub">${esc(anT('Points d’attention', 'Points of attention'))}</h4>${attention.length ? `<ul class="an-list">${attention.map(li).join('')}</ul>` : `<p class="na">${esc(anT('Aucun point d’attention majeur détecté d’après les règles de contrôle.', 'No major point of attention detected by the control rules.'))}</p>`}
    <p class="na an-foot"><small>${esc(anT('Analyse calculée automatiquement par Logbook à partir des chiffres (règles fixes, aucun chiffre estimé) ; elle ne remplace pas l’avis de la comptabilité. Calculée le', 'Analysis computed automatically by Logbook from the figures (fixed rules, no estimated figure); it does not replace accounting advice. Computed on'))} ${esc(when)}.</small> <button type="button" class="mini" data-an="refresh">↻ ${esc(tx('Actualiser'))}</button></p>`;
}

document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('[data-an=refresh]'); if (b) { an.html = ''; anLoad(true); } });
