// Picto « Suggérer / signaler » (en-tête, tous les utilisateurs) : un message est envoyé par e-mail au Super User, avec la page d'origine jointe.
const fbState = {open: false, kind: 'idea', msg: '', sending: false, err: '', done: false, page: '', title: '', files: []};
const FB_MAX = 3, FB_BYTES = 4 * 1024 * 1024;
const fbSize = n => n > 1048576 ? (n / 1048576).toFixed(1).replace('.', LANG === 'en' ? '.' : ',') + ' Mo' : Math.max(1, Math.round(n / 1024)) + ' ko';
const fbDraw = () => {
  let el = document.getElementById('fb-modal');
  if (!fbState.open) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'fb-modal'; document.body.appendChild(el); }
  const s = fbState;
  el.innerHTML = `<div class="fb-back" data-fb="close"></div><div class="fb-box" role="dialog" aria-modal="true" aria-labelledby="fb-h">
    <h3 id="fb-h">Suggérer une amélioration ou signaler un bug</h3>
    ${s.done ? `<p>Merci, votre message est parti. Il sera lu par l’équipe de développement de l’App Lifelive Motorsport Logbook.</p><div class="sdbar"><button type="button" class="primary" data-fb="close">Fermer</button></div>` : `
    <div class="bu-filter" role="group"><button type="button" class="rs-pill" data-fb="kind" data-k="idea" aria-pressed="${s.kind === 'idea'}">💡 Suggestion</button><button type="button" class="rs-pill" data-fb="kind" data-k="bug" aria-pressed="${s.kind === 'bug'}">🐞 Bug</button></div>
    <p class="na" style="margin:8px 0">Page concernée : <b>${esc(s.title || s.page || 'Accueil')}</b> (jointe automatiquement)</p>
    <textarea id="fb-msg" rows="6" maxlength="4000" placeholder="${s.kind === 'bug' ? 'Que s’est-il passé ? Que faisiez-vous ? Qu’attendiez-vous ?' : 'Quelle amélioration proposez-vous ?'}">${esc(s.msg)}</textarea>
    <div class="fb-files">${s.files.map((f, i) => `<span class="tagchip">📎 ${esc(f.name)} <small class="na">${esc(fbSize(f.size))}</small> <button type="button" class="mini" data-fb="rmfile" data-i="${i}" aria-label="Retirer">✕</button></span>`).join(' ')}${s.files.length < FB_MAX ? `<label class="fb-add">📎 Joindre une image ou un PDF<input type="file" id="fb-file" accept="image/*,application/pdf" multiple hidden></label>` : ''}</div>
    ${s.err ? `<p class="neg">${esc(s.err)}</p>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-fb="send" ${s.sending || s.msg.trim().length < 3 ? 'disabled' : ''}>${s.sending ? 'Envoi…' : 'Envoyer'}</button><button type="button" data-fb="close">Annuler</button></div>`}</div>`;
  const ta = el.querySelector('#fb-msg'); if (ta && !s.sending) ta.focus();
};
function fbOpen() {
  const h = $('page-title');
  if (fbState.done) fbState.files = [];
  Object.assign(fbState, {open: true, done: false, err: '', sending: false, msg: fbState.done ? '' : fbState.msg, page: route(), title: (h ? h.textContent : '').replace(/\s+/g, ' ').trim()});
  fbDraw();
}
// Ajout d'une pièce jointe : les images sont réduites (1 600 px, JPEG) avant l'envoi ; les PDF sont envoyés tels quels (4 Mo au maximum).
async function fbAdd(file) {
  if (fbState.files.length >= FB_MAX) return;
  const toB64 = blob => new Promise((ok, ko) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(',')[1]); r.onerror = ko; r.readAsDataURL(blob); });
  try {
    let blob = file, type = file.type, name = file.name || 'capture';
    if (type === 'application/pdf') { if (file.size > FB_BYTES) throw new Error('PDF trop volumineux (4 Mo maximum).'); }
    else if (/^image\/(jpeg|png|webp|gif)$/.test(type)) {
      if (type !== 'gif') {
        const img = await createImageBitmap(file), k = Math.min(1, 1600 / Math.max(img.width, img.height)), c = document.createElement('canvas');
        c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        blob = await new Promise(ok => c.toBlob(ok, 'image/jpeg', .85)); type = 'image/jpeg'; name = name.replace(/\.\w+$/, '') + '.jpg';
      }
      if (blob.size > FB_BYTES) throw new Error('Image trop volumineuse (4 Mo maximum).');
    } else throw new Error('Pièce jointe : image ou PDF seulement.');
    fbState.files.push({name, type, size: blob.size, data: await toB64(blob)}); fbState.err = '';
  } catch (e) { fbState.err = e.message || 'Pièce jointe illisible.'; }
  fbDraw();
}
document.addEventListener('change', async e => { if (e.target.id === 'fb-file') { const fs = [...e.target.files]; e.target.value = ''; for (const f of fs) await fbAdd(f); } });
document.addEventListener('paste', async e => { if (!fbState.open || fbState.done) return; const fs = [...(e.clipboardData ? e.clipboardData.files : [])].filter(f => f.type.startsWith('image/')); if (fs.length) { e.preventDefault(); for (const f of fs) await fbAdd(f); } });
document.addEventListener('input', e => { if (e.target.id === 'fb-msg') { fbState.msg = e.target.value; const b = document.querySelector('#fb-modal [data-fb=send]'); if (b) b.disabled = fbState.sending || fbState.msg.trim().length < 3; } });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && fbState.open) { fbState.open = false; fbDraw(); } });
document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('#fb-open, [data-fb]'); if (!t) return;
  if (t.id === 'fb-open') return fbOpen();
  const a = t.dataset.fb;
  if (a === 'close') { fbState.open = false; fbDraw(); }
  else if (a === 'rmfile') { fbState.files.splice(+t.dataset.i, 1); fbDraw(); }
  else if (a === 'kind') { fbState.kind = t.dataset.k; fbDraw(); }
  else if (a === 'send' && !fbState.sending) {
    fbState.sending = true; fbState.err = ''; fbDraw();
    try {
      await rsCall('/api/feedback', {method: 'POST', body: JSON.stringify({kind: fbState.kind, message: fbState.msg.trim(), page: fbState.page, title: fbState.title, url: location.href.slice(0, 400), lang: LANG, agent: navigator.userAgent.slice(0, 300), screen: `${innerWidth}×${innerHeight}`, attachments: fbState.files.map(f => ({name: f.name, type: f.type, data: f.data}))})});
      fbState.done = true; fbState.msg = ''; fbState.files = [];
    } catch (err) { fbState.err = err.message; }
    fbState.sending = false; fbDraw();
  }
});
(() => { const app = $('app'), b = $('fb-open'); if (!app || !b) return; const sync = () => { b.hidden = app.hidden; }; sync(); new MutationObserver(sync).observe(app, {attributes: true, attributeFilter: ['hidden']}); })();
