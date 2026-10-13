// Consigner › Congés : soldes, demande (journées et demi-journées), suivi, et validation par le chef d'atelier (mécaniciens de son équipe) ou le Managing Director (les autres).
// Données : /api/leaves (backend/app/leaves.py). S'appuie sur les outils de dates de planning.js / events.js et sur tsAsk (timesheets.js).
const LV_TYPES = [{id: 'paid', label: 'Congés payés', balance: true}, {id: 'comp', label: 'Jours de compensation', balance: true}, {id: 'extra', label: 'Congé extra-légal', balance: true},
                  {id: 'recup', label: 'Récupération de jour férié', balance: true}, {id: 'sick', label: 'Congé maladie', balance: false}, {id: 'other', label: 'Autre congé (sans solde)', balance: false}];
let lv = {data: null, form: null, days: null, err: null, msg: null, busy: false};
const lvStatus = {pending: ['À approuver', ''], approved: ['Validé', 'done'], refused: ['Refusé', 'late'], cancelled: ['Annulé', 'absent']};
const lvDays = n => `${String(n).replace('.', LOCALE() === 'en-GB' ? '.' : ',')} ${n > 1 ? 'jours' : 'jour'}`;
const lvDate = iso => fmtDate(iso);

function leavesBlocks() { return [{static: '<section class="block" data-bid="lv"><div class="block-head"><h3>Congés</h3></div><div class="block-body" id="lv-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function lvLoad() {
  lv.err = null; lvDraw();
  try { lv.data = await rsCall('/api/leaves/me'); } catch (e) { lv.err = e.message; }
  lvDraw();
}

function lvBlank() { const d = plToday(); return {id: null, type: 'paid', start: d, end: d, start_half: 'full', end_half: 'full', comment: '', proofs: []}; }
const lvDateField = (f, iso) => `<span class="datef"><input class="sdin lv-d" data-k="${f}" value="${iso ? fmtDate(iso) : ''}" placeholder="jj/mm/aaaa" inputmode="numeric" maxlength="10" autocomplete="off"><button type="button" class="lv-cal" data-k="${f}" aria-label="Calendrier" title="Calendrier"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1.5v3M11 1.5v3"/></svg></button><input type="date" class="lv-dp" data-k="${f}" value="${iso || ''}" tabindex="-1" aria-hidden="true"></span>`;

function lvFormHtml() {
  const f = lv.form, ty = lv.data.types.find(t => t.id === f.type), needProof = ty && ty.proof_over_one_day && (lv.days || 0) > 1;
  const proofs = f.proofs.map((p, i) => `<span class="tagchip">${esc(p.name)} <button type="button" class="mini" data-lv="rmproof" data-i="${i}" aria-label="Retirer">✕</button></span>`).join(' ');
  return `<div class="ts-form"><h4>${f.id ? 'Modifier la demande' : 'Demander un congé'}</h4>
    <label class="sdfield"><span>Type de congé</span><select class="sdin" data-k="type">${lv.data.types.map(t => `<option value="${t.id}"${f.type === t.id ? ' selected' : ''}>${esc(t.label)}</option>`).join('')}</select></label>
    <div class="sdgrid"><label class="sdfield"><span>Du</span>${lvDateField('start', f.start)}</label><label class="sdfield"><span>Début</span><select class="sdin" data-k="start_half"><option value="full"${f.start_half === 'full' ? ' selected' : ''}>Journée entière</option><option value="pm"${f.start_half === 'pm' ? ' selected' : ''}>À partir de l’après-midi</option></select></label></div>
    <div class="sdgrid"><label class="sdfield"><span>Au</span>${lvDateField('end', f.end)}</label><label class="sdfield"><span>Fin</span><select class="sdin" data-k="end_half"><option value="full"${f.end_half === 'full' ? ' selected' : ''}>Journée entière</option><option value="am"${f.end_half === 'am' ? ' selected' : ''}>Jusqu’à midi</option></select></label></div>
    <p class="lv-days">${lv.days == null ? '' : lv.days ? `<b>${lvDays(lv.days)}</b> <span class="na">ouvrables</span>` : '<span class="neg">Aucun jour ouvré dans cette période</span>'}</p>
    ${needProof || f.proofs.length ? `<div class="sdfield"><span>Justificatif${needProof ? ' (obligatoire)' : ''}</span><div class="ts-media"><label class="btn">📎 Ajouter un certificat<input type="file" accept="image/*,application/pdf" hidden data-lv-file></label>${proofs}</div></div>` : ''}
    <label class="sdfield"><span>Commentaire (facultatif)</span><textarea class="sdin" data-k="comment" rows="2" maxlength="500">${esc(f.comment)}</textarea></label>
    <div class="sdbar"><button type="button" class="primary" data-lv="send"${lv.busy ? ' disabled' : ''}>Envoyer la demande</button><button type="button" data-lv="cancelform">Annuler</button></div></div>`;
}

function lvReqHtml(r, decide) {
  const [lab, cls] = lvStatus[r.status] || [r.status, ''], coarse = typeof tsCoarse === 'function' && tsCoarse();
  const acts = decide ? `<button type="button" class="okbtn" data-lv="approve" data-id="${r.id}"${coarse ? ' data-hold' : ''}>${coarse ? 'Maintenir pour approuver' : 'Approuver'}</button><button type="button" data-lv="refuse" data-id="${r.id}">Refuser</button>`
    : r.mine && r.status === 'pending' ? `<button type="button" data-lv="edit" data-id="${r.id}">Modifier</button><button type="button" class="danger" data-lv="cancel" data-id="${r.id}">Supprimer</button>`
    : (r.mine && r.status === 'approved' && r.start > plToday()) || (r.can_decide && r.status === 'approved') ? `<button type="button" class="danger" data-lv="cancel" data-id="${r.id}">Annuler le congé</button>` : '';
  const proofs = (r.proof_files || (r.proofs || []).map(id => ({id}))).map((p, i) => p.expired ? '<span class="ts-n">📎 Justificatif supprimé</span>' : `<a href="/api/leaves-proofs/${p.id}" target="_blank" rel="noopener">📎 Justificatif ${i + 1}</a>`).join(' ');
  return `<div class="ts-entry"><div class="ts-top"><b>${decide || !r.mine ? esc(r.name) + ' · ' : ''}${esc(t(r.type_label))}</b><span class="ts-st ${cls}">${esc(t(lab))}</span><span class="ts-min">${lvDays(r.days)}</span></div>
    <div class="ts-sub">${esc(lvDate(r.start))}${r.start_half === 'pm' ? ' (' + t('après-midi') + ')' : ''} → ${esc(lvDate(r.end))}${r.end_half === 'am' ? ' (' + t('matin') + ')' : ''}${r.comment ? ' — ' + esc(r.comment) : ''}</div>
    ${r.status === 'refused' && r.reason ? `<div class="ts-reason"><b>Motif :</b> ${esc(r.reason)}</div>` : ''}${r.calendar_error ? `<div class="ts-reason">${esc(t('Agenda « warnings » non mis à jour'))} : ${esc(r.calendar_error)}</div>` : ''}
    ${proofs ? `<div class="ts-sub">${proofs}</div>` : ''}${acts ? `<div class="ts-act">${acts}</div>` : ''}</div>`;
}

function lvDraw() {
  const v = document.getElementById('lv-view'); if (!v) return;
  const d = lv.data;
  if (lv.err) v.innerHTML = `<p class="err">${esc(lv.err)}</p>`;
  else if (!d) v.innerHTML = '<p class="na loading">Chargement…</p>';
  else if (!d.person.linked) v.innerHTML = '<p class="na">Votre adresse Google n’est liée à aucune fiche du staff : demandez au Super User de la renseigner (Planifier › Ressources › Staff interne).</p>';
  else {
    const bal = d.balances.map(b => `<div><small>${esc(t(b.label))}</small><b>${lvDays(b.remaining)}</b><small>${b.used ? `${esc(t('pris'))} ${b.used} · ` : ''}${esc(t('alloués'))} ${b.allocated}${b.pending ? ` · ${esc(t('en attente'))} ${b.pending}` : ''}</small></div>`).join('');
    const dec = d.to_decide.length ? `<div class="block-head"><h3>Demandes à valider</h3></div>${d.to_decide.map(r => lvReqHtml(r, true)).join('')}` : '';
    const up = d.upcoming.length ? `<div class="block-head"><h3>Absences à venir</h3></div>${d.upcoming.map(r => lvReqHtml(r, false)).join('')}` : '';
    v.innerHTML = (lv.msg ? `<p class="ts-msg">${esc(lv.msg)}</p>` : '') + dec
      + `<div class="ts-kpis">${bal}</div>` + (lv.form ? lvFormHtml() : '<div class="sdbar ts-add"><button type="button" class="primary" data-lv="new">+ Demander un congé</button></div>')
      + `<div class="block-head"><h3>Mes demandes</h3></div>${d.requests.length ? d.requests.map(r => lvReqHtml(r, false)).join('') : '<p class="na">Aucune demande.</p>'}` + up;
  }
  if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(v);
}

function lvRead() { const v = document.getElementById('lv-view'); if (!v || !lv.form) return; v.querySelectorAll('select[data-k], textarea[data-k]').forEach(el => { lv.form[el.dataset.k] = el.value; }); }
async function lvPreview() {
  const f = lv.form; if (!f || !f.start || !f.end || f.end < f.start) { lv.days = null; return; }
  try { lv.days = (await rsCall(`/api/leaves/preview?start=${f.start}&end=${f.end}&start_half=${f.start_half}&end_half=${f.end_half}`)).days; } catch { lv.days = null; }
}
async function lvDo(fn) { lv.busy = true; try { await fn(); lv.msg = null; } catch (e) { lv.msg = e.message; } lv.busy = false; await lvLoad(); }

document.addEventListener('change', async e => {
  const el = e.target; if (!document.getElementById('lv-view') || !el.classList) return;
  if (el.classList.contains('lv-d') || el.classList.contains('lv-dp')) {
    const iso = el.classList.contains('lv-dp') ? el.value : peParse(el.value);
    if (!iso) { lv.msg = 'Date invalide : saisissez jj/mm/aaaa.'; return lvDraw(); }
    lvRead(); lv.form[el.dataset.k] = iso; if (el.dataset.k === 'start' && lv.form.end < iso) lv.form.end = iso; lv.msg = null; await lvPreview(); return lvDraw();
  }
  if (el.dataset.k && ['type', 'start_half', 'end_half'].includes(el.dataset.k)) { lvRead(); await lvPreview(); return lvDraw(); }
  if (el.hasAttribute('data-lv-file') && el.files[0]) {
    const f = el.files[0]; lvRead();
    try { const r = await fetch(`/api/leaves-proofs?filename=${encodeURIComponent(f.name)}`, {method: 'POST', headers: {...rsAuth(), 'Content-Type': f.type || 'application/octet-stream'}, body: f}), j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Envoi impossible'); lv.form.proofs.push({id: j.id, name: j.name}); lv.msg = null; } catch (err) { lv.msg = err.message; }
    lvDraw();
  }
});
document.addEventListener('click', async e => {
  if (!document.getElementById('lv-view')) return;
  const c = e.target.closest && e.target.closest('.lv-cal'); if (c) { const dp = document.querySelector(`.lv-dp[data-k="${c.dataset.k}"]`); if (dp) dpOpen(dp, c); return; }
  const b = e.target.closest && e.target.closest('[data-lv]'); if (!b) return; const a = b.dataset.lv;
  if (a === 'new') { lv.form = lvBlank(); lv.days = null; await lvPreview(); return lvDraw(); }
  if (a === 'cancelform') { lv.form = null; lv.msg = null; return lvDraw(); }
  if (a === 'rmproof') { lvRead(); lv.form.proofs.splice(+b.dataset.i, 1); return lvDraw(); }
  if (a === 'edit') { const r = lv.data.requests.find(x => x.id === b.dataset.id); if (!r) return; lv.form = {id: r.id, type: r.type, start: r.start, end: r.end, start_half: r.start_half, end_half: r.end_half, comment: r.comment || '', proofs: []}; await lvPreview(); lvDraw(); return document.querySelector('#lv-view .ts-form').scrollIntoView(); }
  if (a === 'send') { lvRead(); const f = lv.form; return lvDo(async () => { await rsCall(f.id ? `/api/leaves/${f.id}` : '/api/leaves', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify({type: f.type, start: f.start, end: f.end, start_half: f.start_half, end_half: f.end_half, comment: f.comment, proofs: f.proofs.map(p => p.id)})}); lv.form = null; }); }
  if (a === 'cancel') { if (!confirm(t('Annuler cette demande ?'))) return; return lvDo(() => rsCall(`/api/leaves/${b.dataset.id}`, {method: 'DELETE'})); }
  if (a === 'approve') { if (b.hasAttribute('data-hold') && !b._held) { lv.msg = 'Maintenez le bouton enfoncé pour approuver.'; return lvDraw(); } return lvDo(() => rsCall(`/api/leaves/${b.dataset.id}/approve`, {method: 'POST'})); }
  if (a === 'refuse') { const why = await tsAsk(t('Refuser la demande'), t('Motif du refus (obligatoire)'), t('Refuser')); if (!why) return; return lvDo(() => rsCall(`/api/leaves/${b.dataset.id}/refuse`, {method: 'POST', body: JSON.stringify({reason: why})})); }
});
