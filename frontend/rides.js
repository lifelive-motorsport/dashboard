// Roulages (Consigner › Roulages) : kilométrage et temps de roulage des voitures de course et de leurs pièces (remplace RPM).
// Voitures = véhicules de course de Ressources ; pièces en arborescence (Groupe › Pièce › Sous-pièce) avec limite et seuil d'alerte ; runs = tours × circuit, ou spéciales × passages.
const rd = {cars: null, catalog: [], circuits: [], car: null, loading: false, error: null, msg: null, form: null, run: null, repl: null, settings: false, showRemoved: false, showArchived: false, odoo: null, cat: null, circ: {name: '', length_km: ''}};
const rdKm = v => v == null ? '–' : new Intl.NumberFormat(LOCALE(), {maximumFractionDigits: 1}).format(v);
const rdPct = r => r == null ? '' : Math.round(r * 100) + ' %';
const RD_STATE = {over: ['neg', 'Limite dépassée'], warn: ['warn', 'À surveiller'], ok: ['pos', 'OK'], none: ['na', '']};
const rdNum = v => v === '' || v == null ? null : parseFloat(String(v).replace(',', '.'));
const rdToday = () => new Date().toISOString().slice(0, 10);
const RD_BUSYM = {XC: 'xc', MODERN_RALLY: 'mr', HISTORIC_RALLY: 'hrl', HISTORIC_RACING: 'hrc'}, RD_BULAB = {XC: 'XC', MODERN_RALLY: 'Modern Rally', HISTORIC_RALLY: 'Historic Rally', HISTORIC_RACING: 'Historic Racing'};
const rdBuOk = c => buSel === 'all' || buMatchesFilter(RD_BUSYM[c.bu] || 'lifelive', buSel);      // une voiture sans BU n'apparaît que dans « ALL »
const rdBuPills = (c) => `<div class="bu-filter rd-bupills" role="group" aria-label="BU de la voiture">${Object.entries(RD_BUSYM).map(([k, sym]) => `<button type="button" class="rs-pill rs-ico" data-rd="setbu" data-b="${k}" aria-pressed="${c.bu === k}" title="${esc(RD_BULAB[k])}" aria-label="${esc(RD_BULAB[k])}">${BuSymbol(sym, {size: 15})}</button>`).join('')}${c.bu ? '' : ' <small class="neg">BU à définir</small>'}</div>`;

function ridesBlocks() { return [{static: '<section class="block" data-bid="rd"><div id="rd-view"><p class="na">Chargement…</p></div></section>'}]; }

async function rdLoad(force) {
  rd.loading = true; rdDraw();
  try {
    const j = await rsCall('/api/rides/cars' + (force ? '?refresh=1' : '')); rd.cars = j.cars; rd.catalog = j.catalog; rd.circuits = j.circuits; rd.error = null;
    if (rd.car) rd.car = await rsCall('/api/rides/cars/' + encodeURIComponent(rd.car.key));
  } catch (e) { rd.error = e.message; }
  rd.loading = false; rdDraw();
}
async function rdLoadOdoo() { try { rd.odoo = await rsCall('/api/rides/odoo'); } catch (e) { rd.odoo = {accounts: [], suggestions: {}, unavailable: e.message}; } rdDraw(); }
async function rdOpen(key) { try { rd.car = await rsCall('/api/rides/cars/' + encodeURIComponent(key)); rd.error = null; } catch (e) { rd.error = e.message; } rd.form = rd.run = rd.repl = null; rdDraw(); window.scrollTo({top: 0}); if (rd.car && !rd.car.odoo && !rd.odoo) rdLoadOdoo(); }
async function rdReload() {
  rd.odoo = null; if (rd.car) { try { rd.car = await rsCall('/api/rides/cars/' + encodeURIComponent(rd.car.key)); } catch (e) { rd.error = e.message; } } try { const j = await rsCall('/api/rides/cars'); rd.cars = j.cars; rd.catalog = j.catalog; rd.circuits = j.circuits; } catch {} rdDraw(); }

// ---- Liste des voitures -----------------------------------------------------------------------------------------------------------------
const rdChip = (state, n) => { const [c, l] = RD_STATE[state] || RD_STATE.none; return l ? `<span class="rd-chip ${c}">${state === 'ok' ? '' : '⚠ '}${esc(l)}${n ? ` · ${n}` : ''}</span>` : ''; };
const rdPhoto = (c, big) => c.photo ? `<img class="rd-photo${big ? ' big' : ''}" src="/api/rides/cars/${encodeURIComponent(c.key)}/photo?t=${rd.photoT || 0}" alt="" loading="lazy">` : `<div class="rd-photo${big ? ' big' : ''} none" aria-hidden="true">${esc(c.name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase())}</div>`;
function rdList() {
  if (!rd.cars) return '<p class="na">Chargement…</p>';
  const nNoBu = rd.cars.filter(c => !c.bu && !c.archived).length;
  const guessBar = nNoBu ? `<div class="note"><b>${nNoBu} voiture${nNoBu > 1 ? 's' : ''} sans BU.</b> <button type="button" data-rd="guessbu">Proposer les BU manquantes</button> <small class="na">d’après la catégorie (Rallye / Circuit) et le nom ; à vérifier ensuite voiture par voiture</small></div>` : '';
  const nNoOdoo = rd.cars.filter(c => !c.odoo && !c.archived).length;
  const odooBar = nNoOdoo ? `<div class="note"><b>${nNoOdoo} voiture${nNoOdoo > 1 ? 's' : ''} non reliée${nNoOdoo > 1 ? 's' : ''} à un compte analytique Odoo (axe CARS).</b> <button type="button" data-rd="linkodoo">Relier les correspondances sûres</button> <small class="na">comparaison des noms ; le reste se relie dans la fiche de chaque voiture</small></div>` : '';
  const nArch = rd.cars.filter(c => c.archived).length, shown = rd.cars.filter(c => rdBuOk(c) && (rd.showArchived || !c.archived));
  if (rd.cars.length && !shown.length) return '<p class="na">Aucune voiture dans cette BU : la BU d’une voiture se choisit dans sa fiche.</p>';
  if (!rd.cars.length) return '<p class="na">Aucune voiture de course : elles viennent de Planifier › Ressources › Véhicules (catégories Rally et Circuit).</p>';
  return guessBar + odooBar + (nArch ? `<label class="chk rd-rm"><input type="checkbox" id="rd-archived" ${rd.showArchived ? 'checked' : ''}> afficher les voitures archivées (${nArch})</label>` : '') + `<div class="rd-grid">${shown.map(c => `<button type="button" class="rd-card${c.archived ? ' arch' : ''}" data-rd="open" data-k="${esc(c.key)}">${rdPhoto(c)}<div class="rd-cbody"><b>${esc(c.name)}${c.archived ? ' <span class="rd-chip">Archivée</span>' : ''}</b><small class="na">${c.odoo ? '<span class="pos" title="' + esc(c.odoo.name) + '">Odoo ✓</span>' : '<span class="neg">non reliée à Odoo</span>'} · ${c.bu ? esc(RD_BULAB[c.bu]) : '<span class="neg">BU à définir</span>'} · ${c.category === 'rally' ? 'Rallye' : 'Circuit'} · ${c.parts} pièce${c.parts > 1 ? 's' : ''}</small>
    <div>${rdChip(c.state, c.alerts)}</div><small class="na">${rdKm(c.km_total)} km${c.hours_total ? ` · ${rdKm(c.hours_total)} h` : ''}${c.last_run ? ' · dernier run ' + fmtDate(c.last_run) : ''}</small></div></button>`).join('')}</div>`;
}

// ---- Liens : ressource Google Agenda et compte analytique Odoo (axe CARS) --------------------------------------------------------------------
function rdLinks(c) {
  const o = rd.odoo, link = (cfg && cfg.analytic_link && c.odoo) ? `<a class="olink" href="${esc(cfg.analytic_link.replace('{id}', encodeURIComponent(c.odoo.id)))}" target="_blank" rel="noopener noreferrer" title="Ouvrir dans Odoo">${esc(c.odoo.name)}</a>` : c.odoo ? esc(c.odoo.name) : '';
  let odoo;
  if (c.odoo) odoo = `<span class="pos">✓</span> ${link} <button type="button" class="mini" data-rd="unlinkodoo">Délier</button>`;
  else if (!o) odoo = '<small class="na">Chargement des comptes Odoo…</small>';
  else if (o.unavailable) odoo = `<small class="neg">${esc(o.unavailable)}</small>`;
  else { const s = o.suggestions[c.key], accts = o.accounts.slice().sort((a, b) => (s && a.id === s.id ? -1 : s && b.id === s.id ? 1 : a.name.localeCompare(b.name)));
    odoo = `<select class="sdin" id="rd-odoo-sel"><option value="">— Choisir le compte Odoo —</option>${accts.map(a => `<option value="${a.id}" ${s && a.id === s.id ? 'selected' : ''}>${esc(a.name)}${a.active ? '' : ' (archivé)'}${s && a.id === s.id ? ` — suggéré (${Math.round(s.score * 100)} %)` : ''}</option>`).join('')}</select> <button type="button" class="mini" data-rd="linkone">Relier</button>`; }
  return `<div class="note rd-links"><div><b>Ressource Google Agenda</b> <span class="pos">✓</span> ${esc(c.name)}</div><div><b>Compte analytique Odoo (axe CARS)</b> ${odoo}</div></div>`;
}

// ---- Arborescence des pièces ------------------------------------------------------------------------------------------------------------
function rdNode(n, depth) {
  if (n.removed_at && !rd.showRemoved) return '';
  const [cls] = RD_STATE[n.state] || RD_STATE.none, pad = `style="padding-left:${depth * 22}px"`;
  const bar = n.group ? '' : n.ratio == null ? '<small class="na">pas de limite</small>' : `<div class="rd-bar ${cls}"><i style="width:${Math.min(100, Math.round(n.ratio * 100))}%"></i></div><small>${rdPct(n.ratio)}</small>`;
  const nums = n.group ? '' : `<small class="na">${rdKm(n.km)} km${n.limit_km ? ' / ' + rdKm(n.limit_km) : ''}${n.hours || n.limit_hours ? ` · ${rdKm(n.hours)} h${n.limit_hours ? ' / ' + rdKm(n.limit_hours) : ''}` : ''}</small>`;
  const acts = n.removed_at ? `<small class="na">démontée le ${fmtDate(n.removed_at)}</small>` : `<span class="rd-acts">${depth < 3 ? `<button type="button" class="mini" data-rd="addpart" data-p="${esc(n.id)}" title="Ajouter dessous">＋</button>` : ''}<button type="button" class="mini" data-rd="editpart" data-p="${esc(n.id)}" title="Modifier">✎</button>${n.group ? '' : `<button type="button" class="mini" data-rd="replace" data-p="${esc(n.id)}" title="Remplacer (démonter et monter une neuve)">⟳</button>`}<button type="button" class="mini" data-rd="delpart" data-p="${esc(n.id)}" title="Supprimer">🗑</button></span>`;
  return `<div class="rd-row ${n.group ? 'grp' : ''} ${n.removed_at ? 'gone' : ''}" ${pad}><span class="rd-name">${n.group ? '▾ ' : ''}${esc(n.name)}${n.serial ? ` <small class="na">${esc(n.serial)}</small>` : ''}</span>${n.group && !n.removed_at ? rdChip(n.state === 'ok' ? 'none' : n.state) : ''}<span class="rd-meter">${bar}</span><span class="rd-nums">${nums}</span>${acts}</div>`
    + n.children.map(c => rdNode(c, depth + 1)).join('');
}
function rdPartForm() {
  const f = rd.form; if (!f) return '';
  const inp = (k, l, o = {}) => `<label class="sdfield"><span>${l}</span><input class="sdin" data-rd-f="${k}" value="${esc(f[k] ?? '')}" ${o.ph ? `placeholder="${o.ph}"` : ''} ${o.list ? `list="${o.list}"` : ''} ${o.w ? `style="max-width:${o.w}"` : ''}></label>`;
  return `<div class="note rd-form"><b>${f.id ? 'Modifier' : f.parent_id ? 'Ajouter sous « ' + esc(rdFind(f.parent_id).name) + ' »' : 'Ajouter à la voiture'}</b>
    <datalist id="rd-cat">${rd.catalog.map(i => `<option value="${esc(i.name)}">`).join('')}</datalist>
    <div class="sdgrid">${inp('name', 'Nom', {list: 'rd-cat', ph: 'Moteur, Turbo, Boîte…'})}${inp('serial', 'N° de série', {w: '200px'})}</div>
    <label class="chk"><input type="checkbox" data-rd-f="group" ${f.group ? 'checked' : ''} ${f.id ? 'disabled' : ''}> Simple groupe (ex. Motorisation) : son état est celui de ses pièces</label>
    ${f.group ? '' : `<div class="sdgrid">${inp('limit_km', 'Limite (km)', {w: '140px'})}${inp('limit_hours', 'Limite (heures)', {w: '140px'})}${inp('warn_pct', 'Alerte à (%)', {w: '120px'})}${inp('km_start', 'Km au montage', {w: '140px'})}${inp('hours_start', 'Heures au montage', {w: '140px'})}
      <label class="sdfield"><span>Monté le</span>${dpField('data-rd-f="mounted_from"', f.mounted_from || '')}</label></div><small class="na">Les runs de la voiture à partir de la date de montage comptent pour cette pièce ; laissez vide si elle est montée depuis toujours.</small>`}
    ${inp('notes', 'Notes')}
    <div class="sdbar"><button type="button" class="primary" data-rd="savepart" ${f.name && f.name.trim() ? '' : 'disabled'}>Enregistrer</button><button type="button" data-rd="cancelform">Annuler</button>${rd.msg ? `<span class="neg">${esc(rd.msg)}</span>` : ''}</div></div>`;
}
function rdFind(id, nodes = (rd.car || {}).tree || []) { for (const n of nodes) { if (n.id === id) return n; const r = rdFind(id, n.children); if (r) return r; } return null; }
function rdReplForm() {
  const r = rd.repl; if (!r) return '';
  const p = rdFind(r.id);
  return `<div class="note rd-form"><b>Remplacer « ${esc(p ? p.name : '')} »</b><p class="na">L’ancienne pièce est démontée (elle garde son historique) et une pièce neuve est montée au même endroit, compteurs repartis de zéro.</p>
    <div class="sdgrid"><label class="sdfield"><span>Date du remplacement</span>${dpField('data-rd-r="on"', r.on)}</label><label class="sdfield"><span>N° de série de la nouvelle</span><input class="sdin" data-rd-r="serial" value="${esc(r.serial)}"></label></div>
    <div class="sdbar"><button type="button" class="primary" data-rd="saverepl">Remplacer</button><button type="button" data-rd="cancelform">Annuler</button>${rd.msg ? `<span class="neg">${esc(rd.msg)}</span>` : ''}</div></div>`;
}

// ---- Runs -------------------------------------------------------------------------------------------------------------------------------
const rdRunBlank = () => ({id: null, date: rdToday(), name: '', kind: 'circuit', circuit: '', laps: '', stages: [{name: '', length_km: '', passes: 1}], km: '', hours: '', drivers: '', notes: ''});
function rdRunKm(r) {
  if (rdNum(r.km) != null) return rdNum(r.km);
  if (r.kind === 'rally') return r.stages.reduce((s, x) => s + (rdNum(x.length_km) || 0) * (parseInt(x.passes) || 0), 0);
  const c = rd.circuits.find(x => x.name === r.circuit), len = c ? c.length_km : rdNum(r.newlen); return len && r.laps ? len * parseInt(r.laps) : null;
}
function rdNewCirc() {
  const r = rd.run; if (!r || r.kind !== 'circuit' || !r.circuit.trim() || rd.circuits.find(c => c.name === r.circuit)) return '';
  return `<div class="note">Circuit inconnu : <label>longueur du tour (km) <input class="sdin" data-rd-u="newlen" value="${esc(r.newlen || '')}" style="max-width:100px" inputmode="decimal"></label> <small class="na">enregistrée avec le circuit au premier run, ou déduite d’un PDF du chronométreur plus tard</small></div>`;
}
function rdRunForm() {
  const r = rd.run; if (!r) return '';
  const km = rdRunKm(r);
  const circ = `<label class="sdfield"><span>Circuit</span><input class="sdin" data-rd-u="circuit" list="rd-circ" value="${esc(r.circuit)}" placeholder="Choisir ou saisir un circuit"></label><datalist id="rd-circ">${rd.circuits.map(c => `<option value="${esc(c.name)}">`).join('')}</datalist>
    <label class="sdfield"><span>Tours</span><input class="sdin" data-rd-u="laps" value="${esc(r.laps)}" style="max-width:100px" inputmode="numeric"></label>`;
  const stages = `<div class="rd-stages">${r.stages.map((s, i) => `<div class="sdbar"><input class="sdin" data-rd-s="name" data-i="${i}" value="${esc(s.name)}" placeholder="Spéciale" style="max-width:220px"><input class="sdin" data-rd-s="length_km" data-i="${i}" value="${esc(s.length_km)}" placeholder="km" style="max-width:90px" inputmode="decimal"><span>×</span><input class="sdin" data-rd-s="passes" data-i="${i}" value="${esc(s.passes)}" style="max-width:70px" inputmode="numeric"><small class="na">passage(s)</small><button type="button" class="mini" data-rd="delstage" data-i="${i}" aria-label="Retirer">✕</button></div>`).join('')}<button type="button" class="mini" data-rd="addstage">＋ Spéciale</button></div>`;
  return `<div class="note rd-form"><b>${r.id ? 'Modifier le run' : 'Nouveau run'}</b>
    <div class="sdgrid"><label class="sdfield"><span>Date</span>${dpField('data-rd-u="date"', r.date)}</label><label class="sdfield"><span>Nom</span><input class="sdin" data-rd-u="name" value="${esc(r.name)}" placeholder="Essais libres, Spa Six Hours…"></label>
    <div class="sdfield"><span>Type</span><div class="bu-filter"><button type="button" class="rs-pill" data-rd="kind" data-k="circuit" aria-pressed="${r.kind === 'circuit'}">Circuit</button><button type="button" class="rs-pill" data-rd="kind" data-k="rally" aria-pressed="${r.kind === 'rally'}">Rallye</button></div></div></div>
    ${r.kind === 'circuit' ? `<div class="sdgrid">${circ}</div><div id="rd-newcirc">${rdNewCirc()}</div>` : stages}
    <div class="sdgrid"><label class="sdfield"><span>Kilomètres (si connus : remplace le calcul)</span><input class="sdin" data-rd-u="km" value="${esc(r.km)}" style="max-width:140px" inputmode="decimal"></label><label class="sdfield"><span>Temps de roulage (heures)</span><input class="sdin" data-rd-u="hours" value="${esc(r.hours)}" style="max-width:140px" inputmode="decimal"></label>
    <label class="sdfield"><span>Pilote(s)</span><input class="sdin" data-rd-u="drivers" value="${esc(r.drivers)}" placeholder="Séparés par des virgules"></label></div>
    <label class="sdfield"><span>Notes</span><input class="sdin" data-rd-u="notes" value="${esc(r.notes)}"></label>
    <p class="rd-km">${km == null ? 'Kilomètres : à compléter' : `<b>${rdKm(km)} km</b> comptés pour toutes les pièces montées`}</p>
    <div class="sdbar"><button type="button" class="primary" data-rd="saverun" ${r.name.trim() && r.date ? '' : 'disabled'}>Enregistrer</button><button type="button" data-rd="cancelform">Annuler</button>${rd.msg ? `<span class="neg">${esc(rd.msg)}</span>` : ''}</div></div>`;
}
function rdRuns(c) {
  if (!c.runs_list.length) return '<p class="na">Aucun run enregistré.</p>';
  return table(['Date', 'Run', 'Circuit / rallye', 'Km', 'Heures', 'Pilote(s)', ''], c.runs_list.map(r => `<tr><td>${fmtDate(r.date)}</td><td class="prod">${esc(r.name)}</td><td>${r.kind === 'rally' ? 'Rallye' + (r.stages.length ? ` · ${r.stages.length} spéciale${r.stages.length > 1 ? 's' : ''}` : '') : esc(r.circuit || '')}${r.laps ? ` · ${r.laps} t` : ''}</td><td>${rdKm(r.km)}</td><td>${r.hours != null ? rdKm(r.hours) : '–'}</td><td>${esc((r.drivers || []).join(', '))}</td><td class="rd-acts"><button type="button" class="mini" data-rd="editrun" data-r="${esc(r.id)}" title="Modifier">✎</button><button type="button" class="mini" data-rd="delrun" data-r="${esc(r.id)}" title="Supprimer">🗑</button></td></tr>`), 'prodtable');
}

// ---- Réglages : catalogue de pièces et circuits ------------------------------------------------------------------------------------------
function rdSettings() {
  if (!rd.settings) return '';
  rd.cat = rd.cat || rd.catalog.map(i => ({...i}));
  const row = (i, k) => `<tr><td><input class="sdin" data-rd-c="name" data-i="${k}" value="${esc(i.name)}" style="min-width:150px"></td><td><input class="sdin" data-rd-c="group" data-i="${k}" value="${esc(i.group || '')}" style="min-width:130px" placeholder="Motorisation…"></td><td><input class="sdin" data-rd-c="limit_km" data-i="${k}" value="${esc(i.limit_km ?? '')}" style="width:90px"></td><td><input class="sdin" data-rd-c="limit_hours" data-i="${k}" value="${esc(i.limit_hours ?? '')}" style="width:80px"></td><td><input class="sdin" data-rd-c="warn_pct" data-i="${k}" value="${esc(i.warn_pct ?? 75)}" style="width:70px"></td><td><button type="button" class="mini" data-rd="delcat" data-i="${k}">✕</button></td></tr>`;
  return `<div class="note rd-form"><b>Catalogue de pièces</b><p class="na">Modèles proposés quand on ajoute une pièce : limite en km et / ou en heures, seuil d’alerte (75 % par défaut) propre à chaque type de pièce.</p>
    <div class="table-wrap"><table class="prodtable"><thead><tr><th>Pièce</th><th>Groupe</th><th>Limite km</th><th>Limite h</th><th>Alerte %</th><th></th></tr></thead><tbody>${rd.cat.map(row).join('')}</tbody></table></div>
    <div class="sdbar"><button type="button" class="mini" data-rd="addcat">＋ Pièce</button><button type="button" class="primary" data-rd="savecat">Enregistrer le catalogue</button></div>
    <b>Circuits</b><p class="na">Longueur du tour : sert à calculer les kilomètres (tours × longueur).</p>
    ${rd.circuits.length ? `<div class="rd-circs">${rd.circuits.map(c => `<span class="tagchip">${esc(c.name)} <small class="na">${rdKm(c.length_km)} km</small></span>`).join(' ')}</div>` : '<p class="na">Aucun circuit enregistré.</p>'}
    <div class="sdbar"><input class="sdin" data-rd-n="name" value="${esc(rd.circ.name)}" placeholder="Nom du circuit" style="max-width:240px"><input class="sdin" data-rd-n="length_km" value="${esc(rd.circ.length_km)}" placeholder="Longueur du tour (km)" style="max-width:190px" inputmode="decimal"><button type="button" data-rd="savecirc" ${rd.circ.name.trim() && rdNum(rd.circ.length_km) > 0 ? '' : 'disabled'}>Ajouter / mettre à jour</button></div></div>`;
}

// ---- Dessin -----------------------------------------------------------------------------------------------------------------------------
function rdDraw() {
  const el = document.getElementById('rd-view'); if (!el) return;
  const sav = [window.scrollX, window.scrollY];
  if (rd.error && !rd.cars) { el.innerHTML = `<p class="neg">${esc(rd.error)}</p>`; return; }
  const c = rd.car;
  const msg = rd.msg && !rd.form && !rd.run && !rd.repl ? `<p class="na">${esc(rd.msg)}</p>` : '';
  if (!c) {
    el.innerHTML = `<div class="sdbar"><button type="button" data-rd="settings">${rd.settings ? 'Fermer les réglages' : '⚙ Catalogue de pièces et circuits'}</button><button type="button" data-rd="reread" title="Relire les ressources Google (nom corrigé, voiture ajoutée)">↻ Relire Google</button>${rd.loading ? '<small class="na">Chargement…</small>' : ''}</div>${msg}${rdSettings()}${rdList()}`;
    return;
  }
  const alertsHtml = c.alerts_list.length ? `<div class="rd-alerts">${c.alerts_list.map(a => `<span class="rd-chip ${a.state === 'over' ? 'neg' : 'warn'}" title="${rdKm(a.km)} km${a.limit_km ? ' / ' + rdKm(a.limit_km) : ''}">${a.state === 'over' ? '⛔' : '⚠'} ${esc(a.path)} · ${rdPct(a.ratio)}</span>`).join(' ')}</div>` : '';
  el.innerHTML = `<div class="sdbar"><button type="button" data-rd="back">← Voitures</button><button type="button" data-rd="settings">${rd.settings ? 'Fermer les réglages' : '⚙ Catalogue de pièces et circuits'}</button><span class="wl-sp"></span><button type="button" data-rd="archive">${c.archived ? '↩ Désarchiver' : '🗄 Archiver'}</button>${c.archived ? '<button type="button" class="danger" data-rd="delcar">🗑 Supprimer définitivement</button>' : ''}</div>${c.archived ? '<p class="na">Voiture archivée : cachée du Garage, ses données sont conservées. « Supprimer définitivement » efface ses pièces, ses runs et sa photo.</p>' : ''}${msg}${rdSettings()}
    <div class="rd-head"><label class="rd-photobtn" title="Changer la photo">${rdPhoto(c, true)}<input type="file" id="rd-photo-in" accept="image/*" hidden><small class="na">📷 Photo</small></label>
      <div><h3 style="margin:0">${esc(c.name)}</h3><small class="na">${c.category === 'rally' ? 'Rallye' : 'Circuit'} · ${rdKm(c.km_total)} km${c.hours_total ? ` · ${rdKm(c.hours_total)} h` : ''} · ${c.runs} run${c.runs > 1 ? 's' : ''}</small><div>${rdChip(c.state, c.alerts)}</div>${rdBuPills(c)}</div></div>${rdLinks(c)}${alertsHtml}
    <h4 class="sub">Pièces <button type="button" class="mini" data-rd="addpart" data-p="">＋ Groupe ou pièce</button> <label class="chk rd-rm"><input type="checkbox" id="rd-removed" ${rd.showRemoved ? 'checked' : ''}> afficher les pièces démontées</label></h4>
    ${rd.form && !rd.form.id && !rd.form.parent_id || rd.form && rd.form.id && rdFind(rd.form.id) && !rdFind(rd.form.id).parent_id ? rdPartForm() : ''}
    <div class="rd-tree">${c.tree.length ? c.tree.map(n => rdNode(n, 0)).join('') : '<p class="na">Aucune pièce : ajoutez un groupe (par exemple Motorisation) puis ses pièces (Moteur, Turbo…), ou utilisez le catalogue.</p>'}</div>
    ${rd.form && (rd.form.parent_id || (rd.form.id && rdFind(rd.form.id) && rdFind(rd.form.id).parent_id)) ? rdPartForm() : ''}${rdReplForm()}
    <h4 class="sub">Roulages <button type="button" class="mini" data-rd="newrun">＋ Nouveau run</button></h4>${rdRunForm()}${rdRuns(c)}`;
  window.scrollTo(...sav);
}

// ---- Actions ----------------------------------------------------------------------------------------------------------------------------
const rdErr = e => { rd.msg = e.message; rdDraw(); };
function rdPartBody(f) {
  const o = {name: f.name.trim(), parent_id: f.parent_id || null, group: !!f.group, serial: f.serial || '', notes: f.notes || ''};
  if (!f.group) Object.assign(o, {limit_km: rdNum(f.limit_km), limit_hours: rdNum(f.limit_hours), warn_pct: rdNum(f.warn_pct) || 75, km_start: rdNum(f.km_start) || 0, hours_start: rdNum(f.hours_start) || 0, mounted_from: f.mounted_from || null});
  return o;
}
document.addEventListener('input', e => {
  const t = e.target; if (!document.getElementById('rd-view')) return;
  if (t.dataset.rdF !== undefined && rd.form && !t.classList.contains('dp-h')) {
    rd.form[t.dataset.rdF] = t.type === 'checkbox' ? t.checked : t.value;
    if (t.dataset.rdF === 'name') { const it = rd.catalog.find(i => i.name.toLowerCase() === t.value.trim().toLowerCase()); if (it && !rd.form.id && !rd.form._cat) { Object.assign(rd.form, {limit_km: it.limit_km ?? '', limit_hours: it.limit_hours ?? '', warn_pct: it.warn_pct ?? 75, _cat: true}); rdDraw(); const n = document.querySelector('[data-rd-f=name]'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } return; } }
    const b = document.querySelector('[data-rd=savepart]'); if (b) b.disabled = !rd.form.name.trim();
  } else if (t.dataset.rdU !== undefined && rd.run && !t.classList.contains('dp-h')) { rd.run[t.dataset.rdU] = t.value; const needRedraw = false; if (t.dataset.rdU === 'circuit') { const nc = document.getElementById('rd-newcirc'); if (nc) nc.innerHTML = rdNewCirc(); } const ph = document.querySelector('.rd-km'); if (!needRedraw && ph) { const km = rdRunKm(rd.run); ph.innerHTML = km == null ? 'Kilomètres : à compléter' : `<b>${rdKm(km)} km</b> comptés pour toutes les pièces montées`; } const b = document.querySelector('[data-rd=saverun]'); if (b) b.disabled = !(rd.run.name.trim() && rd.run.date); }
  else if (t.dataset.rdS !== undefined && rd.run) { rd.run.stages[+t.dataset.i][t.dataset.rdS] = t.value; const ph = document.querySelector('.rd-km'); if (ph) { const km = rdRunKm(rd.run); ph.innerHTML = km == null ? 'Kilomètres : à compléter' : `<b>${rdKm(km)} km</b> comptés pour toutes les pièces montées`; } }
  else if (t.dataset.rdR !== undefined && rd.repl && !t.classList.contains('dp-h')) rd.repl[t.dataset.rdR] = t.value;
  else if (t.dataset.rdC !== undefined && rd.cat) rd.cat[+t.dataset.i][t.dataset.rdC] = t.value;
  else if (t.dataset.rdN !== undefined) { rd.circ[t.dataset.rdN] = t.value; const b = document.querySelector('[data-rd=savecirc]'); if (b) b.disabled = !(rd.circ.name.trim() && rdNum(rd.circ.length_km) > 0); }
});
document.addEventListener('change', async e => {
  const t = e.target; if (!document.getElementById('rd-view')) return;
  if (t.classList.contains('dp-h')) {               // dates (calendrier maison)
    if (t.dataset.rdF === 'mounted_from' && rd.form) rd.form.mounted_from = t.value || '';
    else if (t.dataset.rdU === 'date' && rd.run) { rd.run.date = t.value; const b = document.querySelector('[data-rd=saverun]'); if (b) b.disabled = !(rd.run.name.trim() && rd.run.date); }
    else if (t.dataset.rdR === 'on' && rd.repl) rd.repl.on = t.value;
    return;
  }
  if (t.id === 'rd-archived') { rd.showArchived = t.checked; rdDraw(); return; }
  if (t.id === 'rd-removed') { rd.showRemoved = t.checked; rdDraw(); return; }
  if (t.dataset.rdF === 'group' && rd.form) { rd.form.group = t.checked; rdDraw(); return; }
  if (t.id === 'rd-photo-in' && t.files[0]) {
    const f = t.files[0]; t.value = '';
    try {
      const img = await createImageBitmap(f), k = Math.min(1, 1400 / Math.max(img.width, img.height)), c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      const blob = await new Promise(ok => c.toBlob(ok, 'image/jpeg', .85));
      const r = await fetch(`/api/rides/cars/${encodeURIComponent(rd.car.key)}/photo`, {method: 'POST', headers: {...rsAuth(), 'Content-Type': 'image/jpeg'}, body: blob}), j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Envoi impossible');
      rd.photoT = Date.now(); rd.car.photo = true; await rdReload();
    } catch (err) { rd.msg = err.message; rdDraw(); }
  }
});
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-rd]'); if (!b || !document.getElementById('rd-view')) return;
  const a = b.dataset.rd, k = rd.car && rd.car.key;
  try {
    if (a === 'open') return rdOpen(b.dataset.k);
    if (a === 'setbu') { const bu = rd.car.bu === b.dataset.b ? '' : b.dataset.b; await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({bu})}); rd.car.bu = bu; return rdReload(); }
    if (a === 'linkodoo') { const j = await rsCall('/api/rides/link-odoo', {method: 'POST', body: '{}'}); rd.msg = j.linked.length ? `Reliées à Odoo : ` + j.linked.map(x => `${x.name} → ${x.odoo}`).join(' · ') + '. À vérifier dans chaque fiche.' : 'Aucune correspondance assez sûre : reliez les voitures une par une dans leur fiche.'; return rdReload(); }
    if (a === 'linkone') { const v = parseInt((document.getElementById('rd-odoo-sel') || {}).value); if (!v) throw new Error('Choisissez un compte Odoo.'); await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({odoo_id: v})}); return rdReload(); }
    if (a === 'unlinkodoo') { await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({odoo_id: 0})}); rd.odoo = null; await rdReload(); if (rd.car && !rd.car.odoo) rdLoadOdoo(); return; }
    if (a === 'guessbu') { const j = await rsCall('/api/rides/guess-bu', {method: 'POST', body: '{}'}); rd.msg = `BU proposées pour ${j.set.length} voiture(s) : ` + j.set.map(x => `${x.name} → ${RD_BULAB[x.bu]}`).join(' · ') + '. À vérifier dans chaque fiche.'; return rdReload(); }
    if (a === 'reread') { await rdLoad(true); return; }
    if (a === 'archive') { await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({archived: !rd.car.archived})}); rd.car.archived = !rd.car.archived; if (rd.car.archived) { rd.car = null; } return rdReload(); }
    if (a === 'delcar') { const c = rd.car; if (!confirm(`Supprimer définitivement « ${c.name} » ?\n\nSes ${c.parts} pièce(s), ses ${c.runs} run(s) et sa photo seront effacés, sans retour possible.${'\n\n'}Le véhicule reste dans Planifier › Ressources : laissez-le archivé s'il y figure encore.`)) return; const j = await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'DELETE'}); rd.car = null; rd.msg = `Données supprimées (${j.parts} pièce(s), ${j.runs} run(s)).`; return rdReload(); }
    if (a === 'back') { rd.car = null; rd.form = rd.run = rd.repl = null; rd.msg = null; await rdReload(); return; }
    if (a === 'settings') { rd.settings = !rd.settings; rd.cat = null; return rdDraw(); }
    if (a === 'addpart') { rd.form = {id: null, parent_id: b.dataset.p || null, name: '', group: false, serial: '', limit_km: '', limit_hours: '', warn_pct: 75, km_start: '', hours_start: '', mounted_from: '', notes: ''}; rd.run = rd.repl = null; rd.msg = null; return rdDraw(); }
    if (a === 'editpart') { const n = rdFind(b.dataset.p); rd.form = {id: n.id, parent_id: n.parent_id, name: n.name, group: !!n.group, serial: n.serial || '', limit_km: n.limit_km ?? '', limit_hours: n.limit_hours ?? '', warn_pct: n.warn_pct ?? 75, km_start: n.km_start || '', hours_start: n.hours_start || '', mounted_from: n.mounted_from || '', notes: n.notes || ''}; rd.run = rd.repl = null; rd.msg = null; return rdDraw(); }
    if (a === 'savepart') { const f = rd.form, body = rdPartBody(f); await rsCall(f.id ? '/api/rides/parts/' + encodeURIComponent(f.id) : `/api/rides/cars/${encodeURIComponent(k)}/parts`, {method: f.id ? 'PUT' : 'POST', body: JSON.stringify(body)}); rd.form = null; rd.msg = null; return rdReload(); }
    if (a === 'delpart') { const n = rdFind(b.dataset.p); if (!confirm(`Supprimer « ${n.name} »${n.children.length ? ' et ses sous-éléments' : ''} ? Pour une pièce usée, préférez « Remplacer » : elle garde son historique.`)) return; await rsCall('/api/rides/parts/' + encodeURIComponent(n.id), {method: 'DELETE'}); return rdReload(); }
    if (a === 'replace') { rd.repl = {id: b.dataset.p, on: rdToday(), serial: ''}; rd.form = rd.run = null; rd.msg = null; return rdDraw(); }
    if (a === 'saverepl') { const r = rd.repl; await rsCall(`/api/rides/parts/${encodeURIComponent(r.id)}/replace`, {method: 'POST', body: JSON.stringify({on: r.on, serial: r.serial})}); rd.repl = null; rd.msg = null; return rdReload(); }
    if (a === 'cancelform') { rd.form = rd.run = rd.repl = null; rd.msg = null; return rdDraw(); }
    if (a === 'newrun') { rd.run = rdRunBlank(); rd.form = rd.repl = null; rd.msg = null; return rdDraw(); }
    if (a === 'editrun') { const r = rd.car.runs_list.find(x => x.id === b.dataset.r); rd.run = {id: r.id, date: r.date, name: r.name, kind: r.kind, circuit: r.circuit || '', laps: r.laps || '', stages: r.stages.length ? r.stages.map(s => ({...s})) : [{name: '', length_km: '', passes: 1}], km: r.source === 'manual' && !r.laps && !r.stages.length ? r.km : '', hours: r.hours ?? '', drivers: (r.drivers || []).join(', '), notes: r.notes || ''}; rd.form = rd.repl = null; rd.msg = null; return rdDraw(); }
    if (a === 'kind') { rd.run.kind = b.dataset.k; return rdDraw(); }
    if (a === 'addstage') { rd.run.stages.push({name: '', length_km: '', passes: 1}); return rdDraw(); }
    if (a === 'delstage') { rd.run.stages.splice(+b.dataset.i, 1); if (!rd.run.stages.length) rd.run.stages.push({name: '', length_km: '', passes: 1}); return rdDraw(); }
    if (a === 'saverun') {
      const r = rd.run, known = rd.circuits.find(c => c.name === r.circuit);
      if (r.kind === 'circuit' && r.circuit.trim() && !known && rdNum(r.newlen) > 0) await rsCall('/api/rides/circuits', {method: 'POST', body: JSON.stringify({name: r.circuit.trim(), length_km: rdNum(r.newlen)})});
      else if (r.kind === 'circuit' && r.circuit.trim() && !known && parseInt(r.laps) > 0 && rdNum(r.km) == null) throw new Error('Indiquez la longueur du tour de ce circuit, ou saisissez les kilomètres.');
      const circ = r.kind === 'circuit' ? r.circuit.trim() : '';
      if (circ && !known && rdNum(r.newlen) > 0) { const j = await rsCall('/api/rides/cars'); rd.circuits = j.circuits; }
      const body = {date: r.date, name: r.name.trim(), kind: r.kind, circuit: circ, laps: r.kind === 'circuit' ? (parseInt(r.laps) || 0) : 0,
        stages: r.kind === 'rally' ? r.stages.filter(s => rdNum(s.length_km) > 0).map(s => ({name: s.name || '', length_km: rdNum(s.length_km), passes: parseInt(s.passes) || 1})) : [],
        km: rdNum(r.km), hours: rdNum(r.hours), drivers: r.drivers.split(',').map(x => x.trim()).filter(Boolean), notes: r.notes || ''};
      await rsCall(r.id ? '/api/rides/runs/' + encodeURIComponent(r.id) : `/api/rides/cars/${encodeURIComponent(k)}/runs`, {method: r.id ? 'PUT' : 'POST', body: JSON.stringify(body)}); rd.run = null; rd.msg = null; return rdReload();
    }
    if (a === 'delrun') { if (!confirm('Supprimer ce run ? Les kilomètres des pièces seront recalculés.')) return; await rsCall('/api/rides/runs/' + encodeURIComponent(b.dataset.r), {method: 'DELETE'}); return rdReload(); }
    if (a === 'addcat') { rd.cat.push({name: '', group: '', limit_km: '', limit_hours: '', warn_pct: 75}); return rdDraw(); }
    if (a === 'delcat') { rd.cat.splice(+b.dataset.i, 1); return rdDraw(); }
    if (a === 'savecat') { const items = rd.cat.filter(i => i.name.trim()).map(i => ({name: i.name.trim(), group: (i.group || '').trim(), limit_km: rdNum(i.limit_km), limit_hours: rdNum(i.limit_hours), warn_pct: rdNum(i.warn_pct) || 75})); const j = await rsCall('/api/rides/catalog', {method: 'PUT', body: JSON.stringify({items})}); rd.catalog = j.catalog; rd.cat = null; rd.msg = 'Catalogue enregistré.'; return rdDraw(); }
    if (a === 'savecirc') { const j = await rsCall('/api/rides/circuits', {method: 'POST', body: JSON.stringify({name: rd.circ.name.trim(), length_km: rdNum(rd.circ.length_km)})}); rd.circuits = rd.circuits.filter(c => c.id !== j.id).concat([j]).sort((x, y) => x.name.localeCompare(y.name)); rd.circ = {name: '', length_km: ''}; return rdDraw(); }
  } catch (err) { rdErr(err); }
});
