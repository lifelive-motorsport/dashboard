// Trafic d'après Google Analytics 4 : blocs réutilisés par les webshops (XC, Goldspeed) et par Others › Marketing (site vitrine).
// Chargé avant app.js ; utilise ses fonctions (esc, num, pct, eur, kpi, table, B, NOTE, multiLineChart, vsPrev) au moment de l'appel.
const gaDur = s => { s = Math.round(s || 0); return s >= 60 ? `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')}` : `${s} s`; };

// Lien vers une page du site (nouvel onglet) ; adresse https construite à partir du nom de domaine du site et du chemin, jamais d'un lien brut.
function pageLink(host, path, text) {
  if (!host || typeof path !== 'string' || !/^\/[^\s]*$/.test(path)) return esc(text);
  return `<a class="olink" href="${esc('https://' + host + path)}" target="_blank" rel="noopener noreferrer" title="Ouvrir la page">${esc(text)}</a>`;
}

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
    return table(['#', 'Page', 'Vues', '% des vues', 'Utilisateurs'], s.pages.map((p, i) => `<tr><td>${i + 1}</td><td class="prod">${pageLink(s.host, p.path, p.title)}<br><small class="na">${esc(p.path)}</small></td><td>${num(p.views)}</td><td>${pct(p.share)}</td><td>${num(p.users)}</td></tr>`), 'prodtable');
  }, 'pages')));
  if (geo) out.push(B(`ga_${key}_geo`, 'Pays et appareils', wrap(s => {
    const part = (title, rows) => `<h4 class="sub">${title}</h4>` + table(['', 'Sessions', '%'], (rows || []).map(r => `<tr><td>${esc(r.name)}</td><td>${num(r.sessions)}</td><td>${pct(r.share)}</td></tr>`), 'prodtable');
    return part('Pays (top 8)', s.countries) + part('Appareils', s.devices);
  }, 'countries')));
  return out;
}

// Marketing › Dépenses marketing : comptes de charges marketing (602019, 602059, 612050), évolution, fournisseurs, remarque sur l'investissement.
function marketingBlocks() {
  const wrap = fn => d => { const m = d.marketing; return (!m || m.unavailable) ? `<p class="na">${esc((m && m.unavailable) || 'Indisponible pour le moment.')}</p>` : fn(m, d); };
  return [
    B('mk_kpi', 'Dépenses marketing', wrap(m => `<div class="kpis">${kpi('Total des dépenses', eur(m.total))}${m.accounts.map(a => kpi(a.name || a.code, eur(a.amount), '', `${a.code} · ${pct(a.share)} du total`)).join('')}</div>`
      + `<small class="na">Charges des comptes ${esc((m.codes || []).join(', '))} (factures fournisseurs comptabilisées, avoirs déduits), hors taxes.</small>`)),
    B('mk_evol', 'Évolution des dépenses', wrap(m => lineChart(m.series.points, null, `Dépenses marketing par ${m.series.granularity === 'week' ? 'semaine' : 'mois'}. Survolez un point pour le détail.`,
      v => eur(Math.round(v)), p => `${p.label} : ${eur(p.total)}`, ''))),
    B('mk_acc', 'Par compte', wrap(m => m.accounts.length ? table(['Compte', 'Libellé', 'Montant HT', '% du total'], m.accounts.map(a => `<tr><td>${esc(a.code)}</td><td class="prod">${esc(a.name)}</td><td>${eur(a.amount)}</td><td>${pct(a.share)}</td></tr>`)
      .concat([`<tr class="tot"><td></td><td>Total</td><td>${eur(m.total)}</td><td>100,0 %</td></tr>`]), 'prodtable') : '<p class="na">Aucune dépense sur la période.</p>')),
    B('mk_sup', 'Principaux fournisseurs', wrap(m => m.suppliers.length ? table(['#', 'Fournisseur', 'Montant HT', '% du total', 'Factures'], m.suppliers.map((s, i) => `<tr><td>${i + 1}</td><td class="prod">${esc(s.name)}</td><td>${eur(s.amount)}</td><td>${pct(s.share)}</td><td>${num(s.invoices)}</td></tr>`), 'prodtable')
      + '<small class="na">Contacts d’une même société fusionnés (et étiquettes « regroup_fournisseur= » appliquées).</small>' : '<p class="na">Aucun fournisseur sur la période.</p>')),
    B('mk_invest', 'Remarque : investissement marketing', wrap(m => {
      const v = m.invest; if (!v) return '<p class="na">Aucun investissement marketing immobilisé repéré cette année.</p>';
      return `<div class="note"><b>Événement ${esc(v.name)}</b> : un investissement marketing de <b>${eur(v.capex)}</b> lié à cet événement a été comptabilisé en immobilisation (comptes INVEST) et non en charge. Il est <b>amorti sur ${v.amort_months ? v.amort_months + ' mois' : 'une durée à préciser'}</b>${v.amort_months ? ` (${Math.round(v.amort_months / 12 * 10) / 10} ans, ≈ ${eur(v.amort_monthly)} par mois)` : ''}${v.amort ? ` — ${eur(v.amort)} déjà amortis en ${v.year}` : ''}. Il n’est donc pas repris dans les dépenses marketing ci-dessus.</div>`;
    }), true),
  ];
}
