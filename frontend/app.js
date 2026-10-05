const $ = id => document.getElementById(id);
const eur = n => new Intl.NumberFormat('fr-BE', {style:'currency', currency:'EUR', maximumFractionDigits:0}).format(n);
const pct = n => (n*100).toFixed(1).replace('.', ',') + ' %';
const cls = n => n < 0 ? 'neg' : 'pos';
const GROUP = {XC:'XC Cross Car', CARS:'CARS (Modern Rally, Historic Rally, Historic Racing, CARS Others)', OTHER:'Non affecté'};
const TABS = [['total','Total'],['XC','XC'],['MODERN_RALLY','Modern Rally'],['HISTORIC_RALLY','Historic Rally'],['HISTORIC_RACING','Historic Racing']];
let token = sessionStorage.getItem('idt'), data = null, tab = 'total';

function range() {
  const t = new Date(), y = t.getFullYear(), f = d => d.toISOString().slice(0,10);
  switch ($('period').value) {
    case 'month': return [f(new Date(Date.UTC(y, t.getMonth(), 1))), f(t)];
    case 'prev': return [`${y-1}-01-01`, `${y-1}-12-31`];
    case '12m': return [f(new Date(Date.UTC(y-1, t.getMonth(), t.getDate()+1))), f(t)];
    default: return [`${y}-01-01`, f(t)];
  }
}
const kpi = (l, v, c='') => `<div class="card"><div class="v ${c}">${v}</div><div class="l">${l}</div></div>`;

function barRows(items, max) {
  return items.map(b => `<div class="row"><span>${b.label}</span>
    <div class="bars"><div class="bar ca" style="width:${Math.max(0,b.ca)/max*100}%"></div>
    <div class="bar m ${b.margin<0?'n':''}" style="width:${Math.abs(b.margin)/max*100}%"></div></div>
    <span class="num">${eur(b.ca)}<br><small class="${cls(b.margin)}">${eur(b.margin)}</small></span></div>`).join('');
}

function render() {
  const {pnl, balance_sheet: bs} = data, t = pnl.total;
  $('kpis').innerHTML = kpi('Chiffre d’affaires', eur(t.ca)) + kpi('Marge brute', eur(t.margin), cls(t.margin))
    + kpi('Marge brute / CA', pct(t.margin_pct), cls(t.margin));
  const bus = pnl.bus.filter(b => b.ca || b.direct_costs);
  const max = Math.max(...bus.map(b => Math.abs(b.ca)), 1);
  $('bus').innerHTML = `<div class="card">${barRows(bus, max)}<small class="na">Barre rouge : CA — barre verte/rouge : marge brute (hors personnel et véhicules)</small></div>`;
  $('groups').innerHTML = pnl.groups.filter(g => g.ca || g.direct_costs).map(g =>
    `<div class="card"><div class="l">${GROUP[g.key]}</div><div class="v">${eur(g.ca)}</div>
     <div class="l">Marge brute <b class="${cls(g.margin)}">${eur(g.margin)}</b> · ${g.ca ? pct(g.margin/g.ca) : '–'}</div></div>`).join('');
  $('bs').innerHTML = kpi('Trésorerie', eur(bs.cash), cls(bs.cash)) + kpi('Créances clients', eur(bs.receivables))
    + kpi('Dettes fournisseurs', eur(bs.payables));
  $('tabs').innerHTML = TABS.map(([k,l]) => `<button data-k="${k}" class="${k===tab?'on':''}">${l}</button>`).join('');
  const tc = data.top_clients;
  $('clients').innerHTML = tc.unavailable ? `<p class="na">${tc.unavailable}</p>`
    : (tc[tab] || []).map(c => `<li><span>${c.name}</span><b>${eur(c.ca)}</b></li>`).join('');
  const ws = data.webshops;
  $('shops').innerHTML = ws.unavailable ? `<p class="na">${ws.unavailable}</p>` : ws.map(w =>
    `<div class="card"><div class="l">${w.name}</div><div class="v">${eur(w.revenue)}</div>
     <div class="l">${w.orders} commandes · panier moyen ${eur(w.avg_basket)}</div></div>`).join('');
  const d = new Date(data.generated_at);
  $('foot').textContent = `Source : ${data.source}${data.source==='demo' ? ' (DONNÉES FICTIVES)' : ''} — période ${data.period.from} → ${data.period.to} — mis à jour ${d.toLocaleString('fr-BE')}`;
  $('app').hidden = false;
}

async function load(force) {
  const [f, t] = range();
  try {
    const r = await fetch(`/api/dashboard?from=${f}&to=${t}${force?'&refresh=true':''}`, {headers: token ? {Authorization: 'Bearer ' + token} : {}});
    if (r.status === 401) { sessionStorage.removeItem('idt'); token = null; return needLogin(); }
    if (!r.ok) throw new Error(r.status === 403 ? 'Accès non autorisé pour ce compte' : r.status === 502 ? 'Odoo est momentanément injoignable (erreur 502)' : 'Erreur ' + r.status);
    data = await r.json(); $('status').textContent = ''; $('status').className = ''; $('login').hidden = true; render();
  } catch (e) { $('status').textContent = e.message + (data ? ' — affichage des dernières données' : ''); $('status').className = 'err'; }
}

let cfg;
function needLogin() {
  $('app').hidden = true; $('login').hidden = false;
  google.accounts.id.initialize({client_id: cfg.google_client_id, hd: undefined,
    callback: r => { token = r.credential; sessionStorage.setItem('idt', token); load(); }});
  google.accounts.id.renderButton($('g_btn'), {theme: 'filled_black', size: 'large', width: 280, locale: 'fr'});
}

$('period').onchange = () => load();
$('refresh').onclick = () => load(true);
$('tabs').onclick = e => { if (e.target.dataset.k) { tab = e.target.dataset.k; render(); } };
setInterval(() => document.visibilityState === 'visible' && load(), 60000);
document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && load());

(async () => {
  cfg = await (await fetch('/api/config')).json();
  if (cfg.auth) {
    await new Promise(res => { const s = document.createElement('script'); s.src = 'https://accounts.google.com/gsi/client'; s.onload = res; document.head.append(s); });
    if (!token) return needLogin();
  }
  load();
})();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');
