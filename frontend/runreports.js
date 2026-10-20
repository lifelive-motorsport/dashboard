// Opérer › Run reports : le rapport remis au client après un meeting (une épreuve, une voiture). Chiffres Al Kamel repris des roulages ; l'ingénieur complète
// par run (objectifs, setup, pressions, observations, retour pilote), puis les pneus et les actions. Validation par le chef d'atelier / l'ingénieur / le Super User.
const rr = {meetings: null, loading: false, view: null, form: null, msg: null, ok: false, saving: false};
const rrKinds = {practice: 'Essais libres', qualifying: 'Qualifications', race: 'Course'};
const rrBlank4 = () => ['', '', '', ''];

function rrBlocks() { return [{static: '<section class="block" data-bid="rr"><div id="rr-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function rrLoad() {
  rr.loading = true; rrDraw();
  try { rr.meetings = (await rsCall('/api/rides/reports')).meetings; } catch (e) { rr.msg = e.message; rr.ok = false; rr.meetings = rr.meetings || []; }
  rr.loading = false; rrDraw();
}

function rrFormOf(v) {
  const runs = {};
  for (const e of v.entries) runs[e.run_id] = {objective: '', setup: '', tyres_start: rrBlank4(), tyres_end: rrBlank4(), tyre_temp: '', observations: '', driver_feedback: '', fuel_l: '', fuel_note: '', ...(v.runs[e.run_id] || {})};
  for (const r of Object.values(runs)) { r.tyres_start = [...(r.tyres_start || []), '', '', '', ''].slice(0, 4); r.tyres_end = [...(r.tyres_end || []), '', '', '', ''].slice(0, 4); if (r.fuel_l == null) r.fuel_l = ''; }
  return {header: {...v.header}, general: v.general || '', runs, tyre_sets: (v.tyre_sets || []).map(t => ({set: t.set || '', model: t.model || '', laps: t.laps ?? '', km: t.km ?? ''})), pressure_base: v.pressure_base || '', actions_car: v.actions_car || '', actions_logistics: v.actions_logistics || ''};
}
const rrBody = f => ({header: f.header, general: f.general, pressure_base: f.pressure_base, actions_car: f.actions_car, actions_logistics: f.actions_logistics,
  runs: Object.fromEntries(Object.entries(f.runs).map(([k, r]) => [k, {...r, fuel_l: rdNum(r.fuel_l)}])),
  tyre_sets: f.tyre_sets.map(t => ({set: t.set, model: t.model, laps: t.laps === '' ? null : parseInt(t.laps), km: rdNum(t.km)}))});

const rrChip = s => s === 'validated' ? `<span class="rd-chip pos">${esc(tx('Validé'))}</span>` : s === 'draft' ? `<span class="rd-chip warn">${esc(tx('Brouillon'))}</span>` : `<span class="rd-chip">${esc(tx('À rédiger'))}</span>`;
const rrDates = m => `${fmtDate(m.from)}${m.to !== m.from ? ' → ' + fmtDate(m.to) : ''}`;

function rrListHtml() {
  if (rr.meetings == null) return `<p class="na loading">${esc(tx('Chargement…'))}</p>`;
  if (!rr.meetings.length) return `<p class="na">${esc(tx('Aucune épreuve : importez d’abord un « Roulage Al Kamel » (page Roulages).'))}</p>`;
  return rr.meetings.map(m => `<div class="rn-card"><div class="rn-head"><div><b>${esc(m.event)}</b> <span class="rd-chip">${esc(m.circuit || '')}</span><br><small class="na">${rrDates(m)}</small></div></div>
    ${table(['Voiture', 'Sessions', 'Km', 'Rapport', ''], m.cars.map(c => `<tr><td class="prod">${esc(c.name)}</td><td>${c.sessions}</td><td>${rdKm(c.km)}</td><td>${rrChip(c.status)}</td><td class="rd-acts"><button type="button" class="mini" data-rr="open" data-m="${esc(m.meeting)}" data-c="${esc(c.key)}">${esc(tx(c.status === 'none' ? 'Rédiger' : 'Ouvrir'))}</button></td></tr>`))}</div>`).join('');
}

const rrInp = (path, val, ph = '', dis = '', style = '') => `<input class="sdin" data-rr-f="${path}" value="${esc(val)}" placeholder="${esc(ph)}" ${dis} ${style ? `style="${style}"` : ''}>`;
const rrArea = (path, val, dis, rows = 3) => `<textarea class="sdin" data-rr-f="${path}" rows="${rows}" ${dis}>${esc(val)}</textarea>`;
const rrP4 = (path, arr, dis) => `<div class="rr-p4">${arr.map((x, i) => rrInp(`${path}.${i}`, x, ['AV G', 'AV D', 'AR G', 'AR D'][i], dis, 'max-width:80px')).join('')}</div>`;

function rrEntryHtml(e, v, f, dis) {
  const n = f.runs[e.run_id], tm = e.timing, sm = (tm && tm.summary) || {}, rk = sm.rank || {}, c = e.conditions || {};
  const lab = rrKinds[e.kind] ? tx(rrKinds[e.kind]) : e.session;
  const cond = [c.track_c != null ? `${tx('piste')} ${c.track_c}°C` : '', c.air_c != null ? `${tx('air')} ${c.air_c}°C` : '', c.status || ''].filter(Boolean).join(' · ');
  const ak = tm ? `<p class="na"><b>Al Kamel</b> · ${esc(tx('Tours'))} ${e.laps} · ${esc(tx('Meilleur tour'))} <b>${esc(tm.best || '–')}</b>${tm.pos ? ` · ${esc(tx('Classement'))} ${tm.pos}` : ''}${tm.grid ? ` · ${esc(tx('Départ'))} P${tm.grid}` : ''}${sm.top_speed ? ` · ${esc(tx('Vitesse de pointe'))} ${sm.top_speed} km/h${rk.top ? ` (${rk.top}/${sm.field})` : ''}` : ''}${rk.s1 ? ` · S1 ${rk.s1}/${sm.field} · S2 ${rk.s2}/${sm.field} · S3 ${rk.s3}/${sm.field}` : ''}</p>` : `<p class="na">${esc(tx('Session non chronométrée'))} · ${esc(tx('Tours'))} ${e.laps} · ${rdKm(e.km)} km</p>`;
  const p = `runs.${e.run_id}`;
  return `<div class="rn-card"><div class="rn-head"><div><b>RUN ${e.n} — ${esc(lab)}</b> <small class="na">${fmtDate(e.date)}${e.drivers.length ? ' · ' + esc(e.drivers.join(', ')) : ''}${cond ? ' · ' + esc(cond) : ''}</small></div></div>${ak}
    <div class="sdgrid"><label class="sdfield"><span>${esc(tx('Objectifs'))}</span>${rrInp(p + '.objective', n.objective, '', dis)}</label><label class="sdfield"><span>Setup</span>${rrInp(p + '.setup', n.setup, '', dis)}</label>
    <label class="sdfield"><span>${esc(tx('Carburant (L)'))}</span>${rrInp(p + '.fuel_l', n.fuel_l, '', dis, 'max-width:110px')}</label></div>
    <div class="sdgrid"><div class="sdfield"><span>${esc(tx('Pneus départ (bar)'))}</span>${rrP4(p + '.tyres_start', n.tyres_start, dis)}</div><label class="sdfield"><span>${esc(tx('Temp. pneus départ'))}</span>${rrInp(p + '.tyre_temp', n.tyre_temp, '17°C', dis, 'max-width:110px')}</label>
    <div class="sdfield"><span>${esc(tx('Pneus fin (bar)'))}</span>${rrP4(p + '.tyres_end', n.tyres_end, dis)}</div></div>
    <label class="sdfield"><span>${esc(tx('Observations (une par ligne)'))}</span>${rrArea(p + '.observations', n.observations, dis)}</label>
    <label class="sdfield"><span>${esc(tx('Retour pilote (une ligne par point)'))}</span>${rrArea(p + '.driver_feedback', n.driver_feedback, dis)}</label></div>`;
}

function rrEditorHtml() {
  const v = rr.view, f = rr.form; if (!v || !f) return '';
  const dis = v.status === 'validated' ? 'disabled' : '';
  const canVal = superUser || workshopRole === 'chef' || workshopRole === 'coordinator';
  const days = table(['Jour', 'Meilleur tour', 'Runs', 'Tours', 'Km', 'Carburant'], v.days.map(d => `<tr><td>${fmtDate(d.date)}</td><td>${esc(d.best || '–')}</td><td>${d.runs}</td><td>${d.laps}</td><td>${rdKm(d.km)}</td><td>${d.fuel == null ? '' : rdKm(d.fuel) + ' L'}</td></tr>`));
  const hdr = [['type_of_event', 'Type d’épreuve'], ['driver', 'Pilote (D1)'], ['codriver', 'Co-pilote (D2)'], ['car_chief', 'Chef mécanicien'], ['engineer', 'Ingénieur']];
  const sets = f.tyre_sets.map((t, i) => `<div class="sdgrid">${rrInp(`tyre_sets.${i}.set`, t.set, 'Set', dis, 'max-width:110px')}${rrInp(`tyre_sets.${i}.model`, t.model, tx('Modèle'), dis)}${rrInp(`tyre_sets.${i}.laps`, t.laps, tx('Tours'), dis, 'max-width:90px')}${rrInp(`tyre_sets.${i}.km`, t.km, 'Km', dis, 'max-width:100px')}${dis ? '' : `<button type="button" class="mini danger" data-rr="delset" data-i="${i}">✕</button>`}</div>`).join('');
  const url = l => `/api/rides/reports/${encodeURIComponent(v.meeting)}/${encodeURIComponent(v.car)}/print?lang=${l}`;
  return `<div class="note rd-form"><div class="sdbar"><button type="button" data-rr="back">← ${esc(tx('Épreuves'))}</button><b>${esc(v.event)} — ${esc(v.car_name)}${v.race_number ? ' #' + esc(v.race_number) : ''}</b> ${rrChip(v.status)}<small class="na">${rrDates(v)} · ${rdKm(v.km_total)} km${v.validated_by ? ' · ' + esc(tx('validé par')) + ' ' + esc(v.validated_by) : ''}</small></div>
    <div class="sdgrid">${hdr.map(([k, l]) => `<label class="sdfield"><span>${esc(tx(l))}</span>${rrInp('header.' + k, f.header[k] || '', '', dis)}</label>`).join('')}</div>
    <p><b>1. ${esc(tx('Synthèse générale'))}</b> <small class="na">${esc(tx('calculée d’après les roulages'))}</small></p>${days}
    <p><b>2. ${esc(tx('Observations générales'))}</b></p>${rrArea('general', f.general, dis, 4)}
    <p><b>3. ${esc(tx('Détail par run'))}</b></p>${v.entries.map(e => rrEntryHtml(e, v, f, dis)).join('')}
    <p><b>4. ${esc(tx('Pneumatiques'))}</b></p>${sets}${dis ? '' : `<div class="sdbar"><button type="button" class="mini" data-rr="addset">＋ ${esc(tx('Ajouter un train de pneus'))}</button></div>`}
    <label class="sdfield"><span>${esc(tx('Base de pression'))}</span>${rrArea('pressure_base', f.pressure_base, dis)}</label>
    <label class="sdfield"><span>5. ${esc(tx('Actions à améliorer pour le prochain meeting (voiture)'))}</span>${rrArea('actions_car', f.actions_car, dis)}</label>
    <label class="sdfield"><span>6. ${esc(tx('Actions pour le prochain meeting (logistique, interne : non visible du client)'))}</span>${rrArea('actions_logistics', f.actions_logistics, dis)}</label>
    <div class="sdbar">${dis ? '' : `<button type="button" class="primary" data-rr="save" ${rr.saving ? 'disabled' : ''}>${esc(tx(rr.saving ? 'Enregistrement…' : 'Enregistrer'))}</button>`}
    ${v.status === 'validated' ? (canVal ? `<button type="button" data-rr="reopen">${esc(tx('Rouvrir'))}</button>` : '') : (canVal ? `<button type="button" data-rr="validate">${esc(tx('Valider (visible du client)'))}</button>` : '')}
    <a class="mini" href="${url('fr')}" target="_blank" rel="noopener">🖨 ${esc(tx('Rapport FR'))}</a><a class="mini" href="${url('en')}" target="_blank" rel="noopener">🖨 ${esc(tx('Rapport EN'))}</a>
    ${rr.msg ? `<span class="${rr.ok ? 'na' : 'neg'}">${esc(rr.msg)}</span>` : ''}</div></div>`;
}

function rrDraw() {
  const el = document.getElementById('rr-view'); if (!el) return;
  const sav = [window.scrollX, window.scrollY];
  el.innerHTML = rr.view ? rrEditorHtml() : `${rr.msg && !rr.ok ? `<p class="neg">${esc(rr.msg)}</p>` : ''}${rrListHtml()}`;
  window.scrollTo(...sav);
}

function rrSet(path, value) {
  const parts = path.split('.'); let o = rr.form;
  for (let i = 0; i < parts.length - 1; i++) o = o[parts[i]];
  o[parts[parts.length - 1]] = value;
}

document.addEventListener('input', e => { const t = e.target; if (t.dataset && t.dataset.rrF !== undefined && rr.form) rrSet(t.dataset.rrF, t.value); });
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-rr]'); if (!b || !document.getElementById('rr-view')) return;
  const a = b.dataset.rr;
  try {
    if (a === 'open') { rr.msg = null; rr.view = await rsCall(`/api/rides/reports/${encodeURIComponent(b.dataset.m)}/${encodeURIComponent(b.dataset.c)}`); rr.form = rrFormOf(rr.view); return rrDraw(); }
    if (a === 'back') { rr.view = rr.form = null; rr.msg = null; rrDraw(); return rrLoad(); }
    if (a === 'addset') { rr.form.tyre_sets.push({set: '', model: '', laps: '', km: ''}); return rrDraw(); }
    if (a === 'delset') { rr.form.tyre_sets.splice(+b.dataset.i, 1); return rrDraw(); }
    const base = `/api/rides/reports/${encodeURIComponent(rr.view.meeting)}/${encodeURIComponent(rr.view.car)}`;
    if (a === 'save' || a === 'validate') {
      rr.saving = true; rr.msg = null; rrDraw();
      try {
        rr.view = await rsCall(base, {method: 'PUT', body: JSON.stringify(rrBody(rr.form))});
        if (a === 'validate') rr.view = await rsCall(base + '/validate', {method: 'POST', body: '{}'});
        rr.form = rrFormOf(rr.view); rr.msg = a === 'validate' ? 'Rapport validé : il est visible du client.' : 'Rapport enregistré.'; rr.ok = true;
      } catch (err) { rr.msg = err.message; rr.ok = false; }
      rr.saving = false; return rrDraw();
    }
    if (a === 'reopen') { rr.view = await rsCall(base + '/reopen', {method: 'POST', body: '{}'}); rr.form = rrFormOf(rr.view); rr.msg = null; return rrDraw(); }
  } catch (err) { rr.msg = err.message; rr.ok = false; rr.saving = false; rrDraw(); }
});
