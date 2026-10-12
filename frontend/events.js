// Planifier › Événements : création et suivi des événements dans les agendas Google des BU (Super User). S'appuie sur les ressources de resources.js. Chargé après resources.js.
const PE_BU_SYM = {XC: 'xc', MODERN_RALLY: 'mr', HISTORIC_RALLY: 'hrl', HISTORIC_RACING: 'hrc'};
const peBlank = () => ({id: null, title: '', bu: '', confirmed: false, start: '', end: '', immo_start: '', immo_end: '', immoTouched: false, place: null, origin: null, route: null, notes: '', staff: [], externals: [], vehicles: []});
let pe = {loaded: false, error: null, cfg: null, events: [], unavailable: null, form: peBlank(), orig: null, open: false, msg: null, msgOk: false, saving: false, q: {dest: '', origin: ''}, sugg: {dest: [], origin: []}, suggMsg: {dest: null, origin: null}, originEdit: false, busy: {}, busyMsg: null, vcat: 'all', showAll: false};
const peDay = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const peToday = () => new Date().toISOString().slice(0, 10);
let peTimer = null, peBusyTimer = null;

function eventsBlocks() { return [{static: '<section class="block" data-bid="pe"><div class="block-head"><h3>Événements</h3></div><div class="block-body" id="pe-view"><p class="na">Chargement…</p></div></section>'}]; }

async function peLoad() {
  try {
    const from = peDay(peToday(), -30), to = peDay(peToday(), 365);
    const [cfg, ev] = await Promise.all([rsCall('/api/events/config'), rsCall(`/api/events?from=${from}&to=${to}`), loadResources()]);
    pe.cfg = cfg; pe.events = ev.events || []; pe.unavailable = ev.unavailable || null; pe.loaded = true; pe.error = null;
  } catch (e) { pe.error = e.message; pe.loaded = true; }
}

// Champ date jj/mm/aaaa (le champ natif suit la langue du navigateur et ne peut pas être forcé) : saisie au clavier + calendrier natif ouvert par le bouton
const peParse = t => { const m = /^\s*(\d{1,2})[\/.\-](\d{1,2})[\/.\-](\d{4})\s*$/.exec(t || ''); if (!m) return null; const d = new Date(Date.UTC(+m[3], +m[2] - 1, +m[1])); return d.getUTCFullYear() === +m[3] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[1] ? d.toISOString().slice(0, 10) : null; };
const peDate = (f, iso, min = '', max = '') => `<span class="datef"><input class="sdin pe-d" data-f="${f}" value="${iso ? fmtDate(iso) : ''}" placeholder="jj/mm/aaaa" inputmode="numeric" maxlength="10" autocomplete="off"><button type="button" class="pe-cal" data-f="${f}" aria-label="Calendrier" title="Calendrier"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1.5v3M11 1.5v3"/></svg></button><input type="date" class="pe-dp" data-f="${f}" value="${iso || ''}" ${min ? `min="${min}"` : ''} ${max ? `max="${max}"` : ''} tabindex="-1" aria-hidden="true"></span>`;
const peIn = (f, v, type = 'text', extra = '') => `<input class="sdin pe-f" data-f="${f}" type="${type}" value="${esc(v || '')}" ${extra}>`;
const peBuLabel = id => ((pe.cfg && pe.cfg.bus.find(b => b.id === id)) || {}).label || id;
// Staff et prestataires proposés : ceux de la BU choisie (imputation du personnel ; BU cochées sur la fiche du prestataire), plus ceux déjà sélectionnés ; « Afficher tout » lève le filtre
const peStaffIn = p => !!pe.form.bu && ((p.alloc || {})[pe.form.bu] || 0) > 0;
const peExtIn = x => !!pe.form.bu && (x.bus || []).includes(pe.form.bu);
const peStaffShown = () => peStaffList().filter(p => pe.showAll || peStaffIn(p) || pe.form.staff.includes(p.email));
const peExtShown = () => rs.externals.filter(x => pe.showAll || peExtIn(x) || pe.form.externals.includes(x.email)).sort(peCmp);
const peCmp = (a, b) => a.name.localeCompare(b.name, 'fr', {sensitivity: 'base'});
const peStaffList = () => rs.staff.filter(p => p.active).sort(peCmp);
const peVehicles = () => ((rs.vehicles || {}).items || []).filter(v => v.email);

function peDraw() {
  const el = document.getElementById('pe-view'); if (!el) return;
  if (!pe.loaded) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (pe.error) { el.innerHTML = `<p class="neg">${esc(pe.error)}</p>`; return; }
  const c = pe.cfg, f = pe.form;
  const warn = [];
  if (!c.delegation) warn.push('La délégation Google n’est pas activée : les événements ne peuvent pas être créés (voir Ressources).');
  if (!c.maps) warn.push('La recherche de lieux n’est pas configurée (clé GOOGLE_MAPS_API_KEY) : un événement ne peut pas être créé sans lieu.');
  const missing = c.bus.filter(b => !b.calendar).map(b => b.label);
  if (missing.length) warn.push('Aucun agenda configuré pour : ' + missing.join(', ') + '.');
  let h = warn.map(w => `<p class="neg">${esc(w)}</p>`).join('');
  h += pe.open ? peFormHtml() : `<div class="sdbar"><button type="button" class="primary" id="pe-new">+ Nouvel événement</button>${pe.msg ? `<span class="${pe.msgOk ? 'na' : 'neg'}">${esc(pe.msg)}</span>` : ''}</div>`;
  h += peListHtml();
  const act = document.activeElement, keepId = act && act.classList && act.classList.contains('pe-q') ? act.id : null, keep = keepId ? act.selectionStart : null;
  el.innerHTML = h;
  if (keep != null) { const q = document.getElementById(keepId); if (q) { q.focus(); q.setSelectionRange(keep, keep); } }
}

function peFormHtml() {
  const f = pe.form, c = pe.cfg, ok = peValid();
  const bus = c.bus.map(b => `<button type="button" class="rs-pill pe-bu" data-bu="${b.id}" aria-pressed="${f.bu === b.id}" ${b.calendar ? '' : 'disabled title="Aucun agenda configuré"'}>${BuSymbol(PE_BU_SYM[b.id], {size: 15})}<span>${esc(b.label)}</span></button>`).join('');
  const routeInfo = r => r ? (r.km != null ? `<br><small>${r.km} km depuis ${esc(r.origin_label || 'Lifelive')} (${Math.floor(r.minutes / 60)} h ${String(r.minutes % 60).padStart(2, '0')}) à l’aller · ${r.km * 2} km aller-retour</small>` : `<br><small class="neg">${esc(r.unavailable || 'Itinéraire non calculé')}</small>`) : '<br><small class="na">Calcul de l’itinéraire…</small>';
  const picker = (role, placeholder) => `<input class="sdin pe-q" data-role="${role}" id="pe-q-${role}" value="${esc(pe.q[role])}" placeholder="${placeholder}" autocomplete="off" style="min-width:320px">${pe.suggMsg[role] ? `<small class="${pe.sugg[role].length ? 'na' : 'neg'}">${esc(pe.suggMsg[role])}</small>` : ''}${pe.sugg[role].map(x => `<div class="sdres"><span>${esc(x.text)}</span> <button type="button" class="pe-pick" data-role="${role}" data-id="${esc(x.id)}">Choisir</button></div>`).join('')}`;
  const place = f.place
    ? `<div class="note"><b>${esc(f.place.name || f.place.address)}</b><br><small class="na">${esc(f.place.address)}</small>${routeInfo(f.route)}${(f.route && f.route.alerts || []).map(a => `<br><b class="neg">⚠ ${esc(a)}</b>`).join('')} <button type="button" class="mini" id="pe-unplace">Changer</button></div>`
    : picker('dest', 'Rechercher le lieu (circuit, ville, adresse…)');
  const origin = pe.originEdit
    ? picker('origin', 'Rechercher le lieu de départ') + ' <button type="button" class="mini" id="pe-origin-reset">Revenir à Lifelive</button>'
    : `<div class="note"><b>${f.origin ? esc(f.origin.name || f.origin.address) : 'Lifelive'}</b><br><small class="na">${esc(f.origin ? f.origin.address : c.origin)}</small> <button type="button" class="mini" id="pe-origin-edit">Changer</button>${f.origin ? ' <button type="button" class="mini" id="pe-origin-reset">Revenir à Lifelive</button>' : ''}</div>`;
  const staffHidden = peStaffList().length - peStaffShown().length, extHidden = rs.externals.length - peExtShown().length;
  const staff = peStaffShown().map(p => `<label class="chk"><input type="checkbox" class="pe-staff" data-e="${esc(p.email)}" ${f.staff.includes(p.email) ? 'checked' : ''} ${p.email ? '' : 'disabled'}> ${esc(p.name)}${p.email ? '' : ' <small class="neg">pas de compte Google</small>'}${peStaffIn(p) ? '' : ' <small class="na">autre BU</small>'}</label>`).join('');
  const exts = peExtShown().map(x => `<label class="chk"><input type="checkbox" class="pe-ext" data-e="${esc(x.email)}" ${f.externals.includes(x.email) ? 'checked' : ''} ${x.email ? '' : 'disabled'}> ${esc(x.name)}${x.company ? ` <small class="na">${esc(x.company)}</small>` : ''}${x.email ? '' : ' <small class="neg">pas d’e-mail</small>'}${peExtIn(x) ? '' : (x.bus || []).length ? ' <small class="na">autre BU</small>' : ' <small class="neg">BU non définie</small>'}</label>`).join('');
  const veh = peVehicles(), cats = ((rs.vehicles || {}).categories || []).filter(k => veh.some(v => v.category === k.id));
  const vcat = (id, label) => `<button type="button" class="rs-pill pe-vcat" data-c="${id}" aria-pressed="${pe.vcat === id}"><span>${esc(label)}</span></button>`;
  const vlist = veh.filter(v => pe.vcat === 'all' || v.category === pe.vcat).map(v => { const b = peBusyOf(v.email);
    return `<label class="chk"><input type="checkbox" class="pe-veh" data-e="${esc(v.email)}" ${f.vehicles.includes(v.email) ? 'checked' : ''}> ${esc(v.name)}${b ? ` <small class="neg">⚠ déjà réservé du ${fmtDate(b[0])} au ${fmtDate(b[1])}</small>` : ''}</label>`; }).join('');
  return `<div class="note pe-form"><b>${f.id ? 'Modifier l’événement' : 'Nouvel événement'}</b>
    <div class="sdgrid"><label class="sdfield" style="grid-column:1/-1"><span>Titre</span>${peIn('title', f.title, 'text', 'maxlength="120"')}</label></div>
    <div class="sdfield"><span>BU</span><div class="bu-filter">${bus}</div></div>
    <label class="chk" style="margin:8px 0"><input type="checkbox" id="pe-conf" ${f.confirmed ? 'checked' : ''}> Confirmé <small class="na">${f.confirmed ? '' : '(sinon « [TBC] » est ajouté au début du titre ; les prestataires sont invités à la confirmation)'}</small></label>
    <div class="sdgrid"><label class="sdfield"><span>Début de l’événement</span>${peDate('start', f.start)}</label><label class="sdfield"><span>Fin de l’événement</span>${peDate('end', f.end, f.start)}</label>
    <label class="sdfield"><span>Début d’immobilisation des véhicules</span>${peDate('immo_start', f.immo_start, '', f.start)}</label><label class="sdfield"><span>Fin d’immobilisation des véhicules</span>${peDate('immo_end', f.immo_end, f.end)}</label></div>
    <small class="na">Par défaut, l’immobilisation reprend les dates de l’événement élargies de ${c.travel_days} jour${c.travel_days > 1 ? 's' : ''} de trajet de chaque côté. Elle ne change que la réservation des véhicules.</small>
    <div class="sdfield" style="margin-top:10px"><span>Lieu de départ</span>${origin}</div>
    <div class="sdfield" style="margin-top:10px"><span>Lieu de l’événement</span>${place}</div>
    <label class="sdfield" style="margin-top:10px"><span>Notes</span><textarea class="sdin pe-f" data-f="notes" rows="3" maxlength="2000">${esc(f.notes)}</textarea></label>
    <label class="chk" style="margin-top:12px"><input type="checkbox" id="pe-all" ${pe.showAll ? 'checked' : ''}> Afficher aussi le staff et les prestataires des autres BU${!pe.showAll && staffHidden + extHidden ? ` <small class="na">(${staffHidden + extHidden} masqué${staffHidden + extHidden > 1 ? 's' : ''})</small>` : ''}</label>
    <h4 class="sub">Staff interne</h4><div class="chkgrid">${staff || `<small class="na">${f.bu ? 'Aucun staff actif imputé à cette BU.' : 'Choisissez d’abord une BU.'}</small>`}</div>
    <h4 class="sub">Staff externe</h4><div class="chkgrid">${exts || `<small class="na">${f.bu ? 'Aucun prestataire rattaché à cette BU : cochez ses BU dans Ressources.' : 'Choisissez d’abord une BU.'}</small>`}</div>
    <h4 class="sub">Véhicules</h4>${cats.length ? `<div class="bu-filter">${vcat('all', 'Tous')}${cats.map(k => vcat(k.id, k.label)).join('')}</div>` : ''}<div class="chkgrid">${vlist || '<small class="na">Aucun véhicule.</small>'}</div>${pe.busyMsg ? `<small class="neg">${esc(pe.busyMsg)}</small>` : ''}
    <div class="sdbar" style="margin-top:12px"><button type="button" class="primary" id="pe-save" ${ok && !pe.saving ? '' : 'disabled'}>${pe.saving ? 'Enregistrement…' : f.id ? 'Enregistrer' : 'Créer l’événement'}</button><button type="button" id="pe-cancel">Annuler</button>${pe.msg ? `<span class="${pe.msgOk ? 'na' : 'neg'}">${esc(pe.msg)}</span>` : ''}</div>
    ${ok ? '' : `<small class="na">À compléter : ${peMissing().join(', ')}.</small>`}</div>`;
}

const peMissing = () => { const f = pe.form, m = []; if (!f.title.trim()) m.push('titre'); if (!f.bu) m.push('BU'); if (!f.start || !f.end) m.push('dates'); if (!f.place) m.push('lieu'); return m; };
const peValid = () => !peMissing().length && pe.form.end >= pe.form.start && pe.form.immo_start && pe.form.immo_end;

// Réservation existante d'un véhicule sur la période d'immobilisation (ignorée quand elle vient de cet événement lui-même : dates inchangées)
function peBusyOf(email) {
  const b = (pe.busy[email] || [])[0]; if (!b) return null;
  const f = pe.form, o = pe.orig;
  if (o && o.vehicles.includes(email) && o.immo_start === f.immo_start && o.immo_end === f.immo_end) return null;
  return [b.start.slice(0, 10), peDay(b.end.slice(0, 10), -1)];
}
function peCheckBusy() {
  clearTimeout(peBusyTimer);
  peBusyTimer = setTimeout(async () => {
    const f = pe.form, emails = peVehicles().map(v => v.email); if (!f.immo_start || !f.immo_end || !emails.length || f.immo_end < f.immo_start) { pe.busy = {}; peDraw(); return; }
    try { const j = await rsCall('/api/events/busy', {method: 'POST', body: JSON.stringify({emails, start: f.immo_start, end: f.immo_end})}); pe.busy = j.busy || {}; pe.busyMsg = j.unavailable || null; } catch (e) { pe.busy = {}; pe.busyMsg = e.message; }
    peDraw();
  }, 400);
}

function peListHtml() {
  const rows = pe.events.map(e => {
    const names = e.staff_and_external.map(m => (rs.staff.find(p => p.email === m) || rs.externals.find(x => x.email === m) || {}).name || m);
    const vnames = e.vehicles.map(m => (peVehicles().find(v => v.email === m) || {}).name || m);
    const sym = PE_BU_SYM[e.bu] ? BuSymbol(PE_BU_SYM[e.bu], {size: 14}) : '';
    return `<tr><td>${fmtDate(e.start)}${e.end !== e.start ? ' → ' + fmtDate(e.end) : ''}</td><td class="prod">${sym} ${e.confirmed ? '' : '<span class="badge-profile">TBC</span> '}<b>${esc(e.title)}</b><br><small class="na">${esc(peBuLabel(e.bu))} · ${esc(e.place.address)}</small>${(e.via || []).map(v => `<br><small class="neg">⚠ ${esc(v === 'CH' ? 'Itinéraire par la Suisse' : 'Itinéraire par le Royaume-Uni')}</small>`).join('')}</td>`
      + `<td>${e.km != null ? e.km + ' km' : '–'}</td><td><small>${esc(names.join(', ') || '–')}${e.externals_pending.length ? `<br><span class="na">${e.externals_pending.length} prestataire${e.externals_pending.length > 1 ? 's' : ''} à inviter à la confirmation</span>` : ''}</small></td><td><small>${esc(vnames.join(', ') || '–')}${vnames.length ? `<br><span class="na">${fmtDate(e.immo_start)} → ${fmtDate(e.immo_end)}</span>` : ''}</small></td>`
      + `<td><button type="button" class="pe-edit" data-id="${e.id}">Modifier</button> <button type="button" class="pe-del" data-id="${e.id}">Supprimer</button></td></tr>`; });
  return '<h4 class="sub">Événements à venir (depuis 30 jours)</h4>' + (pe.unavailable ? `<p class="neg">${esc(pe.unavailable)}</p>` : '')
    + (rows.length ? table(['Dates', 'Événement', 'Distance', 'Personnes invitées', 'Véhicules', ''], rows, 'prodtable') : '<p class="na">Aucun événement créé depuis Logbook.</p>');
}

function peOpenNew() { pe.form = peBlank(); pe.orig = null; pe.open = true; pe.msg = null; pe.q = {dest: '', origin: ''}; pe.sugg = {dest: [], origin: []}; pe.suggMsg = {dest: null, origin: null}; pe.originEdit = false; pe.busy = {}; peDraw(); }
function peOpenEdit(id) {
  const e = pe.events.find(x => x.id === id); if (!e) return;
  const sEmails = new Set(rs.staff.map(p => p.email).filter(Boolean)), att = e.staff_and_external;
  pe.form = {id: e.id, title: e.title, bu: e.bu, confirmed: e.confirmed, start: e.start, end: e.end, immo_start: e.immo_start, immo_end: e.immo_end, immoTouched: true,
    place: e.place.id ? {id: e.place.id, name: '', address: e.place.address, lat: null, lng: null, country: ''} : null, origin: e.origin ? {id: e.origin.id, name: '', address: e.origin.address, lat: null, lng: null, country: ''} : null, route: e.km != null ? {km: e.km, minutes: 0, alerts: (e.via || []).map(v => `L’itinéraire depuis le départ passe par ${v === 'CH' ? 'la Suisse' : 'le Royaume-Uni'}.`)} : null,
    notes: e.notes, staff: att.filter(m => sEmails.has(m)), externals: att.filter(m => !sEmails.has(m)).concat(e.externals_pending), vehicles: e.vehicles.slice()};
  pe.orig = {immo_start: e.immo_start, immo_end: e.immo_end, vehicles: e.vehicles.slice()};
  pe.open = true; pe.msg = null; pe.originEdit = false; pe.busy = {}; peDraw(); peCheckBusy();
  if (e.place.id) peChoose(e.place.id, 'dest');
}
function peWiden() { const f = pe.form; if (f.immoTouched) return; const n = pe.cfg.travel_days; f.immo_start = f.start ? peDay(f.start, -n) : ''; f.immo_end = f.end ? peDay(f.end, n) : ''; }

// Lieu choisi dans la recherche : `role` = 'dest' (lieu de l'événement, avec itinéraire) ou 'origin' (lieu de départ, l'itinéraire est recalculé)
const peOriginQuery = () => pe.form.origin ? '?origin=' + encodeURIComponent(pe.form.origin.id) : '';
async function peChoose(id, role = 'dest') {
  const f = pe.form; pe.suggMsg[role] = null; pe.sugg[role] = [];
  try {
    if (role === 'origin') {
      const j = await rsCall('/api/places/' + encodeURIComponent(id) + '?route=false');
      f.origin = j.place; pe.originEdit = false; pe.q.origin = ''; f.route = null; peDraw(); await peRoute(); return;
    }
    const j = await rsCall('/api/places/' + encodeURIComponent(id) + peOriginQuery());
    f.place = j.place; f.route = j.route; pe.q.dest = '';
  } catch (e) { pe.suggMsg[role] = e.message; }
  peDraw();
}
async function peRoute() {
  const f = pe.form; if (!f.place) { peDraw(); return; }
  try { const j = await rsCall('/api/places/' + encodeURIComponent(f.place.id) + peOriginQuery()); f.route = j.route; } catch (e) { f.route = {km: null, unavailable: e.message}; }
  peDraw();
}

document.addEventListener('input', e => {
  const t = e.target; if (!t.classList || !document.getElementById('pe-view')) return;
  if (t.classList.contains('pe-q')) {
    const role = t.dataset.role; pe.q[role] = t.value; clearTimeout(peTimer);
    if (pe.q[role].trim().length < 3) { pe.sugg[role] = []; pe.suggMsg[role] = null; peDraw(); return; }
    peTimer = setTimeout(async () => {
      try { const j = await rsCall('/api/places/autocomplete?q=' + encodeURIComponent(pe.q[role].trim())); pe.sugg[role] = j.suggestions || []; pe.suggMsg[role] = pe.sugg[role].length ? null : 'Aucun lieu trouvé.'; } catch (err) { pe.sugg[role] = []; pe.suggMsg[role] = err.message; }
      peDraw();
    }, 350);
  } else if (t.classList.contains('pe-f') && t.dataset.f === 'notes') pe.form.notes = t.value;
  else if (t.classList.contains('pe-f') && t.dataset.f === 'title') { pe.form.title = t.value; const b = document.getElementById('pe-save'); if (b) b.disabled = !peValid() || pe.saving; }
});

document.addEventListener('change', e => {
  const t = e.target; if (!t.classList || !document.getElementById('pe-view')) return;
  const f = pe.form;
  if (t.classList.contains('pe-d') || t.classList.contains('pe-dp')) {
    const k = t.dataset.f, iso = t.classList.contains('pe-dp') ? t.value : peParse(t.value);
    if (!iso) { pe.msg = 'Date invalide : saisissez jj/mm/aaaa.'; pe.msgOk = false; peDraw(); return; }
    pe.msg = null; f[k] = iso;
    if (k === 'start' && (!f.end || f.end < f.start)) f.end = f.start;
    if (k === 'end' && f.end < f.start) f.start = f.end;
    if (k === 'immo_start' || k === 'immo_end') f.immoTouched = true;
    peWiden(); if (f.immo_start > f.start) f.immo_start = f.start; if (f.immo_end < f.end) f.immo_end = f.end;
    peDraw(); peCheckBusy();
  } else if (t.id === 'pe-conf') { f.confirmed = t.checked; peDraw(); }
  else if (t.id === 'pe-all') { pe.showAll = t.checked; peDraw(); }
  else if (t.classList.contains('pe-staff') || t.classList.contains('pe-ext') || t.classList.contains('pe-veh')) {
    const k = t.classList.contains('pe-staff') ? 'staff' : t.classList.contains('pe-ext') ? 'externals' : 'vehicles', m = t.dataset.e;
    f[k] = t.checked ? f[k].concat(f[k].includes(m) ? [] : [m]) : f[k].filter(x => x !== m);
  }
});

document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('button'); if (!t || !document.getElementById('pe-view')) return;
  const f = pe.form;
  if (t.id === 'pe-new') peOpenNew();
  else if (t.classList.contains('pe-cal')) { const dp = document.querySelector(`.pe-dp[data-f="${t.dataset.f}"]`); if (dp) { try { dp.showPicker(); } catch { dp.focus(); dp.click(); } } }
  else if (t.id === 'pe-cancel') { pe.open = false; pe.msg = null; peDraw(); }
  else if (t.classList.contains('pe-bu')) { f.bu = t.dataset.bu; peDraw(); }
  else if (t.classList.contains('pe-vcat')) { pe.vcat = t.dataset.c; peDraw(); }
  else if (t.classList.contains('pe-pick')) peChoose(t.dataset.id, t.dataset.role);
  else if (t.id === 'pe-origin-edit') { pe.originEdit = true; peDraw(); }
  else if (t.id === 'pe-origin-reset') { f.origin = null; pe.originEdit = false; f.route = null; peDraw(); peRoute(); }
  else if (t.id === 'pe-unplace') { f.place = null; f.route = null; peDraw(); }
  else if (t.classList.contains('pe-edit')) peOpenEdit(t.dataset.id);
  else if (t.classList.contains('pe-del')) {
    const ev = pe.events.find(x => x.id === t.dataset.id); if (!ev || !confirm('Supprimer « ' + ev.title + ' » de Google Agenda ? Les invités seront prévenus.')) return;
    try { await rsCall('/api/events/' + encodeURIComponent(ev.id), {method: 'DELETE'}); pe.msg = 'Événement supprimé.'; pe.msgOk = true; await peLoad(); } catch (err) { pe.msg = err.message; pe.msgOk = false; }
    peDraw();
  } else if (t.id === 'pe-save') {
    pe.saving = true; pe.msg = null; peDraw();
    const body = {title: f.title.trim(), bu: f.bu, confirmed: f.confirmed, start: f.start, end: f.end, immo_start: f.immo_start, immo_end: f.immo_end, notes: f.notes,
      place: {id: f.place.id, name: f.place.name || '', address: f.place.address || '', lat: f.place.lat, lng: f.place.lng, country: f.place.country || ''},
      origin: f.origin ? {id: f.origin.id, name: f.origin.name || '', address: f.origin.address || '', lat: f.origin.lat, lng: f.origin.lng, country: f.origin.country || ''} : null, staff: f.staff, externals: f.externals, vehicles: f.vehicles};
    try {
      await rsCall(f.id ? '/api/events/' + encodeURIComponent(f.id) : '/api/events', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify(body)});
      pe.open = false; pe.msg = f.id ? 'Événement mis à jour dans Google Agenda.' : 'Événement créé dans Google Agenda.'; pe.msgOk = true; await peLoad();
    } catch (err) { pe.msg = 'Échec : ' + err.message; pe.msgOk = false; }
    pe.saving = false; peDraw();
  }
});
