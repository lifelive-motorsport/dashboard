// Planifier › Planning (lecture seule, tous les utilisateurs) : deux vues, « Par ressource » (une ligne par personne ou véhicule) et « Calendrier » (grille semaine ou mois),
// avec le détail complet de l'événement au survol. Les données viennent de /api/planning (événements Logbook dans Google Agenda). Chargé après events.js.
let pl = {loaded: false, loading: false, error: null, data: {resources: [], events: [], categories: []}, mode: 'rows', span: 'week', anchor: '', res: 'all', hideEmpty: false};
const PL_BU = {XC: ['var(--bu-xc)', '#fff', 'XC'], MODERN_RALLY: ['var(--bu-mr-ui)', '#fff', 'Modern Rally'], HISTORIC_RALLY: ['var(--bu-hrl)', '#2B2B2B', 'Historic Rally'], HISTORIC_RACING: ['var(--bu-hrc)', '#fff', 'Historic Racing']};
const plAdd = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const plMonday = iso => { const d = new Date(iso + 'T12:00:00Z'), w = (d.getUTCDay() + 6) % 7; return plAdd(iso, -w); };
const plMonthStart = iso => iso.slice(0, 8) + '01';
const plMonthEnd = iso => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCMonth(d.getUTCMonth() + 1, 0); return d.toISOString().slice(0, 10); };
const plIdx = (a, b) => Math.round((new Date(b + 'T12:00:00Z') - new Date(a + 'T12:00:00Z')) / 86400000);
const plToday = () => new Date().toISOString().slice(0, 10);
const plFmt = (iso, o) => new Date(iso + 'T12:00:00Z').toLocaleDateString(LOCALE(), {timeZone: 'UTC', ...o});
const plWeekNo = iso => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7)); const y = new Date(Date.UTC(d.getUTCFullYear(), 0, 1)); return Math.ceil(((d - y) / 86400000 + 1) / 7); };

// Période affichée : liste de jours (colonnes de la vue « Par ressource » ; grille complète des semaines pour le calendrier)
function plDays() { const a = pl.anchor; return pl.span === 'week' ? Array.from({length: 7}, (_, i) => plAdd(a, i)) : Array.from({length: plIdx(a, plMonthEnd(a)) + 1}, (_, i) => plAdd(a, i)); }
function plGridDays() { if (pl.span === 'week') return plDays(); const s = plMonday(plMonthStart(pl.anchor)), e = plAdd(plMonday(plMonthEnd(pl.anchor)), 6); return Array.from({length: plIdx(s, e) + 1}, (_, i) => plAdd(s, i)); }
const plRangeFetch = () => { const d = pl.mode === 'cal' ? plGridDays() : plDays(); return [d[0], d[d.length - 1]]; };
const plLabel = () => pl.span === 'week' ? `Semaine ${plWeekNo(pl.anchor)} · ${plFmt(pl.anchor, {day: 'numeric', month: 'short'})} – ${plFmt(plAdd(pl.anchor, 6), {day: 'numeric', month: 'short', year: 'numeric'})}` : (s => s.charAt(0).toUpperCase() + s.slice(1))(plFmt(pl.anchor, {month: 'long', year: 'numeric'}));

function planningBlocks() { return [BU_BAR(), {static: '<section class="block" data-bid="pl"><div class="block-head"><h3>Planning</h3></div><div class="block-body" id="pl-view"><p class="na">Chargement…</p></div></section>'}]; }

async function plLoad() {
  if (!pl.anchor) pl.anchor = pl.span === 'week' ? plMonday(plToday()) : plMonthStart(plToday());
  const [from, to] = plRangeFetch(); pl.loading = true; plDraw();
  try { pl.data = await rsCall(`/api/planning?from=${from}&to=${to}`); pl.error = null; } catch (e) { pl.error = e.message; }
  pl.loaded = true; pl.loading = false; plDraw();
}

// ---- Données filtrées ----------------------------------------------------------------------------------------------------------------------------------------------
const plRes = () => Object.fromEntries(pl.data.resources.map(r => [r.id, r]));
const plGroup = r => r.kind === 'vehicle' ? (r.category || 'other') : r.kind;
const plBuOk = r => buSel === 'all' || r.all_bus || (BU_KEYS[buSel] || []).some(k => (r.bus || []).includes(k));
const plEvents = () => pl.data.events.filter(e => buSel === 'all' || buMatchesFilter(PE_BU_SYM[e.bu] || 'lifelive', buSel));
const PL_RACE = ['rally', 'circuit'];                                   // voitures de course : ressources de la BU CARS, masquées quand XC est sélectionné
function plGroups() {
  const cats = (pl.data.categories || []), order = [['staff', 'Staff interne'], ['external', 'Staff externe']].concat(cats.map(c => [c.id, c.label]));
  return order.filter(([id]) => !(buSel === 'xc' && PL_RACE.includes(id)) && pl.data.resources.some(r => plGroup(r) === id));
}

// Voies : place les barres qui se chevauchent sur des lignes différentes. items = [{a, b, ...}] (indices de colonnes inclusifs)
function plLanes(items) { const ends = []; items.sort((x, y) => x.a - y.a || y.b - x.b).forEach(it => { let l = ends.findIndex(e => e < it.a); if (l < 0) { l = ends.length; ends.push(0); } ends[l] = it.b; it.lane = l; }); return Math.max(1, ends.length); }

const plBar = (e, a, b, lane, o = {}) => { const [bg, fg] = PL_BU[e.bu] || ['var(--mut)', '#fff'];
  return `<div class="pl-bar${e.confirmed ? '' : ' tbc'}${o.cutL ? ' cutl' : ''}${o.cutR ? ' cutr' : ''}${o.veh ? ' veh' : ''}${o.st === 'declined' ? ' declined' : ''}" data-id="${esc(e.id)}" style="grid-column:${a + 1} / ${b + 2};grid-row:${lane + 1};background:${bg};color:${fg}">${o.st === 'declined' ? '✗ ' : ''}${e.confirmed ? '' : '[TBC] '}${esc(e.title)}</div>`; };

const plImmo = (e, a, b, lane) => `<div class="pl-immo" data-id="${esc(e.id)}" style="grid-column:${a + 1} / ${b + 2};grid-row:${lane + 1};background:${(PL_BU[e.bu] || ['var(--mut)'])[0]}" title=""></div>`;
function plHead(days) { const t = plToday(); return days.map(d => { const we = [0, 6].includes(new Date(d + 'T12:00:00Z').getUTCDay());
  return `<div class="pl-day${we ? ' we' : ''}${d === t ? ' today' : ''}"><small>${esc(plFmt(d, {weekday: 'short'}))}</small><b>${+d.slice(8)}</b></div>`; }).join(''); }
const plBg = days => days.map((d, i) => { const we = [0, 6].includes(new Date(d + 'T12:00:00Z').getUTCDay()); return `<div class="pl-cell${we ? ' we' : ''}${d === plToday() ? ' today' : ''}" style="grid-column:${i + 1};grid-row:1 / -1"></div>`; }).join('');

// ---- Vue « Par ressource » -------------------------------------------------------------------------------------------------------------------------------
function plRowsHtml() {
  const days = plDays(), n = days.length, d0 = days[0], dN = days[n - 1], evs = plEvents(), groups = plGroups();
  let h = `<div class="pl-rows" style="--n:${n}"><div class="pl-line pl-hd"><div class="pl-lab"></div><div class="pl-days">${plHead(days)}</div></div>`, shown = 0;
  for (const [gid, glabel] of groups) {
    if (pl.res !== 'all' && pl.res !== gid) continue;
    const rows = pl.data.resources.filter(r => plGroup(r) === gid && (r.kind === 'vehicle' || plBuOk(r))).sort(gid === 'staff' || gid === 'external' ? byName : (a, b) => a.name.localeCompare(b.name, 'fr', {numeric: true, sensitivity: 'base'}));
    let body = '';
    for (const r of rows) {
      const items = [];
      for (const e of evs) { const own = e.people.find(p => p.rid === r.id) || e.vehicles.find(p => p.rid === r.id); if (!own) continue;
        const veh = r.kind === 'vehicle', s = veh ? e.immo_start : e.start, en = veh ? e.immo_end : e.end; if (en < d0 || s > dN) continue;
        items.push({e, a: Math.max(0, plIdx(d0, s)), b: Math.min(n - 1, plIdx(d0, en)), cutL: s < d0, cutR: en > dN, veh, st: own.status}); }
      const lv = r.kind === 'staff' ? (pl.data.leaves || []).filter(l => l.rid === r.id && l.end >= d0 && l.start <= dN) : [];
      if (pl.hideEmpty && !items.length && !lv.length) continue;
      const lanes = plLanes(items); shown++;
      body += `<div class="pl-line"><div class="pl-lab" title="${esc(r.name)}">${esc(r.name)}${r.company ? ` <small>${esc(r.company)}</small>` : r.type ? ` <small>${esc(r.type)}</small>` : ''}</div><div class="pl-track" style="grid-template-rows:repeat(${lanes},24px)">${plBg(days)}${lv.map(l => `<div class="pl-leave" style="grid-column:${Math.max(0, plIdx(d0, l.start)) + 1} / ${Math.min(n - 1, plIdx(d0, l.end)) + 2};grid-row:1 / -1" title="${esc(t('Congé'))}">${l.half ? '½ ' : ''}${esc(t('Congé'))}</div>`).join('')}${items.map(it => plBar(it.e, it.a, it.b, it.lane, it)).join('')}</div></div>`;
    }
    if (body) h += `<div class="pl-grp">${esc(glabel)}</div>` + body;
  }
  return shown ? h + '</div>' : h + '</div><p class="na">Aucune ressource à afficher pour ces filtres.</p>';
}

// ---- Vue « Calendrier » ----------------------------------------------------------------------------------------------------------------------------------
function plCalHtml() {
  const days = plGridDays(), weeks = []; for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  const R = plRes(), grp = pl.res, vehGroup = !['all', 'staff', 'external'].includes(grp), evs = plEvents().filter(e => grp === 'all' || e.people.concat(e.vehicles).some(p => R[p.rid] && plGroup(R[p.rid]) === grp));
  const t = plToday(), month = pl.anchor.slice(0, 7);
  return '<div class="pl-cal">' + `<div class="pl-calhd">${weeks[0].map(d => `<div>${esc(plFmt(d, {weekday: 'short'}))}</div>`).join('')}</div>` + weeks.map(w => {
    const s = w[0], en = w[6], items = [];
    // Filtre « véhicules » : la barre couvre l'immobilisation (comme dans la vue par ressource). Sinon : dates de l'événement, avec un trait fin sous la barre pour l'immobilisation des véhicules.
    for (const e of evs) {
      const hasV = e.vehicles.length > 0, vehFilter = vehGroup && hasV, s0 = vehFilter ? e.immo_start : e.start, e0 = vehFilter ? e.immo_end : e.end, wide = !vehFilter && hasV && (e.immo_start < e.start || e.immo_end > e.end);
      const fs = wide ? e.immo_start : s0, fe = wide ? e.immo_end : e0; if (fe < s || fs > en) continue;
      items.push({e, a: Math.max(0, plIdx(s, fs)), b: Math.min(6, plIdx(s, fe)), ea: Math.max(0, plIdx(s, s0)), eb: Math.min(6, plIdx(s, e0)), cutL: s0 < s, cutR: e0 > en, veh: vehFilter, ia: wide ? Math.max(0, plIdx(s, e.immo_start)) : null, ib: wide ? Math.min(6, plIdx(s, e.immo_end)) : null});
    }
    const lanes = plLanes(items);
    const nums = w.map((d, i) => `<div class="pl-num${d === t ? ' today' : ''}${pl.span === 'month' && d.slice(0, 7) !== month ? ' out' : ''}" style="grid-column:${i + 1}">${+d.slice(8) === 1 || d === s ? esc(plFmt(d, {day: 'numeric', month: 'short'})) : +d.slice(8)}</div>`).join('');
    return `<div class="pl-week${pl.span === 'week' ? ' big' : ''}"><div class="pl-nums">${nums}</div><div class="pl-wtrack" style="grid-template-rows:repeat(${lanes},28px)">${plBg(w)}${items.map(it => (it.ia != null ? plImmo(it.e, it.ia, it.ib, it.lane) : '') + plBar(it.e, it.ea, it.eb, it.lane, it)).join('')}</div></div>`;
  }).join('') + '</div>';
}

function plDraw() {
  const el = document.getElementById('pl-view'); if (!el) { plHideTip(); return; }
  plHideTip();
  if (pl.error) { el.innerHTML = `<p class="neg">${esc(pl.error)}</p>`; return; }
  if (!pl.loaded) { el.innerHTML = '<p class="na">Chargement…</p>'; return; }
  const pill = (cls, k, label, on, extra = '') => `<button type="button" class="rs-pill ${cls}" data-k="${k}" aria-pressed="${on}"${extra}><span>${esc(label)}</span></button>`;
  const cats = plGroups(), nav = `<button type="button" class="mini pl-nav" data-d="-1" aria-label="Précédent">‹</button><button type="button" class="mini pl-nav" data-d="0">Aujourd’hui</button><button type="button" class="mini pl-nav" data-d="1" aria-label="Suivant">›</button>`;
  el.innerHTML = `<div class="sdbar pl-bar-top">${nav}<b class="pl-label">${esc(plLabel())}</b><span class="pl-sp"></span><div class="bu-filter">${pill('pl-mode', 'rows', 'Par ressource', pl.mode === 'rows')}${pill('pl-mode', 'cal', 'Calendrier', pl.mode === 'cal')}</div><div class="bu-filter">${pill('pl-span', 'week', 'Semaine', pl.span === 'week')}${pill('pl-span', 'month', 'Mois', pl.span === 'month')}</div></div>`
    + `<div class="sdbar"><div class="bu-filter" role="group" aria-label="Filtrer par ressource">${pill('pl-res', 'all', 'Tous', pl.res === 'all')}${cats.map(([id, l]) => pill('pl-res', id, l, pl.res === id)).join('')}</div>${pl.mode === 'rows' ? `<label class="chk"><input type="checkbox" id="pl-empty" ${pl.hideEmpty ? 'checked' : ''}> Seulement les ressources occupées</label>` : ''}${pl.loading ? '<small class="na">Chargement…</small>' : ''}</div>`
    + (pl.data.vehicles_message ? `<p class="na">${esc(pl.data.vehicles_message)}</p>` : '')
    + (pl.mode === 'rows' ? plRowsHtml() : plCalHtml())
    + '<small class="na">Barres : couleur de la BU · hachurées = événement non confirmé (TBC) · ✗ = invitation refusée. Pour un véhicule, la barre couvre toute l’immobilisation ; dans le calendrier, le trait fin sous une barre indique l’immobilisation des véhicules. Survolez une barre pour le détail.</small>';
}

// ---- Détail au survol -----------------------------------------------------------------------------------------------------------------------------------------
function plTipHtml(e) {
  const R = plRes(), name = p => `${peRsvp(p.status)} ${esc((R[p.rid] || {}).name || '?')}`, byKind = k => e.people.filter(p => (R[p.rid] || {}).kind === k).sort((a, b) => byName(R[a.rid], R[b.rid]));
  const sec = (t, list) => list.length ? `<div class="pl-tsec"><b>${t}</b> ${list.map(name).join(', ')}</div>` : '';
  const [bg, , bl] = PL_BU[e.bu] || ['var(--mut)', '', e.bu];
  const pend = (e.pending || []).map(r => esc((R[r] || {}).name || '?'));
  return `<div class="pl-thead"><span class="pl-dot" style="background:${bg}"></span><b>${e.confirmed ? '' : '[TBC] '}${esc(e.title)}</b></div><div class="pl-tmeta">${esc(bl)} · ${fmtDate(e.start)}${e.end !== e.start ? ' → ' + fmtDate(e.end) : ''}</div>`
    + (e.vehicles.length && (e.immo_start !== e.start || e.immo_end !== e.end) ? `<div class="pl-tmeta">Immobilisation véhicules : ${fmtDate(e.immo_start)} → ${fmtDate(e.immo_end)}</div>` : '')
    + (e.place ? `<div class="pl-tsec"><b>Lieu</b> ${esc(e.place)}${e.km != null ? ` · ${e.km} km depuis Lifelive` : ''}</div>` : '')
    + (e.via || []).map(v => `<div class="neg">⚠ ${v === 'CH' ? 'Itinéraire par la Suisse' : 'Itinéraire par le Royaume-Uni'}</div>`).join('')
    + sec('Staff interne', byKind('staff')) + sec('Staff externe', byKind('external'))
    + (pend.length ? `<div class="pl-tsec"><b>À inviter à la confirmation</b> ${pend.join(', ')}</div>` : '')
    + sec('Véhicules', e.vehicles.slice().sort((a, b) => (R[a.rid] || {}).name.localeCompare((R[b.rid] || {}).name, 'fr', {numeric: true})))
    + (e.other_guests ? `<div class="pl-tsec na">${e.other_guests} autre${e.other_guests > 1 ? 's' : ''} invité${e.other_guests > 1 ? 's' : ''}</div>` : '')
    + (e.notes ? `<div class="pl-tsec"><b>Notes</b> ${esc(e.notes)}</div>` : '');
}
function plTip(ev, show) {
  let t = document.getElementById('pl-tip');
  if (!show) { if (t) t.hidden = true; return; }
  const bar = ev.target.closest && ev.target.closest('.pl-bar, .pl-immo'); if (!bar) return;
  const e = pl.data.events.find(x => x.id === bar.dataset.id); if (!e) return;
  if (!t) { t = document.createElement('div'); t.id = 'pl-tip'; t.className = 'pl-tip'; document.body.appendChild(t); }
  t.innerHTML = plTipHtml(e);
  t.hidden = false; const r = bar.getBoundingClientRect(), w = t.offsetWidth, h = t.offsetHeight;
  t.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left)) + 'px'; t.style.top = (r.bottom + 6 + h > innerHeight ? Math.max(8, r.top - h - 6) : r.bottom + 6) + 'px';
}
// L'infobulle ne doit jamais rester affichée : on la masque dès que la souris quitte une barre (même si la barre a été redessinée ou si la page a changé), au clic, au défilement, à la navigation et avec Échap
const plHideTip = () => { const t = document.getElementById('pl-tip'); if (t) t.hidden = true; };
document.addEventListener('mouseover', e => { if (document.getElementById('pl-view')) plTip(e, true); });
document.addEventListener('mousemove', e => { const t = document.getElementById('pl-tip'); if (t && !t.hidden && !(e.target.closest && e.target.closest('.pl-bar, .pl-immo'))) t.hidden = true; });
window.addEventListener('hashchange', plHideTip); window.addEventListener('scroll', plHideTip, true); window.addEventListener('blur', plHideTip);
document.addEventListener('keydown', e => { if (e.key === 'Escape') plHideTip(); });
document.addEventListener('mouseout', e => { if (e.target.closest && e.target.closest('.pl-bar, .pl-immo') && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.pl-bar, .pl-immo'))) plTip(e, false); });

// ---- Interactions --------------------------------------------------------------------------------------------------------------------------------------------------
document.addEventListener('click', e => {
  if (!document.getElementById('pl-view')) return;
  const bar = e.target.closest('.pl-bar, .pl-immo');
  if (bar) { plHideTip(); if (superUser) { window.peEditAfter = bar.dataset.id; location.hash = '#/planifier/events'; } return; }
  const b = e.target.closest('button'); if (!b) return;
  if (b.classList.contains('pl-nav')) {
    const d = +b.dataset.d;
    if (d === 0) pl.anchor = pl.span === 'week' ? plMonday(plToday()) : plMonthStart(plToday());
    else if (pl.span === 'week') pl.anchor = plAdd(pl.anchor, 7 * d);
    else { const x = new Date(pl.anchor + 'T12:00:00Z'); x.setUTCMonth(x.getUTCMonth() + d, 1); pl.anchor = x.toISOString().slice(0, 10); }
    plLoad();
  } else if (b.classList.contains('pl-mode')) { pl.mode = b.dataset.k; plLoad(); }
  else if (b.classList.contains('pl-span')) { pl.span = b.dataset.k; pl.anchor = pl.span === 'week' ? plMonday(pl.anchor || plToday()) : plMonthStart(pl.anchor || plToday()); plLoad(); }
  else if (b.classList.contains('pl-res')) { pl.res = b.dataset.k; plDraw(); }
});
document.addEventListener('change', e => { if (e.target.id === 'pl-empty') { pl.hideEmpty = e.target.checked; plDraw(); } });
