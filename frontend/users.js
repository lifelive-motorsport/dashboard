// Settings › Utilisateurs : le Super User crée les utilisateurs et choisit leur rôle. Chargé avant app.js.
let us = {loaded: false, users: [], fixed: [], domain: '', error: null, msg: null, dirty: false};
const US_ROLES = [['standard', 'Standard : consulte tout sauf les données du personnel'], ['admin', 'Administrateur : saisit les ajustements et voit le personnel'], ['xc', 'XC : uniquement les 6 pages XC']];
const US_LABEL = {super: 'Super User', admin: 'Administrateur', standard: 'Standard', xc: 'XC'};
const usAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};

function usersBlocks() { return [{static: '<section class="block" data-bid="users"><div class="block-head"><h3>Utilisateurs et rôles</h3></div><div class="block-body" id="users-view"><p class="na">Chargement…</p></div></section>'}]; }

async function loadUsers() {
  try {
    const r = await fetch('/api/users', {headers: usAuth()});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    us = {...us, ...j, loaded: true, error: null, dirty: false};
  } catch (e) { us.error = e.message; us.loaded = true; }
}

function drawUsers() {
  const el = document.getElementById('users-view'); if (!el) return;
  if (!us.loaded) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (us.error) { el.innerHTML = `<p class="neg">${esc(us.error)}</p>`; return; }
  const sel = (v, i) => `<select class="sdin us-role" data-i="${i}">${US_ROLES.map(([k, l]) => `<option value="${k}"${v === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  const rows = us.users.map((u, i) => `<tr><td>${esc(u.email)}${u.email.endsWith('@' + us.domain) ? '' : ' <small class="na">hors domaine</small>'}</td><td>${sel(u.role, i)}</td><td><input class="sdin us-note" data-i="${i}" value="${esc(u.note || '')}" placeholder="Nom, société…" maxlength="120"></td><td><button type="button" class="danger us-del" data-i="${i}">Retirer</button></td></tr>`).join('');
  el.innerHTML = `<p class="na">Vous êtes Super User : vous créez ici les utilisateurs et choisissez leur rôle. Une adresse enregistrée peut se connecter avec son compte Google, même hors du domaine @${esc(us.domain)}. Les modifications s’appliquent en moins d’une minute.</p>`
    + `<div class="table-wrap"><table class="prodtable"><thead><tr><th>Adresse e-mail</th><th>Rôle</th><th>Note</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="na">Aucun utilisateur enregistré.</td></tr>'}</tbody></table></div>`
    + `<div class="sdbar"><input class="sdin" id="us-new" type="email" placeholder="nouvelle.adresse@exemple.com" style="max-width:300px"><select class="sdin" id="us-newrole" style="max-width:360px">${US_ROLES.map(([k, l]) => `<option value="${k}"${k === 'xc' ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select><button type="button" id="us-add">Ajouter</button>`
    + `<button type="button" class="primary" id="us-save"${us.dirty ? '' : ' disabled'}>Enregistrer</button>${us.msg ? `<span class="${us.msg.ok ? 'pos' : 'neg'}">${esc(us.msg.t)}</span>` : us.dirty ? '<span class="na">Modifications non enregistrées</span>' : ''}</div>`
    + '<h4 class="sub">Comptes définis par la configuration du serveur (non modifiables ici)</h4>'
    + table(['Adresse e-mail', 'Rôle', 'Origine'], us.fixed.map(f => `<tr><td>${esc(f.email)}</td><td>${esc(US_LABEL[f.role] || f.role)}</td><td><small class="na">${esc(f.source)}</small></td></tr>`), 'prodtable')
    + '<small class="na">Rôles : <b>Standard</b> voit tout sauf les données du personnel et ne modifie rien ; <b>Administrateur</b> saisit les ajustements (MB, stock, hypothèses de simulation) et voit le personnel ; <b>XC</b> n’accède qu’à XC Webshop, Goldspeed EAX Webshop, Par événement (XC), Inventory et aux deux contrôles de marges, rien d’autre (le serveur refuse tout le reste). Un rôle choisi ici l’emporte sur la configuration du serveur. Le Super User, lui, ne se modifie pas depuis cet écran.</small>';
}
async function usSave() {
  us.msg = null;
  try {
    const r = await fetch('/api/users', {method: 'PUT', headers: {'Content-Type': 'application/json', ...usAuth()}, body: JSON.stringify({users: us.users.map(u => ({email: u.email, role: u.role, note: u.note || ''}))})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? 'Adresse invalide' : 'Erreur ' + r.status);
    us = {...us, ...j, dirty: false, msg: {ok: true, t: 'Enregistré'}};
  } catch (e) { us.msg = {ok: false, t: e.message}; }
  drawUsers();
}
document.addEventListener('change', e => { const t = e.target; if (t.classList && t.classList.contains('us-role')) { us.users[+t.dataset.i].role = t.value; us.dirty = true; us.msg = null; drawUsers(); } });
document.addEventListener('input', e => { const t = e.target; if (t.classList && t.classList.contains('us-note')) { us.users[+t.dataset.i].note = t.value; if (!us.dirty) { us.dirty = true; const b = document.getElementById('us-save'); if (b) b.disabled = false; } } });
document.addEventListener('click', e => {
  const t = e.target;
  if (t.classList && t.classList.contains('us-del')) { us.users.splice(+t.dataset.i, 1); us.dirty = true; us.msg = null; drawUsers(); return; }
  if (t.id === 'us-add') { const m = document.getElementById('us-new').value.trim().toLowerCase();
    if (!/^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/.test(m)) { us.msg = {ok: false, t: 'Adresse e-mail invalide'}; drawUsers(); return; }
    if (us.users.some(u => u.email === m)) { us.msg = {ok: false, t: 'Adresse déjà présente'}; drawUsers(); return; }
    us.users.push({email: m, role: document.getElementById('us-newrole').value, note: ''}); us.dirty = true; us.msg = null; drawUsers(); return; }
  if (t.id === 'us-save') usSave();
});
