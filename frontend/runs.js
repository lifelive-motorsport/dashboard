// Technique › Roulages : les sorties (essais, meetings, rallyes) saisies une fois, auxquelles on associe les voitures avec leurs tours / spéciales / kilomètres.
// Les kilomètres des pièces d'une voiture se calculent depuis ses participations (rides.py). La fenêtre d'association (ptOpen) sert aussi dans la fiche d'une voiture du Garage.
const rn = {sessions: null, circuits: [], cars: null, form: null, circ: {name: '', length_km: ''}, showCirc: false, msg: null, ok: false, loading: false, saving: false};
const rnBlank = () => ({id: null, date: rdToday(), name: '', kind: 'circuit', circuit: '', stages: [{name: '', length_km: '', passes: 1}], notes: ''});

function runsBlocks() { return [{static: '<section class="block" data-bid="rn"><div id="ak-view"></div><div id="rn-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function rnLoad() {
  rn.loading = true; rnDraw();
  try {
    const j = await rsCall('/api/rides/sessions'); rn.sessions = j.sessions; rn.circuits = j.circuits; rd.circuits = j.circuits;
    if (!rn.cars) rn.cars = (await rsCall('/api/rides/cars')).cars;
    await tyLoadOpts(true);
    rn.msg = rn.msg && rn.ok ? rn.msg : null;
  } catch (e) { rn.msg = e.message; rn.ok = false; rn.sessions = rn.sessions || []; }
  rn.loading = false; rnDraw();
}

const rnKind = s => s.kind === 'rally' ? `Rallye${s.stages.length ? ` · ${s.stages.length} spéciale${s.stages.length > 1 ? 's' : ''}` : ''}` : esc(s.circuit || 'Circuit');
function rnSessionHtml(s) {
  const cars = s.cars.length ? table(['Voiture', 'Tours', 'Km', 'Heures', 'Pilote(s)', 'Pneus', ''], s.cars.map(c => `<tr><td class="prod">${esc(c.name)}</td><td>${c.laps || ''}</td><td>${rdKm(c.km)}</td><td>${c.hours ? rdKm(c.hours) : ''}</td><td>${esc((c.drivers || []).join(', '))}</td><td>${esc(tyLabels(c.tyres))}</td>
      <td class="rd-acts"><button type="button" class="mini" data-rn="editcar" data-s="${esc(s.id)}" data-r="${esc(c.run_id)}" title="${esc(tx('Modifier la participation'))}">✎</button><button type="button" class="mini" data-rn="delcar" data-r="${esc(c.run_id)}" data-n="${esc(c.name)}" title="${esc(tx('Retirer cette voiture du roulage'))}">✕</button></td></tr>`)) : `<p class="na">${esc(tx('Aucune voiture associée.'))}</p>`;
  return `<div class="rn-card"><div class="rn-head"><div><b>${esc(s.name)}</b> <span class="rd-chip">${rnKind(s)}</span><br><small class="na">${fmtDate(s.date)}${s.cars.length ? ` · ${rdKm(s.km_total)} km ${esc(tx('au total'))}` : ''}${s.notes ? ' · ' + esc(s.notes) : ''}</small></div>
    <div class="rd-acts"><button type="button" class="mini" data-rn="addcar" data-s="${esc(s.id)}">＋ ${esc(tx('Associer une voiture'))}</button><button type="button" class="mini" data-rn="edit" data-s="${esc(s.id)}" title="${esc(tx('Modifier le roulage'))}">✎</button><button type="button" class="mini danger" data-rn="del" data-s="${esc(s.id)}" title="${esc(tx('Supprimer le roulage'))}">🗑</button></div></div>${cars}</div>`;
}
function rnFormHtml() {
  const f = rn.form; if (!f) return '';
  const circ = `<label class="sdfield"><span>Circuit</span><select class="sdin" data-rn-f="circuit"><option value="">—</option>${rn.circuits.map(c => `<option value="${esc(c.name)}" ${f.circuit === c.name ? 'selected' : ''}>${esc(c.name)} · ${rdKm(c.length_km)} km</option>`).join('')}</select></label>${rn.circuits.length ? '' : `<small class="na">${esc(tx('Aucun circuit : enregistrez-en un avec « ⚙ Circuits ».'))}</small>`}`;
  return `<div class="note rd-form"><b>${f.id ? esc(tx('Modifier le roulage')) : esc(tx('Nouveau roulage'))}</b>
    <div class="sdgrid"><label class="sdfield"><span>Date</span>${dpField('data-rn-f="date"', f.date)}</label><label class="sdfield"><span>Nom</span><input class="sdin" data-rn-f="name" value="${esc(f.name)}" placeholder="Essais libres, Spa Six Hours…"></label>
    <div class="sdfield"><span>Type</span><div class="bu-filter"><button type="button" class="rs-pill" data-rn="kind" data-k="circuit" aria-pressed="${f.kind === 'circuit'}">Circuit</button><button type="button" class="rs-pill" data-rn="kind" data-k="rally" aria-pressed="${f.kind === 'rally'}">Rallye</button></div></div></div>
    ${f.kind === 'circuit' ? `<div class="sdgrid">${circ}</div>` : ptStagesHtml(f.stages, 'rn-s')}
    <label class="sdfield"><span>Notes</span><input class="sdin" data-rn-f="notes" value="${esc(f.notes)}"></label>
    ${f.kind === 'rally' ? `<small class="na">${esc(tx('Les spéciales sont recopiées dans la participation de chaque voiture (modifiables voiture par voiture).'))}</small>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-rn="save" ${f.name.trim() && f.date && !rn.saving ? '' : 'disabled'}>${esc(tx(rn.saving ? 'Enregistrement…' : 'Enregistrer'))}</button><button type="button" data-rn="cancel">${esc(tx('Annuler'))}</button>${rn.msg && !rn.ok ? `<span class="neg">${esc(rn.msg)}</span>` : ''}</div></div>`;
}
function rnCircHtml() {
  if (!rn.showCirc) return '';
  return `<div class="note rd-form"><b>Circuits</b><p class="na">${esc(tx('Longueur du tour : sert à calculer les kilomètres (tours × longueur).'))}</p>
    ${rn.circuits.length ? `<div class="rd-circs">${rn.circuits.map(c => `<span class="tagchip">${esc(c.name)} <small class="na">${rdKm(c.length_km)} km</small></span>`).join(' ')}</div>` : `<p class="na">${esc(tx('Aucun circuit enregistré.'))}</p>`}
    <div class="sdbar"><input class="sdin" data-rn-c="name" value="${esc(rn.circ.name)}" placeholder="${esc(tx('Nom du circuit'))}" style="max-width:240px"><input class="sdin" data-rn-c="length_km" value="${esc(rn.circ.length_km)}" placeholder="${esc(tx('Longueur du tour (km)'))}" style="max-width:190px" inputmode="decimal"><button type="button" data-rn="savecirc" ${rn.circ.name.trim() && rdNum(rn.circ.length_km) > 0 ? '' : 'disabled'}>${esc(tx('Enregistrer le circuit'))}</button></div></div>`;
}
function rnDraw() {
  const el = document.getElementById('rn-view'); if (!el) return;
  const msg = rn.msg && rn.ok ? `<p class="na">${esc(rn.msg)}</p>` : rn.msg && !rn.form ? `<p class="neg">${esc(rn.msg)}</p>` : '';
  const list = rn.sessions == null ? `<p class="na loading">${esc(tx('Chargement…'))}</p>` : rn.sessions.length ? rn.sessions.map(rnSessionHtml).join('') : `<p class="na">${esc(tx('Aucun roulage : créez-en un, puis associez-y les voitures qui ont roulé.'))}</p>`;
  const sav = [window.scrollX, window.scrollY];
  el.innerHTML = `<div class="sdbar"><button type="button" class="primary" data-rn="new">＋ ${esc(tx('Nouveau roulage'))}</button><button type="button" data-ak="open">${esc(tx('Roulage Al Kamel'))}</button><button type="button" data-rn="circuits">${esc(tx(rn.showCirc ? 'Fermer les circuits' : '⚙ Circuits'))}</button>${rn.loading && rn.sessions ? '<small class="na loading">Chargement…</small>' : ''}</div>${msg}${rnCircHtml()}${rnFormHtml()}<div class="rn-list">${list}</div>`;
  window.scrollTo(...sav);
}

// ---- Fenêtre d'association d'une voiture à un roulage -----------------------------------------------------------------------------------------
let pt = null;
function ptStagesHtml(stages, ns) {
  return `<div class="rd-stages">${stages.map((s, i) => `<div class="sdbar"><input class="sdin" data-${ns}="name" data-i="${i}" value="${esc(s.name)}" placeholder="Spéciale" style="max-width:220px"><input class="sdin" data-${ns}="length_km" data-i="${i}" value="${esc(s.length_km)}" placeholder="km" style="max-width:90px" inputmode="decimal"><span>×</span><input class="sdin" data-${ns}="passes" data-i="${i}" value="${esc(s.passes)}" style="max-width:60px" inputmode="numeric"><small class="na">${esc(tx('passages'))}</small><button type="button" class="mini" data-${ns === 'rn-s' ? 'rn' : 'pt'}="delstage" data-i="${i}" title="${esc(tx('Retirer cette spéciale'))}">✕</button></div>`).join('')}<button type="button" class="mini" data-${ns === 'rn-s' ? 'rn' : 'pt'}="addstage">＋ ${esc(tx('Spéciale'))}</button></div>`;
}
const ptSession = () => pt && (pt.sessions || []).find(s => s.id === pt.sid);
function ptKm() {
  if (rdNum(pt.km) != null) return rdNum(pt.km);
  const s = ptSession(); if (!s) return null;
  if (s.kind === 'rally') return pt.stages.reduce((t, x) => t + (rdNum(x.length_km) || 0) * (parseInt(x.passes) || 0), 0);
  const c = rd.circuits.find(x => x.name === s.circuit); return c && pt.laps ? c.length_km * parseInt(pt.laps) : null;
}
function ptHtml() {
  const s = ptSession(), p = pt;
  const sessSel = p.fixedSession ? `<div class="sdfield"><span>Roulage</span><b>${esc(s ? s.name : '')}</b> <small class="na">${s ? fmtDate(s.date) : ''}</small></div>`
    : `<label class="sdfield"><span>Roulage</span><select class="sdin" data-pt-f="sid"><option value="">—</option>${p.sessions.map(x => `<option value="${esc(x.id)}" ${p.sid === x.id ? 'selected' : ''}>${fmtDate(x.date)} · ${esc(x.name)}</option>`).join('')}</select></label>`;
  const carSel = p.fixedCar ? `<div class="sdfield"><span>Voiture</span><b>${esc(p.carName)}</b></div>`
    : `<label class="sdfield"><span>Voiture</span><select class="sdin" data-pt-f="key"><option value="">—</option>${(p.cars || []).map(x => `<option value="${esc(x.key)}" ${p.key === x.key ? 'selected' : ''} ${p.taken.has(x.key) ? 'disabled' : ''}>${esc(x.name)}${p.taken.has(x.key) ? ' (' + esc(tx('déjà associée')) + ')' : ''}</option>`).join('')}</select></label>`;
  const body = !s ? '' : s.kind === 'rally' ? `${ptStagesHtml(p.stages, 'pt-s')}`
    : `<div class="sdgrid"><div class="sdfield"><span>Circuit</span><b>${esc(s.circuit || '—')}</b>${(rd.circuits.find(x => x.name === s.circuit) || {}).length_km ? ` <small class="na">${rdKm(rd.circuits.find(x => x.name === s.circuit).length_km)} km / ${esc(tx('tour'))}</small>` : ''}</div><label class="sdfield"><span>Tours</span><input class="sdin" data-pt-f="laps" value="${esc(p.laps)}" style="max-width:100px" inputmode="numeric"></label></div>`;
  const km = s ? ptKm() : null;
  return `<div class="fb-back" data-pt="close"></div><div class="fb-box pt-box" role="dialog" aria-modal="true"><h3>${esc(tx(p.runId ? 'Modifier la participation' : 'Associer une voiture à un roulage'))}</h3>
    <div class="sdgrid">${sessSel}${carSel}</div>${body}
    <div class="sdgrid"><label class="sdfield"><span>Kilomètres (si connus : remplace le calcul)</span><input class="sdin" data-pt-f="km" value="${esc(p.km)}" style="max-width:140px" inputmode="decimal"></label><label class="sdfield"><span>Temps de roulage (heures)</span><input class="sdin" data-pt-f="hours" value="${esc(p.hours)}" style="max-width:140px" inputmode="decimal"></label>
    ${tyPickerHtml('pt', p.key, p.tyres)}
    <label class="sdfield"><span>Pilote(s)</span><input class="sdin" data-pt-f="drivers" value="${esc(p.drivers)}" placeholder="${esc(tx('Séparés par des virgules'))}"></label></div>
    <label class="sdfield"><span>Notes</span><input class="sdin" data-pt-f="notes" value="${esc(p.notes)}"></label>
    <p class="rd-km" id="pt-km">${km == null ? esc(tx('Kilomètres : à compléter')) : `<b>${rdKm(km)} km</b> ${esc(tx('comptés pour toutes les pièces montées'))}`}</p>
    <div class="sdbar"><button type="button" class="primary" data-pt="save" ${p.sid && p.key && !p.saving ? '' : 'disabled'}>${esc(tx(p.saving ? 'Enregistrement…' : 'Enregistrer'))}</button><button type="button" data-pt="close">${esc(tx('Annuler'))}</button>${p.err ? `<span class="neg">${esc(p.err)}</span>` : ''}</div></div>`;
}
function ptDraw() {
  let el = document.getElementById('pt-modal');
  if (!pt) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'pt-modal'; document.body.appendChild(el); }
  el.innerHTML = ptHtml();
  if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(el);
}
// opts : {sid?, key?, carName?, run?, after}. sid fixe le roulage ; key fixe la voiture ; run = participation à modifier.
async function ptOpen(opts) {
  pt = {sid: opts.sid || '', key: opts.key || '', carName: opts.carName || '', runId: opts.run ? opts.run.id : null, fixedSession: !!opts.sid, fixedCar: !!opts.key, sessions: [], cars: null, taken: new Set(), tyres: (opts.run && opts.run.tyres ? opts.run.tyres.map(u => ({set_id: u.set_id, laps: u.laps ?? '', cycles: u.cycles ?? 1})) : []), laps: '', stages: [{name: '', length_km: '', passes: 1}], km: '', hours: '', drivers: '', notes: '', saving: false, err: '', after: opts.after};
  ptDraw();
  try {
    await tyLoadOpts(true);
    const j = await rsCall('/api/rides/sessions'); rd.circuits = j.circuits;
    pt.allSessions = j.sessions;
    pt.sessions = opts.key ? j.sessions.filter(s => !s.cars.some(c => c.key === opts.key) || (opts.run && s.id === opts.run.session_id)) : j.sessions;
    if (!opts.key) { pt.cars = (rn.cars || (rn.cars = (await rsCall('/api/rides/cars')).cars)).filter(c => !c.archived); }
    const s = ptSession();
    if (s && !opts.run) pt.taken = new Set(s.cars.map(c => c.key));
    if (s && s.kind === 'rally' && !opts.run) pt.stages = s.stages.length ? s.stages.map(x => ({name: x.name, length_km: x.length_km, passes: x.passes})) : pt.stages;
    if (opts.run) { const r = opts.run; Object.assign(pt, {laps: r.laps || '', stages: (r.stages && r.stages.length) ? r.stages.map(x => ({name: x.name, length_km: x.length_km, passes: x.passes})) : pt.stages, km: r.km_manual ? r.km : '', hours: r.hours ?? '', drivers: (r.drivers || []).join(', '), notes: r.notes || ''}); }
  } catch (e) { pt.err = e.message; }
  ptDraw();
}
const ptClose = () => { pt = null; ptDraw(); };
function ptOnSession() {
  const s = ptSession(); if (!s) return;
  pt.taken = new Set(s.cars.map(c => c.key));
  if (pt.key && pt.taken.has(pt.key)) pt.key = '';
  if (s.kind === 'rally') pt.stages = s.stages.length ? s.stages.map(x => ({name: x.name, length_km: x.length_km, passes: x.passes})) : [{name: '', length_km: '', passes: 1}];
}
const rnStages = list => list.map(s => ({name: (s.name || '').trim(), length_km: rdNum(s.length_km), passes: parseInt(s.passes) || 1})).filter(s => s.length_km > 0);

document.addEventListener('input', e => {
  const t = e.target;
  if (pt && t.dataset.ptF !== undefined) { pt[t.dataset.ptF] = t.value; if (t.tagName !== 'SELECT') { const k = document.getElementById('pt-km'); const s = ptSession(), km = s ? ptKm() : null; if (k) k.innerHTML = km == null ? esc(tx('Kilomètres : à compléter')) : `<b>${rdKm(km)} km</b> ${esc(tx('comptés pour toutes les pièces montées'))}`; } return; }
  if (pt && t.dataset.ptS !== undefined) { pt.stages[+t.dataset.i][t.dataset.ptS] = t.value; const k = document.getElementById('pt-km'), km = ptKm(); if (k) k.innerHTML = km == null ? esc(tx('Kilomètres : à compléter')) : `<b>${rdKm(km)} km</b> ${esc(tx('comptés pour toutes les pièces montées'))}`; return; }
  if (!document.getElementById('rn-view')) return;
  if (t.dataset.rnF !== undefined && rn.form && !t.classList.contains('dp-h')) { rn.form[t.dataset.rnF] = t.value; const b = document.querySelector('[data-rn=save]'); if (b) b.disabled = !(rn.form.name.trim() && rn.form.date); }
  else if (t.dataset.rnS !== undefined && rn.form) rn.form.stages[+t.dataset.i][t.dataset.rnS] = t.value;
  else if (t.dataset.rnC !== undefined) { rn.circ[t.dataset.rnC] = t.value; const b = document.querySelector('[data-rn=savecirc]'); if (b) b.disabled = !(rn.circ.name.trim() && rdNum(rn.circ.length_km) > 0); }
});
document.addEventListener('change', e => {
  const t = e.target;
  if (pt && t.dataset.ptF === 'sid') { ptOnSession(); ptDraw(); return; }
  if (pt && t.dataset.ptF === 'key') { pt.tyres = []; ptDraw(); return; }
  if (rn.form && t.classList.contains('dp-h') && t.dataset.rnF === 'date') { rn.form.date = t.value; const b = document.querySelector('[data-rn=save]'); if (b) b.disabled = !(rn.form.name.trim() && rn.form.date); }
  if (rn.form && t.dataset.rnF === 'circuit') rn.form.circuit = t.value;
});
document.addEventListener('keydown', e => { if (e.key === 'Escape' && pt) ptClose(); });
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-pt],[data-rn]'); if (!b) return;
  try {
    if (b.dataset.pt) {
      const a = b.dataset.pt;
      if (a === 'close') return ptClose();
      if (a === 'addstage') { pt.stages.push({name: '', length_km: '', passes: 1}); return ptDraw(); }
      if (a === 'delstage') { pt.stages.splice(+b.dataset.i, 1); if (!pt.stages.length) pt.stages.push({name: '', length_km: '', passes: 1}); return ptDraw(); }
      if (a === 'save') {
        const s = ptSession(); pt.saving = true; pt.err = ''; ptDraw();
        const body = {laps: parseInt(pt.laps) || 0, km: rdNum(pt.km), hours: rdNum(pt.hours), drivers: String(pt.drivers).split(',').map(x => x.trim()).filter(Boolean), notes: pt.notes || '', tyres: tyUsesBody(pt.tyres)};
        if (s.kind === 'rally') body.stages = rnStages(pt.stages);
        try {
          if (pt.runId) await rsCall('/api/rides/runs/' + encodeURIComponent(pt.runId), {method: 'PUT', body: JSON.stringify({...body, stages: s.kind === 'rally' ? body.stages : [], date: s.date, name: s.name, kind: s.kind, circuit: s.circuit || '', event_id: s.event_id || ''})});
          else await rsCall(`/api/rides/sessions/${encodeURIComponent(pt.sid)}/cars/${encodeURIComponent(pt.key)}`, {method: 'POST', body: JSON.stringify(body)});
        } catch (err) { pt.saving = false; pt.err = err.message; return ptDraw(); }
        const after = pt.after; ptClose(); if (after) await after(); return;
      }
      return;
    }
    if (!document.getElementById('rn-view')) return;
    const a = b.dataset.rn, sid = b.dataset.s;
    if (a === 'new') { rn.form = rnBlank(); rn.msg = null; return rnDraw(); }
    if (a === 'edit') { const s = rn.sessions.find(x => x.id === sid); rn.form = {id: s.id, date: s.date, name: s.name, kind: s.kind, circuit: s.circuit || '', stages: s.stages.length ? s.stages.map(x => ({...x})) : [{name: '', length_km: '', passes: 1}], notes: s.notes || ''}; rn.msg = null; return rnDraw(); }
    if (a === 'cancel') { rn.form = null; rn.msg = null; return rnDraw(); }
    if (a === 'kind') { rn.form.kind = b.dataset.k; return rnDraw(); }
    if (a === 'addstage') { rn.form.stages.push({name: '', length_km: '', passes: 1}); return rnDraw(); }
    if (a === 'delstage') { rn.form.stages.splice(+b.dataset.i, 1); if (!rn.form.stages.length) rn.form.stages.push({name: '', length_km: '', passes: 1}); return rnDraw(); }
    if (a === 'circuits') { rn.showCirc = !rn.showCirc; return rnDraw(); }
    if (a === 'savecirc') { await rsCall('/api/rides/circuits', {method: 'POST', body: JSON.stringify({name: rn.circ.name.trim(), length_km: rdNum(rn.circ.length_km)})}); rn.circ = {name: '', length_km: ''}; rn.msg = 'Circuit enregistré.'; rn.ok = true; return rnLoad(); }
    if (a === 'save') {
      const f = rn.form; rn.saving = true; rn.msg = null; rnDraw();
      try { await rsCall(f.id ? '/api/rides/sessions/' + encodeURIComponent(f.id) : '/api/rides/sessions', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify({date: f.date, name: f.name.trim(), kind: f.kind, circuit: f.kind === 'circuit' ? f.circuit : '', stages: f.kind === 'rally' ? rnStages(f.stages) : [], notes: f.notes || ''})});
        rn.form = null; rn.saving = false; rn.msg = 'Roulage enregistré.'; rn.ok = true; return rnLoad();
      } catch (err) { rn.saving = false; rn.msg = err.message; rn.ok = false; return rnDraw(); }
    }
    if (a === 'del') { const s = rn.sessions.find(x => x.id === sid); if (!confirm(`${tx('Supprimer le roulage')} « ${s.name} » ?${s.cars.length ? '\n\n' + s.cars.length + ' ' + tx('participation(s) de voitures seront supprimées et les kilomètres des pièces recalculés.') : ''}`)) return;
      await rsCall('/api/rides/sessions/' + encodeURIComponent(sid), {method: 'DELETE'}); rn.msg = 'Roulage supprimé.'; rn.ok = true; rn.cars = null; return rnLoad(); }
    if (a === 'addcar') return ptOpen({sid, after: rnLoad});
    if (a === 'editcar') { const s = rn.sessions.find(x => x.id === sid), c = s.cars.find(x => x.run_id === b.dataset.r); const run = await rsCall('/api/rides/cars/' + encodeURIComponent(c.key)).then(d => d.runs_list.find(r => r.id === c.run_id)); return ptOpen({sid, key: c.key, carName: c.name, run, after: rnLoad}); }
    if (a === 'delcar') { if (!confirm(`${tx('Retirer')} « ${b.dataset.n} » ${tx('de ce roulage ? Les kilomètres des pièces seront recalculés.')}`)) return; await rsCall('/api/rides/runs/' + encodeURIComponent(b.dataset.r), {method: 'DELETE'}); return rnLoad(); }
  } catch (err) { rn.msg = err.message; rn.ok = false; rn.saving = false; rnDraw(); }
});
