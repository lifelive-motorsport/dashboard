// Consigner › Pointages : « Mes pointages » (chaque mécanicien : saisie en durée sur un job, photos, mémo vocal, récapitulatif de la semaine) et « Équipe »
// (chef d'atelier : heures de chaque mécanicien, taux d'occupation et taux facturable, validation, jobs et propositions d'après le planning).
// Données : /api/timesheets (backend/app/timesheets.py). S'appuie sur les outils de dates de planning.js et sur rsCall (resources.js).
let ts = {me: null, jobs: [], start: '', week: null, team: null, form: null, pend: {photos: [], audio: null}, rec: null, open: new Set(), err: null, msg: null, loading: false, jobsAll: [], sugg: null, veh: null, evs: null, recent: [], cockpit: null, tpls: [], tplForm: null, openJobs: new Set(), jobForm: null, busy: false};
const TS_BU = {CARS: 'CARS (toutes)', MODERN_RALLY: 'CARS · Modern Rally', HISTORIC_RALLY: 'CARS · Historic Rally', HISTORIC_RACING: 'CARS · Historic Racing', XC: 'XC', ALL: 'Toutes'};
const tsBuOpts = me => ['XC', 'CARS', 'MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING'].filter(b => me.super || me.bus.includes(b === 'XC' ? 'XC' : 'CARS')).concat(['ALL']);
const TS_KIND = {atelier: 'Job atelier', event: 'Job événement', background: 'Tâche de fond'};
const tsUrls = new WeakMap();
const tsUrl = blob => { if (!tsUrls.has(blob)) tsUrls.set(blob, URL.createObjectURL(blob)); return tsUrls.get(blob); };
const tsSystems = () => ts.me.systems.slice().sort((a, b) => (a.id === 'autre') - (b.id === 'autre') || a.label.localeCompare(b.label, LOCALE(), {sensitivity: 'base'}));   // ordre alphabétique, « Autre » en dernier
const tsDur = m => { const h = Math.floor(m / 60), r = m % 60; return h ? (r ? `${h} h ${String(r).padStart(2, '0')}` : `${h} h`) : `${r} min`; };
const tsPct = x => x == null ? '–' : Math.round(x * 100) + ' %';
const tsStamp = iso => new Date(iso).toLocaleString(LOCALE(), {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
const tsPage = () => location.hash.includes('consigner/team') ? 'team' : location.hash.includes('consigner/jobs') ? 'jobs' : 'mine';

function tsBlocks(page) {
  return [{static: `<section class="block" data-bid="ts"><div class="block-head"><h3>${page === 'team' ? 'Équipe' : page === 'jobs' ? 'Jobs' : 'Mes pointages'}</h3></div><div class="block-body" id="ts-view"><p class="na loading">Chargement…</p></div></section>`}];
}

async function tsLoad(page) {
  if (!ts.start) ts.start = plMonday(plToday());
  ts.loading = true; ts.err = null; tsDraw();
  try {
    if (!ts.me) ts.me = await rsCall('/api/timesheets/me');
    if (ts.me.role) {
      const jr = await rsCall('/api/timesheets/jobs'); ts.jobs = jr.jobs; ts.recent = jr.recent || [];
      if (page === 'team') {
        if (ts.me.role === 'chef') { ts.team = await rsCall(`/api/timesheets/team?start=${ts.start}&bu=${buSel}`); ts.cockpit = await rsCall('/api/timesheets/cockpit'); }
      } else if (page === 'jobs') {
        if (ts.me.role === 'chef') { ts.jobsAll = (await rsCall('/api/timesheets/jobs?all=true')).jobs; ts.tpls = (await rsCall('/api/timesheets/templates')).templates; }
      } else {
        ts.week = await rsCall(`/api/timesheets/week?start=${ts.start}`);
        const dr = !ts.form && tsDraft();
        if (dr) { ts.form = {...tsBlank(), ...dr, id: null}; ts.pend = {photos: [], audio: null}; ts.msg = 'Brouillon restauré : votre pointage en cours de saisie a été retrouvé.'; }
      }
    }
  } catch (e) { ts.err = e.message; }
  ts.loading = false; tsDraw();
}

// ---- Dessin -------------------------------------------------------------------------------------------------------------------------------------------------------
const tsNav = () => `<div class="ts-nav"><button type="button" data-ts="prev" aria-label="Semaine précédente">‹</button><b>${esc(`Semaine ${plWeekNo(ts.start)} · ${plFmt(ts.start, {day: 'numeric', month: 'short'})} – ${plFmt(plAdd(ts.start, 6), {day: 'numeric', month: 'short', year: 'numeric'})}`)}</b><button type="button" data-ts="next" aria-label="Semaine suivante">›</button><button type="button" data-ts="today">Aujourd’hui</button></div>`;
const tsKpis = s => `<div class="ts-kpis"><div><small>Heures pointées</small><b>${tsDur(s.total)}</b></div><div><small>Facturables</small><b>${tsDur(s.billable)}</b></div><div><small>Taux d’occupation</small><b>${tsPct(s.occupancy)}</b></div><div><small>Taux facturable</small><b>${tsPct(s.billable_rate)}</b></div><div><small>Horaire théorique</small><b>${s.theoretical ? tsDur(s.theoretical) : '–'}</b></div></div>`;

const tsCoarse = () => !!(window.matchMedia && matchMedia('(pointer:coarse)').matches);
function tsEntryHtml(e, mine) {
  const a = (ts.me.assignments.find(x => x.id === (e.job.assignment || e.assignment)) || {}).label, sy = (ts.me.systems.find(x => x.id === e.system) || {}).label;
  const att = (e.attachments || []).map(x => { const u = `/api/timesheets/entries/${e.id}/attachments/${x.id}`; return x.kind === 'photo' ? `<img class="ts-ph" src="${u}" loading="lazy" alt="Photo">` : x.expired ? '<span class="ts-n">🎙 Mémo supprimé (conservé 90 jours)</span>' : `<audio controls preload="none" src="${u}"></audio>`; }).join('');
  const coarse = tsCoarse(), hold = coarse ? ' data-hold' : '';
  const lock = e.status === 'returned' ? '<span class="ts-lock bad">↩ Info requise</span>' : e.validated ? `<span class="ts-lock ok">✓ ${e.status === 'adjusted' ? 'Validé (ajusté)' : 'Validé'}</span>` : e.can_edit && !(ts.me.role === 'chef') ? `<span class="ts-lock">Modifiable jusqu’à</span> <span class="ts-lock">${esc(tsStamp(e.editable_until))}</span>` : e.can_edit ? '' : '<span class="ts-lock bad">🔒 Verrouillé</span>';
  const acts = e.can_edit ? `<button type="button" data-ts="edit" data-id="${e.id}">${e.status === 'returned' ? 'Corriger' : 'Modifier'}</button><button type="button" class="danger" data-ts="del" data-id="${e.id}">Supprimer</button>` : '';
  const chef = ts.me.role === 'chef' && !mine;
  const val = chef ? (e.validated ? `<button type="button" data-ts="val" data-id="${e.id}" data-v="0">Annuler la validation</button>` : `<button type="button" class="okbtn" data-ts="val" data-id="${e.id}" data-v="1"${hold}>${coarse ? 'Maintenir pour valider' : 'Valider'}</button>${e.status === 'returned' ? '' : `<button type="button" data-ts="rej" data-id="${e.id}">Renvoyer</button>`}`) : '';
  const hide = chef && e.text ? `<button type="button" data-ts="hide" data-id="${e.id}" data-v="${e.client_hidden ? 0 : 1}" title="Texte visible ou non dans l’espace client">${e.client_hidden ? '👁 Afficher au client' : '🚫 Masquer pour le client'}</button>` : '';
  const th = e.thread || [], last = th.length ? th[th.length - 1] : null;
  const note = e.status === 'returned' && e.return_reason ? `<div class="ts-reason"><b>Motif :</b> ${esc(e.return_reason)}</div>` : (e.status === 'adjusted' || e.status === 'sent') && last && last.kind !== 'reject' ? `<div class="ts-reason soft">${esc(last.by)} : ${esc(last.text)}</div>` : '';
  const done = e.job_done ? '<span class="ts-tag">Job terminé</span>' : '';
  return `<div class="ts-entry"><div class="ts-top"><b>${esc(e.job.title)}</b>${e.job.billable ? '<span class="ts-tag">Facturable</span>' : ''}${done}<span class="ts-min">${tsDur(e.minutes)}</span></div>
    <div class="ts-sub">${[a && (e.job.assignment || e.assignment) !== 'autre' ? a : '', sy && e.system !== 'autre' ? sy : ''].filter(Boolean).map(esc).join(' · ')}${e.text ? ' — ' + esc(e.text) : ''}${e.client_hidden && e.text ? ' <span class="ts-n">🚫 masqué au client</span>' : ''}</div>${note}${tsLinesHtml(e)}${att ? `<div class="ts-att">${att}</div>` : ''}<div class="ts-act">${lock}${acts}${val}${hide}</div></div>`;
}

function tsLinesHtml(e) {
  if (!(e.lines || []).length) return '';
  const g = {}; e.lines.forEach(l => (g[l.section] = g[l.section] || []).push(l.text));
  return `<div class="ts-sub ts-lines">${Object.entries(g).map(([k, v]) => `<div>☑ <b>${esc(k)}</b> : ${v.map(esc).join(' ; ')}</div>`).join('')}</div>`;
}
// Liste de contrôle du job choisi, dans le formulaire de pointage : on coche ce qui a été fait pendant ce temps
function tsChecklistHtml(job, f) {
  const cl = job && job.checklist; if (!cl) return '';
  const mine = new Set(f.lines || []);
  const body = cl.sections.map(sec => `<details class="ts-sec" open><summary><b>${esc(sec.title)}</b> <small>${sec.lines.filter(l => l.done || mine.has(l.id)).length} / ${sec.lines.length}</small></summary>${sec.lines.map(l => {
    const other = l.done && l.entry_id !== f.id;
    return `<label class="ts-line${other ? ' done' : ''}"><input type="checkbox" data-ts-line="${l.id}"${other ? ' checked disabled' : mine.has(l.id) ? ' checked' : ''}> <span>${esc(l.text)}${l.note ? ` <small>(${esc(l.note)})</small>` : ''}${other ? ` <small class="ok">✓ ${esc(l.done_by || '')} · ${esc(tsStamp(l.done_at))}</small>` : ''}</span></label>`; }).join('')}</details>`).join('');
  return `<div class="sdfield"><span>Liste de contrôle — ${esc(cl.template_name)} (cochez ce qui a été fait)</span>${body}</div>`;
}
const tsNorm = x => String(x || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
function tsJobOptions(sel, q) {
  const ok = j => j.id === sel || !q || tsNorm(j.title).includes(tsNorm(q));
  const rec = ts.recent.map(id => ts.jobs.find(j => j.id === id)).filter(j => j && ok(j)), recIds = new Set(rec.map(j => j.id));
  const opt = j => `<option value="${j.id}"${j.id === sel ? ' selected' : ''}>${esc(j.title)}</option>`;
  const groups = [['atelier', 'Jobs atelier'], ['event', 'Jobs événement'], ['background', 'Tâches de fond']];
  return `<option value="">— Choisir un job —</option>${rec.length ? `<optgroup label="${esc(t('Récents'))}">${rec.map(opt).join('')}</optgroup>` : ''}${groups.map(([k, l]) => { const js = ts.jobs.filter(j => j.kind === k && !recIds.has(j.id) && ok(j)); return js.length ? `<optgroup label="${esc(t(l))}">${js.map(opt).join('')}</optgroup>` : ''; }).join('')}`;
}
function tsJobSelect(sel) {
  return `<input class="sdin ts-jq" data-jq type="search" placeholder="${esc(t('Rechercher un job…'))}" autocomplete="off"><select class="sdin" data-f="job_id">${tsJobOptions(sel, '')}</select>`;
}
document.addEventListener('input', e => { const q = e.target.closest && e.target.closest('[data-jq]'); if (!q) return; const sel = q.parentElement.querySelector('[data-f="job_id"]'); if (sel) sel.innerHTML = tsJobOptions(sel.value, q.value); });
function tsFormHtml() {
  const f = ts.form; if (!f) return '';
  const chips = [30, 60, 120, 240, 480].map(m => `<button type="button" class="ts-chip${f.minutes === m ? ' sel' : ''}" data-ts="dur" data-m="${m}">${tsDur(m)}</button>`).join('');
  const x = (k, i) => `<button type="button" class="ts-x" data-ts="rm" data-k="${k}" data-i="${i}" aria-label="Retirer" title="Retirer">✕</button>`;
  const photos = ts.pend.photos.map((p, i) => `<span class="ts-pp"><img class="ts-ph" src="${tsUrl(p)}" alt="Photo">${x('photo', i)}</span>`).join('');
  const audio = ts.pend.audio ? `<span class="ts-pp"><audio controls src="${tsUrl(ts.pend.audio)}"></audio>${x('audio', 0)}</span>${{busy: '<span class="ts-n">Transcription en cours…</span>', ok: '<span class="ts-n">✓ Transcrit : relisez et corrigez le texte ci-dessus</span>', empty: '<span class="ts-n">Aucune parole reconnue</span>'}[ts.pend.tr] || ''}` : '';
  const saved = (f.atts || []).map(at => { const u = `/api/timesheets/entries/${f.id}/attachments/${at.id}`; return `<span class="ts-pp">${at.kind === 'photo' ? `<img class="ts-ph" src="${u}" alt="Photo">` : at.expired ? '<span class="ts-n">🎙 Mémo supprimé (conservé 90 jours)</span>' : `<audio controls preload="none" src="${u}"></audio>`}<button type="button" class="ts-x" data-ts="rmsaved" data-id="${at.id}" aria-label="Supprimer" title="Supprimer">✕</button></span>`; }).join('');
  return `<div class="ts-form"><h4>${f.id ? 'Modifier le pointage' : 'Nouveau pointage'}</h4>
    <label class="sdfield"><span>Job</span>${tsJobSelect(f.job_id)}</label>
    <div class="sdgrid"><label class="sdfield"><span>Date</span><span class="datef"><input class="sdin ts-d" value="${fmtDate(f.date)}" placeholder="jj/mm/aaaa" inputmode="numeric" maxlength="10" autocomplete="off"><button type="button" class="ts-cal" aria-label="Calendrier" title="Calendrier"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1.5v3M11 1.5v3"/></svg></button><input type="date" class="ts-dp" value="${f.date}" max="${plToday()}" tabindex="-1" aria-hidden="true"></span></label>
    <div class="sdfield"><span>Rapide</span><div class="ts-chips"><button type="button" class="ts-chip" data-ts="day" data-d="0">Aujourd’hui</button><button type="button" class="ts-chip" data-ts="day" data-d="-1">Hier</button></div></div></div>
    <div class="sdfield"><span>Durée</span><div class="ts-dur"><button type="button" data-ts="step" data-n="-15" aria-label="Moins 15 minutes">−</button><b id="ts-dur">${tsDur(f.minutes)}</b><button type="button" data-ts="step" data-n="15" aria-label="Plus 15 minutes">+</button></div><div class="ts-chips">${chips}</div></div>
    ${(ts.jobs.find(j => j.id === f.job_id) || {}).kind === 'atelier' ? `<div><button type="button" data-tf="open" data-id="${esc(f.job_id)}">📋 ${t('Formulaires techniques de ce job')}</button></div>` : ''}
    ${tsChecklistHtml(ts.jobs.find(j => j.id === f.job_id), f)}
    ${(ts.jobs.find(j => j.id === f.job_id) || {}).kind === 'atelier' && !(ts.jobs.find(j => j.id === f.job_id) || {}).checklist ? `<label class="sdfield"><span>Système</span><select class="sdin" data-f="system">${tsSystems().map(s => `<option value="${s.id}"${f.system === s.id ? ' selected' : ''}>${esc(s.label)}</option>`).join('')}</select></label>` : ''}
    <label class="sdfield"><span>Intervention</span><textarea class="sdin" data-f="text" rows="3" maxlength="3000" placeholder="Ce qui a été fait…">${esc(f.text)}</textarea></label>
    ${ts.me.attachments ? `<div class="ts-media"><label class="btn">📷 Prendre une photo<input type="file" accept="image/*" capture="environment" hidden data-ts-file></label>
      <label class="btn">🖼 Galerie<input type="file" accept="image/*" multiple hidden data-ts-file></label>
      <button type="button" data-ts="rec" class="${ts.rec ? 'rec' : ''}">${ts.rec ? '⏹ Arrêter' : '🎙 Mémo vocal'}</button></div><div class="ts-att">${saved}${photos}${audio}</div>` : ''}
    ${['atelier', 'event'].includes((ts.jobs.find(j => j.id === f.job_id) || {}).kind) ? `<div class="sdfield"><span>Le job est-il terminé ?</span><div class="ts-chips"><button type="button" class="ts-chip${f.job_done ? ' sel' : ''}" data-ts="jd" data-v="1">Oui</button><button type="button" class="ts-chip${f.job_done ? '' : ' sel'}" data-ts="jd" data-v="0">Non</button></div>${f.job_done ? '<small class="na">Le job sera clôturé : il n’apparaîtra plus dans la liste (le chef d’atelier peut le rouvrir).</small>' : ''}</div>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-ts="save"${ts.busy ? ' disabled' : ''}>Enregistrer</button><button type="button" data-ts="cancel">Annuler</button></div></div>`;
}

function tsMineHtml() {
  const w = ts.week; if (!w) return '';
  const days = Array.from({length: 7}, (_, i) => plAdd(ts.start, i)), t = plToday();
  const byDay = Object.fromEntries(days.map(d => [d, w.entries.filter(e => e.date === d)]));
  const back = w.entries.filter(e => e.status === 'returned').length, miss = (w.missing || []);
  return `${tsNav()}${back ? `<div class="ts-msg">↩ <span>Pointages à corriger</span> <b>${back}</b></div>` : ''}${miss.length && !ts.form ? `<div class="ts-miss"><span>⚠ Pointages manquants :</span>${miss.map(d => `<button type="button" data-ts="fill" data-d="${d}">${esc(plFmt(d, {weekday: 'short', day: 'numeric', month: 'short'}))}</button>`).join('')}</div>` : ''}${tsKpis(w.summary)}${ts.form ? tsFormHtml() : '<div class="sdbar ts-add"><button type="button" class="primary" data-ts="new">+ Nouveau pointage</button></div>'}
    ${days.map(d => { const es = byDay[d], tot = w.summary.by_day[d] || 0;
      return `<div class="ts-day${d === t ? ' today' : ''}"><div class="ts-dh"><b>${esc(plFmt(d, {weekday: 'long', day: 'numeric', month: 'short'}))}</b><span>${tot ? tsDur(tot) : ''}</span></div>${es.map(e => tsEntryHtml(e, true)).join('') || ''}</div>`; }).join('')}`;
}

function tsTeamHtml() {
  const tm = ts.team; if (!tm) return '';
  const days = Array.from({length: 7}, (_, i) => plAdd(ts.start, i));
  const head = `<tr><th>Personne</th>${days.map(d => `<th class="num">${esc(plFmt(d, {weekday: 'short'}))} ${+d.slice(8)}</th>`).join('')}<th class="num">Total</th><th class="num">Occupation</th><th class="num">Facturable</th><th class="num">À valider</th></tr>`;
  const inBu = r => buSel === 'all' || r.all_bus || (BU_KEYS[buSel] || []).some(k => (r.bus || []).includes(k));
  const rows = tm.rows.filter(r => inBu(r) || r.summary.count > 0).map(r => { const s = r.summary, op = ts.open.has(r.user), todo = s.count - s.validated;
    return `<tr class="ts-row" data-ts="open" data-u="${esc(r.user)}"><td><b>${op ? '▾' : '▸'} ${esc(r.name)}</b>${r.other ? ` <small class="na">${esc(t('hors liste de l’équipe'))}</small>` : ''}</td>${days.map(d => `<td class="num">${s.by_day[d] ? tsDur(s.by_day[d]) : ''}</td>`).join('')}<td class="num"><b>${tsDur(s.total)}</b></td><td class="num">${tsPct(s.occupancy)}</td><td class="num">${tsPct(s.billable_rate)}</td><td class="num">${todo || '✓'}</td></tr>`
      + (op ? `<tr><td colspan="${days.length + 5}"><div class="ts-detail">${r.entries.length ? r.entries.map(e => `<div class="ts-dline"><small>${esc(plFmt(e.date, {weekday: 'short', day: 'numeric', month: 'short'}))}</small>${tsEntryHtml(e, false)}</div>`).join('') + (todo ? `<div class="sdbar"><button type="button" class="okbtn" data-ts="valall" data-u="${esc(r.user)}"${tsCoarse() ? ' data-hold' : ''}>${tsCoarse() ? 'Maintenir pour valider la semaine' : 'Valider toute la semaine'}</button></div>` : '') : '<p class="na">Aucun pointage cette semaine.</p>'}</div></td></tr>` : ''); }).join('');
  return `${tsCockpitHtml()}${tsNav()}${ts.form ? tsFormHtml() : ''}<div class="tblwrap"><table class="sdtable ts-team"><thead>${head}</thead><tbody>${rows || '<tr><td colspan="12" class="na">Aucun membre de l’atelier pour cette BU : choisissez un rôle dans la colonne Atelier (Planifier › Ressources › Staff interne) et renseignez le compte Google.</td></tr>'}</tbody></table></div>`;
}

const tsGrp = bu => bu === 'XC' ? 'XC' : bu === 'ALL' ? 'ALL' : 'CARS';
const tsTplOk = (t, f) => t.bu === 'ALL' || f.bu === 'ALL' || t.bu === tsGrp(f.bu);
const tsMatchTpl = f => ts.tpls.find(t => tsTplOk(t, f) && t.natures.includes(f.nature));
function tsTplSelect(f) {
  if (f.hasChecklist) return `<p class="na">Liste de contrôle : <b>${esc(f.tplName)}</b> — ${f.progress.done} / ${f.progress.total} faites</p>`;
  const ok = ts.tpls.filter(t => tsTplOk(t, f)), m = tsMatchTpl(f);
  return `<label class="sdfield"><span>Liste de contrôle (modèle)</span><select class="sdin" data-j="template"><option value="">— Aucune —</option>${ok.sort((a, b) => (b === m) - (a === m) || a.name.localeCompare(b.name, LOCALE())).map(t => `<option value="${t.id}"${f.template === t.id ? ' selected' : ''}>${esc(t.name)}${t === m ? ' ★' : ''}</option>`).join('')}</select></label>`;
}
// ---- Modèles de jobs (chef d'atelier) -------------------------------------------------------------------------------------------------------------------
const TS_NAT = {pre_event: 'Pre-event', post_event: 'Post-event', custom: 'Autre intervention'};
const tsLinesText = sec => sec.lines.map(l => l.note ? `${l.text} | ${l.note}` : l.text).join('\n');
function tsTemplatesHtml() {
  const f = ts.tplForm;
  const list = ts.tpls.length ? `<table class="sdtable"><thead><tr><th>Modèle</th><th>BU</th><th>Proposé pour</th><th>Lignes</th><th></th></tr></thead><tbody>${ts.tpls.map(t => `<tr><td><b>${esc(t.name)}</b></td><td>${esc(TS_BU[t.bu] || t.bu)}</td><td>${esc(t.natures.map(n => TS_NAT[n]).join(', '))}</td><td>${t.sections.reduce((n, s) => n + s.lines.length, 0)} (${t.sections.length} sections)</td><td class="num"><button type="button" data-ts="edittpl" data-id="${t.id}">Modifier</button> <button type="button" data-ts="duptpl" data-id="${t.id}">Dupliquer</button> <button type="button" class="danger" data-ts="deltpl" data-id="${t.id}">Supprimer</button></td></tr>`).join('')}</tbody></table>` : '<p class="na">Aucun modèle.</p>';
  const ed = !f ? '<button type="button" data-ts="newtpl">+ Nouveau modèle</button>' : `<div class="ts-form"><div class="sdgrid">
    <label class="sdfield"><span>Nom</span><input class="sdin" data-t="name" value="${esc(f.name)}" maxlength="100" placeholder="Révision Circuit"></label>
    <label class="sdfield"><span>BU</span><select class="sdin" data-t="bu">${['CARS', 'XC', 'ALL'].filter(b => ts.me.super || b === 'ALL' || ts.me.bus.includes(b)).map(b => `<option value="${b}"${f.bu === b ? ' selected' : ''}>${esc(TS_BU[b])}</option>`).join('')}</select></label></div>
    <div class="sdfield"><span>Proposé automatiquement pour les jobs de nature</span><div class="ts-chips">${Object.entries(TS_NAT).map(([k, l]) => `<label class="ts-chip${f.natures.includes(k) ? ' sel' : ''}"><input type="checkbox" hidden data-t-nat="${k}"${f.natures.includes(k) ? ' checked' : ''}>${esc(l)}</label>`).join('')}</div></div>
    ${f.sections.map((sec, i) => `<div class="ts-tsec"><div class="sdgrid"><label class="sdfield"><span>Section</span><input class="sdin" data-t-title="${i}" value="${esc(sec.title)}" maxlength="80" placeholder="Moteur"></label><div class="sdfield"><span>&nbsp;</span><div class="ts-chips"><button type="button" data-ts="secup" data-i="${i}" aria-label="Monter">▲</button><button type="button" data-ts="secdown" data-i="${i}" aria-label="Descendre">▼</button><button type="button" class="danger" data-ts="secdel" data-i="${i}">Retirer la section</button></div></div></div>
      <label class="sdfield"><span>Lignes de travail (une par ligne ; « texte | remarque » pour ajouter une remarque)</span><textarea class="sdin" data-t-lines="${i}" rows="${Math.min(14, Math.max(3, sec.lines.length + 1))}">${esc(tsLinesText(sec))}</textarea></label></div>`).join('')}
    <div class="sdbar"><button type="button" data-ts="secadd">+ Section</button><button type="button" class="primary" data-ts="savetpl">Enregistrer le modèle</button><button type="button" data-ts="canceltpl">Annuler</button></div></div>`;
  return `<div class="block-head"><h3>Modèles de jobs</h3></div><p class="na">Listes de contrôle réutilisables : un job atelier en reçoit une copie à sa création, et les mécaniciens cochent ce qu'ils ont fait en pointant.</p>${ed}${list}`;
}
function tsReadTpl() {
  const v = document.getElementById('ts-view'), f = ts.tplForm; if (!v || !f) return;
  const g = k => v.querySelector(`[data-t="${k}"]`); if (g('name')) { f.name = g('name').value; f.bu = g('bu').value; }
  f.natures = [...v.querySelectorAll('[data-t-nat]:checked')].map(c => c.dataset.tNat);
  f.sections.forEach((sec, i) => { const t = v.querySelector(`[data-t-title="${i}"]`), l = v.querySelector(`[data-t-lines="${i}"]`); if (t) sec.title = t.value; if (l) sec.lines = l.value.split('\n').map(x => x.trim()).filter(Boolean).map(x => { const [a, ...b] = x.split('|'); return {text: a.trim(), note: b.join('|').trim()}; }); });
}
function tsPreview(f) {
  const v = f.vehicle === '__keep' ? {name: f.vehicleName} : (ts.veh || []).find(x => x.id === f.vehicle), lab = (l, id) => (l.find(n => n.id === id) || {}).label;
  if (f.kind === 'event') return f.event && f.nature ? `${lab(ts.me.natures, f.nature)} — ${f.event}` : '';
  if (f.kind !== 'atelier' || !v || !f.nature) return '';
  if (f.nature === 'custom') return f.title ? `${f.title} / ${v.name}` : '';
  return f.event ? `${lab(ts.me.atelier_natures, f.nature)} ${f.event} / ${v.name}` : '';
}
function tsReadonlyList(j) {
  return `<div class="ts-detail">${j.checklist.sections.map(sec => `<div><b>${esc(sec.title)}</b>${sec.lines.map(l => `<div class="ts-line${l.done ? ' done' : ''}">${l.done ? '☑' : '☐'} ${esc(l.text)}${l.done ? ` <small class="ok">✓ ${esc(l.done_by || '')} · ${esc(tsStamp(l.done_at))}</small>` : ''}</div>`).join('')}</div>`).join('')}</div>`;
}
const TS_STATE = {done: '✓ Pointé', waiting: '⏳ Pas encore', late: '⚠ En retard', absent: '🌴 Absent', off: 'Jour non travaillé'};
function tsCockpitHtml() {
  const c = ts.cockpit; if (!c) return '';
  const inBu = r => buSel === 'all' || r.all_bus || (BU_KEYS[buSel] || []).some(k => (r.bus || []).includes(k));
  const rows = c.rows.filter(inBu).map(r => `<tr><td><b>${esc(r.name)}</b></td><td><span class="ts-st ${r.state}">${esc(t(TS_STATE[r.state]))}</span>${r.reason ? ` <small class="na">${esc(r.reason)}</small>` : ''}${r.minutes ? ` <b>${tsDur(r.minutes)}</b>` : ''}</td><td>${r.missing.map(d => `<span class="ts-st late">${esc(plFmt(d, {weekday: 'short', day: 'numeric', month: 'short'}))}</span>`).join(' ') || '<span class="ts-st done">✓</span>'}</td></tr>`).join('');
  return `<div class="block-head"><h3>Aujourd’hui à l’atelier</h3><small class="na">${esc(plFmt(c.date, {weekday: 'long', day: 'numeric', month: 'long'}))} · ${esc(t('pointages attendus après'))} ${esc(c.cutoff)}</small></div><div class="tblwrap"><table class="sdtable ts-cp"><thead><tr><th>Personne</th><th>Aujourd’hui</th><th>Pointages manquants (14 jours)</th></tr></thead><tbody>${rows || '<tr><td colspan="3" class="na">Aucun membre de l’atelier pour cette BU.</td></tr>'}</tbody></table></div><div class="block-head"><h3>Semaine</h3></div>`;
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
    ${f.kind === 'atelier' ? tsTplSelect(f) : ''}
    ${f.kind === 'event' || (f.kind === 'atelier' && ['pre_event', 'post_event'].includes(f.nature)) ? `<label class="sdfield"><span>Événement (Odoo)</span><input class="sdin" data-j="event" list="ts-evl" value="${esc(f.event)}" maxlength="160" placeholder="Commencez à taper le nom de l’événement" autocomplete="off"><datalist id="ts-evl">${(ts.evs || []).map(v => `<option value="${esc(v.name)}"></option>`).join('')}</datalist></label>` : ''}
    ${f.kind === 'event' ? `<label class="sdfield"><span>Nature du job</span><select class="sdin" data-j="nature"><option value="">— Choisir —</option>${ts.me.natures.map(n => `<option value="${n.id}"${f.nature === n.id ? ' selected' : ''}>${esc(n.label)}</option>`).join('')}</select></label>` : ''}
    ${tsPreview(f) ? `<p class="na">Intitulé : <b>${esc(tsPreview(f))}</b></p>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-ts="savejob">${f.id ? 'Enregistrer' : 'Créer le job'}</button><button type="button" data-ts="canceljob">Annuler</button></div></div>`;
  const list = ts.jobsAll.length ? `<table class="sdtable"><thead><tr><th>Job</th><th>Type</th><th>BU</th><th>Rattachement</th><th>Liste</th><th></th></tr></thead><tbody>${ts.jobsAll.map(j => `<tr class="${j.open ? '' : 'ts-closed'}"><td>${esc(j.title)}</td><td>${esc(TS_KIND[j.kind])}</td><td>${TS_BU[j.bu] || j.bu}</td><td>${esc((j.vehicle && j.vehicle.name) || (j.event && j.event.title) || '')}</td><td>${j.progress ? `<button type="button" data-ts="togl" data-id="${j.id}">${j.progress.done} / ${j.progress.total} ${ts.openJobs.has(j.id) ? '▾' : '▸'}</button>` : ''}</td><td class="num"><button type="button" data-tf="open" data-id="${j.id}">Formulaires</button> <button type="button" data-ts="editjob" data-id="${j.id}">Modifier</button> <button type="button" data-ts="togjob" data-id="${j.id}">${j.open ? 'Clôturer' : 'Rouvrir'}</button> <button type="button" class="danger" data-ts="deljob" data-id="${j.id}">Supprimer</button></td></tr>${j.progress && ts.openJobs.has(j.id) ? `<tr><td colspan="6">${tsReadonlyList(j)}</td></tr>` : ''}`).join('')}</tbody></table>` : '';
  return `<h4 class="sub">Propositions d’après le planning</h4>${sug}<h4 class="sub">Jobs</h4>${form}${list}${tsTemplatesHtml()}`;
}

function tsDraw() {
  const v = document.getElementById('ts-view'); if (!v) return;
  const page = tsPage();
  let h = '';
  if (ts.err) h = `<p class="err">${esc(ts.err)}</p>`;
  else if (!ts.me) h = '<p class="na loading">Chargement…</p>';
  else if (!ts.me.role) h = '<p class="na">Vous n’êtes pas encore inscrit à l’atelier : demandez au Super User de renseigner votre compte Google et votre rôle (Planifier › Ressources › Staff interne › Atelier).</p>';
  else if ((page === 'team' || page === 'jobs') && ts.me.role !== 'chef') h = '<p class="na">Cette page est réservée au chef d’atelier.</p>';
  else if (page === 'jobs' && !ts.jobsAll) h = '<p class="na loading">Chargement…</p>';
  else h = (ts.msg ? `<p class="ts-msg">${esc(ts.msg)}</p>` : '') + (page === 'team' ? tsTeamHtml() : page === 'jobs' ? tsJobsHtml() : tsMineHtml());
  v.innerHTML = (typeof tfHtml === 'function' ? tfHtml() : '') + h;
  if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(v);
}

// ---- Formulaire ---------------------------------------------------------------------------------------------------------------------------------------------------
const tsBlank = () => ({id: null, job_id: '', date: plToday(), minutes: 60, system: 'autre', text: '', lines: [], job_done: false});
// Brouillon : le pointage en cours de saisie est gardé sur l'appareil (iOS ferme volontiers les applications installées) ; les photos et mémos, trop lourds, ne le sont pas
const TS_DRAFT = 'lm_ts_draft';
function tsDraft(f) {
  try {
    if (f === null) return localStorage.removeItem(TS_DRAFT);
    if (f === undefined) return JSON.parse(localStorage.getItem(TS_DRAFT) || 'null');
    if (f.job_id || f.text) localStorage.setItem(TS_DRAFT, JSON.stringify({job_id: f.job_id, date: f.date, minutes: f.minutes, system: f.system, text: f.text, lines: f.lines || [], job_done: !!f.job_done}));
  } catch {}
}
function tsReadForm() {
  const v = document.getElementById('ts-view'); if (!v || !ts.form) return;
  v.querySelectorAll('[data-f]').forEach(el => { ts.form[el.dataset.f] = el.value; });
  if (!ts.form.id) tsDraft(ts.form);
  if (v.querySelector('[data-ts-line]')) ts.form.lines = [...v.querySelectorAll('[data-ts-line]:checked:not(:disabled)')].map(c => c.dataset.tsLine);
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
  const jb = ts.jobs.find(j => j.id === f.job_id);
  if (f.job_done && jb && jb.checklist) {                               // le job est terminé mais la liste n'est pas complète : on demande confirmation
    const left = jb.checklist.sections.flatMap(sec => sec.lines).filter(l => !(l.done && l.entry_id !== f.id) && !(f.lines || []).includes(l.id)).length;
    if (left && !confirm(`${t('Il reste des lignes non cochées')} (${left}). ${t('Terminer quand même ?')}`)) return;
  }
  ts.busy = true; ts.msg = null; tsDraw();
  try {
    const body = JSON.stringify({job_id: f.job_id, date: f.date, minutes: f.minutes, system: f.system, text: f.text, lines: f.lines || [], job_done: !!f.job_done});
    const e = await rsCall(f.id ? `/api/timesheets/entries/${f.id}` : '/api/timesheets/entries', {method: f.id ? 'PUT' : 'POST', body});
    let i = 1;
    for (const p of ts.pend.photos) await tsUpload(e.id, p, `photo-${i++}.jpg`);
    if (ts.pend.audio) await tsUpload(e.id, ts.pend.audio, 'memo-vocal');
    ts.form = null; ts.pend = {photos: [], audio: null}; tsDraft(null);
  } catch (e) { ts.msg = e.message; }
  ts.busy = false; await tsLoad(tsPage());
}

// ---- Actions -------------------------------------------------------------------------------------------------------------------------------------------------------
async function tsDo(fn) { try { await fn(); ts.msg = null; } catch (e) { ts.msg = e.message; } await tsLoad(tsPage()); }
const tsAllEntries = () => (ts.week ? ts.week.entries : []).concat(ts.team ? ts.team.rows.flatMap(r => r.entries) : []);

document.addEventListener('click', ev => {
  const c = ev.target.closest && ev.target.closest('.ts-cal'); if (c && document.getElementById('ts-view')) { const dp = document.querySelector('.ts-dp'); if (dp) dpOpen(dp, c); }
});
document.addEventListener('click', async ev => {
  const b = ev.target.closest && ev.target.closest('[data-ts]'); if (!b || !document.getElementById('ts-view') || b.tagName === 'INPUT') return;
  const a = b.dataset.ts, page = tsPage();
  if (a === 'prev' || a === 'next' || a === 'today') { ts.start = a === 'today' ? plMonday(plToday()) : plAdd(ts.start, a === 'next' ? 7 : -7); return tsLoad(page); }
  if (a === 'open') { const u = b.dataset.u; ts.open.has(u) ? ts.open.delete(u) : ts.open.add(u); return tsDraw(); }
  if (a === 'fill') { ts.form = {...tsBlank(), date: b.dataset.d}; ts.pend = {photos: [], audio: null}; return tsDraw(); }
  if (a === 'new') { ts.form = tsBlank(); ts.pend = {photos: [], audio: null}; tsDraw(); return; }
  if (a === 'edit') { const e = tsAllEntries().find(x => x.id === b.dataset.id); if (e) { ts.form = {id: e.id, job_id: e.job_id, date: e.date, minutes: e.minutes, system: e.system, text: e.text, lines: e.line_ids || [], job_done: !!e.job_done, atts: e.attachments || []}; ts.pend = {photos: [], audio: null}; tsDraw(); document.getElementById('ts-view').scrollIntoView(); } return; }
  if (a === 'cancel') { if (ts.rec) ts.rec.stop(); ts.form = null; ts.msg = null; tsDraft(null); return tsDraw(); }
  if (a === 'del') { if (!confirm(t('Supprimer ce pointage ?'))) return; return tsDo(() => rsCall(`/api/timesheets/entries/${b.dataset.id}`, {method: 'DELETE'})); }
  if (a === 'jd') { tsReadForm(); ts.form.job_done = b.dataset.v === '1'; return tsDraw(); }
  if (a === 'rej') { const why = await tsAsk(t('Renvoyer le pointage'), t('Motif (obligatoire) : ce que le mécanicien doit corriger'), t('Renvoyer')); if (!why) return; return tsDo(() => rsCall(`/api/timesheets/entries/${b.dataset.id}/reject`, {method: 'POST', body: JSON.stringify({reason: why})})); }
  if ((a === 'val' || a === 'valall') && b.hasAttribute('data-hold') && !b._held) { ts.msg = 'Maintenez le bouton enfoncé pour valider.'; return tsDraw(); }
  if (a === 'hide') return tsDo(() => rsCall(`/api/timesheets/entries/${b.dataset.id}/client-visibility?hidden=${b.dataset.v === '1'}`, {method: 'POST'}));
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
  if (a === 'mk') { const s = ts.sugg[+b.dataset.i]; return tsDo(async () => { for (const n of (s.natures || [''])) await rsCall('/api/timesheets/jobs', {method: 'POST', body: JSON.stringify({kind: s.kind, title: s.title, nature: n, template_id: s.kind === 'atelier' ? ((tsMatchTpl({nature: s.nature, bu: s.bu}) || {}).id || '') : '', bu: s.bu, assignment: s.assignment || 'autre', vehicle: s.vehicle, event: s.event})}); ts.sugg.splice(+b.dataset.i, 1); }); }
  if (a === 'newjob') { ts.jobForm = {kind: 'atelier', nature: '', template: '', bu: ts.me.bus[0] || 'CARS', title: '', vehicle: '', event: ''}; if (!ts.evs) { ts.evs = []; rsCall('/api/timesheets/events').then(j => { ts.evs = j.events; if (j.unavailable) ts.msg = j.unavailable; tsReadJob(); tsDraw(); }).catch(() => {}); }
    if (!ts.veh) { ts.veh = []; rsCall('/api/timesheets/vehicles').then(j => { ts.veh = j.vehicles; if (j.unavailable) ts.msg = j.unavailable; tsReadJob(); tsDraw(); }).catch(() => {}); } return tsDraw(); }
  if (a === 'editjob') {
    const j = ts.jobsAll.find(x => x.id === b.dataset.id); if (!j) return;
    ts.jobForm = {id: j.id, open: j.open, template: '', hasChecklist: !!j.checklist, tplName: j.checklist ? j.checklist.template_name : '', progress: j.progress, assignment: j.assignment, kind: j.kind, nature: j.nature || '', bu: j.bu, title: j.kind === 'background' || j.nature === 'custom' ? (j.nature === 'custom' ? j.title.replace(/ \/ [^/]*$/, '') : j.title) : '', vehicle: j.vehicle ? (j.vehicle.id || '__keep') : '', vehicleName: j.vehicle ? j.vehicle.name : '', event: j.event ? j.event.title : ''};
    if (!ts.evs) { ts.evs = []; rsCall('/api/timesheets/events').then(r => { ts.evs = r.events; tsReadJob(); tsDraw(); }).catch(() => {}); }
    if (!ts.veh) { ts.veh = []; rsCall('/api/timesheets/vehicles').then(r => { ts.veh = r.vehicles; tsReadJob(); tsDraw(); }).catch(() => {}); }
    tsDraw(); return document.getElementById('ts-view').querySelector('.ts-form').scrollIntoView();
  }
  if (a === 'togl') { ts.openJobs.has(b.dataset.id) ? ts.openJobs.delete(b.dataset.id) : ts.openJobs.add(b.dataset.id); return tsDraw(); }
  if (a === 'newtpl') { ts.tplForm = {id: null, name: '', bu: ts.me.bus.length === 1 ? ts.me.bus[0] : 'CARS', natures: [], sections: [{title: '', lines: []}]}; return tsDraw(); }
  if (a === 'edittpl' || a === 'duptpl') { const t = ts.tpls.find(x => x.id === b.dataset.id); if (!t) return; ts.tplForm = {id: a === 'edittpl' ? t.id : null, name: a === 'duptpl' ? t.name + ' (copie)' : t.name, bu: t.bu, natures: t.natures.slice(), sections: t.sections.map(s => ({title: s.title, lines: s.lines.map(l => ({text: l.text, note: l.note || ''}))}))}; tsDraw(); return document.querySelector('#ts-view .ts-form').scrollIntoView(); }
  if (a === 'canceltpl') { ts.tplForm = null; return tsDraw(); }
  if (['secadd', 'secdel', 'secup', 'secdown'].includes(a)) { tsReadTpl(); const f = ts.tplForm, i = +b.dataset.i;
    if (a === 'secadd') f.sections.push({title: '', lines: []}); else if (a === 'secdel') f.sections.splice(i, 1); else { const j = a === 'secup' ? i - 1 : i + 1; if (j >= 0 && j < f.sections.length) [f.sections[i], f.sections[j]] = [f.sections[j], f.sections[i]]; }
    return tsDraw(); }
  if (a === 'savetpl') { tsReadTpl(); const f = ts.tplForm; return tsDo(async () => { await rsCall(f.id ? `/api/timesheets/templates/${f.id}` : '/api/timesheets/templates', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify({name: f.name, bu: f.bu, natures: f.natures, sections: f.sections.filter(s => s.title.trim() || s.lines.length).map(s => ({title: s.title || 'Divers', lines: s.lines}))})}); ts.tplForm = null; }); }
  if (a === 'deltpl') { if (!confirm(t('Supprimer ce modèle ? Les jobs déjà créés gardent leur liste.'))) return; return tsDo(() => rsCall(`/api/timesheets/templates/${b.dataset.id}`, {method: 'DELETE'})); }
  if (a === 'canceljob') { ts.jobForm = null; return tsDraw(); }
  if (a === 'savejob') {
    tsReadJob(); const f = ts.jobForm, v = f.vehicle === '__keep' ? {id: '', name: f.vehicleName} : (ts.veh || []).find(x => x.id === f.vehicle);
    return tsDo(async () => { await rsCall(f.id ? `/api/timesheets/jobs/${f.id}` : '/api/timesheets/jobs', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify({open: f.open !== false, assignment: f.assignment || 'autre', kind: f.kind, title: f.title, template_id: f.kind === 'atelier' ? (f.template || '') : '', nature: f.kind === 'background' ? '' : f.nature, bu: f.bu, vehicle: f.kind === 'atelier' && v ? {id: v.id, name: v.name} : null, event: f.kind !== 'background' && f.nature !== 'custom' && f.event ? {id: ((ts.evs || []).find(x => x.name === f.event) || {}).id || '', title: f.event} : null})}); ts.jobForm = null; });
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
  if (el.matches && el.matches('[data-f="job_id"]')) { tsReadForm(); ts.form.lines = []; tsDraw(); return; }
  if (el.matches && el.matches('[data-t-nat]')) { tsReadTpl(); tsDraw(); return; }
  if (el.matches && el.matches('[data-j="kind"]')) { tsReadJob(); tsDraw(); }
  if (el.matches && el.matches('[data-j="event"]')) { tsReadJob(); const v = (ts.evs || []).find(x => x.name === ts.jobForm.event); if (v && v.bu && tsBuOpts(ts.me).includes(v.bu)) ts.jobForm.bu = v.bu; tsDraw(); }
  if (el.matches && el.matches('[data-j="nature"]')) { tsReadJob(); const f = ts.jobForm; if (f.kind === 'atelier' && !f.hasChecklist) { const m = tsMatchTpl(f); if (m && !f.template) f.template = m.id; } tsDraw(); }
  if (el.matches && el.matches('[data-j="vehicle"]')) { tsReadJob(); const v = (ts.veh || []).find(x => x.id === ts.jobForm.vehicle); if (v && v.bu && !ts.jobForm.event && tsBuOpts(ts.me).includes(v.bu)) ts.jobForm.bu = v.bu; tsDraw(); }
});

// ---- Visionneuse de photos : s'ouvre dans la page (pas d'onglet), flèches et balayage pour parcourir les photos du même pointage ----------------------
let tsLb = null;
function tsLbShow(i) {
  const L = tsLb; L.i = (i + L.urls.length) % L.urls.length;
  L.el.querySelector('img').src = L.urls[L.i]; L.el.querySelector('.lb-n').textContent = L.urls.length > 1 ? `${L.i + 1} / ${L.urls.length}` : '';
  L.el.classList.toggle('one', L.urls.length < 2);
}
function tsLbOpen(urls, i) {
  tsLbClose();
  const el = document.createElement('div'); el.className = 'ts-lb'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', 'Photo');
  el.innerHTML = '<button type="button" class="lb-x" aria-label="Fermer" title="Fermer">✕</button><button type="button" class="lb-p" aria-label="Photo précédente" title="Photo précédente">‹</button><img alt="Photo"><button type="button" class="lb-s" aria-label="Photo suivante" title="Photo suivante">›</button><span class="lb-n"></span>';
  document.body.appendChild(el); tsLb = {el, urls, i}; tsLbShow(i);
  let x0 = null;
  el.addEventListener('click', e => { if (e.target.closest('.lb-x') || e.target === el || e.target.tagName === 'IMG') tsLbClose(); else if (e.target.closest('.lb-p')) tsLbShow(tsLb.i - 1); else if (e.target.closest('.lb-s')) tsLbShow(tsLb.i + 1); });
  let y0 = 0;
  el.addEventListener('touchstart', e => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, {passive: true});
  el.addEventListener('touchend', e => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0; x0 = null; if (dy > 90 && Math.abs(dx) < 60) tsLbClose(); else if (Math.abs(dx) > 50) tsLbShow(tsLb.i + (dx < 0 ? 1 : -1)); });
}
function tsLbClose() { if (tsLb) { tsLb.el.remove(); tsLb = null; } }
document.addEventListener('click', e => {
  const im = e.target.closest && e.target.closest('#ts-view img.ts-ph'); if (!im) return;
  const all = [...(im.closest('.ts-att') || im.parentElement).querySelectorAll('img.ts-ph')]; tsLbOpen(all.map(x => x.src), all.indexOf(im));
});
document.addEventListener('keydown', e => { if (!tsLb) return; if (e.key === 'Escape') tsLbClose(); else if (e.key === 'ArrowLeft') tsLbShow(tsLb.i - 1); else if (e.key === 'ArrowRight') tsLbShow(tsLb.i + 1); });
window.addEventListener('hashchange', tsLbClose);

// Photo introuvable (fichier supprimé) : message à la place de l'image cassée
document.addEventListener('error', e => { const im = e.target; if (im && im.tagName === 'IMG' && im.classList.contains('ts-ph') && im.closest('#ts-view') && /\/attachments\//.test(im.src)) { const m = document.createElement('span'); m.className = 'ts-n'; m.textContent = t('Photo supprimée'); im.replaceWith(m); } }, true);

document.addEventListener('input', e => { if (e.target.closest && e.target.closest('#ts-view .ts-form')) { clearTimeout(tsReadForm.t); tsReadForm.t = setTimeout(tsReadForm, 400); } });

// Dialogue de saisie d'un motif (renvoi d'un pointage)
function tsAsk(title, label, ok) {
  return new Promise(res => {
    const el = document.createElement('div'); el.className = 'ts-dlg';
    el.innerHTML = `<div class="ts-dlgbox" role="dialog" aria-label="${esc(title)}"><h4>${esc(title)}</h4><label class="sdfield"><span>${esc(label)}</span><textarea class="sdin" rows="4" maxlength="500"></textarea></label><div class="sdbar"><button type="button" class="primary" data-k="ok">${esc(ok)}</button><button type="button" data-k="no">${esc(t('Annuler'))}</button></div></div>`;
    document.body.appendChild(el); const ta = el.querySelector('textarea'); ta.focus();
    const end = v => { el.remove(); res(v); };
    el.addEventListener('click', e => { const k = e.target.dataset && e.target.dataset.k; if (k === 'ok') { if (ta.value.trim().length < 3) { ta.focus(); return; } end(ta.value.trim()); } else if (k === 'no' || e.target === el) end(null); });
  });
}
// Appui long (écrans tactiles) : valider demande de maintenir le bouton, pour éviter une validation par erreur
(() => {
  let tm = null, btn = null;
  const stop = () => { clearTimeout(tm); if (btn) btn.classList.remove('holding'); btn = null; };
  document.addEventListener('pointerdown', e => { const b = e.target.closest && e.target.closest('[data-hold]'); if (!b) return; btn = b; b.classList.add('holding'); tm = setTimeout(() => { b._held = true; stop(); b.click(); setTimeout(() => { b._held = false; }, 300); }, 700); });
  ['pointerup', 'pointerleave', 'pointercancel', 'scroll'].forEach(t => document.addEventListener(t, stop, true));
  document.addEventListener('contextmenu', e => { if (e.target.closest && e.target.closest('[data-hold]')) e.preventDefault(); });
})();
