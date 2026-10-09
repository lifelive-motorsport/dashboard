# Logbook — identité et conventions visuelles

Référence pour tout ce qui touche au nom, à l'apparence et au code couleur des BU de l'application.
Les valeurs exactes sont dans `tokens.css` et `bu.ts` ; les logos officiels dans `brand/`.

## 1. Nom et orthographe

- L'application s'appelle **Logbook** (anciennement « Dashboard »).
- L'entreprise s'écrit **toujours** « Lifelive » ou, de préférence, « Lifelive Motorsport ».
  Jamais « LifeLive », « LIFELIVE » en texte courant, ni « Live Life ».
- « Tableaux de bord » reste le nom du module d'indicateurs à l'intérieur de Logbook.

## 2. Renommage Dashboard → Logbook (à faire)

1. Nouveau sous-domaine `logbook.lifelive-motorsport.com`.
2. Redirection **301** permanente de `dashboard-app.lifelive-motorsport.com` (chemins et paramètres conservés).
3. Mettre à jour : `<title>`, manifest / PWA (`name`, `short_name`, icônes), favicon, expéditeur et objets des e-mails/notifications.
4. Mettre à jour le nom de l'app OAuth dans Google Cloud Console (écran de consentement) et les URI de redirection autorisées pour le nouveau domaine.
5. Rechercher toutes les occurrences de « Dashboard » dans le code et l'UI ; ne garder que le libellé du module « Tableaux de bord ».

## 3. Couleurs

Structure (écran) :

| Token | Valeur | Usage |
|---|---|---|
| `--graphite` | #2B2B2B | surfaces sombres, barre latérale, texte principal sur fond clair |
| `--fond-sombre` | #1F1F1F | fond de page en mode sombre |
| `--papier` | #F4F4F2 | fond de page en mode clair |
| `--blanc-casse` | #EDEDEB | texte principal en mode sombre |
| `--noir-base` | #000000 | **logo et print uniquement**, jamais en grande surface à l'écran |

BU (valeurs issues des SVG officiels — elles font foi) :

| BU | Pôle | Couleur | Texte sur fond | Google Agenda (colorId) |
|---|---|---|---|---|
| Groupe (transverse) | — | #2B2B2B | blanc | Graphite (8) |
| XC Cross | XC | #D8113E | blanc | Tomato (11) |
| Modern Rally | CARS | #2C4F9C (mode sombre, petits éléments : #6F8FD6) | blanc | Blueberry (9) |
| Historic Racing | CARS | #009540 | blanc, gras ≥ 18 px seulement | Basil (10) |
| Historic Rally | CARS | #F4BE00 | **noir/graphite uniquement** | Banana (5) |
| CARS (ombrelle) | CARS | pas de couleur propre — symbole tricolore | blanc sur Graphite | Lavender (1), seulement si aucune BU précise |

Règles :
- Les couleurs BU servent **uniquement** à distinguer les BU. Jamais pour les boutons, liens, alertes ou états.
- Boutons d'action : Graphite en mode clair, blanc cassé en mode sombre.
- Un événement rattaché à une BU précise prend toujours la couleur de cette BU, même s'il concerne aussi CARS.

## 4. Hiérarchie des BU et filtre

```
Toutes
├── XC Cross
└── CARS
    ├── Modern Rally
    ├── Historic Racing
    └── Historic Rally
```

Filtre à deux niveaux : niveau 1 = Toutes / XC Cross / CARS. Quand CARS ou une de ses BU est sélectionnée, afficher le niveau 2 = Toutes CARS / Modern Rally / Historic Racing / Historic Rally.
Filtrer sur une BU CARS précise affiche aussi les éléments rattachés à CARS (communs à l'équipe).

## 5. Symbole BU

Le symbole est composé de trois parallélogrammes (géométrie extraite des logos officiels, viewBox `34 38 93 85`) :

```svg
<svg viewBox="34 38 93 85" aria-hidden="true">
  <polygon points="96.4,39.61 125.02,39.61 111.82,68.22 83.09,68.22" />   <!-- haut -->
  <polygon points="50.61,68.22 83.09,68.22 68.34,99.95 35.98,99.95" />    <!-- centre (grande pièce) -->
  <polygon points="68.34,99.95 90.28,99.95 80.31,121.39 58.45,121.39" />  <!-- bas -->
</svg>
```

- BU simple : haut et bas en couleur de texte (graphite en clair, blanc cassé en sombre), centre en couleur BU.
- CARS : haut = Modern Rally, centre = Historic Racing, bas = Historic Rally.
- Groupe : centre en gris #8A8F95.
- En faire un composant réutilisable `<BuSymbol bu="…" size="…" />` ; l'utiliser dans les pastilles, filtres, listes et agendas.

## 6. Logo Logbook

Carré arrondi (rayon ≈ 16 % du côté) Graphite, deux perforations de reliure à gauche et trois lignes d'écriture :

```svg
<svg viewBox="0 0 64 64">
  <rect width="64" height="64" rx="10" fill="#2B2B2B"/>
  <circle cx="13" cy="20" r="2.5" fill="#fff"/>
  <circle cx="13" cy="44" r="2.5" fill="#fff"/>
  <line x1="22" y1="20" x2="50" y2="20" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
  <line x1="22" y1="32" x2="46" y2="32" stroke="#fff" stroke-width="4" stroke-linecap="round"/>
  <line x1="22" y1="44" x2="36" y2="44" stroke="#fff" stroke-width="4" stroke-linecap="round"/> <!-- entrée en cours -->
</svg>
```

- Version neutre : tout en blanc (icône d'app, favicon, écran de connexion).
- Dans l'app, la dernière ligne prend la couleur de la BU filtrée ; pour CARS, trois tirets bleu / vert / jaune.
- Favicon 16–24 px : retirer les perforations, ne garder que deux lignes.
- Wordmark : « LOGBOOK » en Barlow Condensed 700 italique, majuscules ; sous-titre = logo Lifelive Motorsport (`brand/LOGO_LIFELIVE_*.svg`).

## 7. Typographie

Google Fonts. **Ne pas utiliser Ethnocentric** (police de la charte, écartée).

- Titres, noms de BU, chiffres clés : **Barlow Condensed** 600/700, italique pour les titres.
- Interface et textes : **IBM Plex Sans** 400/500/600.
- Relevés, heures, quantités, références : **IBM Plex Mono** 400/500.

## 8. Modes clair et sombre

- Clair : fond `--papier`, cartes blanches bordure #DCDCD8, texte Graphite.
- Sombre : fond `--fond-sombre`, cartes/barre latérale `--graphite` bordure #3A3A3A, texte `--blanc-casse`, texte secondaire #A3A6AA.
- Contraste minimum 4,5:1 pour le texte courant.

## 9. Modules (navigation)

| Chapitre | Modules |
|---|---|
| Piloter | Tableaux de bord (Odoo) |
| Planifier | Événements (Google Agenda), Ressources |
| Consigner | Pointages (Odoo), Roulages, Consommables — pneus & carburant (Odoo stock) |
| Administrer | Équipage (utilisateurs, rôles, accès — Google Workspace), Connexions (sync Odoo/Google) |

## 10. Fichiers logos (`brand/`)

- `LOGO_LIFELIVE_Black.svg` / `_White.svg` — logo groupe.
- `LOGO_<BU>_<Couleur>.svg` — version pleine couleur (fond inclus).
- `LOGO_<BU>_Black_<Couleur>.svg` — pour fond clair.
- `LOGO_<BU>_White_<Couleur>.svg` — pour fond sombre.
- `LOGO_<BU>_White.svg` — monochrome blanc.
- `ICONE_RS_*` — icônes réseaux sociaux, pas utilisées dans l'app.

Pas de logo officiel CARS : utiliser le symbole tricolore (§5) avec le libellé « CARS ».
