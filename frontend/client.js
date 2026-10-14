// Espace client (page autonome, sans rien de l'application interne) : le client ouvre un lien magique reçu par e-mail, puis consulte ses voitures du Garage,
// leurs documents, leurs roulages et les jobs avec leurs pointages validés. Lecture seule ; toutes les données viennent de /api/client/* (voir backend/app/clients.py).
const cl = {me: null, car: null, jobs: null, tab: 'jobs', err: null, sent: false, busy: false, email: ''};
const $c = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const LOC = () => LANG === 'en' ? 'en-GB' : 'fr-BE';
const fmtD = iso => iso ? new Date(iso.slice(0, 10) + 'T12:00:00').toLocaleDateString(LOC()) : '';
const fmtKm = v => v == null ? '–' : new Intl.NumberFormat(LOC(), {maximumFractionDigits: 1}).format(v);
const fmtMin = m => m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? ' ' + String(m % 60).padStart(2, '0') : ''}` : `${m} min`;
async function api(url, opt) {
  const r = await fetch(url, {...opt, headers: opt && opt.body ? {'Content-Type': 'application/json'} : {}}), j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(typeof j.detail === 'string' ? j.detail : 'Erreur ' + r.status); e.status = r.status; throw e; }
  return j;
}
const carHash = () => (location.hash.match(/^#\/car\/([\w-]+)/) || [])[1] || '';

// ---- Vues ---------------------------------------------------------------------------------------------------------------------------------
function loginHtml() {
  return `<section class="block cl-login"><h2>${esc(tx('Espace client'))}</h2>
    <p class="na">${esc(tx('Saisissez l’adresse e-mail enregistrée par Lifelive Motorsport : un lien de connexion, valable 15 minutes, vous y sera envoyé.'))}</p>
    ${cl.sent ? `<p class="cl-ok">${esc(tx('Si cette adresse est enregistrée, un lien de connexion vient de vous être envoyé. Pensez à vérifier vos courriers indésirables.'))}</p>` : ''}
    ${cl.err ? `<p class="neg">${esc(cl.err)}</p>` : ''}
    <div class="sdbar"><input class="sdin" id="cl-email" type="email" autocomplete="email" inputmode="email" placeholder="${esc(tx('Votre adresse e-mail'))}" value="${esc(cl.email)}" style="max-width:340px">
    <button type="button" class="primary" id="cl-send" ${cl.busy ? 'disabled' : ''}>${esc(tx(cl.busy ? 'Envoi…' : 'Recevoir un lien de connexion'))}</button></div></section>`;
}
const initials = n => n.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
const carThumb = (c, big) => c.photo ? `<img class="rd-photo${big ? ' big' : ''}" src="/api/client/cars/${encodeURIComponent(c.key)}/photo" alt="" loading="lazy">` : `<div class="rd-photo${big ? ' big' : ''} none" aria-hidden="true">${esc(initials(c.name))}</div>`;
function homeHtml() {
  const m = cl.me, who = m.clients.map(c => c.name).join(' · ');
  return `<h2 class="cl-title">${esc(who)}</h2>${m.cars.length ? `<div class="rd-grid">${m.cars.map(c => `<a class="rd-card" href="#/car/${encodeURIComponent(c.key)}" style="text-decoration:none">${carThumb(c)}<div class="rd-cbody"><b>${c.race_number ? `<span class="rd-no">#${esc(c.race_number)}</span> ` : ''}${esc(c.name)}</b>${c.livery ? `<small class="na">${esc(c.livery)}</small>` : ''}</div></a>`).join('')}</div>`
    : `<p class="na">${esc(tx('Aucune voiture n’est associée à votre compte pour le moment.'))}</p>`}`;
}
const DOC_CHIP = d => d.state === 'over' ? `<span class="rd-chip neg">⛔ ${esc(tx('Échu'))}</span>` : d.state === 'warn' ? `<span class="rd-chip warn">⚠ ${esc(tx('Bientôt échu'))}</span>` : d.state === 'ok' ? `<span class="rd-chip pos">✓ ${esc(tx('Valide'))}</span>` : '';
function docsHtml(c) {
  const u = (d, f) => `/api/client/cars/${encodeURIComponent(c.key)}/docs/${d.item}/files/${f.id}`;
  const list = c.docs.filter(d => d.expires || d.files.length);
  return list.length ? `<div class="rd-docs">${list.map(d => `<div class="rd-doc ${d.state}"><div class="rd-doc-h"><b>${esc(d.label)}</b> ${DOC_CHIP(d)} ${d.expires ? `<small class="na">${esc(tx('jusqu’au'))} ${fmtD(d.expires)}</small>` : ''}</div>
    <div class="rd-files">${d.files.map(f => { const pdf = /pdf/.test(f.ctype); return `<div class="rd-fcard"><button type="button" class="rd-fthumb" data-cl="preview" data-u="${u(d, f)}" data-n="${esc(f.name)}" data-pdf="${pdf ? 1 : 0}"><img src="${pdf ? u(d, f) + '/thumb' : u(d, f)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'rd-fnone',textContent:'${pdf ? '📄 PDF' : '🖼'}'}))"></button><div class="rd-fcap"><span class="rd-fname" title="${esc(f.name)}">${pdf ? '📄' : '🖼'} ${esc(f.name)}</span></div></div>`; }).join('')}</div></div>`).join('')}</div>`
    : `<p class="na">${esc(tx('Aucun document pour le moment.'))}</p>`;
}
function runsHtml(c) {
  return c.runs.length ? `<div class="table-wrap"><table><thead><tr><th>${esc(tx('Date'))}</th><th>${esc(tx('Roulage'))}</th><th>${esc(tx('Circuit / rallye'))}</th><th>${esc(tx('Km'))}</th><th>${esc(tx('Heures'))}</th></tr></thead><tbody>${c.runs.map(r => `<tr><td>${fmtD(r.date)}</td><td>${esc(r.name)}</td><td>${r.kind === 'rally' ? esc(tx('Rallye')) : esc(r.circuit || '')}</td><td>${fmtKm(r.km)}</td><td>${r.hours != null ? fmtKm(r.hours) : '–'}</td></tr>`).join('')}</tbody></table></div>`
    : `<p class="na">${esc(tx('Aucun roulage enregistré.'))}</p>`;
}
function jobsHtml(c) {
  if (cl.jobs == null) return '<p class="na loading">Chargement…</p>';
  if (!cl.jobs.length) return `<p class="na">${esc(tx('Aucun job pour cette voiture pour le moment.'))}</p>`;
  const ph = (e, id) => `/api/client/cars/${encodeURIComponent(c.key)}/entries/${encodeURIComponent(e.id)}/photos/${encodeURIComponent(id)}`;
  return cl.jobs.map(j => `<section class="rn-card"><div class="rn-head"><div><b>${esc(j.title)}</b> <span class="rd-chip ${j.open ? 'warn' : 'pos'}">${esc(tx(j.open ? 'En cours' : 'Terminé'))}</span>${j.nature ? ` <span class="rd-chip">${esc(j.nature)}</span>` : ''}<br><small class="na">${j.event ? esc(j.event) + ' · ' : ''}${esc(tx('ouvert le'))} ${fmtD(j.created)}${j.minutes ? ' · ' + esc(tx('temps passé')) + ' ' + fmtMin(j.minutes) : ''}${j.progress ? ` · ${j.progress.done} / ${j.progress.total} ${esc(tx('points de contrôle'))}` : ''}</small></div></div>
    ${j.checklist.length ? `<details class="cl-check"><summary>${esc(tx('Liste de contrôle'))}</summary>${j.checklist.map(s => `<h5>${esc(s.title)}</h5><ul class="cl-lines">${s.lines.map(l => `<li class="${l.done ? 'done' : ''}">${l.done ? '☑' : '☐'} ${esc(l.text)}${l.done && l.done_at ? ` <small class="na">${fmtD(l.done_at)}</small>` : ''}</li>`).join('')}</ul>`).join('')}</details>` : ''}
    ${j.entries.length ? `<div class="cl-entries">${j.entries.map(e => `<div class="cl-entry"><div class="cl-edate"><b>${fmtD(e.date)}</b><small class="na">${fmtMin(e.minutes)}</small></div><div class="cl-ebody">${e.system || e.assignment ? `<small class="na">${esc([e.assignment, e.system].filter(Boolean).join(' · '))}</small><br>` : ''}${e.text ? `<span class="cl-etext">${esc(e.text)}</span>` : ''}${e.lines.length ? `<ul class="cl-lines">${e.lines.map(l => `<li>☑ ${esc(l)}</li>`).join('')}</ul>` : ''}
      ${e.photos.length ? `<div class="cl-photos">${e.photos.map(p => `<button type="button" class="rd-fthumb cl-ph" data-cl="preview" data-u="${ph(e, p.id)}" data-n="${esc(p.name || '')}" data-pdf="0"><img src="${ph(e, p.id)}" alt="" loading="lazy"></button>`).join('')}</div>` : ''}</div></div>`).join('')}</div>` : `<p class="na">${esc(tx('Aucune intervention validée pour le moment.'))}</p>`}</section>`).join('');
}
function carHtml() {
  const c = cl.car; if (!c) return '<p class="na loading">Chargement…</p>';
  const id = [['chassis', 'N° de châssis'], ['engine_no', 'N° de moteur'], ['gearbox_no', 'N° de boîte de vitesse'], ['livery', 'Couleur / livrée'], ['race_number', 'N° de course habituel']].filter(([k]) => c[k]);
  const tabs = [['jobs', 'Interventions'], ['docs', 'Documents'], ['runs', 'Roulages']];
  return `<p><a href="#" class="cl-back">← ${esc(tx('Mes voitures'))}</a></p>
    <div class="rd-head">${carThumb(c, true)}<div><h2 class="cl-title">${esc(c.name)}</h2><small class="na">${c.category === 'rally' ? esc(tx('Rallye')) : esc(tx('Circuit'))} · ${fmtKm(c.km_total)} km</small>
    ${id.length ? `<dl class="cl-id">${id.map(([k, l]) => `<div><dt>${esc(tx(l))}</dt><dd>${esc(c[k])}</dd></div>`).join('')}</dl>` : ''}</div></div>
    <div class="bu-filter cl-tabs" role="tablist">${tabs.map(([k, l]) => `<button type="button" class="rs-pill" role="tab" data-cl="tab" data-k="${k}" aria-pressed="${cl.tab === k}">${esc(tx(l))}</button>`).join('')}</div>
    <div class="cl-pane">${cl.tab === 'jobs' ? jobsHtml(c) : cl.tab === 'docs' ? docsHtml(c) : runsHtml(c)}</div>`;
}
function draw() {
  const el = $c('cl'); if (!el) return;
  $c('cl-out').hidden = !cl.me;
  el.innerHTML = !cl.me ? loginHtml() : carHash() ? carHtml() : homeHtml();
}
async function route() {
  if (!cl.me) return draw();
  const k = carHash();
  cl.car = null; cl.jobs = null;
  if (!k) return draw();
  draw();
  try {
    cl.car = await api('/api/client/cars/' + encodeURIComponent(k)); draw();
    cl.jobs = (await api(`/api/client/cars/${encodeURIComponent(k)}/jobs`)).jobs; draw();
  } catch (e) { if (e.status === 401) { cl.me = null; cl.err = e.message; } else location.hash = ''; draw(); }
}
function lightbox(u, name, pdf) {
  const old = $c('cl-lb'); if (old) old.remove();
  const lb = document.createElement('div'); lb.id = 'cl-lb'; lb.className = 'rd-lb';
  lb.innerHTML = `<div class="rd-lb-bar"><b>${esc(name)}</b><span class="wl-sp"></span><a href="${u}" target="_blank" rel="noopener" class="mini">↗ ${esc(tx('Ouvrir dans un onglet'))}</a><button type="button" class="mini" data-cl="close">✕ ${esc(tx('Fermer'))}</button></div>${pdf ? `<iframe src="${u}"></iframe>` : `<div class="rd-lb-img"><img src="${u}" alt=""></div>`}`;
  document.body.appendChild(lb);
}

// ---- Événements ---------------------------------------------------------------------------------------------------------------------------
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-cl],#cl-send,#cl-out,.cl-back'); if (!b) { const lb = $c('cl-lb'); if (lb && e.target === lb) lb.remove(); return; }
  if (b.id === 'cl-send') {
    cl.email = ($c('cl-email').value || '').trim(); cl.err = null; if (!cl.email) return;
    cl.busy = true; draw();
    try { await api('/api/client/request-link', {method: 'POST', body: JSON.stringify({email: cl.email})}); cl.sent = true; } catch (err) { cl.err = err.message; }
    cl.busy = false; return draw();
  }
  if (b.id === 'cl-out') { try { await api('/api/client/logout', {method: 'POST', body: '{}'}); } catch {} cl.me = cl.car = cl.jobs = null; cl.sent = false; location.hash = ''; return draw(); }
  if (b.classList.contains('cl-back')) { e.preventDefault(); location.hash = ''; return; }
  const a = b.dataset.cl;
  if (a === 'tab') { cl.tab = b.dataset.k; return draw(); }
  if (a === 'preview') return lightbox(b.dataset.u, b.dataset.n, b.dataset.pdf === '1');
  if (a === 'close') { const lb = $c('cl-lb'); if (lb) lb.remove(); }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') { const lb = $c('cl-lb'); if (lb) lb.remove(); } else if (e.key === 'Enter' && e.target && e.target.id === 'cl-email') { const s = $c('cl-send'); if (s) s.click(); } });
async function boot() {
  const m = location.hash.match(/^#t=([\w-]+)/);
  if (m) {                                         // lien magique : on le brûle puis on retire le jeton de l'adresse
    history.replaceState(null, '', location.pathname);
    cl.err = null;
    try { cl.me = await api('/api/client/verify', {method: 'POST', body: JSON.stringify({token: m[1]})}); } catch (e) { cl.err = e.message; cl.me = null; }
  } else {
    try { cl.me = await api('/api/client/me'); } catch { cl.me = null; }
  }
  await route();
}
window.addEventListener('hashchange', () => /^#t=/.test(location.hash) ? boot() : route());
boot();
