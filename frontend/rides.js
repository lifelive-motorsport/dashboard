// Roulages (Consigner › Roulages) : kilométrage et temps de roulage des voitures de course et de leurs pièces (remplace RPM).
// Voitures = véhicules de course de Ressources ; pièces en arborescence (Groupe › Pièce › Sous-pièce) avec limite et seuil d'alerte ; runs = tours × circuit, ou spéciales × passages.
const rd = {cars: null, catalog: [], circuits: [], car: null, loading: false, error: null, msg: null, form: null, run: null, repl: null, settings: false, showRemoved: false, showArchived: false, odoo: null, templates: null, mf: null, cat: null, circ: {name: '', length_km: ''}};
const rdKm = v => v == null ? '–' : new Intl.NumberFormat(LOCALE(), {maximumFractionDigits: 1}).format(v);
const rdPct = r => r == null ? '' : Math.round(r * 100) + ' %';
const RD_STATE = {over: ['neg', 'Limite dépassée'], warn: ['warn', 'À surveiller'], ok: ['pos', 'OK'], none: ['na', '']};
const rdNum = v => v === '' || v == null ? null : parseFloat(String(v).replace(',', '.'));
const rdToday = () => new Date().toISOString().slice(0, 10);
const RD_MAINT = [['inspection', 'Contrôle'], ['fluids', 'Vidange et nouveaux fluides'], ['revision', 'Révision 1'], ['revision2', 'Révision 2'], ['replace', 'Remplacement']];       // ordre chronologique logique
const RD_MLAB = Object.fromEntries(RD_MAINT);
const rdLimBlank = () => ({limit_km: '', limit_hours: '', limit_events: '', warn_pct: 75, note: ''});
const rdLimOf = x => ({limit_km: x.limit_km ?? '', limit_hours: x.limit_hours ?? '', limit_events: x.limit_events ?? '', warn_pct: x.warn_pct ?? 75, note: x.note ?? x.limit_note ?? ''});
// Ligne d'intervalle d'un type de maintenance (partagée par la fiche voiture et le Magasin de pièces) : km, heures, roulages (sauf remplacement), alerte (sauf contrôle), critère
const rdLimRow = (t, L, attr) => { const f = (k, lab, w, ph) => `<label class="rd-lf" style="width:${w}"><span>${esc(tx(lab))}</span><input class="sdin" ${attr(k)} value="${esc(L[k] ?? '')}" inputmode="decimal" placeholder="${ph}"></label>`;
  return `<div class="rd-limrow"><div class="rd-lt"><b>${esc(RD_MLAB[t])}</b><small class="na">${esc(tx(t === 'replace' ? 'limite de vie' : 'tous les'))}</small></div>${f('limit_km', 'km', '84px', 'km')}${f('limit_hours', 'heures', '70px', 'h')}${t === 'replace' ? '<span class="rd-lf" style="width:78px"></span>' : f('limit_events', 'roulages', '78px', '1')}${t === 'inspection' ? '<span class="rd-lf" style="width:72px"></span>' : f('warn_pct', 'alerte %', '72px', '75')}<label class="rd-lf rd-lnote"><span>${esc(tx('Critère'))}</span><input class="sdin" ${attr('note')} value="${esc(L.note ?? '')}" maxlength="160" placeholder="${esc(tx('critère, ex. quand abîmé'))}"></label></div>`; };
const RD_BUSYM = {XC: 'xc', MODERN_RALLY: 'mr', HISTORIC_RALLY: 'hrl', HISTORIC_RACING: 'hrc'}, RD_BULAB = {XC: 'XC', MODERN_RALLY: 'Modern Rally', HISTORIC_RALLY: 'Historic Rally', HISTORIC_RACING: 'Historic Racing'};
const rdBuOk = c => buSel === 'all' || buMatchesFilter(RD_BUSYM[c.bu] || 'lifelive', buSel);      // une voiture sans BU n'apparaît que dans « ALL »
const rdBuPills = (c) => `<div class="bu-filter rd-bupills" role="group" aria-label="BU de la voiture">${Object.entries(RD_BUSYM).map(([k, sym]) => `<button type="button" class="rs-pill rs-ico" data-rd="setbu" data-b="${k}" aria-pressed="${c.bu === k}" title="${esc(RD_BULAB[k])}" aria-label="${esc(RD_BULAB[k])}">${BuSymbol(sym, {size: 15})}</button>`).join('')}${c.bu ? '' : ' <small class="neg">BU à définir</small>'}</div>`;

function ridesBlocks() { return [{static: '<section class="block" data-bid="rd"><div id="rd-view"><p class="na">Chargement…</p></div></section>'}]; }

async function rdLoad(force) {
  rd.loading = true; rdDraw();
  try {
    const j = await rsCall('/api/rides/cars' + (force ? '?refresh=1' : '')); rd.cars = j.cars; rd.catalog = j.catalog; rd.circuits = j.circuits; rd.ensembles = j.ensembles || rd.ensembles; rd.error = null;
    if (rd.car) rd.car = await rsCall('/api/rides/cars/' + encodeURIComponent(rd.car.key));
  } catch (e) { rd.error = e.message; }
  rd.loading = false; rdDraw();
  if (rd.want) { const k = rd.want; rd.want = null; if (rd.cars && rd.cars.some(c => c.key === k)) rdOpen(k); }
}
async function rdLoadTemplates() { try { rd.templates = (await rsCall('/api/rides/templates')).templates; } catch { rd.templates = []; } rdDraw(); }
async function rdLoadOdoo() { try { rd.odoo = await rsCall('/api/rides/odoo'); } catch (e) { rd.odoo = {accounts: [], suggestions: {}, unavailable: e.message}; } rdDraw(); }
async function rdOpen(key) { try { rd.car = await rsCall('/api/rides/cars/' + encodeURIComponent(key)); rd.error = null; } catch (e) { rd.error = e.message; } rd.form = rd.run = rd.repl = null; rdDraw(); window.scrollTo({top: 0}); if (rd.car && !rd.car.odoo && !rd.odoo) rdLoadOdoo(); if (rd.car && !rd.templates) rdLoadTemplates(); }
async function rdReload() { if (rd.car) { try { rd.car = await rsCall('/api/rides/cars/' + encodeURIComponent(rd.car.key)); } catch (e) { rd.error = e.message; } } try { const j = await rsCall('/api/rides/cars'); rd.cars = j.cars; rd.catalog = j.catalog; rd.circuits = j.circuits; rd.ensembles = j.ensembles || rd.ensembles; } catch {} rdDraw(); }

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
  return guessBar + odooBar + `<div class="rd-grid">${shown.map(c => `<button type="button" class="rd-card${c.archived ? ' arch' : ''}" data-rd="open" data-k="${esc(c.key)}">${rdPhoto(c)}<div class="rd-cbody"><b>${c.race_number ? `<span class="rd-no">#${esc(c.race_number)}</span> ` : ''}${esc(c.name)}${c.archived ? ' <span class="rd-chip">Archivée</span>' : ''}</b><small class="na">${c.odoo ? '<span class="pos" title="' + esc(c.odoo.name) + '">Odoo ✓</span>' : '<span class="neg">non reliée à Odoo</span>'} · ${c.bu ? esc(RD_BULAB[c.bu]) : '<span class="neg">BU à définir</span>'} · ${c.category === 'rally' ? 'Rallye' : 'Circuit'} · ${c.parts} pièce${c.parts > 1 ? 's' : ''}</small>
    <div>${rdChip(c.state, c.alerts)}${c.doc_alerts ? ` <span class="rd-chip ${c.doc_over ? 'neg' : 'warn'}" title="${esc(t('Documents à renouveler'))}">📄 ${c.doc_alerts}</span>` : ''}</div><small class="na">${rdKm(c.km_total)} km${c.hours_total ? ` · ${rdKm(c.hours_total)} h` : ''}${c.last_run ? ' · dernier run ' + fmtDate(c.last_run) : ''}</small></div></button>`).join('')}</div>`;
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
  const tpl = c.template ? `<span class="pos">✓</span> ${esc(c.template.name)} <small class="na">(les éléments déjà présents sont conservés, les manquants sont ajoutés)</small> ` : '<small class="na">aucun</small> ';
  const tsel = rd.templates && rd.templates.length ? `<select class="sdin" id="rd-tpl-sel"><option value="">— Choisir un modèle —</option>${rd.templates.map(t => `<option value="${esc(t.id)}" ${c.template && c.template.id === t.id ? 'selected' : ''}>${esc(t.name)}</option>`).join('')}</select> <button type="button" class="mini" data-rd="applytpl">${c.template ? 'Réappliquer' : 'Appliquer'}</button>` : rd.templates ? '<small class="na">Aucun modèle : créez-en dans « Magasin de pièces ».</small>' : '<small class="na">Chargement des modèles…</small>';
  return `<div class="note rd-links"><div><b>Ressource Google Agenda</b> <span class="pos">✓</span> ${esc(c.name)}</div><div><b>Compte analytique Odoo (axe CARS)</b> ${odoo}</div><div><b>Modèle d’architecture</b> ${tpl}${tsel}</div></div>`;
}

// ---- Arborescence des pièces ------------------------------------------------------------------------------------------------------------
function rdMeter(m) {
  const cls = (RD_STATE[m.state] || RD_STATE.none)[0];
  const bar = m.ratio == null ? `<small class="na">${esc(tx(m.note ? 'sur condition' : 'pas de limite'))}</small>` : `<div class="rd-bar ${cls}"><i style="width:${Math.min(100, Math.round(m.ratio * 100))}%"></i></div><small>${rdPct(m.ratio)}</small>`;
  const nums = `${rdKm(m.km)} km${m.limit_km ? ' / ' + rdKm(m.limit_km) : ''}${m.hours || m.limit_hours ? ` · ${rdKm(m.hours)} h${m.limit_hours ? ' / ' + rdKm(m.limit_hours) : ''}` : ''}${m.limit_events ? ` · ${m.events} / ${m.limit_events} ${esc(tx('roulages'))}` : ''}${m.last ? ` · faite le ${fmtDate(m.last)}` : m.type !== 'replace' ? ' · jamais faite' : ''}${m.note ? ` · ${esc(m.note)}` : ''}`;
  return `<div class="rd-m"><span class="rd-ml">${esc(m.label)}</span><span class="rd-meter">${bar}</span><small class="na rd-mn">${nums}</small></div>`;
}
const rdHasFold = ns => ns.some(n => n.children.length > 0);
const rdHasRemoved = ns => ns.some(n => n.removed_at || rdHasRemoved(n.children));
const rdCount = n => n.children.reduce((t, c) => t + (c.removed_at ? 0 : 1 + rdCount(c)), 0);
const rdFolded = (n, depth) => n.children.some(c => !c.removed_at || rd.showRemoved) && (rd.fold && n.id in rd.fold ? rd.fold[n.id] : depth === 0 && !['warn', 'over'].includes(n.state));    // les ensembles sans alerte sont repliés par défaut
function rdFoldAll(on) { rd.fold = rd.fold || {}; const walk = (ns, d) => ns.forEach(n => { if (n.children.length) { rd.fold[n.id] = on; walk(n.children, d + 1); } }); walk((rd.car || {}).tree || [], 0); }
function rdNode(n, depth) {
  if (n.removed_at && !rd.showRemoved) return '';
  const folded = rdFolded(n, depth), hasKids = n.children.some(c => !c.removed_at || rd.showRemoved);
  const pad = `style="padding-left:${depth * 22}px"`;
  const ms = n.group ? '' : (n.meters && n.meters.length) ? n.meters.map(rdMeter).join('') : `<div class="rd-m"><small class="na">${rdKm(n.km)} km · pas de maintenance suivie</small></div>`;
  const hasMaint = (n.types || []).some(t => t !== 'replace');
  const acts = n.removed_at ? `<small class="na">démontée le ${fmtDate(n.removed_at)}</small>` : `<span class="rd-acts">${depth < 3 ? `<button type="button" class="mini" data-rd="addpart" data-p="${esc(n.id)}" title="Ajouter dessous">＋</button>` : ''}${hasMaint ? `<button type="button" class="mini" data-rd="maint" data-p="${esc(n.id)}" title="Enregistrer une révision / une vidange">🛠</button>` : ''}<button type="button" class="mini" data-rd="editpart" data-p="${esc(n.id)}" title="Modifier">✎</button>${n.group ? '' : `<button type="button" class="mini" data-rd="replace" data-p="${esc(n.id)}" title="Remplacer (démonter et monter une neuve)">⟳</button>`}<button type="button" class="mini" data-rd="delpart" data-p="${esc(n.id)}" title="Supprimer">🗑</button></span>`;
  return `<div class="rd-row ${n.group ? 'grp' : ''} ${n.removed_at ? 'gone' : ''}" ${pad}><span class="rd-name">${hasKids ? `<button type="button" class="rd-fold" data-rd="fold" data-p="${esc(n.id)}" aria-label="${esc(tx(folded ? 'Déplier' : 'Replier'))}">${folded ? '▸' : '▾'}</button>` : n.group ? '▾ ' : ''}${esc(n.name)}${n.reference ? ` <small class="na">${esc(n.reference)}</small>` : ''}${n.serial ? ` <small class="na">${esc(n.serial)}</small>` : ''}${folded ? ` <small class="na">· ${rdCount(n)} ${esc(tx('éléments'))}</small>` : ''}</span>${n.group && !n.removed_at ? rdChip(n.state === 'ok' ? 'none' : n.state) : ''}<span class="rd-ms">${ms}</span>${acts}</div>`
    + (folded ? '' : n.children.map(c => rdNode(c, depth + 1)).join(''));
}
function rdPartForm() {
  const f = rd.form; if (!f) return '';
  const inp = (k, l, o = {}) => `<label class="sdfield"><span>${l}</span><input class="sdin" data-rd-f="${k}" value="${esc(f[k] ?? '')}" ${o.ph ? `placeholder="${o.ph}"` : ''} ${o.w ? `style="max-width:${o.w}"` : ''}></label>`;
  const lim = t => rdLimRow(t, f.lim[t], k => `data-rd-fl="${t}.${k}"`);
  const root = !f.parent_id && !(f.id && rdFind(f.id) && rdFind(f.id).parent_id);
  const used = new Set(((rd.car || {}).tree || []).filter(n => !n.removed_at && n.id !== f.id).map(n => n.name));
  const nameField = root ? `<label class="sdfield"><span>Ensemble</span><select class="sdin" data-rd-f="name"><option value="">—</option>${(rd.ensembles || []).map(e => `<option value="${esc(e)}" ${f.name === e ? 'selected' : ''} ${used.has(e) ? 'disabled' : ''}>${esc(e)}</option>`).join('')}${f.name && !(rd.ensembles || []).includes(f.name) ? `<option value="${esc(f.name)}" selected>${esc(f.name)}</option>` : ''}</select></label>` : inp('name', 'Nom', {ph: 'Moteur, Turbo, Boîte…'});
  return `<div class="note rd-form"><b>${f.id ? 'Modifier' : f.parent_id ? 'Ajouter sous « ' + esc(rdFind(f.parent_id).name) + ' »' : 'Ajouter à la voiture'}</b>
    <div class="sdgrid">${nameField}${root ? '' : inp('reference', 'Référence constructeur', {w: '220px'})}${root ? '' : inp('serial', 'N° de série', {w: '200px'})}</div>
    ${root ? '' : `<label class="chk"><input type="checkbox" data-rd-f="group" ${f.group ? 'checked' : ''} ${f.id ? 'disabled' : ''}> Regroupement : pas de compteur propre, son état est celui de ses éléments</label>`}
    ${f.group ? '' : `<div class="rd-types"><b>Maintenances suivies</b>${RD_MAINT.map(([t, l]) => `<label class="chk"><input type="checkbox" data-rd-ft="${t}" ${f.types.includes(t) ? 'checked' : ''}> ${esc(l)}</label>`).join('')}</div>
      ${RD_MAINT.filter(([t]) => f.types.includes(t)).map(([t]) => lim(t)).join("")}
      <div class="sdgrid">${inp('km_start', 'Km au montage', {w: '140px'})}${inp('hours_start', 'Heures au montage', {w: '140px'})}
      <label class="sdfield"><span>Monté le</span>${dpField('data-rd-f="mounted_from"', f.mounted_from || '')}</label></div><small class="na">Les runs de la voiture à partir de la date de montage comptent pour cette pièce ; laissez vide si elle est montée depuis toujours. Les révisions, la vidange et le contrôle repartent à chaque maintenance enregistrée (🛠).</small>`}
    ${inp('notes', 'Notes')}
    <div class="sdbar"><button type="button" class="primary" data-rd="savepart" ${f.name && f.name.trim() ? '' : 'disabled'}>Enregistrer</button><button type="button" data-rd="cancelform">Annuler</button>${rd.msg ? `<span class="neg">${esc(rd.msg)}</span>` : ''}</div></div>`;
}
function rdMaintForm() {
  const m = rd.mf; if (!m) return '';
  const p = rdFind(m.part_id); if (!p) return '';
  const types = (p.types || []).filter(t => t !== 'replace');
  return `<div class="note rd-form"><b>Maintenance sur « ${esc(p.name)} »</b><p class="na">Le compteur du type choisi repart de cette date (les runs de ce jour comptent après). Pour un remplacement, utilisez ⟳.</p>
    <div class="sdgrid"><label class="sdfield"><span>Type</span><select class="sdin" data-rd-m="type">${types.map(t => `<option value="${t}" ${m.type === t ? 'selected' : ''}>${esc(RD_MLAB[t])}</option>`).join('')}</select></label>
    <label class="sdfield"><span>Date</span>${dpField('data-rd-m="date"', m.date)}</label><label class="sdfield"><span>Notes</span><input class="sdin" data-rd-m="notes" value="${esc(m.notes)}"></label></div>
    <div class="sdbar"><button type="button" class="primary" data-rd="savemaint">Enregistrer la maintenance</button><button type="button" data-rd="cancelform">Fermer</button>${rd.msg ? `<span class="neg">${esc(rd.msg)}</span>` : ''}</div>
    ${(p.history || []).length ? `<div class="rd-hist"><b>Historique</b>${p.history.map(h => `<div>${fmtDate(h.date)} · ${esc(RD_MLAB[h.type] || h.type)}${h.notes ? ' · ' + esc(h.notes) : ''} <button type="button" class="mini" data-rd="delmaint" data-m="${esc(h.id)}" title="Supprimer cette maintenance">✕</button></div>`).join('')}</div>` : ''}</div>`;
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
  return `<div class="note rd-form"><b>Circuits</b><p class="na">Longueur du tour : sert à calculer les kilomètres (tours × longueur). Les architectures de pièces se construisent dans « Magasin de pièces ».</p>
    ${rd.circuits.length ? `<div class="rd-circs">${rd.circuits.map(c => `<span class="tagchip">${esc(c.name)} <small class="na">${rdKm(c.length_km)} km</small></span>`).join(' ')}</div>` : '<p class="na">Aucun circuit enregistré.</p>'}
    <div class="sdbar"><input class="sdin" data-rd-n="name" value="${esc(rd.circ.name)}" placeholder="Nom du circuit" style="max-width:240px"><input class="sdin" data-rd-n="length_km" value="${esc(rd.circ.length_km)}" placeholder="Longueur du tour (km)" style="max-width:190px" inputmode="decimal"><button type="button" data-rd="savecirc" ${rd.circ.name.trim() && rdNum(rd.circ.length_km) > 0 ? '' : 'disabled'}>Ajouter / mettre à jour</button></div></div>`;
}

// ---- Documents et validités de la voiture ---------------------------------------------------------------------------------------------------
const rdDocChip = d => d.state === 'over' ? `<span class="rd-chip neg">⛔ ${esc(t('Échu depuis'))} ${-d.days} ${esc(t(-d.days > 1 ? 'jours' : 'jour'))}</span>` : d.state === 'warn' ? `<span class="rd-chip warn">⚠ ${esc(t('Échéance dans'))} ${d.days} ${esc(t(d.days > 1 ? 'jours' : 'jour'))}</span>` : d.state === 'ok' ? `<span class="rd-chip pos">✓ ${esc(t('Valide'))}</span>` : `<span class="rd-chip">${esc(t('Date non renseignée'))}</span>`;
const rdSize = n => n > 1048576 ? (n / 1048576).toFixed(1).replace('.', ',') + ' Mo' : Math.max(1, Math.round(n / 1024)) + ' Ko';
const rdDocAlerts = c => { const a = (c.docs || []).filter(d => d.state === 'over' || d.state === 'warn'); return a.length ? `<div class="rd-alerts">${a.map(d => `<span class="rd-chip ${d.state === 'over' ? 'neg' : 'warn'}">${d.state === 'over' ? '⛔' : '⚠'} ${esc(d.label)} · ${d.state === 'over' ? esc(t('échu')) : esc(t('échéance'))} ${fmtDate(d.expires)}</span>`).join(' ')}</div>` : ''; };
const RD_ID = [['chassis', 'N° de châssis'], ['engine_no', 'N° de moteur'], ['gearbox_no', 'N° de boîte de vitesse'], ['livery', 'Couleur / livrée'], ['race_number', 'N° de course habituel']];
const rdIdentity = c => `<h4 class="sub">Identité de la voiture</h4><div class="sdgrid rd-ident">${RD_ID.map(([k, l]) => `<label class="sdfield"><span>${esc(l)}</span><input class="sdin" data-rd-id="${k}" value="${esc(c[k] || '')}" maxlength="80"></label>`).join('')}</div>`;
const rdNorm = x => String(x || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
function rdFileCard(c, d, f) {
  const url = `/api/rides/cars/${encodeURIComponent(c.key)}/docs/${d.item}/files/${f.id}`, pdf = /pdf/.test(f.ctype);
  const thumb = `<img src="${pdf ? url + '/thumb' : url}" alt="${esc(f.name)}" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'rd-fnone',textContent:'${pdf ? '📄 PDF' : '🖼'}'}))">`;
  return `<div class="rd-fcard"><button type="button" class="rd-fthumb" data-rd="preview" data-u="${url}" data-n="${esc(f.name)}" data-pdf="${pdf ? 1 : 0}" title="${esc(t('Agrandir'))}">${thumb}</button>
    <div class="rd-fcap"><span class="rd-fname" title="${esc(f.name)}">${pdf ? '📄' : '🖼'} ${esc(f.name)}</span><small class="na">${rdSize(f.size)} · ${fmtDate(f.created_at.slice(0, 10))}</small>
    <span class="rd-fact"><a href="${url}" target="_blank" rel="noopener" class="mini" title="${esc(t('Ouvrir dans un onglet'))}">↗</a><button type="button" class="mini danger" data-rd="delfile" data-item="${d.item}" data-f="${f.id}" title="${esc(t('Supprimer ce fichier'))}">✕</button></span></div></div>`;
}
function rdDocs(c) {
  const docs = c.docs || [];
  return `<h4 class="sub">Documents et validités</h4><small class="na">Chaque élément a une date limite : une alerte apparaît ici et sur l’accueil (Super User et chef d’atelier de la BU) quelques semaines avant l’échéance (3 par défaut), et un e-mail leur est envoyé la veille de l’expiration.</small>
  <div class="sdbar rd-docbar"><input type="search" class="sdin" id="rd-docq" placeholder="${esc(t('Rechercher un document, une note, un fichier…'))}" value="${esc(rd.docQ || '')}" autocomplete="off"><small class="na" id="rd-docn"></small></div>
  <div class="rd-docs">${docs.map(d => `<div class="rd-doc ${d.state}" data-item="${d.item}" data-q="${esc(rdNorm([d.label, t(d.label), d.note, ...d.files.map(f => f.name)].join(' ')))}"><div class="rd-doc-h"><b>${esc(d.label)}</b> ${rdDocChip(d)}</div>
    <div class="sdgrid"><label class="sdfield"><span>Date limite de validité</span>${dpField(`data-rd-d="expires" data-item="${d.item}"`, d.expires)}</label>
    <label class="sdfield"><span>Alerte (semaines avant)</span><input class="sdin" type="number" min="1" max="52" step="1" data-rd-d="weeks" data-item="${d.item}" value="${d.weeks}"></label>
    <label class="sdfield rd-doc-note"><span>Note</span><input class="sdin" data-rd-d="note" data-item="${d.item}" value="${esc(d.note)}"></label></div>
    <div class="rd-files">${d.files.map(f => rdFileCard(c, d, f)).join('')}<label class="rd-fadd" title="${esc(t('Ajouter un document'))}"><span>＋</span><small>Document</small><input type="file" accept="application/pdf,image/*" multiple hidden data-rd-up="${d.item}"></label></div></div>`).join('')}</div>`;
}
function rdDocFilter() {
  const q = rdNorm(rd.docQ).trim(), all = [...document.querySelectorAll('.rd-doc')]; let n = 0;
  all.forEach(el => { const ok = !q || q.split(/\s+/).every(w => el.dataset.q.includes(w)); el.hidden = !ok; if (ok) n++; });
  const c = document.getElementById('rd-docn'); if (c) c.textContent = q ? `${n} / ${all.length}` : '';
}
function rdLightbox(u, name, pdf) {
  const old = document.getElementById('rd-lb'); if (old) old.remove();
  const lb = document.createElement('div'); lb.id = 'rd-lb'; lb.className = 'rd-lb';
  lb.innerHTML = `<div class="rd-lb-bar"><b>${esc(name)}</b><span class="wl-sp"></span><a href="${u}" target="_blank" rel="noopener" class="mini">↗ ${esc(t('Ouvrir dans un onglet'))}</a><button type="button" class="mini" data-lb="close">✕ ${esc(t('Fermer'))}</button></div>${pdf ? `<iframe src="${u}"></iframe>` : `<div class="rd-lb-img"><img src="${u}" alt="${esc(name)}"></div>`}`;
  document.body.appendChild(lb);
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') { const lb = document.getElementById('rd-lb'); if (lb) lb.remove(); } });
document.addEventListener('click', e => { const lb = document.getElementById('rd-lb'); if (lb && (e.target === lb || (e.target.closest && e.target.closest('[data-lb=close]')))) lb.remove(); });
document.addEventListener('input', e => { if (e.target.id === 'rd-docq') { rd.docQ = e.target.value; rdDocFilter(); } });

// ---- Dessin -----------------------------------------------------------------------------------------------------------------------------
function rdDraw() {
  const el = document.getElementById('rd-view'); if (!el) return;
  const bar = document.querySelector('#page .bu-bar'); if (bar) bar.hidden = !!rd.car;        // le filtre BU n'a de sens que dans la liste des voitures, pas dans la fiche d'une voiture
  const sav = [window.scrollX, window.scrollY];
  if (rd.error && !rd.cars) { el.innerHTML = `<p class="neg">${esc(rd.error)}</p>`; return; }
  const c = rd.car;
  const msg = rd.msg && !rd.form && !rd.run && !rd.repl ? `<p class="na">${esc(rd.msg)}</p>` : '';
  if (!c) {
    const nArchBar = rd.cars ? rd.cars.filter(c => c.archived).length : 0;
    el.innerHTML = `<div class="sdbar"><button type="button" data-rd="settings">${rd.settings ? 'Fermer les réglages' : '⚙ Circuits'}</button><button type="button" data-rd="reread" title="Relire les ressources Google (nom corrigé, voiture ajoutée)">↻ Relire Google</button><span class="wl-sp"></span>${nArchBar ? `<label class="chk rd-rm"><input type="checkbox" id="rd-archived" ${rd.showArchived ? 'checked' : ''}> afficher les voitures archivées (${nArchBar})</label>` : ''}${rd.loading ? '<small class="na">Chargement…</small>' : ''}</div>${msg}${rdSettings()}${rdList()}`;
    return;
  }
  const alertsHtml = c.alerts_list.length ? `<div class="rd-alerts">${c.alerts_list.map(a => a.type === 'inspection' ? `<span class="rd-chip warn" title="${esc((a.items || []).join('\n'))}">⚠ ${esc(a.label)}</span>` : `<span class="rd-chip ${a.state === 'over' ? 'neg' : 'warn'}" title="${rdKm(a.km)} km${a.limit_km ? ' / ' + rdKm(a.limit_km) : ''}">${a.state === 'over' ? '⛔' : '⚠'} ${esc(a.path)} · ${esc(a.label)} · ${rdPct(a.ratio)}</span>`).join(' ')}</div>` : '';
  el.innerHTML = `<div class="sdbar"><button type="button" data-rd="back">← Voitures</button><button type="button" data-rd="settings">${rd.settings ? 'Fermer les réglages' : '⚙ Circuits'}</button><span class="wl-sp"></span><button type="button" data-rd="archive">${c.archived ? '↩ Désarchiver' : '🗄 Archiver'}</button>${c.archived ? '<button type="button" class="danger" data-rd="delcar">🗑 Supprimer définitivement</button>' : ''}</div>${c.archived ? '<p class="na">Voiture archivée : cachée du Garage, ses données sont conservées. « Supprimer définitivement » efface ses pièces, ses runs et sa photo.</p>' : ''}${msg}${rdSettings()}
    <div class="rd-head"><label class="rd-photobtn" title="Changer la photo">${rdPhoto(c, true)}<input type="file" id="rd-photo-in" accept="image/*" hidden><small class="na">📷 Photo</small></label>
      <div><h3 style="margin:0">${esc(c.name)}</h3><small class="na">${c.category === 'rally' ? 'Rallye' : 'Circuit'} · ${rdKm(c.km_total)} km${c.hours_total ? ` · ${rdKm(c.hours_total)} h` : ''} · ${c.runs} run${c.runs > 1 ? 's' : ''}</small><div>${rdChip(c.state, c.alerts)}</div>${rdBuPills(c)}</div></div>${rdLinks(c)}${rdIdentity(c)}${alertsHtml}${rdDocAlerts(c)}${rdDocs(c)}
    <h4 class="sub">Pièces <button type="button" class="mini" data-rd="addpart" data-p="">＋ Ensemble</button>${rdHasFold(c.tree) ? ` <button type="button" class="mini" data-rd="foldall" data-on="0">${esc(tx('Tout déplier'))}</button> <button type="button" class="mini" data-rd="foldall" data-on="1">${esc(tx('Tout replier'))}</button>` : ''}${rdHasRemoved(c.tree) ? ` <label class="chk rd-rm"><input type="checkbox" id="rd-removed" ${rd.showRemoved ? 'checked' : ''}> afficher les pièces démontées</label>` : ''}</h4>
    ${rd.form && !rd.form.id && !rd.form.parent_id || rd.form && rd.form.id && rdFind(rd.form.id) && !rdFind(rd.form.id).parent_id ? rdPartForm() : ''}
    <div class="rd-tree">${c.tree.length ? c.tree.map(n => rdNode(n, 0)).join('') : '<p class="na">Aucune pièce : ajoutez un ensemble (par exemple Moteur) ou appliquez un modèle du Magasin de pièces.</p>'}</div>
    ${rd.form && (rd.form.parent_id || (rd.form.id && rdFind(rd.form.id) && rdFind(rd.form.id).parent_id)) ? rdPartForm() : ''}${rdReplForm()}${rdMaintForm()}
    <h4 class="sub">Roulages <button type="button" class="mini" data-rd="newrun">＋ Nouveau run</button></h4>${rdRunForm()}${rdRuns(c)}`;
  rdDocFilter();
  window.scrollTo(...sav);
}

// ---- Actions ----------------------------------------------------------------------------------------------------------------------------
const rdErr = e => { rd.msg = e.message; rdDraw(); };
function rdPartBody(f) {
  const o = {name: f.name.trim(), parent_id: f.parent_id || null, group: !!f.group, serial: f.serial || '', reference: f.reference || '', notes: f.notes || ''};
  if (!f.group) {
    const L = t => ({limit_km: rdNum(f.lim[t].limit_km), limit_hours: rdNum(f.lim[t].limit_hours), warn_pct: rdNum(f.lim[t].warn_pct) || 75});
    Object.assign(o, {types: f.types, km_start: rdNum(f.km_start) || 0, hours_start: rdNum(f.hours_start) || 0, mounted_from: f.mounted_from || null, maint: {}});
    if (f.types.includes('replace')) Object.assign(o, L('replace'), {limit_note: f.lim.replace.note || ''}); else Object.assign(o, {limit_km: null, limit_hours: null, limit_note: ''});
    ['revision', 'revision2', 'fluids', 'inspection'].forEach(t => { if (f.types.includes(t)) o.maint[t] = {...L(t), limit_events: rdNum(f.lim[t].limit_events), note: f.lim[t].note || ''}; });
  }
  return o;
}
document.addEventListener('input', e => {
  const t = e.target; if (!document.getElementById('rd-view')) return;
  if (t.dataset.rdF !== undefined && rd.form && !t.classList.contains('dp-h')) {
    rd.form[t.dataset.rdF] = t.type === 'checkbox' ? t.checked : t.value;
    const b = document.querySelector('[data-rd=savepart]'); if (b) b.disabled = !rd.form.name.trim();
  } else if (t.dataset.rdU !== undefined && rd.run && !t.classList.contains('dp-h')) { rd.run[t.dataset.rdU] = t.value; const needRedraw = false; if (t.dataset.rdU === 'circuit') { const nc = document.getElementById('rd-newcirc'); if (nc) nc.innerHTML = rdNewCirc(); } const ph = document.querySelector('.rd-km'); if (!needRedraw && ph) { const km = rdRunKm(rd.run); ph.innerHTML = km == null ? 'Kilomètres : à compléter' : `<b>${rdKm(km)} km</b> comptés pour toutes les pièces montées`; } const b = document.querySelector('[data-rd=saverun]'); if (b) b.disabled = !(rd.run.name.trim() && rd.run.date); }
  else if (t.dataset.rdFl !== undefined && rd.form) { const [ty, k] = t.dataset.rdFl.split('.'); rd.form.lim[ty][k] = t.value; }
  else if (t.dataset.rdM !== undefined && rd.mf && !t.classList.contains('dp-h')) rd.mf[t.dataset.rdM] = t.value;
  else if (t.dataset.rdS !== undefined && rd.run) { rd.run.stages[+t.dataset.i][t.dataset.rdS] = t.value; const ph = document.querySelector('.rd-km'); if (ph) { const km = rdRunKm(rd.run); ph.innerHTML = km == null ? 'Kilomètres : à compléter' : `<b>${rdKm(km)} km</b> comptés pour toutes les pièces montées`; } }
  else if (t.dataset.rdR !== undefined && rd.repl && !t.classList.contains('dp-h')) rd.repl[t.dataset.rdR] = t.value;
  else if (t.dataset.rdN !== undefined) { rd.circ[t.dataset.rdN] = t.value; const b = document.querySelector('[data-rd=savecirc]'); if (b) b.disabled = !(rd.circ.name.trim() && rdNum(rd.circ.length_km) > 0); }
});
document.addEventListener('change', async e => {
  const t = e.target; if (!document.getElementById('rd-view')) return;
  if (t.dataset.rdId) {                             // identité : enregistrement dès la saisie
    try { await rsCall('/api/rides/cars/' + encodeURIComponent(rd.car.key), {method: 'PUT', body: JSON.stringify({[t.dataset.rdId]: t.value})}); rd.car[t.dataset.rdId] = t.value.trim(); const k = rd.cars && rd.cars.find(x => x.key === rd.car.key); if (k) k[t.dataset.rdId] = t.value.trim(); } catch (err) { rdErr(err); }
    return;
  }
  if (t.dataset.rdD !== undefined) {                // documents : enregistrement dès la saisie
    const f = t.dataset.rdD, body = f === 'weeks' ? {weeks: parseInt(t.value) || 0} : f === 'expires' ? {expires: t.value || ''} : {note: t.value};
    try { rd.car.docs = await rsCall(`/api/rides/cars/${encodeURIComponent(rd.car.key)}/docs/${t.dataset.item}`, {method: 'PUT', body: JSON.stringify(body)}); await rdReload(); } catch (err) { rdErr(err); }
    return;
  }
  if (t.dataset.rdUp) {
    const item = t.dataset.rdUp, files = [...t.files]; t.value = '';
    try { for (const f0 of files) {
      let f = f0;
      if (/^image\//.test(f0.type) && f0.size > 1.5 * 1048576) {          // grosse photo : réduite à 2 000 px (JPEG) avant l'envoi
        try { const img = await createImageBitmap(f0), k = Math.min(1, 2000 / Math.max(img.width, img.height)), cv = document.createElement('canvas');
          cv.width = Math.round(img.width * k); cv.height = Math.round(img.height * k); cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
          const bl = await new Promise(ok => cv.toBlob(ok, 'image/jpeg', .86)); if (bl) f = new File([bl], f0.name.replace(/\.\w+$/, '') + '.jpg', {type: 'image/jpeg'}); } catch {}
      }
      const r = await fetch(`/api/rides/cars/${encodeURIComponent(rd.car.key)}/docs/${item}/files?name=${encodeURIComponent(f.name)}`, {method: 'POST', headers: {...rsAuth(), 'Content-Type': f.type || 'application/octet-stream'}, body: f}), j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : 'Envoi impossible');
      rd.car.docs = j; }
      await rdReload();
    } catch (err) { rdErr(err); }
    return;
  }
  if (t.classList.contains('dp-h')) {               // dates (calendrier maison)
    if (t.dataset.rdF === 'mounted_from' && rd.form) rd.form.mounted_from = t.value || '';
    else if (t.dataset.rdU === 'date' && rd.run) { rd.run.date = t.value; const b = document.querySelector('[data-rd=saverun]'); if (b) b.disabled = !(rd.run.name.trim() && rd.run.date); }
    else if (t.dataset.rdR === 'on' && rd.repl) rd.repl.on = t.value;
    else if (t.dataset.rdM === 'date' && rd.mf) rd.mf.date = t.value;
    return;
  }
  if (t.id === 'rd-archived') { rd.showArchived = t.checked; rdDraw(); return; }
  if (t.dataset.rdFt !== undefined && rd.form) { const ty = t.dataset.rdFt, on = t.checked; rd.form.types = RD_MAINT.map(x => x[0]).filter(x => x === ty ? on : rd.form.types.includes(x)); rdDraw(); return; }
  if (t.dataset.rdM === 'type' && rd.mf) { rd.mf.type = t.value; return; }
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
    if (a === 'fold') { const n = rdFind(b.dataset.p); rd.fold = rd.fold || {}; rd.fold[n.id] = !rdFolded(n, n.parent_id ? 1 : 0); return rdDraw(); }
    if (a === 'foldall') { rdFoldAll(b.dataset.on === '1'); return rdDraw(); }
    if (a === 'preview') return rdLightbox(b.dataset.u, b.dataset.n, b.dataset.pdf === '1');
    if (a === 'delfile') { if (!confirm(t('Supprimer ce fichier ?'))) return; rd.car.docs = await rsCall(`/api/rides/cars/${encodeURIComponent(k)}/docs/${b.dataset.item}/files/${b.dataset.f}`, {method: 'DELETE'}); return rdReload(); }
    if (a === 'setbu') { const bu = rd.car.bu === b.dataset.b ? '' : b.dataset.b; await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({bu})}); rd.car.bu = bu; return rdReload(); }
    if (a === 'linkodoo') { const j = await rsCall('/api/rides/link-odoo', {method: 'POST', body: '{}'}); rd.msg = j.linked.length ? `Reliées à Odoo : ` + j.linked.map(x => `${x.name} → ${x.odoo}`).join(' · ') + '. À vérifier dans chaque fiche.' : 'Aucune correspondance assez sûre : reliez les voitures une par une dans leur fiche.'; rd.odoo = null; return rdReload(); }
    if (a === 'linkone') { const v = parseInt((document.getElementById('rd-odoo-sel') || {}).value); if (!v) throw new Error('Choisissez un compte Odoo.'); await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({odoo_id: v})}); rd.odoo = null; return rdReload(); }
    if (a === 'unlinkodoo') { await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({odoo_id: 0})}); rd.odoo = null; await rdReload(); if (rd.car && !rd.car.odoo) rdLoadOdoo(); return; }
    if (a === 'guessbu') { const j = await rsCall('/api/rides/guess-bu', {method: 'POST', body: '{}'}); rd.msg = `BU proposées pour ${j.set.length} voiture(s) : ` + j.set.map(x => `${x.name} → ${RD_BULAB[x.bu]}`).join(' · ') + '. À vérifier dans chaque fiche.'; return rdReload(); }
    if (a === 'reread') { await rdLoad(true); return; }
    if (a === 'archive') { await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'PUT', body: JSON.stringify({archived: !rd.car.archived})}); rd.car.archived = !rd.car.archived; if (rd.car.archived) { rd.car = null; } return rdReload(); }
    if (a === 'delcar') { const c = rd.car; if (!confirm(`Supprimer définitivement « ${c.name} » ?\n\nSes ${c.parts} pièce(s), ses ${c.runs} run(s) et sa photo seront effacés, sans retour possible.${'\n\n'}Le véhicule reste dans Planifier › Ressources : laissez-le archivé s'il y figure encore.`)) return; const j = await rsCall('/api/rides/cars/' + encodeURIComponent(k), {method: 'DELETE'}); rd.car = null; rd.msg = `Données supprimées (${j.parts} pièce(s), ${j.runs} run(s)).`; return rdReload(); }
    if (a === 'back') { rd.car = null; rd.form = rd.run = rd.repl = null; rd.msg = null; await rdReload(); return; }
    if (a === 'settings') { rd.settings = !rd.settings; rd.cat = null; return rdDraw(); }
    if (a === 'addpart') { rd.form = {id: null, parent_id: b.dataset.p || null, name: '', group: !b.dataset.p, serial: '', reference: '', types: [], lim: Object.fromEntries(RD_MAINT.map(([t]) => [t, rdLimBlank()])), km_start: '', hours_start: '', mounted_from: '', notes: ''}; rd.run = rd.repl = rd.mf = null; rd.msg = null; return rdDraw(); }
    if (a === 'editpart') { const n = rdFind(b.dataset.p); const tys = (n.types && n.types.length) ? n.types : (n.limit_km || n.limit_hours) ? ['replace'] : [], mm = n.maint || {}, lm = rdLimOf;
      rd.form = {id: n.id, parent_id: n.parent_id, name: n.name, group: !!n.group, serial: n.serial || '', reference: n.reference || '', types: tys, lim: {replace: lm(n), revision: lm(mm.revision || {}), revision2: lm(mm.revision2 || {}), fluids: lm(mm.fluids || {}), inspection: lm(mm.inspection || {})}, km_start: n.km_start || '', hours_start: n.hours_start || '', mounted_from: n.mounted_from || '', notes: n.notes || ''}; rd.run = rd.repl = rd.mf = null; rd.msg = null; return rdDraw(); }
    if (a === 'savepart') { const f = rd.form, body = rdPartBody(f); await rsCall(f.id ? '/api/rides/parts/' + encodeURIComponent(f.id) : `/api/rides/cars/${encodeURIComponent(k)}/parts`, {method: f.id ? 'PUT' : 'POST', body: JSON.stringify(body)}); rd.form = null; rd.msg = null; return rdReload(); }
    if (a === 'delpart') { const n = rdFind(b.dataset.p); if (!confirm(`Supprimer « ${n.name} »${n.children.length ? ' et ses sous-éléments' : ''} ? Pour une pièce usée, préférez « Remplacer » : elle garde son historique.`)) return; await rsCall('/api/rides/parts/' + encodeURIComponent(n.id), {method: 'DELETE'}); return rdReload(); }
    if (a === 'replace') { rd.repl = {id: b.dataset.p, on: rdToday(), serial: ''}; rd.form = rd.run = null; rd.msg = null; return rdDraw(); }
    if (a === 'saverepl') { const r = rd.repl; await rsCall(`/api/rides/parts/${encodeURIComponent(r.id)}/replace`, {method: 'POST', body: JSON.stringify({on: r.on, serial: r.serial})}); rd.repl = null; rd.msg = null; return rdReload(); }
    if (a === 'maint') { const n = rdFind(b.dataset.p), ty = (n.types || []).filter(t => t !== 'replace'); rd.mf = {part_id: n.id, type: ty[0] || 'revision', date: rdToday(), notes: ''}; rd.form = rd.run = rd.repl = null; rd.msg = null; return rdDraw(); }
    if (a === 'savemaint') { const m = rd.mf; await rsCall(`/api/rides/parts/${encodeURIComponent(m.part_id)}/maint`, {method: 'POST', body: JSON.stringify({type: m.type, date: m.date, notes: m.notes})}); rd.msg = null; const pid = m.part_id; await rdReload(); rd.mf = {part_id: pid, type: m.type, date: rdToday(), notes: ''}; return rdDraw(); }
    if (a === 'delmaint') { if (!confirm('Supprimer cette maintenance ? Le compteur reprend depuis la précédente.')) return; await rsCall('/api/rides/maint/' + encodeURIComponent(b.dataset.m), {method: 'DELETE'}); const m = rd.mf; await rdReload(); rd.mf = m; return rdDraw(); }
    if (a === 'applytpl') { const v = (document.getElementById('rd-tpl-sel') || {}).value; if (!v) throw new Error('Choisissez un modèle.'); const j = await rsCall(`/api/rides/cars/${encodeURIComponent(k)}/template`, {method: 'POST', body: JSON.stringify({template_id: v})}); rd.msg = `Modèle « ${j.template.name} » appliqué : ${j.created} élément(s) créé(s), ${j.kept} déjà présent(s) conservé(s).`; return rdReload(); }
    if (a === 'cancelform') { rd.form = rd.run = rd.repl = rd.mf = null; rd.msg = null; return rdDraw(); }
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
    if (a === 'savecirc') { const j = await rsCall('/api/rides/circuits', {method: 'POST', body: JSON.stringify({name: rd.circ.name.trim(), length_km: rdNum(rd.circ.length_km)})}); rd.circuits = rd.circuits.filter(c => c.id !== j.id).concat([j]).sort((x, y) => x.name.localeCompare(y.name)); rd.circ = {name: '', length_km: ''}; return rdDraw(); }
  } catch (err) { rdErr(err); }
});
