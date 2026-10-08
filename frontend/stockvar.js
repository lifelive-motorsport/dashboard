// Variations de stock (positives ou négatives) saisies à la main : elles s'ajoutent à la marge brute de XC quand l'option « avec variation de stock » est active.
// Liste partagée, enregistrée côté serveur (comme les ajustements de marge brute). Chargé avant app.js.
let sv = {items: [], can_edit: false, can_save: true, loaded: false, error: null, updated_at: null, updated_by: null};
let svDraft = [], svDirty = false, svMsg = '';
let stockOn = (() => { try { return localStorage.getItem('lm_stockvar') === '1'; } catch { return false; } })();
const svAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};
const svClone = x => JSON.parse(JSON.stringify(x));
const svId = () => 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

async function loadStockVar() {
  if (typeof role !== 'undefined' && role === 'xc') { sv = {...sv, loaded: true}; return; }          // catégorie « XC » : pas d'ajustements ni de variations de stock
  try {
    const r = await fetch('/api/stockvar', {headers: svAuth()});
    if (!r.ok) throw new Error(r.status);
    sv = {...(await r.json()), loaded: true};
  } catch (e) { sv = {...sv, loaded: true, error: 'Variations de stock indisponibles pour le moment.'}; }
  if (!svDirty) svDraft = svClone(sv.items || []);
}

// Effet sur la marge brute de XC des variations actives dont la date tombe dans la période de `d` (positif = la marge augmente).
function svEffects(d) {
  const from = d.period && d.period.from, to = d.period && d.period.to;
  return (sv.items || []).filter(a => a.enabled).map(a => ({...a, effect: a.date && (!from || a.date >= from) && (!to || a.date <= to) ? a.amount : 0}));
}
// Copie des chiffres où la marge brute de XC inclut les variations de stock (les coûts directs absorbent l'écart, comme pour les ajustements).
function applyStockVar(d) {
  if (!d || !d.pnl || !stockOn || !sv.loaded) return d;
  const fx = svEffects(d), eff = fx.reduce((t, a) => t + a.effect, 0), pnl = svClone(d.pnl);
  pnl.bus.forEach(b => { if (b.key === 'XC') { b.direct_costs -= eff; b.margin = b.ca - b.direct_costs; } });
  pnl.groups.forEach(g => { const m = pnl.bus.filter(b => b.group === g.key); g.direct_costs = m.reduce((s, b) => s + b.direct_costs, 0); g.margin = g.ca - g.direct_costs; });
  const t = pnl.total; t.direct_costs = pnl.bus.reduce((s, b) => s + b.direct_costs, 0); t.margin = t.ca - t.direct_costs; t.margin_pct = t.ca ? t.margin / t.ca : 0;
  return {...d, pnl, _stock: {items: fx, effect: eff}};
}
// Chiffres affichés : ajustements de MB si activés, puis variations de stock si activées.
const viewData = d => applyStockVar(typeof adjOn !== 'undefined' && adjOn ? adjustedData(d) : d);

// Interrupteur « sans / avec variation de stock » (pages de marge d'Overview et de XC Detail, et page Marge nette).
function stockToggleHtml() {
  const n = (sv.items || []).filter(a => a.enabled).length;
  return `<div class="adjbar stockbar ${stockOn ? 'on' : ''}"><div class="seg" role="group" aria-label="Variation de stock"><button type="button" data-stockon="0" class="${stockOn ? '' : 'sel'}">Sans variation de stock</button><button type="button" data-stockon="1" class="${stockOn ? 'sel' : ''}">Avec variation de stock</button></div>`
    + `<span class="adjtxt">${stockOn ? `<b>Variations de stock incluses</b> dans la marge de XC (${n} élément${n > 1 ? 's' : ''} actif${n > 1 ? 's' : ''}).` : `Variations de stock non incluses${n ? ` — ${n} élément${n > 1 ? 's' : ''} disponible${n > 1 ? 's' : ''}` : ''}.`} <a href="#/xc/inventory">Voir et saisir les variations</a></span></div>`;
}
document.addEventListener('click', e => {
  const t = e.target.closest('button'); if (!t || t.dataset.stockon === undefined) return;
  stockOn = t.dataset.stockon === '1'; try { localStorage.setItem('lm_stockvar', stockOn ? '1' : '0'); } catch {}
  if (typeof render === 'function') render();
});

// ---- Volet « Variations de stock » de la page Inventory ---------------------------------------------------------------
function stockVarBlocks() {
  return [{static: '<section class="block" data-bid="stockvar"><div class="block-head"><h3>Variations de stock</h3></div><div class="block-body" id="stockvar-view"><p class="na">Chargement…</p></div></section>'}];
}
function drawStockVar() {
  const el = document.getElementById('stockvar-view'); if (!el) return;
  if (!sv.loaded) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (sv.error) { el.innerHTML = `<p class="neg">${esc(sv.error)}</p>`; return; }
  const edit = sv.can_edit && sv.can_save !== false, items = edit ? svDraft : (sv.items || []), dis = edit ? '' : ' disabled';
  const year = new Date().getFullYear(), tot = items.filter(a => a.enabled && a.date && a.date.startsWith(String(year))).reduce((t, a) => t + (+a.amount || 0), 0);
  const cards = items.map((a, i) => `<div class="adjcard${a.enabled ? '' : ' off'}"><div class="adjrow"><label class="chk"><input type="checkbox" data-sv="enabled" data-i="${i}"${a.enabled ? ' checked' : ''}${dis}> Actif</label>
      <input class="lbl" type="text" maxlength="160" placeholder="Description (ex. Dépréciation du stock de pièces lentes, inventaire de fin d’année…)" data-sv="label" data-i="${i}" value="${esc(a.label)}"${dis}>
      ${edit ? `<button type="button" class="mini" data-svdel="${i}" title="Supprimer">✕</button>` : ''}</div>
    <div class="adjbody"><label>Effet sur la marge brute de XC (€ ; + = le stock augmente, − = il diminue)<input type="number" step="0.01" data-sv="amount" data-i="${i}" value="${a.amount}"${dis}></label>
      <label>Date d’effet<input type="date" data-sv="date" data-i="${i}" value="${esc(a.date || '')}"${dis}></label></div>
    <input class="note" type="text" maxlength="300" placeholder="Note (justification, visible par tous)" data-sv="note" data-i="${i}" value="${esc(a.note || '')}"${dis}></div>`).join('');
  el.innerHTML = `<p class="na">Saisissez ici les variations de stock à prendre en compte (positives ou négatives). Elles modifient la marge brute et la marge nette de <b>XC</b> uniquement lorsque l’option « Avec variation de stock » est activée dans les pages de marge d’Overview et de XC Detail. Elles ne sont jamais écrites dans Odoo.</p>`
    + `<div class="kpis">${kpi('Variations actives en ' + year, (tot > 0 ? '+' : '') + eur(tot), tot < 0 ? 'neg' : tot > 0 ? 'pos' : '', 'effet cumulé sur la marge brute XC')}${kpi('Éléments', num(items.length), '', `${items.filter(a => a.enabled).length} actif${items.filter(a => a.enabled).length > 1 ? 's' : ''}`)}</div>`
    + (items.length ? cards : '<p class="na">Aucune variation de stock saisie.</p>')
    + (edit ? `<div class="adjbtns"><button type="button" data-svadd>+ Ajouter une variation de stock</button><button type="button" class="primary" data-svsave${svDirty ? '' : ' disabled'}>Enregistrer</button><button type="button" data-svcancel${svDirty ? '' : ' disabled'}>Annuler les modifications</button></div>`
      : `<p class="na">${sv.can_edit ? 'Saisie réservée au propriétaire des hypothèses.' : 'Lecture seule : la saisie est réservée aux administrateurs.'}</p>`)
    + `<small class="na">${esc(svMsg || (sv.updated_at ? 'Dernier enregistrement : ' + new Date(sv.updated_at).toLocaleString('fr-BE') + (sv.updated_by ? ' par ' + sv.updated_by : '') + '.' : 'Rien d’enregistré pour le moment.'))}</small>`;
}
document.addEventListener('change', e => {
  const el = e.target; if (!el.dataset || el.dataset.sv === undefined) return;
  const a = svDraft[+el.dataset.i]; if (!a) return; const f = el.dataset.sv;
  a[f] = f === 'enabled' ? el.checked : f === 'amount' ? (parseFloat(String(el.value).replace(',', '.')) || 0) : f === 'date' ? (el.value || null) : el.value;
  svDirty = true; svMsg = '';
  if (f === 'enabled') { drawStockVar(); return; }                                      // pas de réaffichage complet pendant la saisie : il ferait perdre le focus
  document.querySelectorAll('[data-svsave],[data-svcancel]').forEach(b => { b.disabled = false; });
});
document.addEventListener('click', async e => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.hasAttribute('data-svadd')) { svDraft.push({id: svId(), label: '', amount: 0, date: new Date().toISOString().slice(0, 10), enabled: true, note: ''}); svDirty = true; drawStockVar(); }
  else if (t.dataset.svdel !== undefined) { svDraft.splice(+t.dataset.svdel, 1); svDirty = true; drawStockVar(); }
  else if (t.hasAttribute('data-svcancel')) { svDraft = svClone(sv.items || []); svDirty = false; svMsg = ''; drawStockVar(); }
  else if (t.hasAttribute('data-svsave')) {
    if (svDraft.some(a => !a.label.trim())) { svMsg = 'Chaque variation doit avoir une description.'; drawStockVar(); return; }
    svMsg = 'Enregistrement…'; drawStockVar();
    try {
      const r = await fetch('/api/stockvar', {method: 'PUT', headers: {'Content-Type': 'application/json', ...svAuth()}, body: JSON.stringify({items: svDraft})});
      const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Données refusées (vérifiez les champs).');
      sv = {...sv, ...j, loaded: true}; svDraft = svClone(sv.items || []); svDirty = false; svMsg = 'Enregistré.';
    } catch (err) { svMsg = 'Échec de l’enregistrement : ' + err.message; }
    drawStockVar(); if (typeof render === 'function') render();
  }
});
window.addEventListener('beforeunload', e => { if (svDirty) { e.preventDefault(); e.returnValue = ''; } });
