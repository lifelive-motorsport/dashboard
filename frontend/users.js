// Settings › Utilisateurs : le Super User crée les utilisateurs et choisit leur rôle. Chargé avant app.js.
let us = {loaded: false, users: [], categories: [], fixed: [], domain: '', error: null, msg: null, dirty: false, open: new Set(), draft: {email: '', name: '', nick: '', role: 'cat:xc'}};
const usCatLabel = id => { const c = us.categories.find(x => x.id === id); return c ? 'Catégorie : ' + c.name : 'Catégorie supprimée'; };
const usRoles = () => [['standard', 'Standard : consulte tout, sans modifier'], ['admin', 'Administrateur : saisit les ajustements et voit le personnel']].concat(us.categories.map(c => ['cat:' + c.id, 'Catégorie : ' + c.name]));
const usRoleLabel = r => r === 'super' ? 'Super User' : r === 'admin' ? 'Administrateur' : r === 'standard' ? 'Standard' : r.startsWith('cat:') ? usCatLabel(r.slice(4)) : r;
// Catalogue des pages cochables, par module (la page « Utilisateurs » n'est jamais attribuable) : [identifiant du module, libellé « Chapitre › Module », [[clé, libellé]]]
const usPages = () => CHAPTERS.flatMap(c => c.modules.map(m => [m.id, c.label + ' › ' + m.label, modulePages(m).filter(p => p[0] !== 'others/users').map(p => [p[0], m.groups ? p[2] + ' › ' + p[1] : p[1]])])).filter(([, , it]) => it.length);
const usAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};

function usersBlocks() { return [{static: '<section class="block" data-bid="users"><div class="block-head"><h3>Utilisateurs et rôles</h3></div><div class="block-body" id="users-view"><p class="na">Chargement…</p></div></section>'}]; }

async function loadUsers() {
  try {
    const r = await fetch('/api/users', {headers: usAuth()});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
    us = {...us, ...j, users: (j.users || []).map(u => u.role === 'xc' ? {...u, role: 'cat:xc'} : u), loaded: true, error: null, dirty: false};
    usAddSupers();
  } catch (e) { us.error = e.message; us.loaded = true; }
}

function usCatHtml(c, i) {
  const groups = usPages().map(([g, label, items]) => { const on = items.filter(([k]) => c.pages.includes(k)).length;
    return `<div class="uscat-grp"><label class="uscat-h"><input type="checkbox" class="us-grp" data-i="${i}" data-g="${g}" ${on === items.length ? 'checked' : ''}> <b>${esc(label)}</b> <small class="na">${on}/${items.length}</small></label><div class="uscat-items">${items.map(([k, l]) => `<label><input type="checkbox" class="us-page" data-i="${i}" data-k="${k}" ${c.pages.includes(k) ? 'checked' : ''}> ${esc(l)}</label>`).join('')}</div></div>`; }).join('');
  const n = us.users.filter(u => u.role === 'cat:' + c.id).length, open = us.open.has(c.id);
  return `<div class="uscat"><div class="sdbar"><button type="button" class="us-toggle" data-i="${i}">${open ? '▾' : '▸'}</button><input class="sdin us-cname" data-i="${i}" value="${esc(c.name)}" maxlength="60" style="max-width:260px"><span class="na">${c.pages.length} page${c.pages.length > 1 ? 's' : ''} cochée${c.pages.length > 1 ? 's' : ''} · ${n} utilisateur${n > 1 ? 's' : ''}</span><button type="button" class="danger us-cdel" data-i="${i}">Supprimer la catégorie</button></div>${open ? `<div class="uscat-body">${groups}</div>` : ''}</div>`;
}

// Le Super User figure dans la liste (nom et surnom modifiables ; son rôle vient de la configuration du serveur)
const usIsSuper = email => (us.fixed || []).some(f => f.role === 'super' && f.email === email);
function usAddSupers() { (us.fixed || []).filter(f => f.role === 'super').forEach(f => { if (!us.users.some(u => u.email === f.email)) us.users.unshift({email: f.email, role: 'standard', note: '', nickname: ''}); }); }
function drawUsers() {
  const el = document.getElementById('users-view'); if (!el) return;
  if (!us.loaded) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (us.error) { el.innerHTML = `<p class="neg">${esc(us.error)}</p>`; return; }
  const roles = usRoles();
  const sel = (v, i) => `<select class="sdin us-role" data-i="${i}">${roles.map(([k, l]) => `<option value="${k}"${v === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}${roles.some(([k]) => k === v) ? '' : `<option value="${esc(v)}" selected>${esc(usRoleLabel(v))}</option>`}</select>`;
  const rows = us.users.map((u, i) => { const su = usIsSuper(u.email);
    return `<tr><td>${esc(u.email)}${u.email.endsWith('@' + us.domain) ? '' : ' <small class="na">hors domaine</small>'}</td><td>${su ? '<span class="badge-profile">Super User</span>' : sel(u.role, i)}</td><td><input class="sdin us-note" data-i="${i}" value="${esc(u.note || '')}" placeholder="Nom complet" maxlength="120"></td><td><input class="sdin us-nick" data-i="${i}" value="${esc(u.nickname || '')}" placeholder="Surnom" maxlength="40"></td><td>${su ? '' : `<button type="button" class="danger us-del" data-i="${i}">Retirer</button>`}</td></tr>`; }).join('');
  el.innerHTML = `<p class="na">Vous êtes Super User : vous créez les catégories d’utilisateurs (en cochant les pages accessibles), puis les utilisateurs et leur rôle. Une adresse enregistrée peut se connecter avec son compte Google, même hors du domaine @${esc(us.domain)}. Les modifications s’appliquent en moins d’une minute.</p>`
    + '<h4 class="sub">Catégories d’utilisateurs</h4>' + (us.categories.map(usCatHtml).join('') || '<p class="na">Aucune catégorie.</p>')
    + `<div class="sdbar"><input class="sdin" id="us-newcat" placeholder="Nom de la nouvelle catégorie" maxlength="60" style="max-width:300px"><button type="button" id="us-addcat">Créer la catégorie</button></div>`
    + '<h4 class="sub">Utilisateurs</h4>'
    + `<div class="table-wrap"><table class="prodtable"><thead><tr><th>Adresse e-mail</th><th>Rôle</th><th>Nom</th><th>Surnom</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="na">Aucun utilisateur enregistré.</td></tr>'}</tbody></table></div>`
    + `<div class="sdbar"><input class="sdin" id="us-new" type="email" value="${esc(us.draft.email)}" placeholder="nouvelle.adresse@exemple.com" style="max-width:260px"><input class="sdin" id="us-newname" value="${esc(us.draft.name)}" placeholder="Nom complet" maxlength="120" style="max-width:200px"><input class="sdin" id="us-newnick" value="${esc(us.draft.nick)}" placeholder="Surnom (utilisé pour « Bonjour … »)" maxlength="40" style="max-width:240px"><select class="sdin" id="us-newrole" style="max-width:360px">${roles.map(([k, l]) => `<option value="${k}"${k === us.draft.role ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select><button type="button" id="us-add">Ajouter</button>`
    + `<button type="button" class="primary" id="us-save"${us.dirty ? '' : ' disabled'}>Enregistrer</button>${us.msg ? `<span class="${us.msg.ok ? 'pos' : 'neg'}">${esc(us.msg.t)}</span>` : us.dirty ? '<span class="na">Modifications non enregistrées</span>' : ''}</div>`
    + '<h4 class="sub">Comptes définis par la configuration du serveur (non modifiables ici)</h4>'
    + table(['Adresse e-mail', 'Rôle', 'Origine'], us.fixed.map(f => `<tr><td>${esc(f.email)}</td><td>${esc(usRoleLabel(f.role))}</td><td><small class="na">${esc(f.source)}</small></td></tr>`), 'prodtable')
    + '<small class="na"><b>Standard</b> voit toutes les pages sans rien modifier (les données du personnel restent masquées) ; <b>Administrateur</b> saisit les ajustements (MB, stock, hypothèses) et voit le personnel ; une <b>catégorie</b> n’ouvre que les pages cochées, en lecture seule : le serveur refuse tout le reste et ne transmet pas les chiffres des autres pages. Cocher une page de marge nette ouvre aussi les données qu’elle utilise (personnel, frais généraux, véhicules). Un rôle choisi ici l’emporte sur la configuration du serveur. Le Super User ne se modifie pas depuis cet écran, et cette page « Utilisateurs » ne peut pas être cochée.</small>';
}
async function usSave() {
  us.msg = null;
  try {
    const r = await fetch('/api/users', {method: 'PUT', headers: {'Content-Type': 'application/json', ...usAuth()}, body: JSON.stringify({users: us.users.map(u => ({email: u.email, role: u.role, note: u.note || '', nickname: u.nickname || ''})), categories: us.categories.map(c => ({id: c.id, name: c.name.trim() || 'Sans nom', pages: c.pages}))})});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? 'Adresse invalide' : 'Erreur ' + r.status);
    us = {...us, ...j, users: (j.users || []).map(u => u.role === 'xc' ? {...u, role: 'cat:xc'} : u), dirty: false, msg: {ok: true, t: 'Enregistré'}}; usAddSupers();
  } catch (e) { us.msg = {ok: false, t: e.message}; }
  drawUsers();
}
document.addEventListener('change', e => { const t = e.target; if (t.id === 'us-newrole') us.draft.role = t.value; if (!t.classList) return;
  if (t.classList.contains('us-page')) { const c = us.categories[+t.dataset.i], k = t.dataset.k; c.pages = t.checked ? [...new Set([...c.pages, k])] : c.pages.filter(x => x !== k); us.dirty = true; us.msg = null; drawUsers(); return; }
  if (t.classList.contains('us-grp')) { const c = us.categories[+t.dataset.i], keys = usPages().find(([g]) => g === t.dataset.g)[2].map(([k]) => k); c.pages = t.checked ? [...new Set([...c.pages, ...keys])] : c.pages.filter(x => !keys.includes(x)); us.dirty = true; us.msg = null; drawUsers(); return; }
});
document.addEventListener('change', e => { const t = e.target; if (t.classList && t.classList.contains('us-role')) { us.users[+t.dataset.i].role = t.value; us.dirty = true; us.msg = null; drawUsers(); } });
document.addEventListener('input', e => { const t = e.target; const dm = {'us-new': 'email', 'us-newname': 'name', 'us-newnick': 'nick'}[t.id]; if (dm) { us.draft[dm] = t.value; return; }
  if (t.classList && t.classList.contains('us-nick')) { us.users[+t.dataset.i].nickname = t.value; if (!us.dirty) { us.dirty = true; const b = document.getElementById('us-save'); if (b) b.disabled = false; } return; }
  if (t.classList && t.classList.contains('us-cname')) { us.categories[+t.dataset.i].name = t.value; if (!us.dirty) { us.dirty = true; const b = document.getElementById('us-save'); if (b) b.disabled = false; } return; }
   if (t.classList && t.classList.contains('us-note')) { us.users[+t.dataset.i].note = t.value; if (!us.dirty) { us.dirty = true; const b = document.getElementById('us-save'); if (b) b.disabled = false; } } });
document.addEventListener('click', e => {
  const t = e.target;
  if (t.classList && t.classList.contains('us-toggle')) { const c = us.categories[+t.dataset.i]; us.open.has(c.id) ? us.open.delete(c.id) : us.open.add(c.id); drawUsers(); return; }
  if (t.classList && t.classList.contains('us-cdel')) { const c = us.categories[+t.dataset.i], n = us.users.filter(u => u.role === 'cat:' + c.id).length;
    if (n) { us.msg = {ok: false, t: `Impossible : ${n} utilisateur${n > 1 ? 's' : ''} dans cette catégorie. Changez d’abord leur rôle.`}; drawUsers(); return; }
    us.categories.splice(+t.dataset.i, 1); us.dirty = true; us.msg = null; drawUsers(); return; }
  if (t.id === 'us-addcat') { const n = document.getElementById('us-newcat').value.trim(); if (!n) return;
    let id = n.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24) || 'cat';
    while (us.categories.some(c => c.id === id)) id += '1';
    us.categories.push({id, name: n, pages: []}); us.open.add(id); us.dirty = true; us.msg = null; drawUsers(); return; }
  if (t.classList && t.classList.contains('us-del')) { us.users.splice(+t.dataset.i, 1); us.dirty = true; us.msg = null; drawUsers(); return; }
  if (t.id === 'us-add') { const m = document.getElementById('us-new').value.trim().toLowerCase();
    if (!/^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$/.test(m)) { us.msg = {ok: false, t: 'Adresse e-mail invalide'}; drawUsers(); return; }
    if (us.users.some(u => u.email === m)) { us.msg = {ok: false, t: 'Adresse déjà présente'}; drawUsers(); return; }
    const nick = document.getElementById('us-newnick').value.trim(), nm0 = document.getElementById('us-newname').value.trim();
    if (!nick) { us.msg = {ok: false, t: 'Indiquez le surnom de l’utilisateur (utilisé pour l’accueillir)'}; drawUsers(); return; }
    us.users.push({email: m, role: document.getElementById('us-newrole').value, note: nm0, nickname: nick}); us.dirty = true; us.msg = null; us.draft = {email: '', name: '', nick: '', role: us.draft.role}; drawUsers(); return; }
  if (t.id === 'us-save') usSave();
});
