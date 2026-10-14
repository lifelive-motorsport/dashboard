// Pointages › formulaires techniques d'un job (phase 5) : mesure d'embrayage 4 et 6 patins, révisions de boîte de vitesses et de pont arrière (listes OK / NOK). Le panneau s'ouvre depuis la page Jobs (chef d'atelier) ou depuis « Ma semaine »
// (mécanicien) ; le mécanicien saisit, le chef d'atelier valide, la feuille imprimable (charte Lifelive) se télécharge en PDF depuis l'impression du navigateur.
// Données : /api/timesheets/jobs/{id}/forms, /api/timesheets/forms/{id} (backend/app/tforms.py) ; les calculs viennent toujours du serveur.
const tf = {job: null, forms: null, parts: [], carKey: null, types: null, edit: null, msg: null, busy: false};
const tfState = {ok: 'OK pour la prochaine course', replace: 'À remplacer'};
const tfNum = (v, u = '', d = 2) => v == null ? '—' : `${Number(v).toLocaleString(LOCALE(), {maximumFractionDigits: d})}${u ? ' ' + u : ''}`;
const tfType = id => ((tf.types || []).find(t => t.id === id) || {});
const tfJobOf = () => ((typeof ts !== 'undefined' && (ts.jobsAll || ts.jobs)) || []).find(j => j.id === tf.job) || {};
const tfBlank = type => { const s = tfType(type);
  if (s.kind === 'checklist') return {id: null, type, part_id: '', data: {header: {date: plToday(), mechanic: '', ...Object.fromEntries(s.header.map(k => [k, '']))}, requests: Object.fromEntries(s.requests.map(r => [r.id, ''])), items: Object.fromEntries(s.sections.flatMap(x => x.items.map(i => [i.id, {status: '', comment: ''}]))), notes: ''}};
  return {id: null, type, part_id: tf.parts.length === 1 ? tf.parts[0].id : '', data: {header: {date: plToday(), km: '', after: '', mechanism: '', gearbox: '', chassis: '', mechanic: ''}, discs: Object.fromEntries((s.discs || []).map(d => [d.id, Array.from({length: d.pads}, () => Array(s.pads_per_measure).fill(''))])), plates: Object.fromEntries((s.plates || []).map(p => [p.id, Array(s.plate_points).fill('')])), spring_fingers: '', notes: ''}}; };

async function tfOpen(jid) {
  tf.job = jid; tf.edit = null; tf.msg = null; tf.forms = null; tf.parts = []; tf.carKey = null; tsDraw(); window.scrollTo({top: 0});
  try { if (!tf.types) tf.types = (await rsCall('/api/timesheets/form-types')).types; const j = await rsCall(`/api/timesheets/jobs/${encodeURIComponent(jid)}/forms`); tf.forms = j.forms; tf.parts = j.parts || []; tf.carKey = j.car_key; } catch (e) { tf.msg = e.message; tf.forms = tf.forms || []; }
  tsDraw();
}
const tfClose = () => { tf.job = null; tf.edit = null; tf.msg = null; tsDraw(); };

const tfGoGarage = key => { location.hash = '#consigner/rides'; let n = 0; const t = setInterval(() => { if (document.getElementById('rd-view') && typeof rdOpen === 'function') { clearInterval(t); rdOpen(key); } else if (++n > 40) clearInterval(t); }, 150); };
function tfGarage(f) {
  const part = tf.parts.find(p => p.id === f.part_id), g = f.garage || {}, out = [];
  if (part) out.push(`<span class="na">🔗 ${esc(tx('Garage'))} : <b>${esc(part.name)}</b></span>`);
  if (g.logged) out.push(`<span class="ok">✓ ${esc(tx('Contrôle enregistré sur la pièce du Garage.'))}</span>`);
  else if (f.validated && g.reason === 'not_tracked') out.push(`<span class="na">${esc(tx('Cette pièce ne suit pas le contrôle dans le Garage : rien n’a été enregistré.'))}</span>`);
  else if (f.validated && g.reason === 'no_part') out.push(`<span class="na">${esc(tx('Aucune pièce du Garage reliée : rien n’a été enregistré.'))}</span>`);
  if (f.calc.state === 'replace') out.push(`<span class="neg">⚠ ${esc(tx('À remplacer : le remplacement se fait dans le Garage (⟳ Remplacer) ; il n’est jamais automatique.'))}</span>${tf.carKey ? ` <button type="button" class="mini" data-tf="garage" data-k="${esc(tf.carKey)}">${esc(tx('Ouvrir le Garage'))}</button>` : ''}`);
  return out.length ? `<p class="tf-garage">${out.join(' ')}</p>` : '';
}
function tfCheckBody(f) {
  const s = tfType(f.type), c = f.calc, d = f.data;
  const nok = s.sections.flatMap(x => x.items.filter(i => d.items[i.id].status === 'nok').map(i => `<li><b>${esc(tx(i.label))}</b>${d.items[i.id].comment ? ' — ' + esc(d.items[i.id].comment) : ''}</li>`));
  const req = s.requests.filter(r => d.requests[r.id]).map(r => `${esc(tx(r.label))} : <b>${esc(d.requests[r.id])}</b>`).join(' · ');
  return `<p class="tf-sum"><span class="ok">✓ ${c.ok} OK</span> · <span class="${c.nok ? 'neg' : 'na'}">✗ ${c.nok} NOK</span> · <span class="na">${c.open} ${esc(tx('non contrôlés'))}</span> <small class="na">/ ${c.total}</small></p>${nok.length ? `<ul class="tf-nok">${nok.join('')}</ul>` : ''}${req ? `<p class="na">${req}</p>` : ''}${d.notes ? `<p class="na">${esc(d.notes)}</p>` : ''}`;
}
function tfCard(f) {
  const s = tfType(f.type), c = f.calc, h = f.data.header;
  const disc = d => { const r = c.discs[d.id]; return `<tr><th>${esc(tx(d.label))}</th><td class="num">${tfNum(r.mean, 'mm')}</td><td class="num">${tfNum(r.wear, 'mm')}</td><td class="num">${tfNum(r.wear_per_1000km, 'mm', 3)}</td><td class="num">${tfNum(r.remaining_km, 'km', 0)}</td><td>${r.state ? `<b class="${r.state === 'ok' ? 'ok' : 'neg'}">${esc(tx(tfState[r.state]))}</b>` : '—'}</td></tr>`; };
  const chef = typeof ts !== 'undefined' && ts.me && ts.me.role === 'chef';
  return `<div class="tf-card${f.validated ? ' ok' : ''}"><div class="tf-head"><b>${esc(tx(f.label))}</b> <small class="na">${esc(fmtDate(h.date))}${h.mechanic ? ' · ' + esc(h.mechanic) : ''}${h.km != null && h.km !== '' ? ' · ' + tfNum(h.km, 'km', 0) : ''}</small> ${f.validated ? `<span class="ts-lock ok">✓ ${esc(tx('Validé'))}</span>` : `<span class="ts-lock">${esc(tx('Non validé'))}</span>`}
    <span class="tf-acts"><a class="mini" href="/api/timesheets/forms/${esc(f.id)}/print${LANG === 'en' ? '?lang=en' : ''}" target="_blank" rel="noopener">🖨 ${esc(tx('Feuille PDF'))}</a>
    ${!f.validated ? `<button type="button" class="mini" data-tf="edit" data-id="${esc(f.id)}">✎ ${esc(tx('Modifier'))}</button>` : ''}
    ${chef ? `<button type="button" class="mini ${f.validated ? '' : 'okbtn'}" data-tf="val" data-id="${esc(f.id)}" data-v="${f.validated ? 0 : 1}">${esc(tx(f.validated ? 'Rouvrir' : 'Valider'))}</button>` : ''}
    ${!f.validated || chef ? `<button type="button" class="mini danger" data-tf="del" data-id="${esc(f.id)}" title="${esc(tx('Supprimer'))}">🗑</button>` : ''}</span></div>
    ${s.kind === 'checklist' ? tfCheckBody(f) : `<table class="sdtable"><thead><tr><th></th><th class="num">${esc(tx('Épaisseur moyenne'))}</th><th class="num">${esc(tx('Usure'))}</th><th class="num">${esc(tx('Usure / 1 000 km'))}</th><th class="num">${esc(tx('Restant estimé'))}</th><th>${esc(tx('État'))}</th></tr></thead><tbody>${s.discs.map(disc).join('')}</tbody></table>
    ${tfGarage(f)}
    <p class="na">${esc(tx('Conicité max'))} : <b>${tfNum(c.taper_max, 'mm')}</b>${f.data.spring_fingers != null ? ` · Spring fingers : <b>${tfNum(f.data.spring_fingers, 'mm')}</b>` : ''}${f.data.notes ? ` · ${esc(f.data.notes)}` : ''}</p>`}</div>`;
}

function tfPartField(e) {
  const lab = tx('Embrayage du Garage');
  if (!tf.parts.length) return `<p class="na">🔗 ${esc(tx('Aucun embrayage encodé dans le Garage pour cette voiture : la mesure ne sera pas reliée (un lien pourra être ajouté plus tard).'))}</p>`;
  if (tf.parts.length === 1) return `<p class="na">🔗 ${esc(lab)} : <b>${esc(tf.parts[0].name)}</b>${tf.parts[0].km != null ? ` · ${tfNum(tf.parts[0].km, 'km', 0)}` : ''}</p>`;
  return `<label class="sdfield"><span>${esc(lab)}</span><select class="sdin" data-tfv="part"><option value="">—</option>${tf.parts.map(p => `<option value="${esc(p.id)}"${e.part_id === p.id ? ' selected' : ''}>${esc(p.name)}${p.km != null ? ' · ' + tfNum(p.km, 'km', 0) + '' : ''}</option>`).join('')}</select></label>`;
}
function tfCheckEditor() {
  const e = tf.edit, s = tfType(e.type), d = e.data, h = d.header;
  const hf = (k, label, extra = '') => `<label class="sdfield"><span>${esc(tx(label))}</span><input class="sdin" data-tfv="h:${k}" value="${esc(h[k] ?? '')}" maxlength="120" ${extra}></label>`;
  const hdr = s.header.map(k => hf(k, s.header_labels[k], k === 'km' ? 'inputmode="numeric"' : '')).join('');
  const req = s.requests.length ? `<h5>${esc(tx('Demande de réglage'))}</h5><div class="sdgrid">${s.requests.map(r => `<label class="sdfield"><span>${esc(tx(r.label))}</span><input class="sdin" data-tfv="r:${r.id}" value="${esc(d.requests[r.id] ?? '')}" maxlength="120"></label>`).join('')}</div>` : '';
  const sec = x => `<div class="tf-sec"><h5>${esc(tx(x.title))} <small class="na">${x.items.length}</small></h5>${x.items.map(i => { const it = d.items[i.id]; return `<div class="tf-item" data-it="${esc(i.id)}"><span class="tf-il">${esc(tx(i.label))}</span><span class="tf-seg" role="group">${[['ok', 'OK'], ['nok', 'NOK']].map(([v, l]) => `<button type="button" class="tf-st ${v}" data-tf="st" data-i="${esc(i.id)}" data-s="${v}" aria-pressed="${it.status === v}">${l}</button>`).join('')}</span><input class="sdin tf-ic" data-tfv="c:${i.id}" value="${esc(it.comment || '')}" maxlength="200" placeholder="${esc(tx('Commentaire'))}"></div>`; }).join('')}</div>`;
  return `<div class="ts-form"><h4>${esc(tx(s.label))}</h4>
    <div class="sdgrid"><label class="sdfield"><span>${esc(tx('Date'))}</span>${dpField('data-tfv="h:date"', h.date)}</label><label class="sdfield"><span>${esc(tx('Voiture'))}</span><input class="sdin" value="${esc((tfJobOf().vehicle || {}).name || '')}" readonly tabindex="-1"></label>${hf('mechanic', 'Mécanicien')}${hdr}</div>
    ${req}${s.sections.map(sec).join('')}
    <label class="sdfield"><span>${esc(tx('Commentaires'))}</span><input class="sdin" data-tfv="notes" value="${esc(d.notes || '')}" maxlength="1500"></label>
    <div class="sdbar"><button type="button" class="primary" data-tf="save"${tf.busy ? ' disabled' : ''}>${esc(tx(tf.busy ? 'Enregistrement…' : 'Enregistrer'))}</button><button type="button" data-tf="cancel">${esc(tx('Annuler'))}</button>${tf.msg ? `<span class="neg">${esc(tf.msg)}</span>` : ''}</div></div>`;
}
function tfEditor() {
  if (tfType(tf.edit.type).kind === 'checklist') return tfCheckEditor();
  const e = tf.edit, s = tfType(e.type), d = e.data, h = d.header;
  const hf = (k, label, extra = '') => `<label class="sdfield"><span>${esc(tx(label))}</span><input class="sdin" data-tfv="h:${k}" value="${esc(h[k] ?? '')}" maxlength="120" ${extra}></label>`;
  const disc = x => `<div class="tf-disc"><h5>${esc(tx(x.label))} <small class="na">ep0 ${tfNum(tf.types[0].ep0, 'mm')} · mini ${tfNum(tf.types[0].mini, 'mm')}</small></h5><div class="tf-grid" style="--cols:${s.pads_per_measure}">
    ${s.measure_names.some(n => n) ? `<span></span>${s.measure_names.map(n => `<small class="na">${esc(tx(n))}</small>`).join('')}` : ''}
    ${d.discs[x.id].map((row, i) => `<label class="tf-pad">${esc(tx('Patin'))} ${i + 1}</label>${row.map((v, j) => `<input class="sdin num" inputmode="decimal" data-tfv="d:${x.id}:${i}:${j}" value="${esc(v ?? '')}" placeholder="mm">`).join('')}`).join('')}</div></div>`;
  const plate = p => `<div class="tf-plate"><b>${esc(tx(p.label))}</b><div class="tf-row">${d.plates[p.id].map((v, i) => `<input class="sdin num" inputmode="decimal" data-tfv="p:${p.id}:${i}" value="${esc(v ?? '')}" placeholder="${i + 1}">`).join('')}</div></div>`;
  return `<div class="ts-form"><h4>${esc(tx(s.label))}</h4>
    <div class="sdgrid"><label class="sdfield"><span>${esc(tx('Date'))}</span>${dpField('data-tfv="h:date"', h.date)}</label><label class="sdfield"><span>${esc(tx('Voiture'))}</span><input class="sdin" value="${esc((tfJobOf().vehicle || {}).name || '')}" readonly tabindex="-1"></label>${hf('after', 'Après (événement)')}${hf('mechanic', 'Mécanicien')}${hf('gearbox', 'Boîte de vitesses')}${hf('mechanism', 'Mécanisme')}${hf('km', 'Kilométrage (km)', 'inputmode="numeric"')}</div>
    ${tfPartField(e)}
    <div class="tf-discs">${s.discs.map(disc).join('')}</div>
    <h5>${esc(tx('Conicité des plateaux'))} <small class="na">${esc(tx('6 mesures par plateau (mm)'))}</small></h5><div class="tf-plates">${s.plates.map(plate).join('')}</div>
    ${s.spring_fingers ? `<label class="sdfield"><span>Spring fingers (mm)</span><input class="sdin num" inputmode="decimal" data-tfv="sf" value="${esc(d.spring_fingers ?? '')}"></label>` : ''}
    <label class="sdfield"><span>${esc(tx('Remarques'))}</span><input class="sdin" data-tfv="notes" value="${esc(d.notes || '')}" maxlength="1000"></label>
    <p class="na">${esc(tx('Contrôler la planéité des disques ainsi que le libre coulissement des plateaux / mécanisme. Un jeu de disques est prévu pour environ 1 000 km. À contrôler après chaque rallye.'))}</p>
    <div class="sdbar"><button type="button" class="primary" data-tf="save"${tf.busy ? ' disabled' : ''}>${esc(tx(tf.busy ? 'Enregistrement…' : 'Enregistrer'))}</button><button type="button" data-tf="cancel">${esc(tx('Annuler'))}</button>${tf.msg ? `<span class="neg">${esc(tf.msg)}</span>` : ''}</div></div>`;
}

function tfHtml() {
  if (!tf.job) return '';
  const j = tfJobOf();
  const body = tf.forms == null ? '<p class="na loading">Chargement…</p>' : tf.edit ? tfEditor() : `${tf.forms.length ? tf.forms.map(tfCard).join('') : `<p class="na">${esc(tx('Aucun formulaire pour ce job.'))}</p>`}
    <div class="sdbar"><select class="sdin" id="tf-newtype">${(tf.types || []).map(t => `<option value="${esc(t.id)}"${tf.newType === t.id ? ' selected' : ''}>${esc(tx(t.label))}</option>`).join('')}</select><button type="button" data-tf="new">＋ ${esc(tx('Nouveau formulaire'))}</button></div>${tf.msg ? `<p class="neg">${esc(tf.msg)}</p>` : ''}`;
  return `<section class="ts-form tf-panel"><div class="tf-top"><h4>${esc(tx('Formulaires techniques'))} · ${esc(j.title || '')}</h4><button type="button" data-tf="close">${esc(tx('Fermer'))}</button></div>${body}</section>`;
}

document.addEventListener('input', e => {
  const k = e.target.dataset && e.target.dataset.tfv; if (!k || !tf.edit) return;
  const d = tf.edit.data, p = k.split(':'), v = e.target.value;
  if (p[0] === 'h') d.header[p[1]] = v; else if (p[0] === 'r') d.requests[p[1]] = v; else if (p[0] === 'c') d.items[p[1]].comment = v; else if (p[0] === 'd') d.discs[p[1]][+p[2]][+p[3]] = v; else if (p[0] === 'p') d.plates[p[1]][+p[2]] = v; else if (k === 'sf') d.spring_fingers = v; else if (k === 'part') { tf.edit.part_id = v; const pt = tf.parts.find(x => x.id === v); if (pt && pt.km != null && !String(d.header.km ?? '').trim()) { d.header.km = Math.round(pt.km); const kb = document.querySelector('[data-tfv="h:km"]'); if (kb) kb.value = d.header.km; } } else if (k === 'notes') d.notes = v;
});
document.addEventListener('change', e => { if (e.target.id === 'tf-newtype') tf.newType = e.target.value; const k = e.target.dataset && e.target.dataset.tfv; if (k === 'h:date' && tf.edit) tf.edit.data.header.date = e.target.value; });

document.addEventListener('click', async ev => {
  const b = ev.target.closest && ev.target.closest('[data-tf]'); if (!b || !document.getElementById('ts-view')) return;
  const a = b.dataset.tf, id = b.dataset.id;
  try {
    if (a === 'close') return tfClose();
    if (a === 'cancel') { tf.edit = null; tf.msg = null; return tsDraw(); }
    if (a === 'st') { const it = tf.edit.data.items[b.dataset.i], v = b.dataset.s; it.status = it.status === v ? '' : v; const row = b.closest('.tf-item'); row.querySelectorAll('.tf-st').forEach(x => x.setAttribute('aria-pressed', String(it.status === x.dataset.s))); return; }
    if (a === 'new') { const sel = document.getElementById('tf-newtype'); tf.edit = tfBlank((sel && sel.value) || b.dataset.t || tf.types[0].id); const p = ts.me && ts.me.name; if (p) tf.edit.data.header.mechanic = p; const j = tfJobOf(); tf.edit.data.header.after = (j.event && j.event.title) || ''; tf.msg = null; return tsDraw(); }
    if (a === 'edit') { const f = tf.forms.find(x => x.id === id); tf.edit = {id, type: f.type, part_id: f.part_id || '', data: JSON.parse(JSON.stringify(f.data))}; const s = tfType(f.type); for (const [k, rows] of Object.entries(tf.edit.data.discs || {})) rows.forEach(r => r.forEach((v, i) => { if (v == null) r[i] = ''; })); for (const k of Object.keys(tf.edit.data.plates || {})) tf.edit.data.plates[k] = tf.edit.data.plates[k].map(v => v == null ? '' : v); if (tf.edit.data.header.km == null) tf.edit.data.header.km = ''; if (tf.edit.data.spring_fingers == null) tf.edit.data.spring_fingers = ''; tf.msg = null; return tsDraw(); }
    if (a === 'save') {
      tf.busy = true; tf.msg = null; tsDraw();
      try {
        const body = JSON.stringify({type: tf.edit.type, data: tf.edit.data, part_id: tf.edit.part_id});
        const f = tf.edit.id ? await rsCall(`/api/timesheets/forms/${encodeURIComponent(tf.edit.id)}`, {method: 'PUT', body}) : await rsCall(`/api/timesheets/jobs/${encodeURIComponent(tf.job)}/forms`, {method: 'POST', body});
        tf.forms = tf.edit.id ? tf.forms.map(x => x.id === f.id ? f : x) : tf.forms.concat(f); tf.edit = null;
      } catch (err) { tf.msg = err.message; }
      tf.busy = false; return tsDraw();
    }
    if (a === 'val') { const f = await rsCall(`/api/timesheets/forms/${encodeURIComponent(id)}/validate?validated=${b.dataset.v === '1'}`, {method: 'POST'}); tf.forms = tf.forms.map(x => x.id === f.id ? f : x); return tsDraw(); }
    if (a === 'del') { if (!confirm(tx('Supprimer ce formulaire ?'))) return; await rsCall(`/api/timesheets/forms/${encodeURIComponent(id)}`, {method: 'DELETE'}); tf.forms = tf.forms.filter(x => x.id !== id); return tsDraw(); }
    if (a === 'garage') return tfGoGarage(b.dataset.k);
    if (a === 'open') return tfOpen(id);
  } catch (err) { tf.msg = err.message; tsDraw(); }
});
