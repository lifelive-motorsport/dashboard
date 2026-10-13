// Picto « Suggérer / signaler » (en-tête, tous les utilisateurs) : un message est envoyé par e-mail au Super User, avec la page d'origine jointe.
const fbState = {open: false, kind: 'idea', msg: '', sending: false, err: '', done: false, page: '', title: ''};
const fbDraw = () => {
  let el = document.getElementById('fb-modal');
  if (!fbState.open) { if (el) el.remove(); return; }
  if (!el) { el = document.createElement('div'); el.id = 'fb-modal'; document.body.appendChild(el); }
  const s = fbState;
  el.innerHTML = `<div class="fb-back" data-fb="close"></div><div class="fb-box" role="dialog" aria-modal="true" aria-labelledby="fb-h">
    <h3 id="fb-h">Suggérer une amélioration ou signaler un bug</h3>
    ${s.done ? `<p>Merci, votre message est parti. Il sera lu par le Super User.</p><div class="sdbar"><button type="button" class="primary" data-fb="close">Fermer</button></div>` : `
    <div class="bu-filter" role="group"><button type="button" class="rs-pill" data-fb="kind" data-k="idea" aria-pressed="${s.kind === 'idea'}">💡 Suggestion</button><button type="button" class="rs-pill" data-fb="kind" data-k="bug" aria-pressed="${s.kind === 'bug'}">🐞 Bug</button></div>
    <p class="na" style="margin:8px 0">Page concernée : <b>${esc(s.title || s.page || 'Accueil')}</b> (jointe automatiquement)</p>
    <textarea id="fb-msg" rows="6" maxlength="4000" placeholder="${s.kind === 'bug' ? 'Que s’est-il passé ? Que faisiez-vous ? Qu’attendiez-vous ?' : 'Quelle amélioration proposez-vous ?'}">${esc(s.msg)}</textarea>
    ${s.err ? `<p class="neg">${esc(s.err)}</p>` : ''}
    <div class="sdbar"><button type="button" class="primary" data-fb="send" ${s.sending || s.msg.trim().length < 3 ? 'disabled' : ''}>${s.sending ? 'Envoi…' : 'Envoyer'}</button><button type="button" data-fb="close">Annuler</button></div>`}</div>`;
  const ta = el.querySelector('#fb-msg'); if (ta && !s.sending) ta.focus();
};
function fbOpen() {
  const h = $('page-title');
  Object.assign(fbState, {open: true, done: false, err: '', sending: false, msg: fbState.done ? '' : fbState.msg, page: route(), title: (h ? h.textContent : '').replace(/\s+/g, ' ').trim()});
  fbDraw();
}
document.addEventListener('input', e => { if (e.target.id === 'fb-msg') { fbState.msg = e.target.value; const b = document.querySelector('#fb-modal [data-fb=send]'); if (b) b.disabled = fbState.sending || fbState.msg.trim().length < 3; } });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && fbState.open) { fbState.open = false; fbDraw(); } });
document.addEventListener('click', async e => {
  const t = e.target.closest && e.target.closest('#fb-open, [data-fb]'); if (!t) return;
  if (t.id === 'fb-open') return fbOpen();
  const a = t.dataset.fb;
  if (a === 'close') { fbState.open = false; fbDraw(); }
  else if (a === 'kind') { fbState.kind = t.dataset.k; fbDraw(); }
  else if (a === 'send' && !fbState.sending) {
    fbState.sending = true; fbState.err = ''; fbDraw();
    try {
      await rsCall('/api/feedback', {method: 'POST', body: JSON.stringify({kind: fbState.kind, message: fbState.msg.trim(), page: fbState.page, title: fbState.title, url: location.href.slice(0, 400), lang: LANG, agent: navigator.userAgent.slice(0, 300), screen: `${innerWidth}×${innerHeight}`})});
      fbState.done = true; fbState.msg = '';
    } catch (err) { fbState.err = err.message; }
    fbState.sending = false; fbDraw();
  }
});
(() => { const app = $('app'), b = $('fb-open'); if (!app || !b) return; const sync = () => { b.hidden = app.hidden; }; sync(); new MutationObserver(sync).observe(app, {attributes: true, attributeFilter: ['hidden']}); })();
