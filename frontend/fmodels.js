// Opérer › Modèles › Modèles de formulaires : les listes de contrôle (révisions de boîte et de pont…) et les feuilles de relevés (setup, setdown) sont des modèles que le chef d'atelier,
// l'ingénieur / coordinateur et le Super User modifient : sections et éléments (ou groupes et lignes), demande de réglage, maintenance proposée au Garage à la validation.
// On peut dupliquer un modèle pour créer un nouveau formulaire ; la mesure d'embrayage (calcul d'usure) reste définie dans l'application et s'affiche en consultation.
// Données : /api/timesheets/form-models (backend/app/tmodels.py).
const fm = {list: null, fn: {}, maint: {}, edit: null, msg: null, busy: false};
const FM_KIND = {checklist: 'Liste de contrôle', sheet: 'Feuille de relevés', clutch: 'Mesure d’embrayage'};
const FM_LAYOUT = {axle: 'AV / AR', wheel4: 'Quatre roues', side: 'G / D', one: 'Une valeur'};
const FM_WEIGHT = 'wheel_weights';
function fmBlocks() { return [{static: '<section class="block" data-bid="fm"><div id="fm-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function fmLoad() {
  try { const j = await rsCall('/api/timesheets/form-models'); fm.list = j.models; fm.fn = j.functions; fm.maint = j.maint; fm.msg = fm.msg; } catch (e) { fm.msg = e.message; fm.list = fm.list || []; }
  fmDraw();
}
const fmClone = o => JSON.parse(JSON.stringify(o));
function fmDraw() {
  const el = document.getElementById('fm-view'); if (!el) return;
  if (fm.list == null) { el.innerHTML = '<p class="na loading">Chargement…</p>'; return; }
  const msg = fm.msg ? `<p class="neg">${esc(fm.msg)}</p>` : '';
  if (fm.edit) { el.innerHTML = msg + fmEditor(); if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(el); return; }
  const rows = fm.list.map(m => `<tr><td><b>${esc(tx(m.label))}</b></td><td>${esc(tx(FM_KIND[m.kind] || m.kind))}</td><td>${m.builtin ? `<small class="na">${esc(tx('d’origine'))}</small>` : esc(tx('Personnalisé'))}</td><td class="num">${m.used}</td>
    <td class="rd-acts">${m.readonly ? `<small class="na">${esc(tx('défini dans l’application'))}</small>` : `<button type="button" class="mini" data-fm="edit" data-id="${esc(m.id)}">${esc(tx('Modifier'))}</button><button type="button" class="mini" data-fm="dup" data-id="${esc(m.id)}">${esc(tx('Dupliquer'))}</button>${!m.builtin ? `<button type="button" class="mini danger" data-fm="del" data-id="${esc(m.id)}">${esc(tx('Supprimer'))}</button>` : ''}`}</td></tr>`);
  el.innerHTML = `<p class="na">${esc(tx('Les formulaires techniques d’un job d’atelier : modifiez leurs éléments, ou dupliquez un modèle pour en créer un nouveau. Un formulaire déjà rempli garde ses valeurs.'))}</p>${msg}${table(['Formulaire', 'Genre', 'Origine', 'Remplis', ''], rows)}`;
  if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(el);
}

const fmItems = x => x.items || x.rows;
function fmSelect(attr, opts, cur, blank) { return `<select class="sdin" ${attr}>${blank ? `<option value="">${esc(tx(blank))}</option>` : ''}${opts.map(([v, l]) => `<option value="${esc(v)}"${cur === v ? ' selected' : ''}>${esc(tx(l))}</option>`).join('')}</select>`; }
function fmEditor() {
  const e = fm.edit, sp = e.spec, isCheck = e.kind === 'checklist', g = sp.garage || {};
  const itemRows = (list, gi, locked) => list.map((it, ii) => { const lock = locked && it.id === FM_WEIGHT; return `<div class="fm-item"><input class="sdin" data-fm-i="${gi}.${ii}" value="${esc(it.label)}" maxlength="300"><span class="fm-ctl"><button type="button" class="mini" data-fm="iup" data-g="${gi}" data-i="${ii}" ${ii ? '' : 'disabled'} title="${esc(tx('Monter'))}">↑</button><button type="button" class="mini" data-fm="idn" data-g="${gi}" data-i="${ii}" ${ii < list.length - 1 ? '' : 'disabled'} title="${esc(tx('Descendre'))}">↓</button><button type="button" class="mini danger" data-fm="idel" data-g="${gi}" data-i="${ii}" ${lock ? 'disabled' : ''} title="${esc(tx(lock ? 'Ligne obligatoire (calcul de la pesée)' : 'Retirer'))}">✕</button></span></div>`; }).join('');
  const groups = (isCheck ? sp.sections : sp.groups).map((x, gi, arr) => `<div class="tf-sec fm-sec"><div class="sdbar"><input class="sdin" data-fm-t="${gi}" value="${esc(x.title)}" maxlength="100" placeholder="${esc(tx('Titre de la section'))}">${isCheck ? '' : fmSelect(`data-fm-l="${gi}"`, Object.entries(FM_LAYOUT), x.layout)}
      <span class="fm-ctl"><button type="button" class="mini" data-fm="gup" data-g="${gi}" ${gi ? '' : 'disabled'}>↑</button><button type="button" class="mini" data-fm="gdn" data-g="${gi}" ${gi < arr.length - 1 ? '' : 'disabled'}>↓</button><button type="button" class="mini danger" data-fm="gdel" data-g="${gi}">✕</button></span></div>
    ${itemRows(fmItems(x), gi, !isCheck && sp.weighing)}<button type="button" class="mini" data-fm="iadd" data-g="${gi}">＋ ${esc(tx(isCheck ? 'Élément' : 'Ligne'))}</button></div>`).join('');
  const reqs = isCheck ? `<h5>${esc(tx('Demande de réglage'))}</h5><div class="fm-reqs">${sp.requests.map((r, ri) => `<div class="fm-item"><input class="sdin" data-fm-r="${ri}" value="${esc(r.label)}" maxlength="120"><span class="fm-ctl"><button type="button" class="mini danger" data-fm="rdel" data-i="${ri}">✕</button></span></div>`).join('')}<button type="button" class="mini" data-fm="radd">＋ ${esc(tx('Champ'))}</button></div>` : '';
  return `<div class="ts-form"><h4>${esc(tx(FM_KIND[e.kind]))}</h4>
    <div class="sdgrid"><label class="sdfield"><span>${esc(tx('Nom du formulaire'))}</span><input class="sdin" data-fm-f="label" value="${esc(sp.label)}" maxlength="100"></label>
    <label class="sdfield"><span>${esc(tx('Maintenance proposée au Garage à la validation'))}</span><span class="fm-gar">${fmSelect('data-fm-g="fn"', Object.entries(fm.fn), g.fn || '', '— Aucune —')}${fmSelect('data-fm-g="mt"', Object.entries(fm.maint), g.mt || '')}</span></label></div>
    ${reqs}<h5>${esc(tx(isCheck ? 'Sections' : 'Groupes de lignes'))}</h5>${groups}<button type="button" data-fm="gadd">＋ ${esc(tx(isCheck ? 'Section' : 'Groupe'))}</button>
    <div class="sdbar"><button type="button" class="primary" data-fm="save"${fm.busy ? ' disabled' : ''}>${esc(tx(fm.busy ? 'Enregistrement…' : 'Enregistrer'))}</button><button type="button" data-fm="cancel">${esc(tx('Annuler'))}</button></div></div>`;
}

document.addEventListener('input', ev => {
  const t = ev.target, e = fm.edit; if (!e || !document.getElementById('fm-view')) return;
  const d = t.dataset, sp = e.spec, secs = e.kind === 'checklist' ? sp.sections : sp.groups;
  if (d.fmF === 'label') sp.label = t.value;
  else if (d.fmT !== undefined) secs[+d.fmT].title = t.value;
  else if (d.fmI !== undefined) { const [g, i] = d.fmI.split('.').map(Number); fmItems(secs[g])[i].label = t.value; }
  else if (d.fmR !== undefined) sp.requests[+d.fmR].label = t.value;
});
document.addEventListener('change', ev => {
  const t = ev.target, e = fm.edit; if (!e || !document.getElementById('fm-view')) return;
  if (t.dataset.fmG) { e.spec.garage = e.spec.garage || {fn: '', mt: 'revision'}; e.spec.garage[t.dataset.fmG] = t.value; if (!e.spec.garage.mt) e.spec.garage.mt = 'revision'; }
  if (t.dataset.fmL !== undefined) e.spec.groups[+t.dataset.fmL].layout = t.value;
});
const fmMove = (arr, i, d) => { const j = i + d; if (j < 0 || j >= arr.length) return; [arr[i], arr[j]] = [arr[j], arr[i]]; };
document.addEventListener('click', async ev => {
  const b = ev.target.closest && ev.target.closest('[data-fm]'); if (!b || !document.getElementById('fm-view')) return;
  const a = b.dataset.fm, id = b.dataset.id, e = fm.edit, g = +b.dataset.g, i = +b.dataset.i;
  const secs = e ? (e.kind === 'checklist' ? e.spec.sections : e.spec.groups) : null;
  try {
    if (a === 'edit') { const m = fm.list.find(x => x.id === id); fm.edit = {id, kind: m.kind, spec: fmClone(m.spec)}; fm.msg = null; return fmDraw(); }
    if (a === 'cancel') { fm.edit = null; fm.msg = null; return fmDraw(); }
    if (a === 'dup') { const m = fm.list.find(x => x.id === id), name = prompt(tx('Nom du nouveau formulaire'), m.label + ' (' + tx('copie') + ')'); if (!name) return; await rsCall('/api/timesheets/form-models', {method: 'POST', body: JSON.stringify({from_id: id, label: name})}); fm.msg = null; return fmLoad(); }
    if (a === 'del') { if (!confirm(tx('Supprimer ce formulaire ?'))) return; await rsCall('/api/timesheets/form-models/' + encodeURIComponent(id), {method: 'DELETE'}); fm.msg = null; return fmLoad(); }
    if (!e) return;
    if (a === 'iadd') { fmItems(secs[g]).push({id: '', label: ''}); return fmDraw(); }
    if (a === 'idel') { fmItems(secs[g]).splice(i, 1); return fmDraw(); }
    if (a === 'iup' || a === 'idn') { fmMove(fmItems(secs[g]), i, a === 'iup' ? -1 : 1); return fmDraw(); }
    if (a === 'gadd') { secs.push(e.kind === 'checklist' ? {id: '', title: '', items: [{id: '', label: ''}]} : {id: '', title: '', layout: 'axle', rows: [{id: '', label: ''}]}); return fmDraw(); }
    if (a === 'gdel') { if (confirm(tx('Retirer cette section et ses éléments ?'))) { secs.splice(g, 1); fmDraw(); } return; }
    if (a === 'gup' || a === 'gdn') { fmMove(secs, g, a === 'gup' ? -1 : 1); return fmDraw(); }
    if (a === 'radd') { e.spec.requests.push({id: '', label: ''}); return fmDraw(); }
    if (a === 'rdel') { e.spec.requests.splice(i, 1); return fmDraw(); }
    if (a === 'save') {
      fm.busy = true; fm.msg = null; fmDraw();
      try {
        const sp = e.spec, gar = sp.garage && sp.garage.fn ? {fn: sp.garage.fn, mt: sp.garage.mt || 'revision'} : null;
        await rsCall('/api/timesheets/form-models/' + encodeURIComponent(e.id), {method: 'PUT', body: JSON.stringify({label: sp.label, garage: gar, requests: sp.requests || [], sections: e.kind === 'checklist' ? sp.sections : [], groups: e.kind === 'sheet' ? sp.groups : []})});
        fm.edit = null; fm.busy = false; return fmLoad();
      } catch (err) { fm.msg = err.message; fm.busy = false; return fmDraw(); }
    }
  } catch (err) { fm.msg = err.message; fmDraw(); }
});
