// Planifier › Ressources : staff (compte Google), prestataires externes (contacts Odoo) et véhicules de service (ressources Google Agenda). Réservé au Super User. Chargé avant app.js.
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
const rsInBu = p => buSel === 'all' || (BU_KEYS[buSel] || []).some(k => ((p.alloc || {})[k] || 0) > 0);
const rsVisible = () => rs.staff.filter(p => p.active && rsInBu(p));
const rsMail = v => !v || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim());

function resourcesBlocks() {
  return [BU_BAR(), {static: '<section class="block" data-bid="rs-staff"><div class="block-head"><h3>Staff</h3></div><div class="block-body" id="rs-staff"><p class="na">Chargement…</p></div></section>'},
    {static: '<section class="block" data-bid="rs-ext"><div class="block-head"><h3>Prestataires externes</h3></div><div class="block-body" id="rs-ext"></div></section>'},
    {static: '<section class="block" data-bid="rs-veh"><div class="block-head"><h3>Véhicules</h3></div><div class="block-body" id="rs-veh"></div></section>'}];
}

async function rsCall(url, opt) {
  const r = await fetch(url, {...opt, headers: {...rsAuth(), ...(opt && opt.body ? {'Content-Type': 'application/json'} : {})}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status);
  return j;
}

async function loadResources() {
  if (rs.dirty) return;                         // les modifications non enregistrées (prestataires) ne sont pas écrasées par un rechargement (ex. changement de filtre BU)
  try {
    const j = await rsCall('/api/resources');
    rs = {...rs, loaded: true, error: null, staff: j.staff || [], externals: (j.externals.data || {}).externals || [], base: j.externals.updated_at || null, vehicles: j.vehicles || {items: []}, delegation: j.delegation, dirty: false};
  } catch (e) { rs.error = e.message; rs.loaded = true; }
}

function drawResources() {
  const a = document.getElementById('rs-staff'); if (!a) return;
  if (!rs.loaded) { a.innerHTML = '<p class="na">Chargement…</p>'; return; }
  if (rs.error) { a.innerHTML = `<p class="neg">${esc(rs.error)}</p>`; return; }
  const vis = rsVisible();
  const row = p => `<tr><td class="prod">${esc(p.name)}${p.active ? '' : ' <small class="na">inactif</small>'}</td><td>${p.kind === 'salarie' ? 'Salarié' : 'Indépendant'}</td><td>${esc(p.function || '')}</td>`
    + `<td><input class="sdin rs-mail" data-pid="${esc(p.id)}" value="${esc(p.email || rs.sugg[p.id] || '')}" placeholder="prenom.nom@lifelive-motorsport.com" style="min-width:240px"> <span class="na" id="rs-st-${esc(p.id)}">${p.email ? '' : rs.sugg[p.id] ? '<small>suggéré : à accepter</small>' : '<small class="neg">à renseigner</small>'}</span></td></tr>`;
  const nSugg = Object.keys(rs.sugg).length;
  a.innerHTML = '<p class="na">Les personnes du staff (telles qu’enregistrées dans Coûts du personnel) peuvent être invitées aux événements une fois leur compte Google renseigné : l’événement apparaît alors dans leur Google Agenda. L’adresse est enregistrée dans leur fiche. Seules les personnes actives sont listées ; le filtre BU suit l’imputation du personnel.</p>'
    + (vis.length ? `<div class="sdbar"><button type="button" id="rs-dir">${rs.suggBusy ? 'Lecture de l’annuaire…' : 'Proposer depuis l’annuaire Google'}</button>${nSugg ? `<button type="button" class="primary" id="rs-acc">Accepter les ${nSugg} suggestions</button>` : ''}<span class="na">${esc(rs.suggMsg || '')}</span></div>` : '') + (vis.length ? table(['Personne', 'Type', 'Fonction', 'Compte Google'], vis.map(row), 'prodtable') : (rs.staff.length ? '<p class="na">Aucune personne active imputée à cette BU.</p>' : '<p class="na">Aucune personne : créez d’abord le staff dans « Coûts du personnel › Données source ».</p>'));
  const b = document.getElementById('rs-ext');
  const RS_BUS = [['XC', 'xc', 'XC'], ['MODERN_RALLY', 'mr', 'Modern Rally'], ['HISTORIC_RALLY', 'hrl', 'Historic Rally'], ['HISTORIC_RACING', 'hrc', 'Historic Racing']];
  const buCell = (e, i) => `<div class="bu-filter" role="group" aria-label="BU concernées">${RS_BUS.map(([k, sym, l]) => `<button type="button" class="rs-pill rs-xbu" data-i="${i}" data-b="${k}" aria-pressed="${(e.bus || []).includes(k)}" title="${esc(l)}">${BuSymbol(sym, {size: 14})}<span>${esc(l)}</span></button>`).join('')}</div>${(e.bus || []).length ? '' : '<small class="neg">à choisir</small>'}`;
  const mailCell = (e, i) => `<input class="sdin rs-email" data-i="${i}" value="${esc(e.email)}" placeholder="adresse e-mail" style="min-width:220px">${e.email ? '' : ' <small class="neg">à compléter</small>'}`;
  const erows = rs.externals.map((e, i) => `<tr><td class="prod">${esc(e.name)}</td><td>${esc(e.company)}</td><td><input class="sdin rs-role" data-i="${i}" value="${esc(e.role)}" maxlength="120" placeholder="fonction" style="min-width:140px"></td><td>${mailCell(e, i)}</td><td>${buCell(e, i)}</td><td>${esc(e.phone)}</td><td><button type="button" class="rs-del" data-i="${i}">Retirer</button></td></tr>`);
  const found = rs.found == null ? '' : rs.found.length ? table(['Contact Odoo', 'Société', 'Fonction', 'E-mail', ''], rs.found.map(c => {
    const has = rs.externals.some(e => e.partner_id === c.id);
    return `<tr><td class="prod">${esc(c.name)}</td><td>${esc(c.company)}</td><td>${esc(c.function)}</td><td>${c.email ? esc(c.email) : '<small class="neg">pas d’e-mail dans Odoo</small>'}</td><td>${has ? '<small class="na">déjà dans la liste</small>' : `<button type="button" class="rs-add" data-id="${c.id}">Ajouter</button>`}</td></tr>`; }), 'prodtable') : '<p class="na">Aucun contact trouvé.</p>';
  b.innerHTML = '<p class="na">Prestataires choisis parmi les contacts Odoo. L’adresse e-mail (reprise d’Odoo, modifiable ici) sert à leur envoyer l’invitation à l’événement Google. Cochez les BU concernées : un prestataire n’est proposé que pour les événements de ces BU. Rien n’est écrit dans Odoo.</p>'
    + (erows.length ? table(['Prestataire', 'Société', 'Fonction', 'E-mail', 'BU concernées', 'Téléphone', ''], erows, 'prodtable') : '<p class="na">Aucun prestataire pour le moment.</p>')
    + `<div class="sdbar"><button type="button" id="rs-save" ${rs.dirty ? '' : 'disabled'}>Enregistrer</button><button type="button" id="rs-cancel" ${rs.dirty ? '' : 'disabled'}>Annuler les modifications</button><span class="na" id="rs-msg">${esc(rs.msg || '')}</span></div>`
    + `<div class="sdbar"><input class="sdin" id="rs-q" placeholder="Rechercher un contact Odoo (nom, société, e-mail)" style="min-width:300px"><button type="button" id="rs-find">${rs.searching ? 'Recherche…' : 'Rechercher'}</button></div>` + found;
  const c = document.getElementById('rs-veh'), v = rs.vehicles;
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
  if (rs.externals.some(e => !rsMail(e.email))) { rs.msg = 'Une adresse e-mail est invalide.'; drawResources(); return; }
  try {
    const j = await rsCall('/api/resources/externals', {method: 'PUT', body: JSON.stringify({data: {externals: rs.externals}, base: rs.base})});
    rs.base = j.updated_at; rs.dirty = false; rs.msg = 'Enregistré.';
  } catch (e) { rs.msg = 'Échec de l’enregistrement : ' + e.message; }
  drawResources();
}

document.addEventListener('change', async e => {
  const t = e.target; if (!t.classList) return;
  if (t.classList.contains('rs-mail')) {
    const pid = t.dataset.pid, st = document.getElementById('rs-st-' + pid), v = t.value.trim();
    if (!rsMail(v)) { if (st) st.innerHTML = '<small class="neg">adresse invalide</small>'; return; }
    try { const j = await rsCall('/api/resources/staff/' + encodeURIComponent(pid), {method: 'PUT', body: JSON.stringify({email: v})}); const p = rs.staff.find(x => x.id === pid); if (p) p.email = j.email; t.value = j.email; if (st) st.innerHTML = j.email ? '<small class="na">enregistré</small>' : '<small class="neg">à renseigner</small>'; }
    catch (err) { if (st) st.innerHTML = '<small class="neg">' + esc(err.message) + '</small>'; }
  } else if (t.classList.contains('rs-email')) { rs.externals[+t.dataset.i].email = t.value.trim().toLowerCase(); rs.dirty = true; rs.msg = null; drawResources(); }
  else if (t.classList.contains('rs-role')) { rs.externals[+t.dataset.i].role = t.value; rs.dirty = true; rs.msg = null; drawResources(); }
});

document.addEventListener('click', async e => {
  const vc = e.target.closest && e.target.closest('.rs-vcat'); if (vc) { rs.vcat = vc.dataset.c; drawResources(); return; }
  const t = e.target.closest && e.target.closest('button'); if (!t || !document.getElementById('rs-ext')) return;
  if (t.classList.contains('rs-xbu')) { const x = rs.externals[+t.dataset.i], b = t.dataset.b; x.bus = (x.bus || []).includes(b) ? x.bus.filter(y => y !== b) : (x.bus || []).concat([b]); rs.dirty = true; rs.msg = null; drawResources(); return; }
  if (t.classList.contains('rs-del')) { rs.externals.splice(+t.dataset.i, 1); rs.dirty = true; rs.msg = null; drawResources(); }
  else if (t.classList.contains('rs-add')) {
    const c = (rs.found || []).find(x => x.id === +t.dataset.id); if (!c) return;
    rs.externals.push({partner_id: c.id, name: c.name, email: (c.email || '').toLowerCase(), company: c.company || '', phone: c.phone || '', role: c.function || '', bus: []}); rs.dirty = true; rs.msg = null; drawResources();
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
