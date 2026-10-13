// Calendrier de sélection de date (semaine du lundi au dimanche, quelle que soit la langue du navigateur).
// dpOpen(input date caché, bouton) : au choix d'un jour, le champ reçoit la valeur AAAA-MM-JJ et un événement « change ».
let dpEl = null, dpState = null;
const dpIso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
function dpClose() { if (dpEl) dpEl.remove(); dpEl = dpState = null; }
function dpDraw() {
  const s = dpState, y = s.view.getFullYear(), m = s.view.getMonth(), loc = LOCALE();
  const first = new Date(y, m, 1), lead = (first.getDay() + 6) % 7, start = new Date(y, m, 1 - lead), today = dpIso(new Date());
  const wd = Array.from({length: 7}, (_, i) => new Intl.DateTimeFormat(loc, {weekday: 'short'}).format(new Date(2024, 0, 1 + i)));
  let cells = '';
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i), iso = dpIso(d);
    const off = (s.min && iso < s.min) || (s.max && iso > s.max);
    cells += `<button type="button" class="dp-d${d.getMonth() !== m ? ' out' : ''}${iso === s.value ? ' sel' : ''}${iso === today ? ' today' : ''}" data-iso="${iso}" ${off ? 'disabled' : ''}>${d.getDate()}</button>`;
  }
  dpEl.innerHTML = `<div class="dp-head"><button type="button" class="dp-nav" data-nav="-1" aria-label="Mois précédent">‹</button><b>${new Intl.DateTimeFormat(loc, {month: 'long', year: 'numeric'}).format(first)}</b><button type="button" class="dp-nav" data-nav="1" aria-label="Mois suivant">›</button></div>`
    + `<div class="dp-grid">${wd.map(w => `<span class="dp-w">${w}</span>`).join('')}${cells}</div><div class="dp-foot"><button type="button" class="mini" data-today>Aujourd’hui</button></div>`;
}
function dpOpen(input, btn) {
  dpClose();
  const v = input.value || dpIso(new Date()), [y, m, d] = v.split('-').map(Number);
  dpState = {input, value: input.value, min: input.min || '', max: input.max || '', view: new Date(y, m - 1, 1)};
  dpEl = document.createElement('div'); dpEl.className = 'dp-pop'; document.body.appendChild(dpEl); dpDraw();
  const r = btn.getBoundingClientRect(), h = dpEl.offsetHeight, w = dpEl.offsetWidth;
  dpEl.style.left = Math.max(8, Math.min(r.right - w, innerWidth - w - 8)) + 'px';
  dpEl.style.top = (r.bottom + h + 8 > innerHeight && r.top > h + 8 ? r.top - h - 4 : r.bottom + 4) + 'px';
}
document.addEventListener('click', e => {
  if (!dpEl) return;
  const t = e.target.closest ? e.target : e.target.parentElement;
  if (dpEl.contains(t)) {
    const nav = t.closest('[data-nav]'), day = t.closest('[data-iso]'), td = t.closest('[data-today]');
    if (nav) { dpState.view = new Date(dpState.view.getFullYear(), dpState.view.getMonth() + (+nav.dataset.nav), 1); dpDraw(); }
    else if (day || td) {
      const iso = day ? day.dataset.iso : dpIso(new Date()), inp = dpState.input; dpClose();
      inp.value = iso; inp.dispatchEvent(new Event('change', {bubbles: true}));
    }
  } else if (!(t.closest && t.closest('.pe-cal, .lv-cal, .ts-cal'))) dpClose();
}, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') dpClose(); });
