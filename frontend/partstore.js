// Magasin de pièces (Consigner › Roulages › Magasin de pièces) : modèles d'architecture réutilisables (Ensemble › Sous-ensemble › Composant)
// avec, pour chaque élément, les maintenances suivies (remplacement, révision, vidange et nouveaux fluides) et leurs intervalles. Un modèle s'applique à une voiture depuis sa fiche du Garage.
const ps = {ensembles: [], list: null, cur: null, dirty: false, msg: null, ok: false, loading: false, saving: false};
const PS_MAINT = RD_MAINT;
const psId = () => 'n' + Math.random().toString(36).slice(2, 9);
const psNum = v => v === '' || v == null ? null : parseFloat(String(v).replace(',', '.'));
const psLim = (l = {}) => rdLimOf(l);
const psMkNode = (parent, group) => ({id: psId(), parent_id: parent, name: '', reference: '', fn: '', group, types: group ? [] : ['replace'], ...Object.fromEntries(PS_MAINT.map(([k]) => [k, psLim()]))});
const psBlank = () => ({id: null, name: '', description: '', nodes: []});

function partsBlocks() { return [{static: '<section class="block" data-bid="ps"><div id="ps-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function psLoad() {
  ps.loading = true; psDraw();
  try { const j = await rsCall('/api/rides/templates'); ps.list = j.templates; ps.ensembles = j.ensembles || ps.ensembles; } catch (e) { ps.msg = e.message; ps.ok = false; ps.list = ps.list || []; }
  ps.loading = false; psDraw();
}
const psDepth = (t, n) => { let d = 1, p = n.parent_id; while (p) { d++; p = (t.nodes.find(x => x.id === p) || {}).parent_id; } return d; };
const psKids = (t, id) => t.nodes.filter(n => (n.parent_id || null) === (id || null));

function psSummary(t) {
  const g = t.nodes.filter(n => n.group).length, p = t.nodes.length - g;
  return `${g} ensemble${g > 1 ? 's' : ''} · ${p} élément${p > 1 ? 's' : ''}`;
}
function psNodeHtml(t, n, depth) {
  const pad = `style="margin-left:${(depth - 1) * 24}px"`;
  const lbl = n.group ? 'Ensemble' : depth === 2 ? 'Sous-ensemble' : 'Composant';
  const maint = n.group ? '' : `<div class="rd-types">${PS_MAINT.map(([k, l]) => `<label class="chk"><input type="checkbox" data-ps-t="${esc(n.id)}" data-k="${k}" ${n.types.includes(k) ? 'checked' : ''}> ${esc(l)}</label>`).join('')}</div>`
    + PS_MAINT.filter(([k]) => n.types.includes(k)).map(([k]) => rdLimRow(k, n[k], f => `data-ps-l="${esc(n.id)}" data-k="${k}" data-f="${f}"`)).join('');
  const used = new Set(t.nodes.filter(x => !x.parent_id && x.id !== n.id).map(x => x.name));
  const nameCtl = !n.parent_id ? `<select class="sdin ps-name" data-ps-n="${esc(n.id)}"><option value="">${esc(tx('Choisir un ensemble…'))}</option>${ps.ensembles.map(e => `<option value="${esc(e)}" ${n.name === e ? 'selected' : ''} ${used.has(e) ? 'disabled' : ''}>${esc(e)}</option>`).join('')}</select>`
    : `<input class="sdin ps-name" data-ps-n="${esc(n.id)}" value="${esc(n.name)}" placeholder="${depth === 2 ? 'Moteur, Turbo, Boîte…' : 'Filtre, Bougies…'}"><input class="sdin ps-ref" data-ps-r="${esc(n.id)}" value="${esc(n.reference || '')}" placeholder="${esc(tx('Référence constructeur'))}" maxlength="60">${n.group ? '' : `<span class="ps-fn" title="${esc(tx('Fonction (lien avec les jobs)'))}">${rdFnSelect(n.fn || '', `data-ps-fn="${esc(n.id)}"`)}</span>`}`;
  return `<div class="ps-node ${n.group ? 'grp' : ''}" ${pad}><div class="sdbar"><small class="na ps-kind">${lbl}</small>${nameCtl}
      ${depth < 3 ? `<button type="button" class="mini" data-ps="add" data-p="${esc(n.id)}" title="Ajouter dessous">＋ ${depth === 1 ? 'Sous-ensemble' : 'Composant'}</button>` : ''}<button type="button" class="mini" data-ps="del" data-p="${esc(n.id)}" title="Supprimer">🗑</button></div>${maint}</div>`
    + psKids(t, n.id).map(c => psNodeHtml(t, c, depth + 1)).join('');
}
function psDraw() {
  const el = document.getElementById('ps-view'); if (!el) return;
  const msg = ps.msg ? `<p class="${ps.ok ? 'na' : 'neg'}">${esc(ps.msg)}</p>` : '';
  if (!ps.cur) {
    const cards = (ps.list || []).map(t => `<div class="ps-card"><div><b>${esc(t.name)}</b>${t.description ? `<br><small class="na">${esc(t.description)}</small>` : ''}<br><small class="na">${psSummary(t)}</small></div>
      <div class="rd-acts"><button type="button" class="mini" data-ps="open" data-t="${esc(t.id)}">✎ Modifier</button><button type="button" class="mini" data-ps="dup" data-t="${esc(t.id)}">⧉ Dupliquer</button><button type="button" class="mini danger" data-ps="deltpl" data-t="${esc(t.id)}" title="Supprimer ce modèle" aria-label="Supprimer ce modèle">🗑 Supprimer</button></div></div>`).join('');
    el.innerHTML = `<p class="na">Un modèle décrit l’architecture d’une voiture : ensembles (liste fixe : Moteur, Transmission, Freins…), sous-ensembles (Engine, Turbo…) et, pour chacun, les maintenances suivies avec leurs intervalles. On l’applique ensuite à une voiture depuis sa fiche dans le Garage.</p>
      <div class="sdbar"><button type="button" class="primary" data-ps="new">＋ Nouveau modèle</button>${ps.loading ? '<small class="na loading">Chargement…</small>' : ''}</div>${msg}
      ${cards ? `<div class="ps-list">${cards}</div>` : (ps.list ? '<p class="na">Aucun modèle : créez-en un (par exemple « Voiture circuit turbo 2 RM »).</p>' : '')}`;
    return;
  }
  const t = ps.cur;
  el.innerHTML = `<div class="sdbar"><button type="button" data-ps="back">← Modèles</button></div>${msg}
    <div class="sdgrid"><label class="sdfield" style="grid-column:1/-1"><span>Nom du modèle</span><input class="sdin" data-ps-f="name" value="${esc(t.name)}" maxlength="80" placeholder="Voiture circuit turbo 2 RM"></label>
    <label class="sdfield" style="grid-column:1/-1"><span>Description</span><input class="sdin" data-ps-f="description" value="${esc(t.description)}" maxlength="300"></label></div>
    <h4 class="sub">Architecture</h4>
    <div class="ps-tree">${psKids(t, null).map(n => psNodeHtml(t, n, 1)).join('') || '<p class="na">Aucun élément : ajoutez un ensemble (par exemple Moteur), puis ses sous-ensembles (Engine, Turbo…).</p>'}</div>
    <div class="sdbar"><button type="button" class="mini" data-ps="addroot">＋ Ensemble</button></div>
    <div class="sdbar"><button type="button" class="primary" data-ps="save" ${ps.saving || !t.name.trim() ? 'disabled' : ''}>${ps.saving ? 'Enregistrement…' : 'Enregistrer le modèle'}</button><button type="button" data-ps="back">Fermer</button>${ps.dirty ? '<small class="na">Modifications non enregistrées</small>' : ''}</div>`;
}
const psLimBody = L => ({limit_km: psNum(L.limit_km), limit_hours: psNum(L.limit_hours), limit_events: psNum(L.limit_events), warn_pct: psNum(L.warn_pct) || 75, note: L.note || ''});
const psBody = t => ({name: t.name.trim(), description: t.description || '', nodes: t.nodes.filter(n => n.name.trim()).map(n => ({id: n.id, parent_id: n.parent_id || null, name: n.name.trim(), reference: n.reference || '', fn: n.group ? '' : (n.fn || ''), group: !!n.group, types: n.group ? [] : n.types,
  ...Object.fromEntries(PS_MAINT.map(([k]) => [k, psLimBody(n[k])]))}))});
const psFromApi = t => ({id: t.id, name: t.name, description: t.description || '', nodes: t.nodes.map(n => ({id: n.id, parent_id: n.parent_id || null, name: n.name, reference: n.reference || '', fn: n.fn || '', group: !!n.group, types: n.types || [], ...Object.fromEntries(PS_MAINT.map(([k]) => [k, psLim(n[k])]))}))});

document.addEventListener('input', e => {
  const t = e.target, c = ps.cur; if (!c || !document.getElementById('ps-view')) return;
  if (t.dataset.psF !== undefined) c[t.dataset.psF] = t.value;
  else if (t.dataset.psN !== undefined) c.nodes.find(n => n.id === t.dataset.psN).name = t.value;
  else if (t.dataset.psR !== undefined) c.nodes.find(n => n.id === t.dataset.psR).reference = t.value;
  else if (t.dataset.psFn !== undefined) c.nodes.find(n => n.id === t.dataset.psFn).fn = t.value;
  else if (t.dataset.psL !== undefined) c.nodes.find(n => n.id === t.dataset.psL)[t.dataset.k][t.dataset.f] = t.value;
  else return;
  ps.dirty = true; const b = document.querySelector('[data-ps=save]'); if (b) b.disabled = ps.saving || !c.name.trim();
});
document.addEventListener('change', e => {
  const t = e.target, c = ps.cur; if (!c || t.dataset.psT === undefined || !document.getElementById('ps-view')) return;
  const n = c.nodes.find(x => x.id === t.dataset.psT), k = t.dataset.k;
  n.types = PS_MAINT.map(x => x[0]).filter(x => x === k ? t.checked : n.types.includes(x)); ps.dirty = true; psDraw();
});
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-ps]'); if (!b || !document.getElementById('ps-view')) return;
  const a = b.dataset.ps, c = ps.cur;
  try {
    if (a === 'new') { ps.cur = psBlank(); ps.dirty = false; ps.msg = null; return psDraw(); }
    if (a === 'open') { ps.cur = psFromApi(ps.list.find(x => x.id === b.dataset.t)); ps.dirty = false; ps.msg = null; return psDraw(); }
    if (a === 'dup') { const x = psFromApi(ps.list.find(y => y.id === b.dataset.t)); x.id = null; x.name += ' (copie)'; ps.cur = x; ps.dirty = true; ps.msg = null; return psDraw(); }
    if (a === 'deltpl') { const x = ps.list.find(y => y.id === b.dataset.t); if (!confirm(`Supprimer le modèle « ${x.name} » ? Les voitures déjà construites avec ce modèle gardent leurs pièces.`)) return; await rsCall('/api/rides/templates/' + encodeURIComponent(x.id), {method: 'DELETE'}); ps.msg = 'Modèle supprimé.'; ps.ok = true; return psLoad(); }
    if (a === 'back') { if (ps.dirty && !confirm('Abandonner les modifications non enregistrées ?')) return; ps.cur = null; ps.dirty = false; return psLoad(); }
    if (a === 'addroot') { c.nodes.push(psMkNode(null, true)); ps.dirty = true; return psDraw(); }
    if (a === 'add') { const par = c.nodes.find(n => n.id === b.dataset.p); c.nodes.push(psMkNode(par.id, false)); ps.dirty = true; return psDraw(); }
    if (a === 'del') { const kill = new Set([b.dataset.p]); let grew = true; while (grew) { grew = false; c.nodes.forEach(n => { if (n.parent_id && kill.has(n.parent_id) && !kill.has(n.id)) { kill.add(n.id); grew = true; } }); }
      const names = c.nodes.filter(n => kill.has(n.id)).length; if (names > 1 && !confirm(`Supprimer cet élément et ses ${names - 1} sous-élément(s) ?`)) return; c.nodes = c.nodes.filter(n => !kill.has(n.id)); ps.dirty = true; return psDraw(); }
    if (a === 'save') {
      ps.saving = true; psDraw();
      try { const j = await rsCall(c.id ? '/api/rides/templates/' + encodeURIComponent(c.id) : '/api/rides/templates', {method: c.id ? 'PUT' : 'POST', body: JSON.stringify(psBody(c))}); ps.cur = psFromApi(j); ps.dirty = false; ps.msg = 'Modèle enregistré.'; ps.ok = true; ps.list = (await rsCall('/api/rides/templates')).templates; }
      catch (err) { ps.msg = err.message; ps.ok = false; }
      ps.saving = false; return psDraw();
    }
  } catch (err) { ps.msg = err.message; ps.ok = false; ps.saving = false; psDraw(); }
});
