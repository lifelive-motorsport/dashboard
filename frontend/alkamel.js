// Opérer › Roulages › « Roulage Al Kamel » : dépôt des PDF du chronométreur (classements, analyse des secteurs), création d'un roulage par session,
// rattachement de nos voitures par numéro de course, et sessions non chronométrées saisies à la main (essais de la veille, shakedown).
const ak = {open: false, parsing: false, saving: false, data: null, event: '', date: '', circuit: '', newCircuit: '', circuitKm: '', map: {}, pick: {}, manual: [], msg: null, ok: false};
const akDayBefore = iso => { if (!iso) return ''; const d = new Date(iso + 'T12:00:00'); d.setDate(d.getDate() - 1); return d.toISOString().slice(0, 10); };
const akBlankManual = () => ({date: akDayBefore(ak.date) || rdToday(), name: 'Essais non chronométrés', cars: [{key: '', laps: '', drivers: ''}]});
const akKinds = {race: 'Course', qualifying: 'Qualifications', practice: 'Essais'};

function akReset() { Object.assign(ak, {open: false, parsing: false, saving: false, data: null, event: '', date: '', circuit: '', newCircuit: '', circuitKm: '', map: {}, pick: {}, manual: [], msg: null, ok: false}); }

function akNumbers() {                                      // numéros de course rencontrés dans les sessions choisies, une seule fois chacun
  const seen = new Map();
  for (const s of ak.data ? ak.data.sessions : []) for (const c of s.classification) if (!seen.has(c.no)) seen.set(c.no, c);
  return [...seen.values()].sort((a, b) => a.no - b.no);
}

function akCarSelect(attr, cur) {
  return `<select class="sdin" ${attr}><option value="">—</option>${(rn.cars || []).map(c => `<option value="${esc(c.key)}" ${cur === c.key ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select>`;
}

function akHtml() {
  if (!ak.open) return '';
  const d = ak.data;
  const files = `<div class="sdbar"><label class="primary ak-file">${esc(tx(ak.parsing ? 'Lecture…' : 'Choisir les PDF Al Kamel'))}<input type="file" id="ak-files" accept="application/pdf,.pdf" multiple hidden></label><small class="na">${esc(tx('Classements et analyses des secteurs (Classification, Analysis) ; les autres PDF sont ignorés.'))}</small></div>`;
  let body = '';
  if (d) {
    const sess = d.sessions.map((s, i) => {
      const cond = s.conditions || {};
      const meta = [akKinds[s.kind] ? tx(akKinds[s.kind]) : '', `${s.classification.length} ${tx('voitures')}`, cond.track_c != null ? `${tx('piste')} ${cond.track_c}°C` : '', cond.air_c != null ? `${tx('air')} ${cond.air_c}°C` : '', cond.status || ''].filter(Boolean).join(' · ');
      return `<label class="chk"><input type="checkbox" data-ak-pick="${i}" ${ak.pick[i] ? 'checked' : ''}> <b>${esc(s.session)}</b> <small class="na">${esc(meta)}</small></label>`;
    }).join('');
    const nums = akNumbers();
    const cars = table(['N°', 'Pilote(s)', 'Voiture', 'Notre voiture'], nums.map(c => `<tr><td>${c.no}</td><td>${esc((c.drivers || []).join(' / '))}</td><td>${esc(c.car)}</td><td>${akCarSelect(`data-ak-car="${c.no}"`, ak.map[c.no] || '')}</td></tr>`));
    body = `<p class="na">${esc(d.series)}${d.ignored && d.ignored.length ? ` · ${d.ignored.length} ${esc(tx('PDF ignorés'))}` : ''}</p><div class="rn-card">${sess}</div>
      <p><b>${esc(tx('Nos voitures'))}</b> <small class="na">${esc(tx('associez chaque voiture du Garage à son numéro de course ; les autres numéros ne sont pas importés.'))}</small></p>${cars}`;
  }
  const circs = `<label class="sdfield"><span>Circuit</span><select class="sdin" data-ak-f="circuit"><option value="">—</option>${(rn.circuits || []).map(c => `<option value="${esc(c.name)}" ${ak.circuit === c.name ? 'selected' : ''}>${esc(c.name)} · ${rdKm(c.length_km)} km</option>`).join('')}<option value="__new" ${ak.circuit === '__new' ? 'selected' : ''}>＋ ${esc(tx('Nouveau circuit'))}</option></select></label>`;
  const newc = ak.circuit === '__new' ? `<label class="sdfield"><span>${esc(tx('Nom du circuit'))}</span><input class="sdin" data-ak-f="newCircuit" value="${esc(ak.newCircuit)}"></label><label class="sdfield"><span>${esc(tx('Longueur du tour (km)'))}</span><input class="sdin" data-ak-f="circuitKm" value="${esc(ak.circuitKm)}" inputmode="decimal"></label>${d && d.circuit_km ? `<small class="na">${esc(tx('Longueur estimée d’après le classement de course (vitesse moyenne × durée ÷ tours) :'))} ${rdKm(d.circuit_km)} km</small>` : ''}` : '';
  const head = `<div class="sdgrid"><label class="sdfield"><span>${esc(tx('Épreuve'))}</span><input class="sdin" data-ak-f="event" value="${esc(ak.event)}" placeholder="Imola Classic"></label><label class="sdfield"><span>Date</span>${dpField('data-ak-f="date"', ak.date)}</label>${circs}${newc}</div>`;
  const manual = ak.manual.map((m, i) => `<div class="rn-card"><div class="sdgrid"><label class="sdfield"><span>Date</span>${dpField(`data-ak-m="date" data-i="${i}"`, m.date)}</label><label class="sdfield"><span>${esc(tx('Nom'))}</span><input class="sdin" data-ak-m="name" data-i="${i}" value="${esc(m.name)}"></label><button type="button" class="mini danger" data-ak="delm" data-i="${i}" title="${esc(tx('Retirer cette session'))}">✕</button></div>
    ${m.cars.map((c, j) => `<div class="sdgrid">${akCarSelect(`data-ak-mc="key" data-i="${i}" data-j="${j}"`, c.key)}<input class="sdin" data-ak-mc="laps" data-i="${i}" data-j="${j}" value="${esc(c.laps)}" placeholder="${esc(tx('Tours'))}" inputmode="numeric" style="max-width:90px"><input class="sdin" data-ak-mc="drivers" data-i="${i}" data-j="${j}" value="${esc(c.drivers)}" placeholder="${esc(tx('Pilote(s)'))}"></div>`).join('')}
    <button type="button" class="mini" data-ak="addmc" data-i="${i}">＋ ${esc(tx('Autre voiture'))}</button></div>`).join('');
  const picked = d ? d.sessions.some((s, i) => ak.pick[i]) : false;
  const hasManual = ak.manual.some(m => m.cars.some(c => c.key));
  const ready = ak.event.trim() && ak.date && ak.circuit && (ak.circuit !== '__new' || (ak.newCircuit.trim() && rdNum(ak.circuitKm) > 0)) && (picked || hasManual) && !ak.saving;
  return `<div class="note rd-form"><b>${esc(tx('Roulage Al Kamel'))}</b>${files}${body}${head}
    <p><b>${esc(tx('Sessions non chronométrées'))}</b> <small class="na">${esc(tx('essais de la veille, shakedown… : sans temps officiels, avec les tours et les pilotes.'))}</small></p>${manual}
    <div class="sdbar"><button type="button" data-ak="addm">＋ ${esc(tx('Ajouter une session manuelle'))}</button></div>
    <div class="sdbar"><button type="button" class="primary" data-ak="import" ${ready ? '' : 'disabled'}>${esc(tx(ak.saving ? 'Enregistrement…' : 'Créer les roulages'))}</button><button type="button" data-ak="cancel">${esc(tx('Annuler'))}</button>${ak.msg ? `<span class="${ak.ok ? 'na' : 'neg'}">${esc(ak.msg)}</span>` : ''}</div></div>`;
}

function akDraw() {
  const el = document.getElementById('ak-view'); if (!el) return;
  const sav = [window.scrollX, window.scrollY];
  el.innerHTML = akHtml();
  window.scrollTo(...sav);
}
function akButtons() { const b = document.querySelector('[data-ak=import]'); if (b) b.disabled = true; akDraw(); }

const akB64 = f => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.onerror = () => rej(new Error('Lecture impossible')); r.readAsDataURL(f); });

async function akParse(list) {
  ak.parsing = true; ak.msg = null; akDraw();
  try {
    const files = [];
    for (const f of list) files.push({name: f.name, data: await akB64(f)});
    const d = await rsCall('/api/rides/alkamel/parse', {method: 'POST', body: JSON.stringify({files})});
    if (!d.sessions.length) throw new Error(tx('Aucune session reconnue dans ces fichiers.'));
    ak.data = d;
    if (!ak.event) ak.event = (d.event || '').replace(/\b\w/g, c => c).trim();
    if (!ak.date && d.date) ak.date = d.date;
    if (d.circuit_km && !ak.circuitKm) ak.circuitKm = String(d.circuit_km);
    d.sessions.forEach((s, i) => { ak.pick[i] = true; });
    for (const s of d.suggest || []) if (!ak.map[s.no]) ak.map[s.no] = s.key;
  } catch (e) { ak.msg = e.message; ak.ok = false; }
  ak.parsing = false; akDraw();
}

document.addEventListener('change', e => {
  const t = e.target;
  if (t.id === 'ak-files') { const list = [...t.files]; t.value = ''; if (list.length) akParse(list); return; }
  if (!ak.open) return;
  if (t.dataset.akPick !== undefined) { ak.pick[+t.dataset.akPick] = t.checked; return akDraw(); }
  if (t.dataset.akCar !== undefined) { ak.map[t.dataset.akCar] = t.value; return; }
  if (t.dataset.akF === 'circuit') { ak.circuit = t.value; return akDraw(); }
  if (t.dataset.akF === 'date' && t.classList.contains('dp-h')) { ak.date = t.value; return akDraw(); }
  if (t.dataset.akM === 'date' && t.classList.contains('dp-h')) { ak.manual[+t.dataset.i].date = t.value; return; }
  if (t.dataset.akMc === 'key') { ak.manual[+t.dataset.i].cars[+t.dataset.j].key = t.value; return akDraw(); }
});
document.addEventListener('input', e => {
  const t = e.target; if (!ak.open) return;
  if (t.dataset.akF && !t.classList.contains('dp-h') && t.dataset.akF !== 'circuit' && t.dataset.akF !== 'date') { ak[t.dataset.akF] = t.value; const b = document.querySelector('[data-ak=import]'); if (b) b.disabled = !(ak.event.trim() && ak.date && ak.circuit && (ak.circuit !== '__new' || (ak.newCircuit.trim() && rdNum(ak.circuitKm) > 0)) && ((ak.data && ak.data.sessions.some((s, i) => ak.pick[i])) || ak.manual.some(m => m.cars.some(c => c.key)))); }
  else if (t.dataset.akM === 'name') ak.manual[+t.dataset.i].name = t.value;
  else if (t.dataset.akMc && t.dataset.akMc !== 'key') ak.manual[+t.dataset.i].cars[+t.dataset.j][t.dataset.akMc] = t.value;
});
document.addEventListener('click', async e => {
  const b = e.target.closest && e.target.closest('[data-ak]'); if (!b) return;
  const a = b.dataset.ak;
  if (a === 'open') { akReset(); ak.open = true; return akDraw(); }
  if (a === 'cancel') { akReset(); return akDraw(); }
  if (a === 'addm') { ak.manual.push(akBlankManual()); return akDraw(); }
  if (a === 'delm') { ak.manual.splice(+b.dataset.i, 1); return akDraw(); }
  if (a === 'addmc') { ak.manual[+b.dataset.i].cars.push({key: '', laps: '', drivers: ''}); return akDraw(); }
  if (a === 'import') {
    ak.saving = true; ak.msg = null; akDraw();
    try {
      const d = ak.data, mapped = {};
      for (const [no, key] of Object.entries(ak.map)) if (key) mapped[no] = key;
      const body = {series: d ? d.series : '', event: ak.event.trim(), date: ak.date, circuit: ak.circuit === '__new' ? ak.newCircuit.trim() : ak.circuit, circuit_km: rdNum(ak.circuitKm) || 0,
        sessions: d ? d.sessions.filter((s, i) => ak.pick[i]).map(s => ({session: s.session, kind: s.kind, conditions: s.conditions, classification: s.classification, cars: mapped})) : [],
        manual: ak.manual.map(m => ({date: m.date, name: m.name, cars: m.cars.filter(c => c.key).map(c => ({key: c.key, laps: parseInt(c.laps) || 0, drivers: String(c.drivers).split(',').map(x => x.trim()).filter(Boolean)}))}))};
      const r = await rsCall('/api/rides/alkamel/import', {method: 'POST', body: JSON.stringify(body)});
      const n = r.sessions.length, m = r.runs;
      akReset(); rn.msg = `${n} ${tx('roulage(s) créé(s)')}, ${m} ${tx('participation(s) de voitures.')}`; rn.ok = true; rn.cars = null; akDraw(); return rnLoad();
    } catch (err) { ak.saving = false; ak.msg = err.message; ak.ok = false; akDraw(); }
  }
});
