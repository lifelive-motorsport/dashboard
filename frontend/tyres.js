// Opérer › Pneus : stock de trains de pneus par voiture (référence, type, dimensions, gomme, état, limites) ; kilomètres, tours et cycles de chauffe CALCULÉS d'après les
// roulages (la participation d'une voiture indique le ou les trains utilisés). Ce fichier fournit aussi le sélecteur de trains des participations (tyPickerHtml).
const ty = {sets: null, cars: [], car: '', showScrap: false, form: null, open: new Set(), msg: null, ok: false, saving: false, loading: false};
let tyOpts = null;
const tyBlank = car => ({id: null, car, ref: '', brand: '', model: '', size: '', compound: '', bought: '', status: 'new', limit_km: '', limit_laps: '', limit_cycles: '', alert_pct: 75, start_km: '', start_laps: '', start_cycles: '', notes: ''});
const tyStatus = {new: 'Neuf', used: 'Utilisé', reserve: 'En réserve', scrap: 'Rebut'};

async function tyLoadOpts(force) {
  if (tyOpts && !force) return tyOpts;
  try { tyOpts = (await rsCall('/api/rides/tyres/options')).options; } catch { tyOpts = tyOpts || []; }
  return tyOpts;
}
const tyRef = id => { const o = (tyOpts || []).find(x => x.id === id); return o ? o.ref : '?'; };
const tyLabels = list => (list || []).map(u => tyRef(u.set_id) + (u.laps != null ? ` (${u.laps})` : '')).join(', ');

// ---- Sélecteur de trains dans une participation ----------------------------------------------------------------------------------------------
function tyTarget(ns) {
  const p = ns.split('|');
  if (p[0] === 'pt') return pt && {list: pt.tyres, draw: ptDraw, car: pt.key};
  if (p[0] === 'ak') { const m = ((ak.tyres[p[1]] = ak.tyres[p[1]] || {})); return {list: (m[p[2]] = m[p[2]] || []), draw: akDraw, car: p[2]}; }
  if (p[0] === 'akm') { const c = ak.manual[+p[1]].cars[+p[2]]; c.tyres = c.tyres || []; return {list: c.tyres, draw: akDraw, car: c.key}; }
  return null;
}
function tyPickerHtml(ns, car, uses) {
  if (!car) return '';
  const opts = (tyOpts || []).filter(o => o.car === car);
  const rows = (uses || []).map((u, i) => `<div class="sdbar ty-row"><select class="sdin" data-ty-ns="${esc(ns)}" data-ty-i="${i}" data-ty-k="set_id" style="max-width:260px"><option value="">—</option>${opts.filter(o => o.status !== 'scrap' || o.id === u.set_id).map(o => `<option value="${esc(o.id)}" ${u.set_id === o.id ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>
    <input class="sdin" data-ty-ns="${esc(ns)}" data-ty-i="${i}" data-ty-k="laps" value="${esc(u.laps ?? '')}" placeholder="${esc(tx('Tours (option)'))}" inputmode="numeric" style="max-width:110px" title="${esc(tx('Tours roulés avec ce train ; vide = tous (un seul train) ou répartis à parts égales'))}">
    <input class="sdin" data-ty-ns="${esc(ns)}" data-ty-i="${i}" data-ty-k="cycles" value="${esc(u.cycles ?? 1)}" placeholder="${esc(tx('Cycles'))}" inputmode="numeric" style="max-width:80px" title="${esc(tx('Cycles de chauffe de ce train pendant la session'))}">
    <button type="button" class="mini danger" data-ty="del" data-ty-ns="${esc(ns)}" data-ty-i="${i}">✕</button></div>`).join('');
  const add = opts.some(o => o.status !== 'scrap') ? `<button type="button" class="mini" data-ty="add" data-ty-ns="${esc(ns)}">＋ ${esc(tx('Train de pneus'))}</button>` : `<small class="na">${esc(tx('Aucun train de pneus pour cette voiture (Opérer › Pneus).'))}</small>`;
  return `<div class="sdfield ty-pick"><span>${esc(tx('Pneus utilisés'))}</span>${rows}${add}</div>`;
}
const tyUsesBody = uses => (uses || []).filter(u => u.set_id).map(u => ({set_id: u.set_id, laps: u.laps === '' || u.laps == null ? null : parseInt(u.laps), cycles: u.cycles === '' || u.cycles == null ? 1 : parseInt(u.cycles) || 0}));

// ---- Page ----------------------------------------------------------------------------------------------------------------------------------------
function tyresBlocks() { return [{static: '<section class="block" data-bid="ty"><div id="ty-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function tyLoad() {
  ty.loading = true; tyDraw();
  try {
    const j = await rsCall('/api/rides/tyres'); ty.sets = j.sets; ty.cars = j.cars;
    if (!ty.car || !ty.cars.some(c => c.key === ty.car)) ty.car = (ty.sets.find(s => s.status !== 'scrap') || ty.sets[0] || {}).car || (ty.cars[0] || {}).key || '';
    await tyLoadOpts(true);
  } catch (e) { ty.msg = e.message; ty.ok = false; ty.sets = ty.sets || []; }
  ty.loading = false; tyDraw();
}

const tyBar = t => { if (t.ratio == null) return ''; const pct = Math.min(100, Math.round(t.ratio * 100)); return `<div class="ty-bar" title="${pct} %"><i style="width:${pct}%;background:var(--${t.state === 'over' ? 'neg' : t.state === 'warn' ? 'red' : 'grn'})"></i></div>`; };
const tyChip = t => `<span class="rd-chip ${t.status === 'scrap' ? '' : t.state === 'over' ? 'neg' : t.state === 'warn' ? 'warn' : t.status === 'new' ? 'pos' : ''}">${esc(tx(tyStatus[t.status]))}${t.state === 'over' && t.status !== 'scrap' ? ' ⛔' : t.state === 'warn' && t.status !== 'scrap' ? ' ⚠' : ''}</span>`;

function tyFormHtml() {
  const f = ty.form; if (!f) return '';
  const inp = (k, label, ph = '', style = '') => `<label class="sdfield"><span>${esc(tx(label))}</span><input class="sdin" data-ty-f="${k}" value="${esc(f[k])}" placeholder="${esc(ph)}" ${style ? `style="${style}"` : ''}></label>`;
  return `<div class="note rd-form"><b>${esc(tx(f.id ? 'Modifier le train de pneus' : 'Nouveau train de pneus'))}</b>
    <div class="sdgrid">${inp('ref', 'Référence du train', 'S9', 'max-width:130px')}${inp('brand', 'Marque', 'Hoosier')}${inp('model', 'Modèle', 'R8')}${inp('size', 'Dimensions', '27/65-18')}${inp('compound', 'Gomme', 'R8, slick, pluie…')}
    <label class="sdfield"><span>${esc(tx('Date d’achat'))}</span>${dpField('data-ty-f="bought"', f.bought)}</label>
    <label class="sdfield"><span>${esc(tx('État'))}</span><select class="sdin" data-ty-f="status">${Object.entries(tyStatus).map(([k, l]) => `<option value="${k}" ${f.status === k ? 'selected' : ''}>${esc(tx(l))}</option>`).join('')}</select></label></div>
    <p class="na">${esc(tx('Limites de vie (facultatives) : une alerte apparaît à partir du seuil.'))}</p>
    <div class="sdgrid">${inp('limit_km', 'Limite (km)', '', 'max-width:120px')}${inp('limit_laps', 'Limite (tours)', '', 'max-width:120px')}${inp('limit_cycles', 'Limite (cycles de chauffe)', '', 'max-width:150px')}${inp('alert_pct', 'Seuil d’alerte (%)', '75', 'max-width:110px')}</div>
    <p class="na">${esc(tx('Déjà roulé à l’encodage (ajouté aux roulages de Logbook) :'))}</p>
    <div class="sdgrid">${inp('start_km', 'Km', '0', 'max-width:110px')}${inp('start_laps', 'Tours', '0', 'max-width:110px')}${inp('start_cycles', 'Cycles', '0', 'max-width:110px')}</div>
    ${inp('notes', 'Notes')}
    <div class="sdbar"><button type="button" class="primary" data-ty="save" ${f.ref.trim() && !ty.saving ? '' : 'disabled'}>${esc(tx(ty.saving ? 'Enregistrement…' : 'Enregistrer'))}</button><button type="button" data-ty="cancel">${esc(tx('Annuler'))}</button>${ty.msg && !ty.ok ? `<span class="neg">${esc(ty.msg)}</span>` : ''}</div></div>`;
}

function tyDraw() {
  const el = document.getElementById('ty-view'); if (!el) return;
  const sav = [window.scrollX, window.scrollY];
  const carSel = `<label class="sdfield"><span>${esc(tx('Voiture'))}</span><select class="sdin" data-ty-f="__car" style="min-width:220px">${ty.cars.filter(c => !c.archived).map(c => `<option value="${esc(c.key)}" ${ty.car === c.key ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>`;
  let list = '';
  if (ty.sets == null) list = `<p class="na loading">${esc(tx('Chargement…'))}</p>`;
  else {
    const mine = ty.sets.filter(t => t.car === ty.car), shown = mine.filter(t => ty.showScrap || t.status !== 'scrap'), hidden = mine.length - shown.length;
    const rows = shown.map(t => `<tr class="${t.status === 'scrap' ? 'na' : ''}"><td class="prod"><b>${esc(t.ref)}</b></td><td>${esc([t.brand, t.model].filter(Boolean).join(' '))}${t.compound ? ` <small class="na">${esc(t.compound)}</small>` : ''}</td><td>${esc(t.size || '')}</td><td>${tyChip(t)}</td>
      <td>${rdKm(t.km)}${t.limit_km ? ` <small class="na">/ ${rdKm(t.limit_km)}</small>` : ''}</td><td>${t.laps}${t.limit_laps ? ` <small class="na">/ ${t.limit_laps}</small>` : ''}</td><td>${t.cycles}${t.limit_cycles ? ` <small class="na">/ ${t.limit_cycles}</small>` : ''}</td><td>${tyBar(t)}</td>
      <td class="rd-acts"><button type="button" class="mini" data-ty="hist" data-id="${esc(t.id)}" title="${esc(tx('Historique d’utilisation'))}">${ty.open.has(t.id) ? '▾' : '▸'} ${t.runs}</button><button type="button" class="mini" data-ty="edit" data-id="${esc(t.id)}" title="${esc(tx('Modifier'))}">✎</button>
      <button type="button" class="mini" data-ty="${t.status === 'scrap' ? 'restore' : 'scrap'}" data-id="${esc(t.id)}" title="${esc(tx(t.status === 'scrap' ? 'Remettre en service' : 'Mettre au rebut'))}">${t.status === 'scrap' ? '↺' : '🗑'}</button></td></tr>
      ${ty.open.has(t.id) ? `<tr><td colspan="9">${t.history.length ? table(['Date', 'Roulage', 'Tours', 'Km', 'Cycles'], t.history.map(h => `<tr><td>${fmtDate(h.date)}</td><td>${esc(h.name)}</td><td>${h.laps}</td><td>${rdKm(h.km)}</td><td>${h.cycles}</td></tr>`)) : `<p class="na">${esc(tx('Pas encore utilisé dans un roulage.'))}</p>`}${t.start_km || t.start_laps || t.start_cycles ? `<small class="na">${esc(tx('Déjà roulé à l’encodage'))} : ${rdKm(t.start_km)} km · ${t.start_laps} ${esc(tx('tours'))} · ${t.start_cycles} ${esc(tx('cycles'))}</small>` : ''}</td></tr>` : ''}`);
    list = shown.length ? table(['Réf.', 'Pneu', 'Dimensions', 'État', 'Km', 'Tours', 'Cycles', 'Usure', ''], rows) : `<p class="na">${esc(tx('Aucun train de pneus pour cette voiture : ajoutez-en un.'))}</p>`;
    if (hidden) list += `<p><button type="button" class="mini" data-ty="toggle">${esc(tx(ty.showScrap ? 'Masquer les trains au rebut' : 'Afficher les trains au rebut'))} (${hidden})</button></p>`;
    else if (ty.showScrap) list += `<p><button type="button" class="mini" data-ty="toggle">${esc(tx('Masquer les trains au rebut'))}</button></p>`;
  }
  el.innerHTML = `<div class="sdbar">${carSel}<button type="button" class="primary" data-ty="new">＋ ${esc(tx('Nouveau train'))}</button>${ty.loading && ty.sets ? '<small class="na loading">Chargement…</small>' : ''}</div>${ty.msg && ty.ok ? `<p class="na">${esc(ty.msg)}</p>` : ''}${tyFormHtml()}${list}`;
  if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(el);
  window.scrollTo(...sav);
}

const tyBody = f => ({car: f.car, ref: f.ref.trim(), brand: f.brand.trim(), model: f.model.trim(), size: f.size.trim(), compound: f.compound.trim(), bought: f.bought || null, status: f.status,
  limit_km: rdNum(f.limit_km), limit_laps: f.limit_laps === '' ? null : parseInt(f.limit_laps), limit_cycles: f.limit_cycles === '' ? null : parseInt(f.limit_cycles), alert_pct: rdNum(f.alert_pct) || 75,
  start_km: rdNum(f.start_km) || 0, start_laps: parseInt(f.start_laps) || 0, start_cycles: parseInt(f.start_cycles) || 0, notes: f.notes.trim()});

document.addEventListener('input', e => {
  const t = e.target;
  if (t.dataset && t.dataset.tyNs !== undefined) { const g = tyTarget(t.dataset.tyNs); if (g) g.list[+t.dataset.tyI][t.dataset.tyK] = t.value; return; }
  if (t.dataset && t.dataset.tyF !== undefined && ty.form && !t.classList.contains('dp-h') && t.tagName !== 'SELECT') { ty.form[t.dataset.tyF] = t.value; const b = document.querySelector('[data-ty=save]'); if (b) b.disabled = !ty.form.ref.trim() || ty.saving; }
});
document.addEventListener('change', e => {
  const t = e.target;
  if (t.dataset && t.dataset.tyNs !== undefined && t.dataset.tyK === 'set_id') { const g = tyTarget(t.dataset.tyNs); if (g) { g.list[+t.dataset.tyI].set_id = t.value; } return; }
  if (!t.dataset || t.dataset.tyF === undefined) return;
  if (t.dataset.tyF === '__car') { ty.car = t.value; ty.form = null; ty.open = new Set(); return tyDraw(); }
  if (ty.form) ty.form[t.dataset.tyF] = t.value;
});
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-ty]'); if (!b) return;
  const a = b.dataset.ty;
  if (b.dataset.tyNs !== undefined) {                                   // sélecteur de trains d'une participation
    const g = tyTarget(b.dataset.tyNs); if (!g) return;
    if (a === 'add') { g.list.push({set_id: '', laps: '', cycles: 1}); return g.draw(); }
    if (a === 'del') { g.list.splice(+b.dataset.tyI, 1); return g.draw(); }
    return;
  }
  if (!document.getElementById('ty-view')) return;
  try {
    if (a === 'new') { ty.form = tyBlank(ty.car); ty.msg = null; return tyDraw(); }
    if (a === 'cancel') { ty.form = null; ty.msg = null; return tyDraw(); }
    if (a === 'toggle') { ty.showScrap = !ty.showScrap; return tyDraw(); }
    if (a === 'hist') { const id = b.dataset.id; ty.open.has(id) ? ty.open.delete(id) : ty.open.add(id); return tyDraw(); }
    if (a === 'edit') { const t = ty.sets.find(x => x.id === b.dataset.id); ty.form = {...tyBlank(t.car), ...Object.fromEntries(Object.keys(tyBlank('')).map(k => [k, t[k] ?? ''])), id: t.id, car: t.car}; ty.msg = null; return tyDraw(); }
    if (a === 'scrap' || a === 'restore') {
      const t = ty.sets.find(x => x.id === b.dataset.id);
      if (a === 'scrap' && !confirm(`${tx('Mettre au rebut le train')} « ${t.ref} » ? ${tx('Il ne sera plus proposé dans les roulages ; son historique est conservé.')}`)) return;
      await rsCall('/api/rides/tyres/' + encodeURIComponent(t.id), {method: 'PUT', body: JSON.stringify({...tyBody({...tyBlank(t.car), ...Object.fromEntries(Object.keys(tyBlank('')).map(k => [k, t[k] ?? ''])), car: t.car}), status: a === 'scrap' ? 'scrap' : 'used'})});
      ty.msg = null; return tyLoad();
    }
    if (a === 'save') {
      const f = ty.form; ty.saving = true; ty.msg = null; tyDraw();
      try { await rsCall(f.id ? '/api/rides/tyres/' + encodeURIComponent(f.id) : '/api/rides/tyres', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify(tyBody(f))}); ty.form = null; ty.saving = false; ty.msg = 'Train de pneus enregistré.'; ty.ok = true; return tyLoad(); }
      catch (err) { ty.saving = false; ty.msg = err.message; ty.ok = false; return tyDraw(); }
    }
  } catch (err) { ty.msg = err.message; ty.ok = false; ty.saving = false; tyDraw(); }
});
