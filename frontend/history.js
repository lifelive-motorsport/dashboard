// Administrer › Historique (Super User) : relevé des modifications des données sensibles (modèles, roulages, pièces, fiches voiture, clients, jobs…) sur les derniers jours, avec
// l'état avant / après et un bouton « Restaurer » qui remet l'objet dans son état d'avant la modification (ou le recrée s'il a été supprimé). Données : /api/admin/history.
const hi = {entries: null, kinds: {}, keep: 30, days: 7, kind: '', q: '', detail: null, msg: null, ok: false, loading: false};
const HI_ACTION = {create: 'Création', update: 'Modification', delete: 'Suppression'};
function historyBlocks() { return [{static: '<section class="block" data-bid="hi"><div id="hi-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function hiLoad() {
  hi.loading = true; hiDraw();
  try {
    const j = await rsCall(`/api/admin/history?days=${hi.days}&kind=${encodeURIComponent(hi.kind)}&q=${encodeURIComponent(hi.q)}`);
    hi.entries = j.entries; hi.kinds = j.kinds; hi.keep = j.keep_days;
  } catch (e) { hi.msg = e.message; hi.ok = false; hi.entries = hi.entries || []; }
  hi.loading = false; hiDraw();
}
const hiVal = v => { const s = v === undefined ? '—' : typeof v === 'string' ? v : JSON.stringify(v); return s.length > 400 ? s.slice(0, 400) + '…' : s; };
function hiDetail() {
  const d = hi.detail; if (!d) return '';
  const b = d.before || {}, a = d.after || {};
  const rows = (d.action === 'update' ? d.fields : []).map(f => `<tr><th>${esc(f)}</th><td><pre class="hi-pre">${esc(hiVal(b[f]))}</pre></td><td><pre class="hi-pre">${esc(hiVal(a[f]))}</pre></td></tr>`);
  const whole = d.action === 'create' ? `<p class="na">${esc(tx('Objet créé : restaurer le supprime.'))}</p>` : d.action === 'delete' ? `<p class="na">${esc(tx('Objet supprimé : restaurer le recrée tel qu’il était.'))}</p>` : '';
  return `<div class="note rd-form"><b>${esc(tx(d.kind))} · ${esc(d.label)}</b> <small class="na">${esc(new Date(d.at).toLocaleString(LOCALE()))} · ${esc(d.by)}</small>${d.stale ? `<p class="neg">⚠ ${esc(tx('Cet objet a encore été modifié depuis : la restauration reprend l’état d’avant CETTE modification.'))}</p>` : ''}${whole}
    ${rows.length ? `<table class="sdtable"><thead><tr><th>${esc(tx('Champ'))}</th><th>${esc(tx('Avant'))}</th><th>${esc(tx('Après'))}</th></tr></thead><tbody>${rows.join('')}</tbody></table>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-hi="restore" data-id="${esc(d.id)}">↩ ${esc(tx('Restaurer l’état d’avant'))}</button><button type="button" data-hi="close">${esc(tx('Fermer'))}</button></div></div>`;
}
function hiDraw() {
  const el = document.getElementById('hi-view'); if (!el) return;
  if (hi.entries == null) { el.innerHTML = '<p class="na loading">Chargement…</p>'; return; }
  const bar = `<div class="sdbar"><select class="sdin" id="hi-days">${[[1, '24 h'], [7, '7 jours'], [30, '30 jours']].filter(([n]) => n <= hi.keep).map(([n, l]) => `<option value="${n}"${hi.days === n ? ' selected' : ''}>${esc(tx(l))}</option>`).join('')}</select>
    <select class="sdin" id="hi-kind"><option value="">${esc(tx('Tous les objets'))}</option>${Object.entries(hi.kinds).map(([k, l]) => `<option value="${esc(k)}"${hi.kind === k ? ' selected' : ''}>${esc(tx(l))}</option>`).join('')}</select>
    <input type="search" class="sdin rd-q" id="hi-q" placeholder="${esc(tx('Rechercher (objet, personne)…'))}" value="${esc(hi.q)}" autocomplete="off">${hi.loading ? '<small class="na loading">Chargement…</small>' : ''}</div>`;
  const msg = hi.msg ? `<p class="${hi.ok ? 'na' : 'neg'}">${esc(hi.msg)}</p>` : '';
  const rows = hi.entries.map(h => `<tr><td>${esc(new Date(h.at).toLocaleString(LOCALE()))}</td><td>${esc(h.by)}</td><td>${esc(tx(HI_ACTION[h.action] || h.action))}${h.restored_from ? ` <small class="na">(${esc(tx('restauration'))})</small>` : ''}</td><td><b>${esc(h.label || h.doc_id)}</b><br><small class="na">${esc(tx(h.kind))}</small></td>
    <td><small class="na">${esc(h.fields.slice(0, 6).join(', '))}${h.fields.length > 6 ? '…' : ''}</small></td><td class="rd-acts"><button type="button" class="mini" data-hi="view" data-id="${esc(h.id)}">${esc(tx('Voir'))}</button></td></tr>`);
  el.innerHTML = `<p class="na">${esc(tx('Chaque modification des modèles, roulages, pièces, fiches voiture, clients et jobs est relevée ; vous pouvez remettre un objet dans son état d’avant. Conservation :'))} ${hi.keep} ${esc(tx('jours'))}. ${esc(tx('Les fichiers (photos, PDF) ne sont pas versionnés.'))}</p>${bar}${msg}${hiDetail()}${rows.length ? table(['Quand', 'Qui', 'Action', 'Objet', 'Champs modifiés', ''], rows) : `<p class="na">${esc(tx('Aucune modification sur cette période.'))}</p>`}`;
  if (typeof i18nNode === 'function' && LANG === 'en') i18nNode(el);
}
document.addEventListener('change', e => {
  if (!document.getElementById('hi-view')) return;
  if (e.target.id === 'hi-days') { hi.days = +e.target.value; hiLoad(); } else if (e.target.id === 'hi-kind') { hi.kind = e.target.value; hiLoad(); }
});
let hiTimer = null;
document.addEventListener('input', e => { if (e.target.id === 'hi-q' && document.getElementById('hi-view')) { hi.q = e.target.value; clearTimeout(hiTimer); hiTimer = setTimeout(async () => { await hiLoad(); const n = document.getElementById('hi-q'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }, 350); } });
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-hi]'); if (!b || !document.getElementById('hi-view')) return;
  try {
    if (b.dataset.hi === 'view') { hi.detail = await rsCall('/api/admin/history/' + encodeURIComponent(b.dataset.id)); hi.msg = null; hiDraw(); window.scrollTo({top: 0}); }
    else if (b.dataset.hi === 'close') { hi.detail = null; hiDraw(); }
    else if (b.dataset.hi === 'restore') {
      if (!confirm(tx('Remettre cet objet dans son état d’avant la modification ?'))) return;
      await rsCall(`/api/admin/history/${encodeURIComponent(b.dataset.id)}/restore`, {method: 'POST'}); hi.detail = null; hi.msg = tx('Objet restauré. La restauration figure elle-même au relevé.'); hi.ok = true; hiLoad();
    }
  } catch (err) { hi.msg = err.message; hi.ok = false; hiDraw(); }
});
