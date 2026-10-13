// Bascule d'affichage clair / sombre (en-tête). Sans choix, l'application suit la préférence de l'appareil ; le choix est gardé dans ce navigateur (lm_theme).
const themeNow = () => document.documentElement.dataset.theme || (window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
const THEME_ICON = {
  light: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  dark: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'};
function themeApply(th, save) {
  document.documentElement.dataset.theme = th;
  if (save) { try { localStorage.setItem('lm_theme', th); } catch {} }
  const b = document.getElementById('theme-btn');
  if (b) { b.innerHTML = THEME_ICON[th === 'dark' ? 'light' : 'dark']; b.setAttribute('aria-pressed', String(th === 'dark')); b.title = th === 'dark' ? 'Passer en affichage clair' : 'Passer en affichage sombre'; b.setAttribute('aria-label', b.title); }
  const m = document.querySelector('meta[name=theme-color]'); if (m) m.content = th === 'dark' ? '#2B2B2B' : '#F4F4F2';
  if (typeof render === 'function' && document.getElementById('app') && !document.getElementById('app').hidden) render();       // icônes de BU et graphiques suivent le thème
}
document.addEventListener('DOMContentLoaded', () => {
  themeApply(themeNow(), false);
  const b = document.getElementById('theme-btn');
  if (b) b.addEventListener('click', () => themeApply(themeNow() === 'dark' ? 'light' : 'dark', true));
});
