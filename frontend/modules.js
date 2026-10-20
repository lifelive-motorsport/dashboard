// Registre des modules de Logbook : 5 chapitres (docs/BRAND.md §9). Chargé avant app.js.
// `groups` : groupes de pages du MENU rangés dans le module ; `pages` : pages du module. Les droits d'accès (catégories d'utilisateurs) se donnent page par page.
const CHAPTERS = [
  {id: 'piloter', n: '01', label: 'Piloter', modules: [
    {id: 'dashboards', label: 'Tableaux de bord', source: 'Odoo', groups: ['overview', 'xc', 'cars', 'staff', 'expenses', 'vehicles', 'marketing']}]},
  {id: 'planifier', n: '02', label: 'Planifier', modules: [
    {id: 'planning', label: 'Planning', source: 'Google Agenda', pages: ['planifier/planning']},
    {id: 'events', label: 'Événements', source: 'Google Agenda', pages: ['planifier/events']},
    {id: 'resources', label: 'Ressources', source: 'Google Agenda · Odoo', sub: true, pages: ['planifier/res_staff', 'planifier/res_ext', 'planifier/res_veh']}]},
  {id: 'technique', n: '03', label: 'Opérer', modules: [
    {id: 'wall', label: 'Cockpit', source: 'Logbook · Google Agenda', pages: ['consigner/wall']},
    {id: 'timesheets', label: 'Atelier', source: 'Logbook · Odoo', sub: true, pages: ['consigner/timesheets', 'consigner/team', 'consigner/jobs']},
    {id: 'garage', label: 'Garage', source: 'Logbook · Odoo · Google Agenda', pages: ['consigner/rides']},
    {id: 'parts', label: 'Magasin de pièces', source: 'Logbook', pages: ['consigner/parts']},
    {id: 'tyres', label: 'Pneus', source: 'Logbook', pages: ['consigner/tyres']},
    {id: 'consumables', label: 'Consommables', source: 'Odoo (stock)', pages: ['consigner/consumables']},
    {id: 'runs', label: 'Roulages', source: 'Logbook', pages: ['consigner/runs']},
    {id: 'runreports', label: 'Run reports', source: 'Logbook', pages: ['consigner/runreports']},
    {id: 'models', label: 'Modèles', source: 'Logbook', sub: true, pages: ['consigner/job_models', 'consigner/form_models', 'consigner/arch_models']}]},
  {id: 'consigner', n: '04', label: 'Consigner', modules: [
    {id: 'leaves', label: 'Congés', source: 'Logbook · Google Agenda', pages: ['consigner/leaves']},
    {id: 'absences', label: 'Absences', source: 'Logbook · Google Agenda', pages: ['consigner/absences']}]},
  {id: 'administrer', n: '05', label: 'Administrer', modules: [
    {id: 'crew', label: 'Équipage', source: 'Google Workspace', pages: ['others/users']},
    {id: 'clients', label: 'Accès clients', source: 'Logbook', pages: ['others/clients']},
    {id: 'history', label: 'Historique', source: 'Logbook', pages: ['others/history']},
    {id: 'connections', label: 'Connexions', source: 'Odoo · Google', pages: ['others/tags']}]},
];
// Pages réservées au Super User : jamais attribuables à une catégorie d'utilisateurs (Événements et Ressources sont cochables ; la modification des fiches du staff reste au Super User)
const SUPER_ONLY = new Set(['others/users', 'others/clients', 'others/history']);
// Pages « Modèles » : réservées au chef d'atelier, à l'ingénieur / coordinateur et au Super User (en plus de la case cochée pour la catégorie) ; le serveur refuse aussi les autres
const WORKSHOP_ONLY = new Set(['consigner/job_models', 'consigner/form_models', 'consigner/arch_models']);
// Pages que seul le Super User ou une catégorie qui les a cochées ouvre (ni « Administrateur » ni les autres)
const GRANT_ONLY = new Set(['consigner/wall', 'consigner/rides', 'consigner/parts', 'consigner/runs', 'consigner/runreports', 'consigner/tyres', 'consigner/job_models', 'consigner/form_models', 'consigner/arch_models', 'planifier/events', 'planifier/res_staff', 'planifier/res_ext', 'planifier/res_veh']);
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
