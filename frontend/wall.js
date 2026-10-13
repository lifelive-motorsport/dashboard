// Écran mural de l'atelier (Piloter › Cockpit ; clé `consigner/wall`) : lecture seule, rafraîchi toutes les 60 s, sans montants. Vues « Événements » (planning à venir) et « Atelier » (jobs, présence, indicateurs).
const wl = {view: 'events', bu: 'all', plan: null, snap: null, error: null, at: null, timer: null, clock: null, loading: false, full: false};
const WL_BU = {XC: ['var(--bu-xc)', 'XC'], MODERN_RALLY: ['var(--bu-mr-ui)', 'Modern Rally'], HISTORIC_RALLY: ['var(--bu-hrl)', 'Historic Rally'], HISTORIC_RACING: ['var(--bu-hrc)', 'Historic Racing'], OTHERS: ['var(--mut)', 'Others']};
const WL_STATE = {done: ['ok', 'Pointé'], waiting: ['wait', 'À venir'], late: ['late', 'Pas encore pointé'], absent: ['off', 'Absent'], off: ['off', 'Repos']};
const wlAdd = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const wlGroup = bu => bu === 'XC' ? 'xc' : bu === 'OTHERS' ? 'others' : 'cars';
const wlBuOk = bu => wl.bu === 'all' ? bu !== 'OTHERS' : bu === 'ALL' || wlGroup(bu) === wl.bu;      // « Others » (transports privés) : seulement si on le choisit
const wlHours = m => { const h = Math.floor(m / 60), r = m % 60; return h ? `${h} h${r ? String(r).padStart(2, '0') : ''}` : `${r} min`; };

function wallBlocks() { return [{static: '<section class="block wl-block" data-bid="wl"><div id="wl-view"><p class="na">Chargement…</p></div></section>'}]; }

const wlClockHtml = () => { const now = new Date(); return `${esc(now.toLocaleDateString(LOCALE(), {weekday: 'long', day: 'numeric', month: 'long'}))} · <b>${esc(now.toLocaleTimeString(LOCALE(), {hour: '2-digit', minute: '2-digit'}))}</b>`; };
function wlTop() {
  const pill = (a, k, l, on) => `<button type="button" class="rs-pill" data-wl="${a}" data-k="${k}" aria-pressed="${on}">${esc(l)}</button>`;
  return `<div class="wl-top"><div class="bu-filter">${pill('view', 'events', 'Événements', wl.view === 'events')}${pill('view', 'atelier', 'Atelier', wl.view === 'atelier')}</div>
    <div class="bu-filter">${[['all', 'Toutes les BU'], ['xc', 'XC'], ['cars', 'CARS']].concat(wl.view === 'events' ? [['others', 'Others']] : []).map(([k, l]) => pill('bu', k, l, wl.bu === k)).join('')}</div>
    <span class="wl-sp"></span><span class="wl-clock" id="wl-clock">${wlClockHtml()}</span>
    <button type="button" class="mini" data-wl="full">${wl.full ? 'Quitter le plein écran' : '⛶ Plein écran'}</button></div>`;
}

function wlEvents() {
  const p = wl.plan; if (!p) return '<p class="na">Chargement…</p>';
  const R = Object.fromEntries(p.resources.map(r => [r.id, r])), today = new Date().toISOString().slice(0, 10), nm = x => (R[x.rid] || {}).name || '?';
  const evs = p.events.filter(e => e.end >= today && wlBuOk(e.bu)).sort((a, b) => a.start.localeCompare(b.start) || a.title.localeCompare(b.title));
  const away = (p.leaves || []).filter(l => l.start <= today && l.end >= today).map(l => (R[l.rid] || {}).name).filter(Boolean);
  const card = e => {
    const [col, bl] = WL_BU[e.bu] || ['var(--mut)', e.bu], going = e.start <= today, d = Math.round((new Date(e.start + 'T12:00:00Z') - new Date(today + 'T12:00:00Z')) / 86400000);
    const when = going ? 'En cours' : d === 1 ? 'Demain' : `J-${d}`;
    const people = e.people.filter(x => (R[x.rid] || {}).kind === 'staff').map(nm), ext = e.people.filter(x => (R[x.rid] || {}).kind === 'external').map(nm), veh = e.vehicles.map(nm);
    return `<div class="wl-card" style="--c:${col}"><div class="wl-when ${going ? 'now' : ''}">${when}</div><div class="wl-main"><div class="wl-title">${e.confirmed ? '' : '<span class="badge-profile">TBC</span> '}${e.transport ? '<span class="badge-profile">Transport</span> ' : ''}${esc(e.title)}</div>
      <div class="wl-meta">${fmtDate(e.start)}${e.start_time ? ' ' + esc(e.start_time) : ''}${e.end !== e.start || e.end_time ? ' → ' + (e.end !== e.start ? fmtDate(e.end) + ' ' : '') + esc(e.end_time || '') : ''} · ${esc(bl)}${e.place ? ' · ' + esc(e.place) : ''}</div>
      ${people.length ? `<div class="wl-line"><b>Équipe</b> ${esc(people.join(', '))}${ext.length ? ' · ' + esc(ext.join(', ')) : ''}</div>` : ''}${veh.length ? `<div class="wl-line"><b>Véhicules</b> ${esc(veh.join(', '))}</div>` : ''}</div></div>`;
  };
  return (evs.length ? `<div class="wl-list">${evs.slice(0, 14).map(card).join('')}</div>` : '<p class="na wl-empty">Aucun événement à venir.</p>')
    + (away.length ? `<div class="wl-away"><b>Absents aujourd’hui</b> ${esc([...new Set(away)].join(', '))}</div>` : '');
}

function wlAtelier() {
  const s = wl.snap; if (!s) return '<p class="na">Chargement…</p>';
  const i = s.indicators, tile = (v, l) => `<div class="wl-tile"><b>${v}</b><span>${esc(l)}</span></div>`;
  const inGroup = p => wl.bu === 'all' || p.all_bus || (wl.bu === 'xc' ? (p.alloc.XC || 0) > 0 : ['MODERN_RALLY', 'HISTORIC_RALLY', 'HISTORIC_RACING', 'CARS_OTHERS', 'CARS'].some(k => (p.alloc[k] || 0) > 0));
  const jobs = s.jobs.filter(j => wl.bu === 'all' || j.group === 'ALL' || (wl.bu === 'xc' ? j.group === 'XC' : j.group === 'CARS'));
  const people = s.people.filter(inGroup);
  const job = j => `<div class="wl-job ${j.today.length ? 'live' : ''}"><div class="wl-title">${esc(j.title)}</div><div class="wl-meta">${esc(j.vehicle || j.event || '')}${j.minutes_week ? ` · ${esc(wlHours(j.minutes_week))} cette semaine` : ''}</div>
    ${j.progress && j.progress.total ? `<div class="wl-bar"><i style="width:${Math.round(100 * j.progress.done / j.progress.total)}%"></i></div><small class="na">${j.progress.done} / ${j.progress.total} points</small>` : ''}${j.today.length ? `<div class="wl-line"><b>Aujourd’hui</b> ${esc(j.today.join(', '))}</div>` : ''}</div>`;
  const person = r => { const [c, l] = WL_STATE[r.state] || ['off', r.state]; return `<div class="wl-person"><span class="wl-pn">${esc(r.name)}</span><span class="wl-st ${c}">${esc(l)}${r.state === 'absent' && r.reason ? ' · ' + esc(r.reason) : ''}</span></div>`; };
  return `<div class="wl-tiles">${tile(i.jobs_open, 'Jobs ouverts')}${tile(i.jobs_closed_week, 'Jobs clôturés cette semaine')}${tile(String(i.hours_week).replace('.', LANG === 'en' ? '.' : ','), 'Heures pointées cette semaine')}${tile(i.billable_pct == null ? '–' : i.billable_pct + ' %', 'Facturable')}${tile(`${i.present} / ${i.expected}`, 'Ont pointé aujourd’hui')}</div>
    <div class="wl-cols"><div><h4 class="sub">Jobs en cours</h4>${jobs.length ? jobs.slice(0, 12).map(job).join('') : '<p class="na">Aucun job ouvert.</p>'}</div><div><h4 class="sub">Équipe aujourd’hui</h4>${people.length ? people.map(person).join('') : '<p class="na">Personne.</p>'}</div></div>`;
}

// La barre du haut n'est reconstruite que si la vue, la BU ou le plein écran changent : les boutons ne sont jamais remplacés sous le doigt par la mise à jour automatique.
function wlDraw() {
  const el = document.getElementById('wl-view'); if (!el) return;
  const sig = [wl.view, wl.bu, wl.full, LANG].join('|');
  if (el.dataset.sig !== sig || !el.querySelector('.wl-top')) { el.dataset.sig = sig; el.innerHTML = wlTop() + '<div id="wl-body"></div>'; }
  document.getElementById('wl-body').innerHTML = (wl.error ? `<p class="neg">${esc(wl.error)}</p>` : '') + (wl.view === 'events' ? wlEvents() : wlAtelier())
    + `<small class="na wl-foot">${wl.at ? 'Actualisé à ' + esc(wl.at.toLocaleTimeString(LOCALE(), {hour: '2-digit', minute: '2-digit'})) + ' · ' : ''}mise à jour automatique toutes les 60 s</small>`;
}
async function wlLoad() {
  if (wl.loading || !document.getElementById('wl-view')) return; wl.loading = true;
  try {
    const t = new Date().toISOString().slice(0, 10);
    const [p, s] = await Promise.all([rsCall(`/api/planning?from=${t}&to=${wlAdd(t, 40)}`), rsCall('/api/wall')]);
    wl.plan = p; wl.snap = s; wl.error = null; wl.at = new Date();
  } catch (e) { wl.error = e.message; }
  wl.loading = false; wlDraw();
}
function wlStart() { wlStop(); wlDraw(); wlLoad(); wl.timer = setInterval(wlLoad, 60000); wl.clock = setInterval(() => { const c = document.getElementById('wl-clock'); if (c) c.innerHTML = wlClockHtml(); }, 15000); }
function wlStop() { clearInterval(wl.timer); clearInterval(wl.clock); wl.timer = wl.clock = null; if (wl.full) wlFull(false); }
function wlFull(on) {
  wl.full = on; document.body.classList.toggle('wall-full', on);
  try { if (on && !document.fullscreenElement) document.documentElement.requestFullscreen(); else if (!on && document.fullscreenElement) document.exitFullscreen(); } catch {}
  wlDraw();
}
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && wl.full) wlFull(false); });
// Boutons de l'écran : l'élément visé est retrouvé aussi par sa position (marge de 8 px), même si un autre élément capte le clic ou si la zone cliquable est décalée par le navigateur en plein écran.
const wlHit = e => {
  const t = e.target.closest && e.target.closest('[data-wl]'); if (t) return t;
  const m = 8; let best = null, bd = 1e9;      // le plus proche dans la marge
  document.querySelectorAll('#wl-view [data-wl]').forEach(b => { const r = b.getBoundingClientRect(), dx = Math.max(r.left - e.clientX, 0, e.clientX - r.right), dy = Math.max(r.top - e.clientY, 0, e.clientY - r.bottom), d = Math.hypot(dx, dy); if (d <= m && d < bd) { best = b; bd = d; } });
  return best;
};
document.addEventListener('mousemove', e => { if (!wl.full || !document.getElementById('wl-view')) return; document.body.style.cursor = wlHit(e) ? 'pointer' : ''; });
document.addEventListener('click', e => {
  if (!document.getElementById('wl-view')) return;
  const b = wlHit(e); if (!b) return;
  const a = b.dataset.wl;
  if (a === 'view') { wl.view = b.dataset.k; if (wl.view === 'atelier' && wl.bu === 'others') wl.bu = 'all'; wlDraw(); }
  else if (a === 'bu') { wl.bu = b.dataset.k; wlDraw(); }
  else if (a === 'full') wlFull(!wl.full);
});
