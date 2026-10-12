// Consigner › Pointages : « Mes pointages » (chaque mécanicien : saisie en durée sur un job, photos, mémo vocal, récapitulatif de la semaine) et « Équipe »
// (chef d'atelier : heures de chaque mécanicien, taux d'occupation et taux facturable, validation, jobs et propositions d'après le planning).
// Données : /api/timesheets (backend/app/timesheets.py). S'appuie sur les outils de dates de planning.js et sur rsCall (resources.js).
let ts = {me: null, jobs: [], start: '', week: null, team: null, form: null, pend: {photos: [], audio: null}, rec: null, open: new Set(), err: null, msg: null, loading: false, jobsAll: [], sugg: null, veh: null, evs: null, jobForm: null, busy: false};
const TS_BU = {CARS: 'CARS (toutes)', MODERN_RALLY: 'CARS · Modern Rally', HISTORIC_RALLY: 'CARS · Historic Rally', HISTORIC_RACING: 'CARS · Historic Racing', XC: 'XC', ALL: 'Toutes'};
const tsBuOpts = me => ['XC', 'CARS', 'MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING'].filter(b => me.super || me.bus.includes(b === 'XC' ? 'XC' : 'CARS')).concat(['ALL']);
const TS_KIND = {atelier: 'Job atelier', event: 'Job événement', background: 'Tâche de fond'};
const tsUrls = new WeakMap();
const tsUrl = blob => { if (!tsUrls.has(blob)) tsUrls.set(blob, URL.createObjectURL(blob)); return tsUrls.get(blob); };
const tsDur = m => { const h = Math.floor(m / 60), r = m % 60; return h ? (r ? `${h} h ${String(r).padStart(2, '0')}` : `${h} h`) : `${r} min`; };
const tsPct = x => x == null ? '–' : Math.round(x * 100) + ' %';
const tsStamp = iso => new Date(iso).toLocaleString(LOCALE(), {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
const tsPage = () => location.hash.includes('consigner/team') ? 'team' : 'mine';

function tsBlocks(page) {
  return [{static: `<section class="block" data-bid="ts"><div class="block-head"><h3>${page === 'team' ? 'Équipe' : 'Mes pointages'}</h3></div><div class="block-body" id="ts-view"><p class="na">Chargement…</p></div></section>`}];
}

async function tsLoad(page) {
  if (!ts.start) ts.start = plMonday(plToday());
  ts.loading = true; ts.err = null; tsDraw();
  try {
    if (!ts.me) ts.me = await rsCall('/api/timesheets/me');
    if (ts.me.role) {
      ts.jobs = (await rsCall('/api/timesheets/jobs')).jobs;
      if (page === 'team') {
        if (ts.me.role === 'chef') { ts.team = await rsCall(`/api/timesheets/team?start=${ts.start}&bu=${buSel}`); ts.jobsAll = (await rsCall('/api/timesheets/jobs?all=true')).jobs; }
      } else ts.week = await rsCall(`/api/timesheets/week?start=${ts.start}`);
    }
  } catch (e) { ts.err = e.message; }
  ts.loading = false; tsDraw();
}

// ---- Dessin -------------------------------------------------------------------------------------------------------------------------------------------------------
const tsNav = () => `<div class="ts-nav"><button type="button" data-ts="prev" aria-label="Semaine précédente">‹</button><b>${esc(`Semaine ${plWeekNo(ts.start)} · ${plFmt(ts.start, {day: 'numeric', month: 'short'})} – ${plFmt(plAdd(ts.start, 6), {day: 'numeric', month: 'short', year: 'numeric'})}`)}</b><button type="button" data-ts="next" aria-label="Semaine suivante">›</button><button type="button" data-ts="today">Aujourd’hui</button></div>`;
const tsKpis = s => `<div class="ts-kpis"><div><small>Heures pointées</small><b>${tsDur(s.total)}</b></div><div><small>Facturables</small><b>${tsDur(s.billable)}</b></div><div><small>Taux d’occupation</small><b>${tsPct(s.occupancy)}</b></div><div><small>Taux facturable</small><b>${tsPct(s.billable_rate)}</b></div><div><small>Horaire théorique</small><b>${s.theoretical ? tsDur(s.theoretical) : '–'}</b></div></div>`;

function tsEntryHtml(e, mine) {
  const a = (ts.me.assignments.find(x => x.id === (e.job.assignment || e.assignment)) || {}).label, sy = (ts.me.systems.find(x => x.id === e.system) || {}).label;
  const att = (e.attachments || []).map(x => { const u = `/api/timesheets/entries/${e.id}/attachments/${x.id}`; return x.kind === 'photo' ? `<a href="${u}" target="_blank" rel="noopener"><img class="ts-ph" src="${u}" loading="lazy" alt="Photo"></a>` : `<audio controls preload="none" src="${u}"></audio>`; }).join('');
  const lock = e.validated ? '<span class="ts-lock ok">✓ Validé</span>' : e.can_edit && !(ts.me.role === 'chef') ? `<span class="ts-lock">Modifiable jusqu’à</span> <span class="ts-lock">${esc(tsStamp(e.editable_until))}</span>` : e.can_edit ? '' : '<span class="ts-lock bad">🔒 Verrouillé</span>';
  const acts = e.can_edit ? `<button type="button" data-ts="edit" data-id="${e.id}">Modifier</button><button type="button" class="danger" data-ts="del" data-id="${e.id}">Supprimer</button>` : '';
  const val = ts.me.role === 'chef' && !mine ? `<button type="button" data-ts="val" data-id="${e.id}" data-v="${e.validated ? 0 : 1}">${e.validated ? 'Annuler la validation' : 'Valider'}</button>` : '';
  return `<div class="ts-entry"><div class="ts-top"><b>${esc(e.job.title)}</b>${e.job.billable ? '<span class="ts-tag">Facturable</span>' : ''}<span class="ts-min">${tsDur(e.minutes)}</span></div>
    <div class="ts-sub">${[a && (e.job.assignment || e.assignment) !== 'autre' ? a : '', sy && e.system !== 'autre' ? sy : ''].filter(Boolean).map(esc).join(' · ')}${e.text ? ' — ' + esc(e.text) : ''}</div>${att ? `<div class="ts-att">${att}</div>` : ''}<div class="ts-act">${lock}${acts}${val}</div></div>`;
}

function tsJobSelect(sel) {
  const groups = [['atelier', 'Jobs atelier'], ['event', 'Jobs événement'], ['background', 'Tâches de fond']];
  return `<select class="sdin" data-f="job_id"><option value="">— Choisir un job —</option>${groups.map(([k, l]) => { const js = ts.jobs.filter(j => j.kind === k); return js.length ? `<optgroup label="${esc(l)}">${js.map(j => `<option value="${j.id}"${j.id === sel ? ' selected' : ''}>${esc(j.title)}</option>`).join('')}</optgroup>` : ''; }).join('')}</select>`;
}
function tsFormHtml() {
  const f = ts.form; if (!f) return '';
  const chips = [30, 60, 120, 240, 480].map(m => `<button type="button" class="ts-chip${f.minutes === m ? ' sel' : ''}" data-ts="dur" data-m="${m}">${tsDur(m)}</button>`).join('');
  const x = (k, i) => `<button type="button" class="ts-x" data-ts="rm" data-k="${k}" data-i="${i}" aria-label="Retirer" title="Retirer">✕</button>`;
  const photos = ts.pend.photos.map((p, i) => `<span class="ts-pp"><img class="ts-ph" src="${tsUrl(p)}" alt="Photo">${x('photo', i)}</span>`).join('');
  const audio = ts.pend.audio ? `<span class="ts-pp"><audio controls src="${tsUrl(ts.pend.audio)}"></audio>${x('audio', 0)}</span>${{busy: '<span class="ts-n">Transcription en cours…</span>', ok: '<span class="ts-n">✓ Transcrit : relisez et corrigez le texte ci-dessus</span>', empty: '<span class="ts-n">Aucune parole reconnue</span>'}[ts.pend.tr] || ''}` : '';
  const saved = (f.atts || []).map(at => { const u = `/api/timesheets/entries/${f.id}/attachments/${at.id}`; return `<span class="ts-pp">${at.kind === 'photo' ? `<img class="ts-ph" src="${u}" alt="Photo">` : `<audio controls preload="none" src="${u}"></audio>`}<button type="button" class="ts-x" data-ts="rmsaved" data-id="${at.id}" aria-label="Supprimer" title="Supprimer">✕</button></span>`; }).join('');
  return `<div class="ts-form"><h4>${f.id ? 'Modifier le pointage' : 'Nouveau pointage'}</h4>
    <label class="sdfield"><span>Job</span>${tsJobSelect(f.job_id)}</label>
    <div class="sdgrid"><label class="sdfield"><span>Date</span><span class="datef"><input class="sdin ts-d" value="${fmtDate(f.date)}" placeholder="jj/mm/aaaa" inputmode="numeric" maxlength="10" autocomplete="off"><button type="button" class="ts-cal" aria-label="Calendrier" title="Calendrier"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1.5v3M11 1.5v3"/></svg></button><input type="date" class="ts-dp" value="${f.date}" max="${plToday()}" tabindex="-1" aria-hidden="true"></span></label>
    <div class="sdfield"><span>Rapide</span><div class="ts-chips"><button type="button" class="ts-chip" data-ts="day" data-d="0">Aujourd’hui</button><button type="button" class="ts-chip" data-ts="day" data-d="-1">Hier</button></div></div></div>
    <div class="sdfield"><span>Durée</span><div class="ts-dur"><button type="button" data-ts="step" data-n="-15" aria-label="Moins 15 minutes">−</button><b id="ts-dur">${tsDur(f.minutes)}</b><button type="button" data-ts="step" data-n="15" aria-label="Plus 15 minutes">+</button></div><div class="ts-chips">${chips}</div></div>
    ${(ts.jobs.find(j => j.id === f.job_id) || {}).kind === 'atelier' ? `<label class="sdfield"><span>Système</span><select class="sdin" data-f="system">${ts.me.systems.map(s => `<option value="${s.id}"${f.system === s.id ? ' selected' : ''}>${esc(s.label)}</option>`).join('')}</select></label>` : ''}
    <label class="sdfield"><span>Intervention</span><textarea class="sdin" data-f="text" rows="3" maxlength="3000" placeholder="Ce qui a été fait…">${esc(f.text)}</textarea></label>
    ${ts.me.attachments ? `<div class="ts-media"><label class="btn">📷 Photo<input type="file" accept="image/*" capture="environment" multiple hidden data-ts-file></label>
      <button type="button" data-ts="rec" class="${ts.rec ? 'rec' : ''}">${ts.rec ? '⏹ Arrêter' : '🎙 Mémo vocal'}</button></div><div class="ts-att">${saved}${photos}${audio}</div>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-ts="save"${ts.busy ? ' disabled' : ''}>Enregistrer</button><button type="button" data-ts="cancel">Annuler</button></div></div>`;
}

function tsMineHtml() {
  const w = ts.week; if (!w) return '';
  const days = Array.from({length: 7}, (_, i) => plAdd(ts.start, i)), t = plToday();
  const byDay = Object.fromEntries(days.map(d => [d, w.entries.filter(e => e.date === d)]));
  return `${tsNav()}${tsKpis(w.summary)}${ts.form ? tsFormHtml() : '<div class="sdbar"><button type="button" class="primary" data-ts="new">+ Nouveau pointage</button></div>'}
    ${days.map(d => { const es = byDay[d], tot = w.summary.by_day[d] || 0;
      return `<div class="ts-day${d === t ? ' today' : ''}"><div class="ts-dh"><b>${esc(plFmt(d, {weekday: 'long', day: 'numeric', month: 'short'}))}</b><span>${tot ? tsDur(tot) : ''}</span></div>${es.map(e => tsEntryHtml(e, true)).join('') || ''}</div>`; }).join('')}`;
}

function tsTeamHtml() {
  const tm = ts.team; if (!tm) return '';
  const days = Array.from({length: 7}, (_, i) => plAdd(ts.start, i));
  const head = `<tr><th>Personne</th>${days.map(d => `<th class="num">${esc(plFmt(d, {weekday: 'short'}))} ${+d.slice(8)}</th>`).join('')}<th class="num">Total</th><th class="num">Occupation</th><th class="num">Facturable</th><th class="num">À valider</th></tr>`;
  const inBu = r => buSel === 'all' || r.all_bus || (BU_KEYS[buSel] || []).some(k => ((r.alloc || {})[k] || 0) > 0);
  const rows = tm.rows.filter(r => inBu(r) || r.summary.count > 0).map(r => { const s = r.summary, op = ts.open.has(r.user), todo = s.count - s.validated;
    return `<tr class="ts-row" data-ts="open" data-u="${esc(r.user)}"><td><b>${op ? '▾' : '▸'} ${esc(r.name)}</b></td>${days.map(d => `<td class="num">${s.by_day[d] ? tsDur(s.by_day[d]) : ''}</td>`).join('')}<td class="num"><b>${tsDur(s.total)}</b></td><td class="num">${tsPct(s.occupancy)}</td><td class="num">${tsPct(s.billable_rate)}</td><td class="num">${todo || '✓'}</td></tr>`
      + (op ? `<tr><td colspan="${days.length + 5}"><div class="ts-detail">${r.entries.length ? r.entries.map(e => `<div class="ts-dline"><small>${esc(plFmt(e.date, {weekday: 'short', day: 'numeric', month: 'short'}))}</small>${tsEntryHtml(e, false)}</div>`).join('') + (todo ? `<div class="sdbar"><button type="button" data-ts="valall" data-u="${esc(r.user)}">Valider toute la semaine</button></div>` : '') : '<p class="na">Aucun pointage cette semaine.</p>'}</div></td></tr>` : ''); }).join('');
  return `${tsNav()}${ts.form ? tsFormHtml() : ''}<div class="tblwrap"><table class="sdtable ts-team"><thead>${head}</thead><tbody>${rows || '<tr><td colspan="12" class="na">Aucun membre de l’atelier pour cette BU : choisissez un rôle dans la colonne Atelier (Planifier › Ressources › Staff interne) et renseignez le compte Google.</td></tr>'}</tbody></table></div>${tsJobsHtml()}`;
}

function tsPreview(f) {
  const v = f.vehicle === '__keep' ? {name: f.vehicleName} : (ts.veh || []).find(x => x.id === f.vehicle), lab = (l, id) => (l.find(n => n.id === id) || {}).label;
  if (f.kind === 'event') return f.event && f.nature ? `${lab(ts.me.natures, f.nature)} — ${f.event}` : '';
  if (f.kind !== 'atelier' || !v || !f.nature) return '';
  if (f.nature === 'custom') return f.title ? `${f.title} / ${v.name}` : '';
  return f.event ? `${lab(ts.me.atelier_natures, f.nature)} ${f.event} / ${v.name}` : '';
}
function tsJobsHtml() {
  const f = ts.jobForm, bus = tsBuOpts(ts.me);
  const sug = ts.sugg == null ? '<button type="button" data-ts="sugg">Voir les propositions d’après le planning</button>' : ts.sugg.length ? `<table class="sdtable"><tbody>${ts.sugg.map((s, i) => `<tr><td><b>${esc(s.title)}</b></td><td>${esc(TS_KIND[s.kind])}${s.natures ? ` · ${s.natures.length} jobs` : ''}</td><td>${esc(plFmt(s.when, {day: 'numeric', month: 'short'}))}</td><td class="num"><button type="button" data-ts="mk" data-i="${i}">Créer ce job</button></td></tr>`).join('')}</tbody></table>` : '<p class="na">Aucune proposition : tous les jobs des prochains événements existent déjà.</p>';
  const form = !f ? '<button type="button" data-ts="newjob">+ Nouveau job</button>' : `<div class="ts-form"><div class="sdgrid">
    <label class="sdfield"><span>Type</span><select class="sdin" data-j="kind">${Object.entries(TS_KIND).map(([k, l]) => `<option value="${k}"${f.kind === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
    <label class="sdfield"><span>BU</span><select class="sdin" data-j="bu">${bus.map(b => `<option value="${b}"${f.bu === b ? ' selected' : ''}>${TS_BU[b]}</option>`).join('')}</select></label></div>
    ${f.kind !== 'background' ? '' : `<label class="sdfield"><span>Intitulé</span><input class="sdin" data-j="title" value="${esc(f.title)}" maxlength="140" placeholder="Pre-event Spa Classic / Porsche 996 GT3 Cup"></label>`}
    ${f.kind === 'atelier' ? `<label class="sdfield"><span>Voiture (Odoo)</span><select class="sdin" data-j="vehicle"><option value="">— Choisir —</option>${f.vehicleName && !(ts.veh || []).some(v => v.id === f.vehicle) ? `<option value="${esc(f.vehicle)}" selected>${esc(f.vehicleName)}</option>` : ''}${(ts.veh || []).map(v => `<option value="${esc(v.id)}"${f.vehicle === v.id ? ' selected' : ''}>${esc(v.name)}</option>`).join('')}</select></label>
      <label class="sdfield"><span>Nature du job</span><select class="sdin" data-j="nature"><option value="">— Choisir —</option>${ts.me.atelier_natures.map(n => `<option value="${n.id}"${f.nature === n.id ? ' selected' : ''}>${esc(n.label)}</option>`).join('')}</select></label>
      ${f.nature === 'custom' ? `<label class="sdfield"><span>Intervention</span><input class="sdin" data-j="title" value="${esc(f.title)}" maxlength="100" placeholder="Révision boîte de vitesse"></label>` : ''}` : ''}
    ${f.kind === 'event' || (f.kind === 'atelier' && ['pre_event', 'post_event'].includes(f.nature)) ? `<label class="sdfield"><span>Événement (Odoo)</span><input class="sdin" data-j="event" list="ts-evl" value="${esc(f.event)}" maxlength="160" placeholder="Commencez à taper le nom de l’événement" autocomplete="off"><datalist id="ts-evl">${(ts.evs || []).map(v => `<option value="${esc(v.name)}"></option>`).join('')}</datalist></label>` : ''}
    ${f.kind === 'event' ? `<label class="sdfield"><span>Nature du job</span><select class="sdin" data-j="nature"><option value="">— Choisir —</option>${ts.me.natures.map(n => `<option value="${n.id}"${f.nature === n.id ? ' selected' : ''}>${esc(n.label)}</option>`).join('')}</select></label>` : ''}
    ${tsPreview(f) ? `<p class="na">Intitulé : <b>${esc(tsPreview(f))}</b></p>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-ts="savejob">${f.id ? 'Enregistrer' : 'Créer le job'}</button><button type="button" data-ts="canceljob">Annuler</button></div></div>`;
  const list = ts.jobsAll.length ? `<table class="sdtable"><thead><tr><th>Job</th><th>Type</th><th>BU</th><th>Rattachement</th><th></th></tr></thead><tbody>${ts.jobsAll.map(j => `<tr class="${j.open ? '' : 'ts-closed'}"><td>${esc(j.title)}</td><td>${esc(TS_KIND[j.kind])}</td><td>${TS_BU[j.bu] || j.bu}</td><td>${esc((j.vehicle && j.vehicle.name) || (j.event && j.event.title) || '')}</td><td class="num"><button type="button" data-ts="editjob" data-id="${j.id}">Modifier</button> <button type="button" data-ts="togjob" data-id="${j.id}">${j.open ? 'Clôturer' : 'Rouvrir'}</button> <button type="button" class="danger" data-ts="deljob" data-id="${j.id}">Supprimer</button></td></tr>`).join('')}</tbody></table>` : '';
  return `<div class="block-head"><h3>Jobs</h3></div><h4 class="sub">Propositions d’après le planning</h4>${sug}<h4 class="sub">Jobs</h4>${form}${list}`;
}

function tsDraw() {
  const v = document.getElementById('ts-view'); if (!v) return;
  const page = tsPage();
  let h = '';
  if (ts.err) h = `<p class="err">${esc(ts.err)}</p>`;
  else if (!ts.me) h = '<p class="na">Chargement…</p>';
  else if (!ts.me.role) h = '<p class="na">Vous n’êtes pas encore inscrit à l’atelier : demandez au Super User de renseigner votre compte Google et votre rôle (Planifier › Ressources › Staff interne › Atelier).</p>';
  else if (page === 'team' && ts.me.role !== 'chef') h = '<p class="na">Cette page est réservée au chef d’atelier.</p>';
  else h = (ts.msg ? `<p class="ts-msg">${esc(ts.msg)}</p>` : '') + (page === 'team' ? tsTeamHtml() : tsMineHtml());
  v.innerHTML = h;
  if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(v);
}

// ---- Formulaire ---------------------------------------------------------------------------------------------------------------------------------------------------
const tsBlank = () => ({id: null, job_id: '', date: plToday(), minutes: 60, system: 'autre', text: ''});
function tsReadForm() {
  const v = document.getElementById('ts-view'); if (!v || !ts.form) return;
  v.querySelectorAll('[data-f]').forEach(el => { ts.form[el.dataset.f] = el.value; });
}
function tsReadJob() {
  const v = document.getElementById('ts-view'); if (!v || !ts.jobForm) return;
  v.querySelectorAll('[data-j]').forEach(el => { ts.jobForm[el.dataset.j] = el.value; });
}

async function tsImage(file) {                 // photo réduite côté téléphone (1600 px, JPEG) : l'envoi reste léger
  try {
    const bmp = await createImageBitmap(file), k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height)), c = document.createElement('canvas');
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k); c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    return await new Promise(r => c.toBlob(r, 'image/jpeg', 0.82)) || file;
  } catch { return file; }
}
async function tsToggleRec() {
  if (ts.rec) { ts.rec.stop(); return; }
  try {
    const st = await navigator.mediaDevices.getUserMedia({audio: true}), mr = new MediaRecorder(st), parts = [];
    mr.ondataavailable = e => parts.push(e.data);
    mr.onstop = async () => { clearTimeout(ts.recTimer); st.getTracks().forEach(t => t.stop()); const raw = new Blob(parts, {type: mr.mimeType || 'audio/webm'}); ts.rec = null; tsReadForm(); ts.pend.audio = raw; tsDraw(); await tsAfterRecord(raw); };
    mr.start(); ts.rec = mr; ts.recTimer = setTimeout(() => ts.rec && ts.rec.stop(), 180000); tsReadForm(); tsDraw();
  } catch { ts.msg = 'Micro indisponible : autorisez l’accès au micro dans le navigateur.'; tsDraw(); }
}
// WAV 16 kHz mono 16 bits : format accepté par la transcription, lisible partout (Chrome enregistre en WebM, Safari en MP4)
async function tsWav(blob) {
  const ctx = new (window.AudioContext || window.webkitAudioContext)(), buf = await ctx.decodeAudioData(await blob.arrayBuffer()); ctx.close();
  const off = new OfflineAudioContext(1, Math.ceil(buf.duration * 16000), 16000), src = off.createBufferSource(); src.buffer = buf; src.connect(off.destination); src.start();
  const pcm = (await off.startRendering()).getChannelData(0), out = new DataView(new ArrayBuffer(44 + pcm.length * 2)), w = (o, t) => [...t].forEach((c, i) => out.setUint8(o + i, c.charCodeAt(0)));
  w(0, 'RIFF'); out.setUint32(4, 36 + pcm.length * 2, true); w(8, 'WAVEfmt '); out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true); out.setUint32(24, 16000, true); out.setUint32(28, 32000, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true); w(36, 'data'); out.setUint32(40, pcm.length * 2, true);
  pcm.forEach((v, i) => out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true));
  return new Blob([out], {type: 'audio/wav'});
}
async function tsAfterRecord(raw) {
  let wav; try { wav = await tsWav(raw); } catch { return; }              // conversion impossible : le mémo reste tel quel, sans transcription
  if (ts.pend.audio !== raw) return;                                      // mémo retiré entre-temps
  ts.pend.audio = wav; if (!ts.me.transcribe) return tsDraw();
  ts.pend.tr = 'busy'; tsReadForm(); tsDraw();
  try {
    const r = await fetch('/api/timesheets/transcribe', {method: 'POST', headers: {...rsAuth(), 'Content-Type': 'audio/wav'}, body: wav}), j = await r.json().catch(() => ({}));
    if (ts.pend.audio !== wav) return;
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    tsReadForm(); if (ts.form && j.text) ts.form.text = (ts.form.text ? ts.form.text.trim() + '\n' : '') + j.text;
    ts.pend.tr = j.text ? 'ok' : 'empty';
  } catch (e) { ts.pend.tr = 'err'; ts.msg = 'Transcription impossible : ' + e.message + ' — saisissez le texte.'; }
  tsDraw();
}
async function tsUpload(eid, blob, name) {
  const r = await fetch(`/api/timesheets/entries/${eid}/attachments?filename=${encodeURIComponent(name)}`, {method: 'POST', headers: {...rsAuth(), 'Content-Type': blob.type || 'application/octet-stream'}, body: blob});
  if (!r.ok) { const j = await r.json().catch(() => ({})); throw new Error(typeof j.detail === 'string' ? j.detail : 'Envoi impossible (' + r.status + ')'); }
}
async function tsSave() {
  tsReadForm(); const f = ts.form;
  if (!f.job_id) { ts.msg = 'Choisissez un job.'; tsDraw(); return; }
  ts.busy = true; ts.msg = null; tsDraw();
  try {
    const body = JSON.stringify({job_id: f.job_id, date: f.date, minutes: f.minutes, system: f.system, text: f.text});
    const e = await rsCall(f.id ? `/api/timesheets/entries/${f.id}` : '/api/timesheets/entries', {method: f.id ? 'PUT' : 'POST', body});
    let i = 1;
    for (const p of ts.pend.photos) await tsUpload(e.id, p, `photo-${i++}.jpg`);
    if (ts.pend.audio) await tsUpload(e.id, ts.pend.audio, 'memo-vocal');
    ts.form = null; ts.pend = {photos: [], audio: null};
  } catch (e) { ts.msg = e.message; }
  ts.busy = false; await tsLoad(tsPage());
}

// ---- Actions -------------------------------------------------------------------------------------------------------------------------------------------------------
async function tsDo(fn) { try { await fn(); ts.msg = null; } catch (e) { ts.msg = e.message; } await tsLoad(tsPage()); }
const tsAllEntries = () => (ts.week ? ts.week.entries : []).concat(ts.team ? ts.team.rows.flatMap(r => r.entries) : []);

document.addEventListener('click', ev => {
  const c = ev.target.closest && ev.target.closest('.ts-cal'); if (c && document.getElementById('ts-view')) { const dp = document.querySelector('.ts-dp'); if (dp) { try { dp.showPicker(); } catch { dp.focus(); dp.click(); } } }
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest && ev.target.closest('[data-ts]'); if (!b || !document.getElementById('ts-view') || b.tagName === 'INPUT') return;
  const a = b.dataset.ts, page = tsPage();
  if (a === 'prev' || a === 'next' || a === 'today') { ts.start = a === 'today' ? plMonday(plToday()) : plAdd(ts.start, a === 'next' ? 7 : -7); return tsLoad(page); }
  if (a === 'open') { const u = b.dataset.u; ts.open.has(u) ? ts.open.delete(u) : ts.open.add(u); return tsDraw(); }
  if (a === 'new') { ts.form = tsBlank(); ts.pend = {photos: [], audio: null}; return tsDraw(); }
  if (a === 'edit') { const e = tsAllEntries().find(x => x.id === b.dataset.id); if (e) { ts.form = {id: e.id, job_id: e.job_id, date: e.date, minutes: e.minutes, system: e.system, text: e.text, atts: e.attachments || []}; ts.pend = {photos: [], audio: null}; tsDraw(); document.getElementById('ts-view').scrollIntoView(); } return; }
  if (a === 'cancel') { if (ts.rec) ts.rec.stop(); ts.form = null; ts.msg = null; return tsDraw(); }
  if (a === 'del') { if (!confirm(t('Supprimer ce pointage ?'))) return; return tsDo(() => rsCall(`/api/timesheets/entries/${b.dataset.id}`, {method: 'DELETE'})); }
  if (a === 'val') return tsDo(() => rsCall(`/api/timesheets/entries/${b.dataset.id}/validate?validated=${b.dataset.v === '1'}`, {method: 'POST'}));
  if (a === 'valall') { const r = ts.team.rows.find(x => x.user === b.dataset.u); return tsDo(async () => { for (const e of r.entries.filter(x => !x.validated)) await rsCall(`/api/timesheets/entries/${e.id}/validate?validated=true`, {method: 'POST'}); }); }
  if (['dur', 'step', 'day'].includes(a)) {
    tsReadForm(); const f = ts.form;
    if (a === 'dur') f.minutes = +b.dataset.m; else if (a === 'step') f.minutes = Math.min(960, Math.max(15, f.minutes + +b.dataset.n)); else f.date = plAdd(plToday(), +b.dataset.d);
    return tsDraw();
  }
  if (a === 'rm') { tsReadForm(); if (b.dataset.k === 'audio') { ts.pend.audio = null; ts.pend.tr = null; } else ts.pend.photos.splice(+b.dataset.i, 1); return tsDraw(); }
  if (a === 'rmsaved') { if (!confirm(t('Supprimer cette pièce jointe ?'))) return; tsReadForm(); try { await rsCall(`/api/timesheets/entries/${ts.form.id}/attachments/${b.dataset.id}`, {method: 'DELETE'}); ts.form.atts = ts.form.atts.filter(x => x.id !== b.dataset.id); } catch (e) { ts.msg = e.message; } return tsDraw(); }
  if (a === 'rec') return tsToggleRec();
  if (a === 'save') return tsSave();
  if (a === 'sugg') { ts.sugg = []; try { const j = await rsCall('/api/timesheets/suggestions'); ts.sugg = j.suggestions; if (j.unavailable) ts.msg = j.unavailable; } catch (e) { ts.sugg = null; ts.msg = e.message; } return tsDraw(); }
  if (a === 'mk') { const s = ts.sugg[+b.dataset.i]; return tsDo(async () => { for (const n of (s.natures || [''])) await rsCall('/api/timesheets/jobs', {method: 'POST', body: JSON.stringify({kind: s.kind, title: s.title, nature: n, bu: s.bu, assignment: s.assignment || 'autre', vehicle: s.vehicle, event: s.event})}); ts.sugg.splice(+b.dataset.i, 1); }); }
  if (a === 'newjob') { ts.jobForm = {kind: 'atelier', nature: '', bu: ts.me.bus[0] || 'CARS', title: '', vehicle: '', event: ''}; if (!ts.evs) { ts.evs = []; rsCall('/api/timesheets/events').then(j => { ts.evs = j.events; if (j.unavailable) ts.msg = j.unavailable; tsReadJob(); tsDraw(); }).catch(() => {}); }
    if (!ts.veh) { ts.veh = []; rsCall('/api/timesheets/vehicles').then(j => { ts.veh = j.vehicles; if (j.unavailable) ts.msg = j.unavailable; tsReadJob(); tsDraw(); }).catch(() => {}); } return tsDraw(); }
  if (a === 'editjob') {
    const j = ts.jobsAll.find(x => x.id === b.dataset.id); if (!j) return;
    ts.jobForm = {id: j.id, open: j.open, assignment: j.assignment, kind: j.kind, nature: j.nature || '', bu: j.bu, title: j.kind === 'background' || j.nature === 'custom' ? (j.nature === 'custom' ? j.title.replace(/ \/ [^/]*$/, '') : j.title) : '', vehicle: j.vehicle ? (j.vehicle.id || '__keep') : '', vehicleName: j.vehicle ? j.vehicle.name : '', event: j.event ? j.event.title : ''};
    if (!ts.evs) { ts.evs = []; rsCall('/api/timesheets/events').then(r => { ts.evs = r.events; tsReadJob(); tsDraw(); }).catch(() => {}); }
    if (!ts.veh) { ts.veh = []; rsCall('/api/timesheets/vehicles').then(r => { ts.veh = r.vehicles; tsReadJob(); tsDraw(); }).catch(() => {}); }
    tsDraw(); return document.getElementById('ts-view').querySelector('.ts-form').scrollIntoView();
  }
  if (a === 'canceljob') { ts.jobForm = null; return tsDraw(); }
  if (a === 'savejob') {
    tsReadJob(); const f = ts.jobForm, v = f.vehicle === '__keep' ? {id: '', name: f.vehicleName} : (ts.veh || []).find(x => x.id === f.vehicle);
    return tsDo(async () => { await rsCall(f.id ? `/api/timesheets/jobs/${f.id}` : '/api/timesheets/jobs', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify({open: f.open !== false, assignment: f.assignment || 'autre', kind: f.kind, title: f.title, nature: f.kind === 'background' ? '' : f.nature, bu: f.bu, vehicle: f.kind === 'atelier' && v ? {id: v.id, name: v.name} : null, event: f.kind !== 'background' && f.nature !== 'custom' && f.event ? {id: ((ts.evs || []).find(x => x.name === f.event) || {}).id || '', title: f.event} : null})}); ts.jobForm = null; });
  }
  if (a === 'deljob') { if (!confirm(t('Supprimer ce job ?'))) return; return tsDo(() => rsCall(`/api/timesheets/jobs/${b.dataset.id}`, {method: 'DELETE'})); }
  if (a === 'togjob') { const j = ts.jobsAll.find(x => x.id === b.dataset.id); return tsDo(() => rsCall(`/api/timesheets/jobs/${j.id}`, {method: 'PUT', body: JSON.stringify({kind: j.kind, title: j.title, bu: j.bu, nature: j.nature || '', assignment: j.assignment || 'autre', vehicle: j.vehicle, event: j.event, open: !j.open})})); }
});
document.addEventListener('change', async ev => {
  const el = ev.target; if (!document.getElementById('ts-view')) return;
  if (el.classList && (el.classList.contains('ts-d') || el.classList.contains('ts-dp'))) {
    const iso = el.classList.contains('ts-dp') ? el.value : peParse(el.value);
    if (!iso || iso > plToday()) { ts.msg = 'Date invalide : saisissez jj/mm/aaaa (pas dans le futur).'; return tsDraw(); }
    tsReadForm(); ts.form.date = iso; ts.msg = null; return tsDraw();
  }
  if (el.matches && el.matches('[data-ts-file]')) { tsReadForm(); for (const f of el.files) ts.pend.photos.push(await tsImage(f)); return tsDraw(); }
  if (el.matches && el.matches('[data-f="job_id"]')) { tsReadForm(); tsDraw(); return; }
  if (el.matches && el.matches('[data-j="kind"]')) { tsReadJob(); tsDraw(); }
  if (el.matches && el.matches('[data-j="event"]')) { tsReadJob(); const v = (ts.evs || []).find(x => x.name === ts.jobForm.event); if (v && v.bu && tsBuOpts(ts.me).includes(v.bu)) ts.jobForm.bu = v.bu; tsDraw(); }
  if (el.matches && el.matches('[data-j="nature"]')) { tsReadJob(); tsDraw(); }
  if (el.matches && el.matches('[data-j="vehicle"]')) { tsReadJob(); const v = (ts.veh || []).find(x => x.id === ts.jobForm.vehicle); if (v && v.bu && !ts.jobForm.event && tsBuOpts(ts.me).includes(v.bu)) ts.jobForm.bu = v.bu; tsDraw(); }
});
