// Administrer › Accès clients (Super User) : fiches clients (adresses e-mail autorisées, voitures du Garage), envoi d'un lien de connexion, journal des connexions.
// Les clients ouvrent ensuite la page autonome client.html (voir client.js) ; données : /api/admin/clients (backend/app/clients.py).
const ca = {list: null, cars: [], audit: [], form: null, q: '', msg: null, ok: false, loading: false, saving: false};
const caBlank = () => ({id: null, name: '', emails: '', cars: [], active: true, note: ''});
function clientsBlocks() { return [{static: '<section class="block" data-bid="ca"><div id="ca-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function caLoad() {
  ca.loading = true; caDraw();
  try { const j = await rsCall('/api/admin/clients'); ca.list = j.clients; ca.cars = j.cars; ca.audit = j.audit; } catch (e) { ca.msg = e.message; ca.ok = false; ca.list = ca.list || []; }
  ca.loading = false; caDraw();
}
const caAct = {link_sent: 'Lien envoyé', login: 'Connexion', login_refused: 'Lien refusé', link_refused: 'Demande refusée (adresse inconnue)', link_throttled: 'Demande bloquée (trop de liens)'};
function caFormHtml() {
  const f = ca.form; if (!f) return '';
  const q = ca.q.trim().toLowerCase(), cars = ca.cars.filter(c => !q || c.name.toLowerCase().includes(q) || f.cars.includes(c.key));
  return `<div class="note rd-form"><b>${esc(tx(f.id ? 'Modifier le client' : 'Nouveau client'))}</b>
    <div class="sdgrid"><label class="sdfield"><span>Nom du client</span><input class="sdin" data-ca-f="name" value="${esc(f.name)}" maxlength="100"></label>
    <label class="sdfield"><span>Adresses e-mail autorisées (une par ligne)</span><textarea class="sdin" data-ca-f="emails" rows="3" placeholder="pilote@exemple.com">${esc(f.emails)}</textarea></label></div>
    <label class="chk"><input type="checkbox" data-ca-f="active" ${f.active ? 'checked' : ''}> ${esc(tx('Accès actif'))}</label>
    <div class="sdfield"><span>Voitures visibles par ce client</span><input class="sdin" id="ca-q" placeholder="${esc(tx('Rechercher une voiture…'))}" value="${esc(ca.q)}" style="max-width:300px">
    <div class="ca-cars">${cars.map(c => `<label class="chk"><input type="checkbox" data-ca-car="${esc(c.key)}" ${f.cars.includes(c.key) ? 'checked' : ''}> ${esc(c.name)}${c.odoo ? '' : ` <small class="na" title="${esc(tx('Sans compte analytique Odoo, les jobs de cette voiture ne sont retrouvés que par son nom.'))}">⚠ ${esc(tx('non reliée à Odoo'))}</small>`}${c.archived ? ` <small class="na">(${esc(tx('archivée'))})</small>` : ''}</label>`).join('')}</div></div>
    <label class="sdfield"><span>Note interne (jamais montrée au client)</span><input class="sdin" data-ca-f="note" value="${esc(f.note)}" maxlength="300"></label>
    <div class="sdbar"><button type="button" class="primary" data-ca="save" ${f.name.trim() && !ca.saving ? '' : 'disabled'}>${esc(tx(ca.saving ? 'Enregistrement…' : 'Enregistrer'))}</button><button type="button" data-ca="cancel">${esc(tx('Annuler'))}</button>${ca.msg && !ca.ok ? `<span class="neg">${esc(ca.msg)}</span>` : ''}</div></div>`;
}
function caDraw() {
  const el = document.getElementById('ca-view'); if (!el) return;
  const msg = ca.msg && (ca.ok || !ca.form) ? `<p class="${ca.ok ? 'na' : 'neg'}">${esc(ca.msg)}</p>` : '';
  const rows = (ca.list || []).map(c => `<tr class="${c.active ? '' : 'gone'}"><td class="prod"><b>${esc(c.name)}</b>${c.active ? '' : ` <span class="rd-chip">${esc(tx('Désactivé'))}</span>`}${c.note ? `<br><small class="na">${esc(c.note)}</small>` : ''}</td>
    <td>${c.emails.map(e => `<div>${esc(e)} <button type="button" class="mini" data-ca="link" data-id="${esc(c.id)}" data-e="${esc(e)}" title="${esc(tx('Envoyer un lien de connexion à cette adresse'))}">✉</button>${c.last_login[e] ? ` <small class="na">${esc(tx('dernière connexion'))} ${fmtDate(c.last_login[e].slice(0, 10))}</small>` : ''}</div>`).join('') || '<small class="na">—</small>'}</td>
    <td>${c.cars.map(x => esc(x.name) + (x.odoo ? '' : ' ⚠')).join('<br>') || '<small class="na">—</small>'}</td>
    <td class="rd-acts"><button type="button" class="mini" data-ca="edit" data-id="${esc(c.id)}" title="${esc(tx('Modifier'))}">✎</button><button type="button" class="mini danger" data-ca="del" data-id="${esc(c.id)}" title="${esc(tx('Supprimer ce client'))}">🗑</button></td></tr>`);
  const list = ca.list == null ? `<p class="na loading">Chargement…</p>` : ca.list.length ? table(['Client', 'Adresses e-mail', 'Voitures', ''], rows) : `<p class="na">${esc(tx('Aucun client : créez-en un, ajoutez ses adresses e-mail et ses voitures.'))}</p>`;
  const log = ca.audit.length ? `<h4 class="sub">${esc(tx('Journal des connexions'))}</h4>${table(['Quand', 'Adresse', 'Événement'], ca.audit.slice(0, 30).map(a => `<tr><td>${esc(new Date(a.at).toLocaleString(LOCALE()))}</td><td>${esc(a.email)}</td><td>${esc(tx(caAct[a.action] || a.action))}</td></tr>`))}` : '';
  el.innerHTML = `<p class="na">${esc(tx('Les clients ouvrent la page client.html avec un lien de connexion reçu par e-mail (valable 15 minutes, à usage unique) et voient, en lecture seule, leurs voitures du Garage, leurs documents, leurs roulages et les jobs avec leurs pointages validés (sans nom de mécanicien, sans coût).'))}</p>
    <div class="sdbar"><button type="button" class="primary" data-ca="new">＋ ${esc(tx('Nouveau client'))}</button>${ca.loading && ca.list ? '<small class="na loading">Chargement…</small>' : ''}</div>${msg}${caFormHtml()}${list}${log}`;
}
document.addEventListener('input', e => {
  const t = e.target; if (!document.getElementById('ca-view')) return;
  if (t.id === 'ca-q') { ca.q = t.value; const pos = t.selectionStart; caDraw(); const n = document.getElementById('ca-q'); if (n) { n.focus(); n.setSelectionRange(pos, pos); } return; }
  if (t.dataset.caF !== undefined && ca.form) { ca.form[t.dataset.caF] = t.type === 'checkbox' ? t.checked : t.value; const b = document.querySelector('[data-ca=save]'); if (b) b.disabled = !ca.form.name.trim(); }
});
document.addEventListener('change', e => {
  const t = e.target; if (!document.getElementById('ca-view') || !ca.form) return;
  if (t.dataset.caCar) { const k = t.dataset.caCar; ca.form.cars = t.checked ? [...new Set([...ca.form.cars, k])] : ca.form.cars.filter(x => x !== k); }
  else if (t.dataset.caF === 'active') ca.form.active = t.checked;
});
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-ca]'); if (!b || !document.getElementById('ca-view')) return;
  const a = b.dataset.ca, id = b.dataset.id;
  try {
    if (a === 'new') { ca.form = caBlank(); ca.msg = null; ca.q = ''; return caDraw(); }
    if (a === 'edit') { const c = ca.list.find(x => x.id === id); ca.form = {id: c.id, name: c.name, emails: c.emails.join('\n'), cars: c.cars.map(x => x.key), active: c.active, note: c.note || ''}; ca.msg = null; ca.q = ''; return caDraw(); }
    if (a === 'cancel') { ca.form = null; ca.msg = null; return caDraw(); }
    if (a === 'save') {
      const f = ca.form; ca.saving = true; ca.msg = null; caDraw();
      try {
        await rsCall(f.id ? '/api/admin/clients/' + encodeURIComponent(f.id) : '/api/admin/clients', {method: f.id ? 'PUT' : 'POST', body: JSON.stringify({name: f.name.trim(), emails: f.emails.split(/[\s,;]+/).filter(Boolean), cars: f.cars, active: f.active, note: f.note})});
        ca.form = null; ca.saving = false; ca.msg = 'Client enregistré.'; ca.ok = true; return caLoad();
      } catch (err) { ca.saving = false; ca.msg = err.message; ca.ok = false; return caDraw(); }
    }
    if (a === 'del') { const c = ca.list.find(x => x.id === id); if (!confirm(`${tx('Supprimer le client')} « ${c.name} » ? ${tx('Ses accès sont coupés immédiatement.')}`)) return; await rsCall('/api/admin/clients/' + encodeURIComponent(id), {method: 'DELETE'}); ca.msg = 'Client supprimé.'; ca.ok = true; return caLoad(); }
    if (a === 'link') { const j = await rsCall(`/api/admin/clients/${encodeURIComponent(id)}/send-link`, {method: 'POST', body: JSON.stringify({email: b.dataset.e})}); ca.msg = j.sent ? `${tx('Lien de connexion envoyé à')} ${b.dataset.e}.` : 'Lien non envoyé (limite de 5 liens par heure atteinte, ou adresse inactive).'; ca.ok = j.sent; return caLoad(); }
  } catch (err) { ca.msg = err.message; ca.ok = false; ca.saving = false; caDraw(); }
});
