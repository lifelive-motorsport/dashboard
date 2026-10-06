// Settings › Tags Odoo : aide-mémoire des étiquettes et conventions Odoo qui pilotent le dashboard (+ présence réelle des étiquettes).
// Chargé avant app.js ; utilise ses fonctions (esc, num, table) au moment de l'appel.
let tagsState = {data: null, error: null};

async function loadTags() {
  try {
    const r = await fetch('/api/tags', {headers: (typeof token !== 'undefined' && token) ? {Authorization: 'Bearer ' + token} : {}});
    if (!r.ok) throw new Error('Erreur ' + r.status);
    tagsState = {data: await r.json(), error: null};
  } catch (e) { tagsState = {data: null, error: e.message}; }
}

const TAGS_DOC = [
  {tag: 'regroup_client=Nom du groupe', where: 'Contacts › fiche du client (contact ou société) › Étiquettes', kind: 'client',
   use: 'Regroupe plusieurs clients sous un même nom dans tous les hit-parades clients : Overview › Clients, XC et CARS (général, par BU) et les meilleurs clients du webshop XC.',
   rules: ['Les contacts d’une même société sont déjà fusionnés automatiquement : l’étiquette sert à regrouper des sociétés différentes (ex. regroup_client=Koramic / C.Dumolin).',
           'Le texte après le « = » est le nom affiché. Un seul regroupement par contact : s’il y en a plusieurs, le premier par ordre alphabétique est retenu.',
           'Les majuscules du préfixe « regroup_client » sont sans importance ; pas d’espace avant le nom.']},
  {tag: 'regroup_fournisseur=Nom du groupe', where: 'Contacts › fiche du fournisseur (contact ou société) › Étiquettes', kind: 'fournisseur',
   use: 'Même principe pour les fournisseurs : hit-parades fournisseurs (Overview › Fournisseurs et pages de BU) et principaux fournisseurs de Marketing › Dépenses marketing.',
   rules: ['Les contacts d’une même société sont fusionnés automatiquement ; l’étiquette regroupe des sociétés différentes (ex. regroup_fournisseur=Pirelli).']},
  {tag: 'invest marketing', where: 'Contacts › fiche du fournisseur › Étiquettes', kind: 'invest',
   use: 'Désigne les fournisseurs dont les factures portées sur le compte INVEST (240050) sont des investissements marketing. Leurs lignes sont reprises dans la remarque de Marketing › Dépenses marketing (montant, imputations, durée d’amortissement).',
   rules: ['Sans cette étiquette, le dashboard retombe sur des mots-clés dans le libellé des lignes (graphique, social media, marketing, photo, vidéo…), moins fiable.',
           'Le matériel et les autres investissements du même compte INVEST ne sont pas repris tant que leur fournisseur n’a pas l’étiquette.']},
];

const TAGS_CONV = [
  ['Axe analytique « BU »', 'Obligatoire sur chaque ligne. Comptes reconnus : XC, Modern Rally, Historic Rally, Historic Racing, Others ; tout compte « OLD… » est ignoré. Il décide de la BU d’un événement ou d’un véhicule.'],
  ['Axe analytique « MEETING »', 'Un compte = un événement (pages Par événement, XC et CARS).'],
  ['Axe analytique « CARS »', 'Un compte = un véhicule (CARS › Par véhicule). Le client et la référence viennent de la fiche du compte analytique ; le libellé s’affiche sans « [référence] » ni nom du client.'],
  ['Comptes de ventes et d’achats', 'Ventes 700xxx ; coûts directs 602, 603, 604 ; la BU est donnée par les 3 derniers chiffres (010 à 019 = XC, 020 Modern Rally, 030 Historic Rally, 040 Historic Racing, 050/059 CARS Others). Un libellé qui commence par « old » est ignoré (sauf pour le CA de l’an dernier, où l’ancien plan comptable compte).'],
  ['Comptes marketing', '602019, 602059 et 612050 = dépenses marketing. Les investissements marketing sont sur le compte INVEST 240050 (amortis via les comptes 630xxx).'],
  ['Fiche produit › Site web', 'Rattache un produit à un webshop : pages vues et visites par webshop, top produits.'],
  ['Fiche produit › code PIF', 'Utilisé par la valorisation du stock XC (XC Detail › Inventory).'],
  ['Nom du site web Odoo', 'Un site dont le nom contient « Goldspeed » est traité comme le webshop Goldspeed : ses livraisons sont exclues des commandes préparées par le magasinier.'],
];

function tagsBlocks() {
  const card = d => `<div class="note"><b><code>${esc(d.tag)}</code></b><br><small class="na">Où : ${esc(d.where)}</small><br>${esc(d.use)}<ul>${d.rules.map(r => `<li>${esc(r)}</li>`).join('')}</ul><div class="tags-live" data-kind="${d.kind}"></div></div>`;
  return [
    {static: `<section class="block"><div class="block-head"><h3>Étiquettes de contact</h3></div><div class="block-body">${TAGS_DOC.map(card).join('')}</div></section>`},
    {static: `<section class="block"><div class="block-head"><h3>Autres conventions Odoo utilisées</h3></div><div class="block-body">${table(['Convention', 'Usage dans le dashboard'], TAGS_CONV.map(([a, b]) => `<tr><td class="prod">${esc(a)}</td><td class="prod">${esc(b)}</td></tr>`), 'prodtable convtable')}<small class="na">Aide-mémoire : si l’une de ces conventions change dans Odoo, le dashboard doit être adapté.</small></div></section>`},
  ];
}

function drawTags() {
  document.querySelectorAll('.tags-live').forEach(el => {
    const d = tagsState.data;
    if (!d) { el.innerHTML = tagsState.error ? `<small class="neg">Étiquettes en place : indisponible (${esc(tagsState.error)}).</small>` : ''; return; }
    if (d.unavailable) { el.innerHTML = `<small class="na">${esc(d.unavailable)}</small>`; return; }
    const mine = (d.tags || []).filter(t => t.kind === el.dataset.kind);
    el.innerHTML = mine.length
      ? `<small class="na">En place dans Odoo (${mine.length}) : </small>` + mine.map(t => `<span class="tagchip">${esc(t.name)} <small>${num(t.count)} contact${t.count > 1 ? 's' : ''}</small></span>`).join(' ')
      : '<small class="na">Aucune étiquette de ce type n’existe encore dans Odoo.</small>';
  });
}
