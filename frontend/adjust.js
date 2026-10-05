// Ajustements de marge brute : liste partagée (enregistrée côté serveur), interrupteur « MB comptable / MB ajustée »,
// rapprochement et éditeur. Chargé avant app.js ; utilise ses fonctions (esc, eur, table, B, NOTE…) au moment de l'appel.
let adj = {items: [], can_edit: false, loaded: false, error: null, updated_at: null, updated_by: null};
let adjDraft = [], adjDirty = false, adjMsg = '';
let adjOn = (() => { try { return localStorage.getItem('lm_adj') === '1'; } catch { return false; } })();

const ADJ_BUS = [['HISTORIC_RACING', 'Historic Racing'], ['HISTORIC_RALLY', 'Historic Rally'], ['MODERN_RALLY', 'Modern Rally'],
                 ['CARS_OTHERS', 'CARS Others'], ['XC', 'XC']];
const ADJ_BU_LABEL = Object.fromEntries(ADJ_BUS);
const ADJ_KINDS = {manual: 'Montant saisi à la main', meeting: 'Événements (axe MEETING)', car: 'Véhicules (axe CARS)'};
const ADJ_MEASURES = {result: 'Résultat après amortissement (CA − frais directs − autres charges − dotations)', margin: 'Contribution à la MB (CA − frais directs)'};
const MB_PAGES = new Set(['overview/mb', 'overview/xcvscars', 'cars/general', 'cars/bu', 'xc/general']);

const adjAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};
const adjClone = x => JSON.parse(JSON.stringify(x));

async function loadAdj() {
  try {
    const r = await fetch('/api/adjustments', {headers: adjAuth()});
    if (!r.ok) throw new Error(r.status);
    adj = {...(await r.json()), loaded: true};
  } catch (e) { adj = {...adj, loaded: true, error: 'Ajustements indisponibles pour le moment.'}; }
  if (!adjDirty) adjDraft = adjClone(adj.items || []);
}

// Effet de chaque ajustement actif sur la MB de sa BU, pour les chiffres `d` d'une période (positif = la MB augmente).
function adjEffects(d) {
  const from = d.period && d.period.from, to = d.period && d.period.to;
  const ev = Object.fromEntries(((d.events && d.events.events) || []).map(e => [e.id, e]));
  const vh = Object.fromEntries(((d.vehicles && d.vehicles.vehicles) || []).map(e => [e.id, e]));
  return (adj.items || []).filter(a => a.enabled).map(a => {
    let effect = 0, detail = '';
    if (a.kind === 'manual') {
      const inside = a.date && (!from || a.date >= from) && (!to || a.date <= to);
      effect = inside ? a.amount : 0; detail = a.date ? `au ${fmtDate(a.date)}` : 'sans date : ignoré';
    } else {
      const src = a.kind === 'car' ? vh : ev;
      const vals = (a.sel || []).map(s => src[s.id]).filter(Boolean);
      const v = vals.reduce((t, e) => t + (a.measure === 'margin' ? e.ca - e.direct_costs : (e.result_accounting ?? e.result)), 0);
      effect = -v; detail = `${vals.length} / ${(a.sel || []).length} actif${vals.length > 1 ? 's' : ''} sur la période`;
    }
    return {...a, effect, detail};
  });
}

// Copie des chiffres où la MB de chaque BU est corrigée (les frais directs absorbent l'écart ; le détail par ligne n'est pas ajusté).
function adjustedData(d) {
  if (!d || !d.pnl) return d;
  const fx = adjEffects(d), byBu = {};
  fx.forEach(a => { byBu[a.bu] = (byBu[a.bu] || 0) + a.effect; });
  const pnl = adjClone(d.pnl);
  pnl.bus.forEach(b => { const e = byBu[b.key] || 0; b.direct_costs -= e; b.margin = b.ca - b.direct_costs; });
  pnl.groups.forEach(g => { const m = pnl.bus.filter(b => b.group === g.key); g.direct_costs = m.reduce((s, b) => s + b.direct_costs, 0); g.margin = g.ca - g.direct_costs; });
  const t = pnl.total; t.direct_costs = pnl.bus.reduce((s, b) => s + b.direct_costs, 0); t.margin = t.ca - t.direct_costs; t.margin_pct = t.ca ? t.margin / t.ca : 0;
  return {...d, pnl, _adj: {items: fx, byBu}};
}

// Bandeau en haut des pages de marge : interrupteur + rappel de ce qui est affiché.
function adjBar(key) {
  if (!MB_PAGES.has(key) || !adj.loaded) return null;
  const n = (adj.items || []).filter(a => a.enabled).length;
  const txt = adjOn
    ? `<b>MB ajustée</b> : ${n} ajustement${n > 1 ? 's' : ''} actif${n > 1 ? 's' : ''} appliqué${n > 1 ? 's' : ''} à la marge brute. <a href="#/overview/adjustments">Voir le détail et le rapprochement</a>`
    : `<b>MB comptable</b> (sans ajustement)${n ? ` — ${n} ajustement${n > 1 ? 's' : ''} disponible${n > 1 ? 's' : ''}` : ''}. <a href="#/overview/adjustments">Ajustements</a>`;
  return {static: `<div class="adjbar ${adjOn ? 'on' : ''}"><div class="seg" role="group" aria-label="Marge brute affichée">
      <button type="button" data-adjmode="0" class="${adjOn ? '' : 'sel'}">MB comptable</button><button type="button" data-adjmode="1" class="${adjOn ? 'sel' : ''}">MB ajustée</button></div>
      <span class="adjtxt">${txt}</span></div>`};
}

// ---- Page « Ajustements MB » ---------------------------------------------------------------------
function adjRecon(d) {
  const raw = d, fx = adjEffects(raw), by = {};
  fx.forEach(a => { by[a.bu] = (by[a.bu] || 0) + a.effect; });
  const bus = raw.pnl.bus.filter(b => b.ca || b.direct_costs || by[b.key]);
  const row = (label, mb, e, cl = '') => `<tr class="${cl}"><td>${esc(label)}</td><td>${eur(mb)}</td><td class="${e ? cls(e) : ''}">${e ? (e > 0 ? '+' : '') + eur(e) : '–'}</td><td><b>${eur(mb + e)}</b></td></tr>`;
  const grpSum = g => raw.pnl.bus.filter(b => b.group === g).reduce((s, b) => s + (by[b.key] || 0), 0);
  const tot = Object.values(by).reduce((s, v) => s + v, 0);
  const items = fx.length ? table(['Ajustement', 'BU', 'Type', 'Effet sur la MB'], fx.map(a => `<tr><td>${esc(a.label)}<br><small class="na">${esc(a.detail)}${a.note ? ' · ' + esc(a.note) : ''}</small></td>
      <td>${esc(ADJ_BU_LABEL[a.bu] || a.bu)}</td><td>${esc(ADJ_KINDS[a.kind])}</td><td class="${cls(a.effect)}">${(a.effect > 0 ? '+' : '') + eur(a.effect)}</td></tr>`), 'prodtable')
    : '<p class="na">Aucun ajustement actif.</p>';
  return table(['', 'MB comptable', 'Ajustements', 'MB ajustée'],
      bus.map(b => row(b.label, b.margin, by[b.key] || 0))
      .concat([row('Total XC', raw.pnl.groups.find(g => g.key === 'XC').margin, grpSum('XC'), 'tot'),
               row('Total CARS', raw.pnl.groups.find(g => g.key === 'CARS').margin, grpSum('CARS'), 'tot'),
               row('Total', raw.pnl.total.margin, tot, 'tot')]), 'prodtable')
    + '<h4 class="sub">Détail des ajustements actifs</h4>' + items;
}

function adjPageBlocks() {
  const recon = {...B('recon', 'Rapprochement : MB comptable → MB ajustée', d => adjRecon(d)), raw: true};
  const editor = {static: '<section class="block" data-bid="adj-ed"><div class="block-head"><h3>Ajustements enregistrés</h3></div><div class="block-body" id="adj-editor"></div></section>'};
  return [recon, editor, NOTE('Un ajustement corrige la marge brute d’une BU sans toucher à la comptabilité : rien n’est écrit dans Odoo. Montant à la main : effet sur la MB (positif = la MB augmente), à la date indiquée. Événements / véhicules : on retire de la MB la balance des comptes analytiques sélectionnés, calculée sur la période affichée. Choisissez un seul mode par élément pour éviter un double comptage (un véhicule et son événement). Le détail par ligne d’activité n’est pas ajusté. L’interrupteur « MB comptable / MB ajustée » se trouve en haut des pages de marge brute.')];
}

const adjId = () => 'a' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
function adjCandidates(kind) {
  const d = (typeof cached === 'function' && cached('ytd')) || (typeof anyData === 'function' && anyData()) || {};
  const list = kind === 'car' ? ((d.vehicles && d.vehicles.vehicles) || []).filter(v => v.group === 'CARS') : ((d.events && d.events.events) || []);
  return list.map(e => ({id: e.id, name: e.name})).sort((a, b) => a.name.localeCompare(b.name, 'fr'));
}

function drawAdjEditor() {
  const el = document.getElementById('adj-editor'); if (!el) return;
  const edit = !!adj.can_edit;
  let h = adj.error ? `<p class="neg">${esc(adj.error)}</p>` : '';
  if (!edit) h += '<p class="na">Lecture seule : seuls les administrateurs du dashboard peuvent modifier les ajustements.</p>';
  if (!adjDraft.length) h += '<p class="na">Aucun ajustement enregistré.</p>';
  adjDraft.forEach((a, i) => {
    const dis = edit ? '' : ' disabled';
    const bu = `<select data-adj="bu" data-i="${i}"${dis}>${ADJ_BUS.map(([k, l]) => `<option value="${k}"${a.bu === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    const kind = `<select data-adj="kind" data-i="${i}"${dis}>${Object.entries(ADJ_KINDS).map(([k, l]) => `<option value="${k}"${a.kind === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    let body;
    if (a.kind === 'manual') {
      body = `<label>Effet sur la MB (€, + = la MB augmente)<input type="number" step="0.01" data-adj="amount" data-i="${i}" value="${a.amount}"${dis}></label>
        <label>Date d’effet<input type="date" data-adj="date" data-i="${i}" value="${esc(a.date || '')}"${dis}></label>`;
    } else {
      const picked = new Set((a.sel || []).map(s => s.id));
      const cands = adjCandidates(a.kind), known = new Set(cands.map(c => c.id));
      const all = cands.concat((a.sel || []).filter(s => !known.has(s.id)));
      body = `<label>Mesure retirée de la MB<select data-adj="measure" data-i="${i}"${dis}>${Object.entries(ADJ_MEASURES).map(([k, l]) => `<option value="${k}"${a.measure === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
        <details class="sellist"><summary>${picked.size} ${a.kind === 'car' ? 'véhicule' : 'événement'}${picked.size > 1 ? 's' : ''} sélectionné${picked.size > 1 ? 's' : ''}</summary>
        <div class="checks">${all.map(c => `<label><input type="checkbox" data-adj="sel" data-i="${i}" data-id="${c.id}" data-name="${esc(c.name)}"${picked.has(c.id) ? ' checked' : ''}${dis}> ${esc(c.name)}</label>`).join('') || '<small class="na">Liste en cours de chargement…</small>'}</div></details>`;
    }
    h += `<div class="adjcard${a.enabled ? '' : ' off'}"><div class="adjrow"><label class="chk"><input type="checkbox" data-adj="enabled" data-i="${i}"${a.enabled ? ' checked' : ''}${dis}> Actif</label>
      <input class="lbl" type="text" maxlength="120" placeholder="Libellé (ex. Andalucia – investissement long terme)" data-adj="label" data-i="${i}" value="${esc(a.label)}"${dis}>
      ${edit ? `<button type="button" class="mini" data-adjdel="${i}" title="Supprimer cet ajustement">✕</button>` : ''}</div>
      <div class="adjrow">${bu}${kind}</div><div class="adjrow">${body}</div>
      <input class="note" type="text" maxlength="300" placeholder="Note (justification, visible par tous)" data-adj="note" data-i="${i}" value="${esc(a.note || '')}"${dis}></div>`;
  });
  if (edit) h += `<div class="adjbtns"><button type="button" data-adjadd>+ Ajouter un ajustement</button><button type="button" class="primary" data-adjsave${adjDirty ? '' : ' disabled'}>Enregistrer</button>
      <button type="button" data-adjcancel${adjDirty ? '' : ' disabled'}>Annuler les modifications</button></div>`;
  h += `<p class="na" id="adj-msg">${esc(adjMsg || (adj.updated_at ? `Dernier enregistrement : ${new Date(adj.updated_at).toLocaleString('fr-BE')}${adj.updated_by ? ' par ' + adj.updated_by : ''}.` : ''))}</p>`;
  el.innerHTML = h;
}

async function adjSave() {
  adjMsg = 'Enregistrement…'; drawAdjEditor();
  try {
    const r = await fetch('/api/adjustments', {method: 'PUT', headers: {'Content-Type': 'application/json', ...adjAuth()}, body: JSON.stringify({items: adjDraft})});
    if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(typeof j.detail === 'string' ? j.detail : 'Données refusées (vérifiez les champs).'); }
    adj = {...(await r.json()), loaded: true, error: null}; adjDirty = false; adjDraft = adjClone(adj.items); adjMsg = 'Enregistré.';
  } catch (e) { adjMsg = 'Échec de l’enregistrement : ' + e.message; }
  drawAdjEditor();
  if (current && current.key === 'overview/adjustments') current.blocks.filter(b => !b.static).forEach(updateBlock);
}

document.addEventListener('click', e => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.adjmode !== undefined) {
    adjOn = t.dataset.adjmode === '1'; try { localStorage.setItem('lm_adj', adjOn ? '1' : '0'); } catch {}
    render(); return;
  }
  if (!document.getElementById('adj-editor')) return;
  if (t.hasAttribute('data-adjadd')) { adjDraft.push({id: adjId(), label: '', bu: 'HISTORIC_RACING', kind: 'meeting', enabled: true, amount: 0, date: null, measure: 'result', sel: [], note: ''}); adjDirty = true; adjMsg = ''; drawAdjEditor(); }
  else if (t.dataset.adjdel !== undefined) { adjDraft.splice(+t.dataset.adjdel, 1); adjDirty = true; adjMsg = ''; drawAdjEditor(); }
  else if (t.hasAttribute('data-adjsave')) adjSave();
  else if (t.hasAttribute('data-adjcancel')) { adjDraft = adjClone(adj.items || []); adjDirty = false; adjMsg = ''; drawAdjEditor(); }
});

document.addEventListener('input', e => {
  const t = e.target, f = t.dataset && t.dataset.adj; if (!f || !document.getElementById('adj-editor')) return;
  const a = adjDraft[+t.dataset.i]; if (!a) return;
  if (f === 'sel') {
    const id = +t.dataset.id; a.sel = (a.sel || []).filter(s => s.id !== id);
    if (t.checked) a.sel.push({id, name: t.dataset.name});
    const sum = t.closest('details').querySelector('summary'), n = a.sel.length;
    sum.textContent = `${n} ${a.kind === 'car' ? 'véhicule' : 'événement'}${n > 1 ? 's' : ''} sélectionné${n > 1 ? 's' : ''}`;
  } else if (f === 'enabled') a.enabled = t.checked;
  else if (f === 'amount') a.amount = parseFloat(t.value) || 0;
  else if (f === 'date') a.date = t.value || null;
  else a[f] = t.value;
  if (f === 'kind') { a.sel = []; }
  adjDirty = true; adjMsg = '';
  const save = document.querySelector('[data-adjsave]'), cancel = document.querySelector('[data-adjcancel]');
  if (save) save.disabled = false; if (cancel) cancel.disabled = false;
  if (f === 'kind' || f === 'enabled') drawAdjEditor();
});
