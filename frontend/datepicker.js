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
  } else if (!(t.closest && t.closest('.pe-cal, .lv-cal, .ts-cal, .dp-cal'))) dpClose();
}, true);
document.addEventListener('keydown', e => { if (e.key === 'Escape') dpClose(); });

// Champ date générique : saisie jj/mm/aaaa + calendrier. `attrs` (ex. 'data-adj="date" data-i="2"') va sur le champ caché AAAA-MM-JJ, qui porte la valeur et reçoit « change ».
const dpField = (attrs, iso, dis = '') => `<span class="datef"><input class="sdin dp-t" value="${iso ? fmtDate(iso) : ''}" placeholder="jj/mm/aaaa" inputmode="numeric" maxlength="10" autocomplete="off"${dis}><button type="button" class="dp-cal" aria-label="Calendrier" title="Calendrier"${dis}><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1.5v3M11 1.5v3"/></svg></button><input type="date" class="dp-h" ${attrs} value="${iso || ''}" tabindex="-1" aria-hidden="true"></span>`;
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('.dp-cal'); if (b && !b.disabled) dpOpen(b.parentElement.querySelector('.dp-h'), b); });
document.addEventListener('change', e => {
  const t = e.target; if (!t.classList || !t.classList.contains('dp-t')) return;
  const h = t.parentElement.querySelector('.dp-h'), iso = t.value.trim() ? peParse(t.value) : '';
  if (iso === null) { t.setCustomValidity('jj/mm/aaaa'); t.reportValidity(); return; }
  t.setCustomValidity(''); h.value = iso; h.dispatchEvent(new Event('change', {bubbles: true}));
});

// Saisie des dates sans séparateurs : « 12102026 » devient « 12/10/2026 » (les « / », « . » et « - » tapés à la main restent acceptés tels quels).
document.addEventListener('input', e => {
  const t = e.target; if (!t.matches || !t.matches('.dp-t, .pe-d, .lv-d, .ts-d') || (e.inputType || '').startsWith('delete')) return;
  const v = t.value; if (/[.\-]/.test(v) || /(^|\D)\d(\D|$)/.test(v) && /\D/.test(v)) return;
  const d = v.replace(/\D/g, '').slice(0, 8), out = d.length > 4 ? `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}` : d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
  if (out !== v) t.value = out;
});
