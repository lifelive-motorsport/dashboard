// Référentiel des BU et symbole BU — port de docs/brand-kit/bu.ts (règles : docs/BRAND.md §3–5). Chargé avant app.js.
// Les couleurs de BU servent uniquement à distinguer les BU : jamais pour des boutons, liens, alertes ou états.
const BUS = {
  lifelive: {id: 'lifelive', label: 'Lifelive', shortLabel: 'Lifelive', color: '#2B2B2B', textOnColor: '#FFFFFF', googleCalendarColorId: '8',
    logo: {full: 'brand/LOGO_LIFELIVE_White.svg', onLight: 'brand/LOGO_LIFELIVE_Black.svg', onDark: 'brand/LOGO_LIFELIVE_White.svg'}},
  xc: {id: 'xc', label: 'XC Cross Car', shortLabel: 'XC', color: '#D8113E', textOnColor: '#FFFFFF', googleCalendarColorId: '11',
    logo: {full: 'brand/LOGO_CROSS-CAR_Red.svg', onLight: 'brand/LOGO_CROSS-CAR_Black_Red.svg', onDark: 'brand/LOGO_CROSS-CAR_White_Red.svg'}},
  cars: {id: 'cars', label: 'CARS', shortLabel: 'CARS', color: null, textOnColor: '#FFFFFF', googleCalendarColorId: '1'},           // ombrelle : pas de couleur propre, symbole tricolore
  mr: {id: 'mr', label: 'Modern Rally', shortLabel: 'Modern Rally', parent: 'cars', color: '#2C4F9C', textOnColor: '#FFFFFF', googleCalendarColorId: '9',
    logo: {full: 'brand/LOGO_MODERN-RALLY_Blue.svg', onLight: 'brand/LOGO_MODERN-RALLY_Black_Blue.svg', onDark: 'brand/LOGO_MODERN-RALLY_White_Blue.svg'}},
  hrc: {id: 'hrc', label: 'Historic Racing', shortLabel: 'Historic Racing', parent: 'cars', color: '#009540', textOnColor: '#FFFFFF', googleCalendarColorId: '10',
    logo: {full: 'brand/LOGO_HISTORIC-RACING_Green.svg', onLight: 'brand/LOGO_HISTORIC-RACING_Black_Green.svg', onDark: 'brand/LOGO_HISTORIC-RACING_White_Green.svg'}},
  hrl: {id: 'hrl', label: 'Historic Rally', shortLabel: 'Historic Rally', parent: 'cars', color: '#F4BE00', textOnColor: '#2B2B2B', googleCalendarColorId: '5',
    logo: {full: 'brand/LOGO_HISTORIC-RALLY_Yellow.svg', onLight: 'brand/LOGO_HISTORIC-RALLY_Black_Yellow.svg', onDark: 'brand/LOGO_HISTORIC-RALLY_White_Yellow.svg'}},
};
// Clés du P&L de l'application (backend/app/bu.py) -> identifiant de BU du référentiel
const BU_OF_KEY = {XC: 'xc', MODERN_RALLY: 'mr', HISTORIC_RACING: 'hrc', HISTORIC_RALLY: 'hrl', CARS: 'cars', CARS_OTHERS: 'cars'};
const buOfKey = key => BU_OF_KEY[key] || 'lifelive';

/** Couleurs des trois pièces du symbole (haut, centre, bas). `ink` = couleur du texte courant. */
function buSymbolColors(id, ink, dark = false) {
  const mr = dark ? '#6F8FD6' : BUS.mr.color;
  if (id === 'cars') return [mr, BUS.hrc.color, BUS.hrl.color];
  if (id === 'lifelive') return [ink, '#8A8F95', ink];
  if (id === 'mr') return [ink, mr, ink];
  return [ink, BUS[id].color, ink];
}
/** Filtre à deux niveaux : un élément est-il visible pour la sélection donnée ? (id d'élément, sélection : 'all' ou id de BU) */
function buMatchesFilter(itemBu, selected) {
  if (selected === 'all' || itemBu === selected) return true;
  if (selected === 'cars') return BUS[itemBu].parent === 'cars';
  if (BUS[selected].parent === 'cars') return itemBu === 'cars';          // éléments communs à CARS
  return false;
}
const buDark = () => document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : !(window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches);
/** Symbole BU : trois parallélogrammes (géométrie des logos officiels). Taille en px ; la couleur du texte courant vient de `currentColor` (ou `ink`). */
function BuSymbol(id, {size = 16, ink = 'currentColor', dark = buDark(), label = ''} = {}) {
  const [top, mid, bot] = buSymbolColors(id, ink, dark);
  return `<svg class="bu-symbol" width="${size}" height="${Math.round(size * 85 / 93)}" viewBox="34 38 93 85" ${label ? `role="img" aria-label="${label}"` : 'aria-hidden="true"'}>`
    + `<polygon points="96.4,39.61 125.02,39.61 111.82,68.22 83.09,68.22" fill="${top}"/><polygon points="50.61,68.22 83.09,68.22 68.34,99.95 35.98,99.95" fill="${mid}"/><polygon points="68.34,99.95 90.28,99.95 80.31,121.39 58.45,121.39" fill="${bot}"/></svg>`;
}
