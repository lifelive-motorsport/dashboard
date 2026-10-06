// Trafic d'après Google Analytics 4 : blocs réutilisés par les webshops (XC, Goldspeed) et par Others › Marketing (site vitrine).
// Chargé avant app.js ; utilise ses fonctions (esc, num, pct, eur, kpi, table, B, NOTE, multiLineChart, vsPrev) au moment de l'appel.
const gaDur = s => { s = Math.round(s || 0); return s >= 60 ? `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')}` : `${s} s`; };

function gaSite(d, key) {                       // -> {site} ou {msg, cls}
  const a = d.analytics;
  if (!a || a.unconfigured) return {msg: 'Google Analytics n’est pas encore relié au dashboard (identifiant de propriété à renseigner).', cls: 'na'};
  if (a.unavailable) return {msg: a.unavailable, cls: 'na'};
  const s = a[key];
  if (!s || s.error) return {msg: 'Google Analytics indisponible : ' + ((s && s.error) || 'pas de données'), cls: 'neg'};
  return {site: s};
}
const gaErr = (s, part) => (s.errors && s.errors[part]) ? `<p class="neg">Indisponible (${esc(s.errors[part])})</p>` : '';

function gaBlocks(key, o = {}) {
  const {shop = false, pages = false, geo = false} = o;
  const wrap = (fn, part) => d => { const g = gaSite(d, key); return g.msg ? `<p class="${g.cls}">${esc(g.msg)}</p>` : (gaErr(g.site, part) || fn(g.site, d)); };
  const out = [
    B(`ga_${key}_traffic`, 'Trafic (Google Analytics)', wrap((s) => {
      const t = s.totals, c = t.current, p = t.previous, yr = t.previous_period.from.slice(0, 4);
      const cmp = k => (p && p[k] > 0) ? vsPrev(c[k], p[k], yr) : '';
      if (!c.sessions) return `<p class="neg">Aucune session pour ${esc(s.host || 'ce site')}${s.path ? ' (pages « ' + esc(s.path) + ' »)' : ''} sur la période.</p>`
        + (s.hosts && s.hosts.length ? `<small class="na">Noms de domaine vus par Google Analytics sur la période : ${s.hosts.map(h => esc(h.name) + ' (' + num(h.sessions) + ')').join(', ')}. Si le vôtre est écrit autrement, indiquez-le avec la variable GA_HOST_XC / GA_HOST_GS / GA_HOST_SITE.</small>` : '<small class="na">Vérifiez le nom de domaine (GA_HOST_XC / GA_HOST_GS / GA_HOST_SITE) et la période.</small>');
      const conv = c.sessions ? c.ecommercePurchases / c.sessions : null;
      const cards = kpi('Sessions', num(c.sessions), '', cmp('sessions')) + kpi('Utilisateurs', num(c.totalUsers), '', cmp('totalUsers')) + kpi('Pages vues', num(c.screenPageViews), '', cmp('screenPageViews'))
        + kpi('Engagement', pct(c.engagementRate || 0), '', 'sessions engagées') + kpi('Durée moyenne', gaDur(c.averageSessionDuration), '', 'par session')
        + (shop ? kpi('Achats', num(c.ecommercePurchases), '', cmp('ecommercePurchases')) + kpi('Conversion', conv == null ? '–' : pct(conv), '', 'achats ÷ sessions') : '');
      return `<div class="kpis">${cards}</div>` + (shop && c.addToCarts ? `<small class="na">Parcours : ${num(c.addToCarts)} ajout${c.addToCarts > 1 ? 's' : ''} au panier → ${num(c.checkouts)} paiement${c.checkouts > 1 ? 's' : ''} lancé${c.checkouts > 1 ? 's' : ''} → ${num(c.ecommercePurchases)} achat${c.ecommercePurchases > 1 ? 's' : ''} (événements e-commerce envoyés par le site).</small>` : '')
        + multiLineChart(s.series.points, [{key: 'sessions', label: 'Sessions', cls: 's1'}, {key: 'users', label: 'Utilisateurs', cls: 's2'}],
          p => `${p.label} : ${num(p.sessions)} sessions, ${num(p.users)} utilisateurs, ${num(p.views)} pages vues` + (shop ? `, ${num(p.purchases)} achats` : ''),
          `Par ${s.series.granularity === 'week' ? 'semaine' : 'mois'}, ${esc(s.host || '')}${s.path ? ' · pages « ' + esc(s.path) + ' »' : ' · toutes les pages'}. Variation par rapport à la même période de ${yr}. Les visiteurs qui refusent les cookies ne sont pas comptés.`);
    }, 'totals')),
    B(`ga_${key}_channels`, 'Canaux d’acquisition', wrap(s => {
      if (!s.channels || !s.channels.length) return '<p class="na">Aucune donnée sur la période.</p>';
      return table(['Canal', 'Sessions', '% des sessions', 'Utilisateurs'].concat(shop ? ['Achats'] : []),
        s.channels.map(c => `<tr><td>${esc(c.name)}</td><td>${num(c.sessions)}</td><td class="sharecell"><span class="sharebar" style="width:${Math.round(c.share * 100)}%"></span><span>${pct(c.share)}</span></td><td>${num(c.users)}</td>${shop ? `<td>${num(c.purchases)}</td>` : ''}</tr>`), 'prodtable')
        + '<small class="na">Canal = regroupement par défaut de Google Analytics (recherche naturelle, direct, réseaux sociaux, e-mail, sites référents, publicité…).</small>';
    }, 'channels')),
  ];
  if (pages) out.push(B(`ga_${key}_pages`, shop ? 'Pages les plus visitées (Google Analytics)' : 'Pages les plus visitées', wrap(s => {
    if (!s.pages || !s.pages.length) return '<p class="na">Aucune page sur la période.</p>';
    return table(['#', 'Page', 'Vues', '% des vues', 'Utilisateurs'], s.pages.map((p, i) => `<tr><td>${i + 1}</td><td class="prod">${esc(p.title)}<br><small class="na">${esc(p.path)}</small></td><td>${num(p.views)}</td><td>${pct(p.share)}</td><td>${num(p.users)}</td></tr>`), 'prodtable');
  }, 'pages')));
  if (geo) out.push(B(`ga_${key}_geo`, 'Pays et appareils', wrap(s => {
    const part = (title, rows) => `<h4 class="sub">${title}</h4>` + table(['', 'Sessions', '%'], (rows || []).map(r => `<tr><td>${esc(r.name)}</td><td>${num(r.sessions)}</td><td>${pct(r.share)}</td></tr>`), 'prodtable');
    return part('Pays (top 8)', s.countries) + part('Appareils', s.devices);
  }, 'countries')));
  return out;
}
