// Planifier › Ressources (trois pages) : staff interne (compte Google), staff externe (contacts Odoo) et véhicules (ressources Google Agenda). Réservé au Super User. Chargé avant app.js.
let rs = {loaded: false, error: null, staff: [], externals: [], base: null, vehicles: {items: []}, delegation: true, dirty: false, msg: null, found: null, searching: false, savingMail: {}, sugg: {}, suggMsg: null, suggBusy: false, vcat: 'all'};
const rsAuth = () => (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {};
const rsNorm = x => x.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z\s'-]/g, ' ').split(/[\s'-]+/).filter(w => w.length > 1 && !['de', 'du', 'van', 'von', 'le', 'la'].includes(w));
// Propose, pour chaque personne sans compte Google, l'utilisateur de l'annuaire dont le nom correspond (mêmes mots, ou tous les mots du staff présents) : seulement si la correspondance est unique
function rsMatch(users) {
  const out = {};
  rsVisible().filter(p => !p.email).forEach(p => {
    const t = rsNorm(p.name); if (!t.length) return;
    const hits = users.filter(u => { const w = rsNorm(u.name); return w.length && (t.every(x => w.includes(x)) || (w.length > 1 && w.every(x => t.includes(x)))); });
    if (hits.length === 1) out[p.id] = hits[0].email.toLowerCase();
  });
  return out;
}
// Une personne relève d'une BU si une part de son imputation y va (le filtre « ALL » montre tout le monde, y compris le support et le management)
const rsInBu = p => buSel === 'all' || p.all_bus || (BU_KEYS[buSel] || []).some(k => ((p.alloc || {})[k] || 0) > 0);
const rsCmp = byName;
const rsVisible = () => rs.staff.filter(p => p.active && rsInBu(p)).sort(rsCmp);
const rsMail = v => !v || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim());

const rsBlock = (id, title) => ({static: `<section class="block" data-bid="${id}"><div class="block-head"><h3>${title}</h3></div><div class="block-body" id="${id}"><p class="na">Chargement…</p></div></section>`});
// Trois pages : staff interne (compte Google), staff externe (contacts Odoo, BU concernées), véhicules (ressources Google Agenda)
function resourcesBlocks(which) {
  return which === 'ext' ? [BU_BAR(), rsBlock('rs-ext', 'Staff externe')] : which === 'veh' ? [rsBlock('rs-veh', 'Véhicules')] : [BU_BAR(), rsBlock('rs-staff', 'Staff interne')];
}

// Erreur de validation du serveur (422) : « champ : règle non respectée », dans la langue de l'utilisateur quand c'est un cas courant
const RS_FIELDS = {title: 'Titre', bu: 'BU', start: 'Début de l’événement', end: 'Fin de l’événement', immo_start: 'Début d’immobilisation', immo_end: 'Fin d’immobilisation', place: 'Lieu de l’événement', origin: 'Lieu de départ', notes: 'Notes', staff: 'Staff interne', externals: 'Staff externe', vehicles: 'Véhicules', email: 'E-mail', bus: 'BU concernées'};
function rsFieldError(d) {
  const path = (d.loc || []).filter(x => x !== 'body' && x !== 'data'), key = path[0], sub = path.slice(1).filter(x => typeof x !== 'number').join('.');
  const label = (RS_FIELDS[key] || String(key || 'champ')) + (sub ? ' › ' + sub : '');
  let m = (d.msg || 'valeur refusée').replace(/^Value error, /, '');
  m = m.replace(/^String should have at most (\d+) characters?$/, 'trop long (maximum $1 caractères)').replace(/^String should have at least \d+ characters?$/, 'obligatoire').replace(/^Field required$/, 'obligatoire').replace(/^Input should be a valid date.*$/, 'date invalide').replace(/^List should have at most (\d+) items.*$/, 'trop d’éléments (maximum $1)');
  return label + ' : ' + m;
}
async function rsCall(url, opt) {
  const r = await fetch(url, {...opt, headers: {...rsAuth(), ...(opt && opt.body ? {'Content-Type': 'application/json'} : {})}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) && j.detail.length ? j.detail.slice(0, 3).map(rsFieldError).join(' ; ') : 'Erreur ' + r.status);
  return j;
}

async function loadResources() {
  if (rs.dirty) return;                         // les modifications non enregistrées (prestataires) ne sont pas écrasées par un rechargement (ex. changement de filtre BU)
  try {
    const j = await rsCall('/api/resources');
    rs = {...rs, loaded: true, error: null, staff: j.staff || [], externals: ((j.externals.data || {}).externals || []).slice().sort(rsCmp), base: j.externals.updated_at || null, vehicles: j.vehicles || {items: []}, delegation: j.delegation, rolesOk: j.roles_from_odoo !== false, dirty: false};
  } catch (e) { rs.error = e.message; rs.loaded = true; }
}

const RS_WS = [['', '— Hors atelier —'], ['mechanic', 'Mécanicien'], ['chef_cars', 'Chef d’atelier CARS'], ['chef_xc', 'Chef d’atelier XC'], ['chef_all', 'Chef d’atelier CARS + XC']];
function drawResources() {
  rsDrawStaff(); rsDrawExt(); rsDrawVeh();
  if (!superUser) {                                                      // fiches du staff : lecture seule (le rôle Atelier et le compte Google se règlent par le Super User)
    const a = document.getElementById('rs-staff');
    if (a) { a.querySelectorAll('input,select,button').forEach(el => { el.disabled = true; }); const d = a.querySelector('#rs-dir'); if (d) d.remove(); }
  }
}
function rsDrawStaff() {
  const a = document.getElementById('rs-staff'); if (!a) return;
  if (!rs.loaded) { a.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (rs.error) { a.innerHTML = `<p class="neg">${esc(rs.error)}</p>`; return; }
  const vis = rsVisible();
  const row = p => `<tr><td class="prod">${esc(p.name)}${p.active ? '' : ' <small class="na">inactif</small>'}</td><td>${p.kind === 'salarie' ? 'Salarié' : 'Indépendant'}</td><td>${esc(p.function || '')}</td>`
    + `<td><input class="sdin rs-mail" data-pid="${esc(p.id)}" value="${esc(p.email || rs.sugg[p.id] || '')}" placeholder="prenom.nom@lifelive-motorsport.com" style="min-width:240px"> <span class="na" id="rs-st-${esc(p.id)}">${p.email ? '' : rs.sugg[p.id] ? '<small>suggéré : à accepter</small>' : '<small class="neg">à renseigner</small>'}</span></td><td><select class="sdin rs-ws" data-pid="${esc(p.id)}">${RS_WS.map(([v, l]) => `<option value="${v}"${(p.workshop || '') === v ? ' selected' : ''}>${l}</option>`).join('')}</select></td><td class="rs-days">${['L', 'M', 'M', 'J', 'V', 'S', 'D'].map((l, i) => `<button type="button" class="rs-wd${(p.work_days || [0, 1, 2, 3, 4]).includes(i) ? ' on' : ''}" data-pid="${esc(p.id)}" data-d="${i}" title="${['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'][i]}">${l}</button>`).join('')}</td><td><label class="chk" title="Proposée pour toutes les BU, quelle que soit son imputation"><input type="checkbox" class="rs-allbu" data-pid="${esc(p.id)}" ${p.all_bus ? 'checked' : ''}> <small class="na">toutes</small></label></td></tr>`;
  const nSugg = Object.keys(rs.sugg).length;
  a.innerHTML = '<p class="na">Les personnes du staff (telles qu’enregistrées dans Coûts du personnel) peuvent être invitées aux événements une fois leur compte Google renseigné : l’événement apparaît alors dans leur Google Agenda. L’adresse est enregistrée dans leur fiche. Seules les personnes actives sont listées ; le filtre BU suit l’imputation du personnel.</p>'
    + (vis.length ? `<div class="sdbar"><button type="button" id="rs-dir">${rs.suggBusy ? 'Lecture de l’annuaire…' : 'Proposer depuis l’annuaire Google'}</button>${nSugg ? `<button type="button" class="primary" id="rs-acc">Accepter les ${nSugg} suggestions</button>` : ''}<span class="na">${esc(rs.suggMsg || '')}</span></div>` : '') + (vis.length ? table(['Personne', 'Type', 'Fonction', 'Compte Google', 'Atelier', 'Jours de présence', 'Toutes les BU'], vis.map(row), 'prodtable') : (rs.staff.length ? '<p class="na">Aucune personne active imputée à cette BU.</p>' : '<p class="na">Aucune personne : créez d’abord le staff dans « Coûts du personnel › Données source ».</p>'));
}
function rsDrawExt() {
  const b = document.getElementById('rs-ext'); if (!b) return;
  if (!rs.loaded || rs.error) { b.innerHTML = rs.error ? `<p class="neg">${esc(rs.error)}</p>` : '<p class="na">Chargement…</p>'; return; }
  const extIn = x => buSel === 'all' || (x.bus || []).some(k => (BU_KEYS[buSel] || []).includes(k));
  const RS_BUS = [['XC', 'xc', 'XC'], ['MODERN_RALLY', 'mr', 'Modern Rally'], ['HISTORIC_RALLY', 'hrl', 'Historic Rally'], ['HISTORIC_RACING', 'hrc', 'Historic Racing']];
  const buCell = (e, i) => `<div class="rs-bus" role="group" aria-label="BU concernées">${RS_BUS.map(([k, sym, l]) => `<button type="button" class="rs-pill rs-ico rs-xbu" data-i="${i}" data-b="${k}" aria-pressed="${(e.bus || []).includes(k)}" aria-label="${esc(l)}" title="${esc(l)}">${BuSymbol(sym, {size: 15})}</button>`).join('')}${(e.bus || []).length ? '' : ' <small class="neg">à choisir</small>'}</div>`;
  const mailCell = e => e.email ? esc(e.email) : '<small class="neg" title="À renseigner dans Odoo (fiche du contact)">⚠ E-mail vide dans Odoo</small>';
  const erows = rs.externals.map((e, i) => [e, i]).filter(([e]) => extIn(e)).map(([e, i]) => `<tr><td class="prod">${esc(e.name)}</td><td>${esc(e.company)}</td><td>${e.role ? esc(e.role) : '<small class="neg" title="À renseigner dans Odoo (fiche du contact)">⚠ Job Position vide</small>'}</td><td>${mailCell(e)}</td><td>${buCell(e, i)}</td><td>${esc(e.phone)}</td><td><button type="button" class="rs-del" data-i="${i}">Retirer</button></td></tr>`);
  const found = rs.found == null ? '' : rs.found.length ? table(['Contact Odoo', 'Société', 'Fonction', 'E-mail', ''], rs.found.map(c => {
    const has = rs.externals.some(e => e.partner_id === c.id);
    return `<tr><td class="prod">${esc(c.name)}</td><td>${esc(c.company)}</td><td>${c.function ? esc(c.function) : '<small class="neg">⚠ Job Position vide dans Odoo</small>'}</td><td>${c.email ? esc(c.email) : '<small class="neg">pas d’e-mail dans Odoo</small>'}</td><td>${has ? '<small class="na">déjà dans la liste</small>' : `<button type="button" class="rs-add" data-id="${c.id}">Ajouter</button>`}</td></tr>`; }), 'prodtable') : '<p class="na">Aucun contact trouvé.</p>';
  b.innerHTML = (rs.rolesOk ? '' : '<p class="neg">Fonctions non relues dans Odoo (indisponible) : les dernières valeurs enregistrées sont affichées.</p>') + '<p class="na">Prestataires choisis parmi les contacts Odoo. L’adresse e-mail (qui sert à leur envoyer l’invitation à l’événement Google), la fonction (Job Position) et le téléphone sont lus dans Odoo à chaque ouverture de la page : on les modifie dans Odoo, pas ici. Cochez les BU concernées : un prestataire n’est proposé que pour les événements de ces BU. Rien n’est écrit dans Odoo.</p>'
    + (erows.length ? table(['Prestataire', 'Société', 'Fonction', 'E-mail', 'BU concernées', 'Téléphone', ''], erows, 'prodtable') : (rs.externals.length ? '<p class="na">Aucun prestataire rattaché à cette BU.</p>' : '<p class="na">Aucun prestataire pour le moment.</p>'))
    + `<div class="sdbar"><button type="button" id="rs-save" ${rs.dirty ? '' : 'disabled'}>Enregistrer</button><button type="button" id="rs-cancel" ${rs.dirty ? '' : 'disabled'}>Annuler les modifications</button><span class="na" id="rs-msg">${esc(rs.msg || '')}</span></div>`
    + `<div class="sdbar"><input class="sdin" id="rs-q" placeholder="Rechercher un contact Odoo (nom, société, e-mail)" style="min-width:300px"><button type="button" id="rs-find">${rs.searching ? 'Recherche…' : 'Rechercher'}</button></div>` + found;
}
function rsDrawVeh() {
  const c = document.getElementById('rs-veh'); if (!c) return;
  if (!rs.loaded || rs.error) { c.innerHTML = rs.error ? `<p class="neg">${esc(rs.error)}</p>` : '<p class="na">Chargement…</p>'; return; }
  const v = rs.vehicles;
  const cats = (v.categories || []).filter(k => (v.items || []).some(x => x.category === k.id));
  const vitems = (v.items || []).filter(x => rs.vcat === 'all' || x.category === rs.vcat);
  const catLabel = id => ((v.categories || []).find(k => k.id === id) || {}).label || id;
  const pill = (id, label, n) => `<button type="button" class="rs-pill rs-vcat" data-c="${id}" aria-pressed="${rs.vcat === id}"><span>${esc(label)}</span> <small>${n}</small></button>`;
  c.innerHTML = '<p class="na">Véhicules lus dans le module « Ressources » de Google Agenda : ils seront réservés comme ressources invitées aux événements.</p>'
    + (cats.length ? `<div class="bu-bar"><div class="bu-filter" role="group" aria-label="Filtrer par catégorie">${pill('all', 'Tous', v.items.length)}${cats.map(k => pill(k.id, k.label, v.items.filter(x => x.category === k.id).length)).join('')}</div></div>` : '')
    + (v.message ? `<p class="${v.items.length ? 'na' : 'neg'}">${esc(v.message)}</p>` : '')
    + (vitems.length ? table(['Véhicule', 'Catégorie', 'Type', 'Adresse de la ressource', 'Description'], vitems.map(x => `<tr><td class="prod">${esc(x.name)}</td><td>${esc(catLabel(x.category))}</td><td>${esc(x.type || '')}</td><td>${x.email ? esc(x.email) : '<small class="na">—</small>'}</td><td>${esc(x.description || '')}</td></tr>`), 'prodtable') : '');
}

async function rsSaveExternals() {
  try {
    const j = await rsCall('/api/resources/externals', {method: 'PUT', body: JSON.stringify({data: {externals: rs.externals}, base: rs.base})});
    rs.base = j.updated_at; rs.dirty = false; rs.msg = 'Enregistré.';
  } catch (e) { rs.msg = 'Échec de l’enregistrement : ' + e.message; }
  drawResources();
}

document.addEventListener('change', async e => {
  const t = e.target; if (!t.classList) return;
  if (t.classList.contains('rs-ws')) {
    const p = rs.staff.find(x => x.id === t.dataset.pid); if (!p) return;
    try { const j = await rsCall('/api/resources/staff/' + encodeURIComponent(p.id), {method: 'PUT', body: JSON.stringify({workshop: t.value})}); p.workshop = j.workshop; } catch (err) { t.value = p.workshop || ''; alert(err.message); }
    return;
  }
  if (t.classList.contains('rs-allbu')) {
    const p = rs.staff.find(x => x.id === t.dataset.pid); if (!p) return;
    try { const j = await rsCall('/api/resources/staff/' + encodeURIComponent(p.id), {method: 'PUT', body: JSON.stringify({all_bus: t.checked})}); p.all_bus = j.all_bus; rs.msg = null; } catch (err) { t.checked = !t.checked; alert(err.message); }
    drawResources(); return;
  }
  if (t.classList.contains('rs-mail')) {
    const pid = t.dataset.pid, st = document.getElementById('rs-st-' + pid), v = t.value.trim();
    if (!rsMail(v)) { if (st) st.innerHTML = '<small class="neg">adresse invalide</small>'; return; }
    try { const j = await rsCall('/api/resources/staff/' + encodeURIComponent(pid), {method: 'PUT', body: JSON.stringify({email: v})}); const p = rs.staff.find(x => x.id === pid); if (p) p.email = j.email; t.value = j.email; if (st) st.innerHTML = j.email ? '<small class="na">enregistré</small>' : '<small class="neg">à renseigner</small>'; }
    catch (err) { if (st) st.innerHTML = '<small class="neg">' + esc(err.message) + '</small>'; }
  }
});

document.addEventListener('click', async e => {
  const vc = e.target.closest && e.target.closest('.rs-vcat'); if (vc) { rs.vcat = vc.dataset.c; drawResources(); return; }
  const t = e.target.closest && e.target.closest('button'); if (!t || !document.getElementById('rs-ext')) return;
  if (t.classList.contains('rs-xbu')) { const x = rs.externals[+t.dataset.i], b = t.dataset.b; x.bus = (x.bus || []).includes(b) ? x.bus.filter(y => y !== b) : (x.bus || []).concat([b]); rs.dirty = true; rs.msg = null; drawResources(); return; }
  if (t.classList.contains('rs-del')) { rs.externals.splice(+t.dataset.i, 1); rs.dirty = true; rs.msg = null; drawResources(); }
  else if (t.classList.contains('rs-add')) {
    const c = (rs.found || []).find(x => x.id === +t.dataset.id); if (!c) return;
    rs.externals.push({partner_id: c.id, name: c.name, email: (c.email || '').toLowerCase(), company: c.company || '', phone: c.phone || '', role: c.function || '', bus: []}); rs.externals.sort(rsCmp); rs.dirty = true; rs.msg = null; drawResources();
  } else if (t.id === 'rs-dir') {
    rs.suggBusy = true; rs.suggMsg = null; drawResources();
    try {
      const j = await rsCall('/api/resources/directory-users');
      if (j.message) rs.suggMsg = j.message; else { rs.sugg = rsMatch(j.items || []); const n = Object.keys(rs.sugg).length, miss = rsVisible().filter(p => !p.email).length - n; rs.suggMsg = n ? n + ' suggestion' + (n > 1 ? 's' : '') + (miss > 0 ? ' · ' + miss + ' sans correspondance unique' : '') : 'Aucune correspondance trouvée.'; }
    } catch (err) { rs.suggMsg = err.message; }
    rs.suggBusy = false; drawResources();
  } else if (t.id === 'rs-acc') {
    for (const [pid, email] of Object.entries(rs.sugg)) {
      try { const j = await rsCall('/api/resources/staff/' + encodeURIComponent(pid), {method: 'PUT', body: JSON.stringify({email})}); const p = rs.staff.find(x => x.id === pid); if (p) p.email = j.email; delete rs.sugg[pid]; } catch (err) { rs.suggMsg = err.message; break; }
    }
    if (!Object.keys(rs.sugg).length) rs.suggMsg = 'Suggestions enregistrées.'; drawResources();
  } else if (t.id === 'rs-save') rsSaveExternals();
  else if (t.id === 'rs-cancel') { rs.dirty = false; await loadResources(); rs.msg = null; drawResources(); }
  else if (t.id === 'rs-find') {
    const q = (document.getElementById('rs-q').value || '').trim(); if (q.length < 2) { rs.msg = 'Saisissez au moins 2 caractères.'; drawResources(); return; }
    rs.searching = true; rs.msg = null; drawResources();
    try { const j = await rsCall('/api/resources/contacts?q=' + encodeURIComponent(q)); rs.found = j.contacts || []; if (j.unavailable) { rs.msg = j.unavailable; rs.found = null; } } catch (err) { rs.found = []; rs.msg = err.message; }
    rs.searching = false; drawResources(); const qi = document.getElementById('rs-q'); if (qi) qi.value = q;
  }
});
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.id === 'rs-q') { e.preventDefault(); document.getElementById('rs-find').click(); } });

// Jours de présence habituels (alertes d'oubli de pointage) : un clic sur la lettre du jour l'ajoute ou le retire
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('.rs-wd'); if (!b) return;
  const p = rs.staff.find(x => x.id === b.dataset.pid); if (!p) return;
  const d = +b.dataset.d, cur = p.work_days || [0, 1, 2, 3, 4], next = cur.includes(d) ? cur.filter(x => x !== d) : cur.concat(d).sort();
  try { const j = await rsCall('/api/resources/staff/' + encodeURIComponent(p.id), {method: 'PUT', body: JSON.stringify({work_days: next})}); p.work_days = j.work_days; } catch (err) { alert(err.message); }
  drawResources();
});
