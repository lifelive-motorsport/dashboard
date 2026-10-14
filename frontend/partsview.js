// Opérer › Magasin de pièces : toutes les pièces d'UNE voiture (vue à plat de l'arborescence du Garage) avec leur fonction, leurs kilomètres, leurs maintenances et leur état ;
// la saisie (remplacer, maintenance, modification) reste dans la fiche de la voiture du Garage. Les modèles d'architecture ont leur page : Modèles › Modèles d'architecture voiture.
// Données : /api/rides/cars (liste) et /api/rides/cars/{clé} (arborescence calculée par le serveur).
const pv = {cars: null, key: '', car: null, q: '', removed: false, loading: false, err: null};
const PV_KEY = 'lm_pv_car';
function partsBlocks() { return [{static: '<section class="block" data-bid="pv"><div id="pv-view"><p class="na loading">Chargement…</p></div></section>'}]; }

async function pvLoad() {
  pv.loading = true; pv.err = null; pvDraw();
  try {
    if (!pv.cars) pv.cars = (await rsCall('/api/rides/cars')).cars.filter(c => !c.archived).sort((a, b) => a.name.localeCompare(b.name));
    if (!pv.key) { try { pv.key = localStorage.getItem(PV_KEY) || ''; } catch {} }
    if (pv.key && !pv.cars.some(c => c.key === pv.key)) pv.key = '';
    if (pv.key) pv.car = await rsCall('/api/rides/cars/' + encodeURIComponent(pv.key));
  } catch (e) { pv.err = e.message; }
  pv.loading = false; pvDraw();
}
// Arborescence -> lignes à plat (chemin « Ensemble › Sous-ensemble › Composant »)
function pvRows(nodes, path = []) {
  return nodes.flatMap(n => {
    const p = path.concat(n.name), self = n.group ? [] : [{n, path: p}];
    return self.concat(pvRows(n.children || [], p));
  });
}
const pvFold = s => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
function pvDraw() {
  const el = document.getElementById('pv-view'); if (!el) return;
  if (pv.err) { el.innerHTML = `<p class="neg">${esc(pv.err)}</p>`; return; }
  if (!pv.cars) { el.innerHTML = '<p class="na loading">Chargement…</p>'; return; }
  const bar = `<div class="sdbar"><select class="sdin" id="pv-car"><option value="">${esc(tx('— Choisir une voiture —'))}</option>${pv.cars.map(c => `<option value="${esc(c.key)}"${pv.key === c.key ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select>
    ${pv.car ? `<input type="search" class="sdin rd-q" id="pv-q" placeholder="${esc(tx('Rechercher une pièce…'))}" value="${esc(pv.q)}" autocomplete="off"><label class="chk"><input type="checkbox" id="pv-rm" ${pv.removed ? 'checked' : ''}> ${esc(tx('afficher les pièces démontées'))}</label><button type="button" data-pv="garage">${esc(tx('Ouvrir dans le Garage'))}</button>` : ''}${pv.loading ? '<small class="na loading">Chargement…</small>' : ''}</div>`;
  el.innerHTML = bar + (pv.car ? `<div id="pv-list">${pvTable()}</div>` : `<p class="na">${esc(tx('Choisissez une voiture pour voir toutes ses pièces.'))}</p>`);
}
function pvTable() {
  const words = pv.q.trim().split(/\s+/).filter(Boolean).map(pvFold);
  const rows = pvRows(pv.car.tree || []).filter(({n, path}) => (pv.removed || !n.removed_at) && words.every(w => pvFold([path.join(' '), n.reference, n.serial, n.fn && (GARAGE_FN.find(f => f[0] === n.fn) || [])[1]].join(' ')).includes(w)));
  if (!rows.length) return `<p class="na">${esc(tx(pv.q ? 'Aucune pièce ne correspond à la recherche.' : 'Aucune pièce : appliquez un modèle d’architecture dans la fiche de la voiture (Garage).'))}</p>`;
  const body = rows.map(({n, path}) => {
    const fn = (GARAGE_FN.find(f => f[0] === n.fn) || [])[1];
    const meters = (n.meters || []).map(m => `<span class="rd-chip ${m.state === 'over' ? 'neg' : m.state === 'warn' ? 'warn' : ''}" title="${esc(tx(m.label))}">${esc(tx(m.label))}${m.ratio != null ? ' · ' + Math.round(m.ratio * 100) + ' %' : m.note ? ' · ' + esc(m.note) : ''}</span>`).join(' ');
    return `<tr class="${n.removed_at ? 'gone' : ''}"><td class="prod">${esc(path.slice(0, -1).join(' › '))}${path.length > 1 ? ' › ' : ''}<b>${esc(n.name)}</b>${n.removed_at ? ` <small class="na">${esc(tx('démontée le'))} ${fmtDate(n.removed_at)}</small>` : ''}</td>
      <td>${fn ? esc(tx(fn)) : '<small class="na">—</small>'}</td><td>${esc([n.reference, n.serial].filter(Boolean).join(' · ')) || '<small class="na">—</small>'}</td>
      <td class="num">${rdKm(n.km)} km</td><td>${meters || '<small class="na">—</small>'}</td><td>${n.removed_at ? '' : rdChip(n.state === 'ok' ? 'ok' : n.state, 0)}</td></tr>`;
  });
  return `<p class="na">${rows.length} ${esc(tx('pièces'))}</p>${table(['Pièce', 'Fonction', 'Référence · n° de série', 'Kilomètres', 'Maintenances', 'État'], body)}`;
}
document.addEventListener('change', async e => {
  if (!document.getElementById('pv-view')) return;
  if (e.target.id === 'pv-car') { pv.key = e.target.value; pv.car = null; try { localStorage.setItem(PV_KEY, pv.key); } catch {} return pv.key ? pvLoad() : pvDraw(); }
  if (e.target.id === 'pv-rm') { pv.removed = e.target.checked; const b = document.getElementById('pv-list'); if (b) b.innerHTML = pvTable(); }
});
document.addEventListener('input', e => { if (e.target.id === 'pv-q') { pv.q = e.target.value; const b = document.getElementById('pv-list'); if (b) b.innerHTML = pvTable(); } });
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-pv]'); if (!b || !document.getElementById('pv-view')) return;
  if (b.dataset.pv === 'garage' && typeof tfGoGarage === 'function') tfGoGarage(pv.key);
});
