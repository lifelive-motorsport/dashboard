// Registre des modules de Logbook : 4 chapitres, 8 modules (docs/BRAND.md §9). Chargé avant app.js.
// `groups` : groupes de pages du MENU rangés dans le module ; `pages` : pages du module. Les droits d'accès (catégories d'utilisateurs) se donnent page par page.
const CHAPTERS = [
  {id: 'piloter', n: '01', label: 'Piloter', modules: [
    {id: 'dashboards', label: 'Tableaux de bord', source: 'Odoo', groups: ['overview', 'xc', 'cars', 'staff', 'expenses', 'vehicles', 'marketing']}]},
  {id: 'planifier', n: '02', label: 'Planifier', modules: [
    {id: 'events', label: 'Événements', source: 'Google Agenda', pages: ['planifier/events']},
    {id: 'resources', label: 'Ressources', source: 'Google Agenda · Odoo', pages: ['planifier/resources']}]},
  {id: 'consigner', n: '03', label: 'Consigner', modules: [
    {id: 'timesheets', label: 'Pointages', source: 'Odoo', pages: ['consigner/timesheets']},
    {id: 'rides', label: 'Roulages', source: 'Logbook', pages: ['consigner/rides']},
    {id: 'consumables', label: 'Consommables', source: 'Odoo (stock)', pages: ['consigner/consumables']}]},
  {id: 'administrer', n: '04', label: 'Administrer', modules: [
    {id: 'crew', label: 'Équipage', source: 'Google Workspace', pages: ['others/users']},
    {id: 'connections', label: 'Connexions', source: 'Odoo · Google', pages: ['others/tags']}]},
];
// Toutes les pages d'un module, dans l'ordre : [clé, libellé]
function modulePages(mod) {
  const out = [];
  (mod.groups || []).forEach(g => { const m = MENU.find(x => x[0] === g); if (m) m[2].forEach(([i, l]) => out.push([g + '/' + i, l, m[1]])); });
  (mod.pages || []).forEach(k => { const [g, i] = k.split('/'), m = MENU.find(x => x[0] === g), it = m && m[2].find(x => x[0] === i); if (it) out.push([k, it[1], m[1]]); });
  return out;
}
// Chapitre et module d'une page
function moduleOf(key) {
  for (const c of CHAPTERS) for (const m of c.modules) if (modulePages(m).some(p => p[0] === key)) return {chapter: c, module: m};
  return null;
}
const pageTitle = key => {
  if (key === 'home/welcome') return 'Accueil';
  const mo = moduleOf(key), it = item(key); if (!mo || !it) return '';
  if (mo.module.id === 'dashboards') return `${esc(it.grp[1])} <small>›</small> ${esc(it.it[1])}`;
  return `${esc(mo.chapter.label)} <small>›</small> ${esc(mo.module.label)}${it.it[1] !== mo.module.label ? ` <small>›</small> ${esc(it.it[1])}` : ''}`;
};
