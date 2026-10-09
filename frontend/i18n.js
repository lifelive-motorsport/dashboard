// Internationalisation FR / EN. Le français est la langue source : le dictionnaire (i18n-en.js) associe un texte français à sa traduction anglaise.
// Un texte absent du dictionnaire reste en français (repli) : on complète le dictionnaire au fil de l'eau. Chargé en premier.
let LANG = (() => { try { return localStorage.getItem('lm_lang') === 'en' ? 'en' : 'fr'; } catch { return 'fr'; } })();
const LOCALE = () => LANG === 'en' ? 'en-GB' : 'fr-BE';
const EN = {};                 // texte français exact -> anglais (rempli par i18n-en.js)
const EN_PATTERNS = [];        // [RegExp, (match) => anglais] pour les phrases à valeurs variables
document.documentElement.lang = LANG;

// Traduit un texte (espaces de début et de fin conservés) ; renvoie le texte d'origine s'il n'y a pas de traduction.
function tx(s) {
  if (LANG !== 'en' || !s) return s;
  const k = s.trim(); if (!k) return s;
  let out = EN[k];
  if (out === undefined) for (const [re, fn] of EN_PATTERNS) { const m = re.exec(k); if (m) { out = fn(m); break; } }
  if (out === undefined && k.includes(' · ')) { const parts = k.split(' · '), tr = parts.map(p => { const o = EN[p.trim()]; return o === undefined ? p : o; }); if (tr.some((p, i) => p !== parts[i])) out = tr.join(' · '); }
  return out === undefined ? s : s.replace(k, out);
}
const t = tx;

const I18N_ATTRS = ['title', 'placeholder', 'aria-label', 'alt'];
const i18nSkip = n => { for (let e = n.nodeType === 1 ? n : n.parentElement; e; e = e.parentElement) { if (/^(SCRIPT|STYLE|TEXTAREA)$/.test(e.tagName) || e.hasAttribute('data-notrans')) return true; } return false; };
function i18nNode(n) {
  if (n.nodeType === 3) {
    if (n.__en !== undefined && n.nodeValue === n.__en) return;
    if (i18nSkip(n)) return;
    const fr = n.nodeValue, en = tx(fr);
    if (en !== fr) { n.__fr = fr; n.__en = en; n.nodeValue = en; } else { delete n.__fr; delete n.__en; }
  } else if (n.nodeType === 1 && !i18nSkip(n)) {
    I18N_ATTRS.forEach(a => { if (n.hasAttribute(a)) { const v = n.getAttribute(a), key = 'data-fr-' + a; if (n.hasAttribute(key) && n.getAttribute(a) === n.__enAttrs?.[a]) return; const en = tx(v); if (en !== v) { n.setAttribute(key, v); (n.__enAttrs = n.__enAttrs || {})[a] = en; n.setAttribute(a, en); } } });
    for (const c of n.childNodes) i18nNode(c);
  }
}
function i18nRestore(root) {
  const w = document.createTreeWalker(root, NodeFilter.SHOW_ALL);
  for (let n = w.currentNode; n; n = w.nextNode()) {
    if (n.nodeType === 3 && n.__fr !== undefined) { n.nodeValue = n.__fr; delete n.__fr; delete n.__en; }
    else if (n.nodeType === 1) I18N_ATTRS.forEach(a => { const key = 'data-fr-' + a; if (n.hasAttribute(key)) { n.setAttribute(a, n.getAttribute(key)); n.removeAttribute(key); delete n.__enAttrs; } });
  }
}
let i18nObs = null;
function i18nStart() {
  if (!i18nObs) i18nObs = new MutationObserver(muts => { if (LANG !== 'en') return; for (const m of muts) { if (m.type === 'childList') m.addedNodes.forEach(i18nNode); else if (m.type === 'characterData') i18nNode(m.target); else if (m.type === 'attributes') i18nNode(m.target); } });
  i18nObs.observe(document.body, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: I18N_ATTRS});
}
function setLang(l) {
  LANG = l === 'en' ? 'en' : 'fr';
  try { localStorage.setItem('lm_lang', LANG); } catch {}
  document.documentElement.lang = LANG;
  i18nObs && i18nObs.disconnect();
  if (LANG === 'en') i18nNode(document.body); else i18nRestore(document.body);
  i18nStart();
  document.querySelectorAll('.lang button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === LANG)));
  document.title = LANG === 'en' ? 'Logbook — Lifelive Motorsport' : 'Logbook — Lifelive Motorsport';
  if (typeof render === 'function' && !document.getElementById('app').hidden) render();
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.lang button').forEach(b => { b.setAttribute('aria-pressed', String(b.dataset.lang === LANG)); b.addEventListener('click', () => { if (b.dataset.lang !== LANG) setLang(b.dataset.lang); }); });
  i18nStart(); if (LANG === 'en') i18nNode(document.body);
});
