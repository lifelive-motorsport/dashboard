// Logbook — référentiel des BU (voir BRAND.md §3–5)

export type BuId = 'groupe' | 'xc' | 'cars' | 'mr' | 'hrc' | 'hrl';

export interface Bu {
  id: BuId;
  label: string;
  parent?: 'cars';
  color: string | null;           // null = pas de couleur propre (CARS)
  textOnColor: string;            // couleur de texte lisible sur `color`
  googleCalendarColorId: string;  // Google Calendar event colorId
  logo?: { full: string; onLight: string; onDark: string };
}

export const BUS: Record<BuId, Bu> = {
  groupe: { id: 'groupe', label: 'Groupe', color: '#2B2B2B', textOnColor: '#FFFFFF', googleCalendarColorId: '8',
    logo: { full: '/brand/LOGO_LIFELIVE_White.svg', onLight: '/brand/LOGO_LIFELIVE_Black.svg', onDark: '/brand/LOGO_LIFELIVE_White.svg' } },
  xc: { id: 'xc', label: 'XC Cross', color: '#D8113E', textOnColor: '#FFFFFF', googleCalendarColorId: '11',
    logo: { full: '/brand/LOGO_CROSS-CAR_Red.svg', onLight: '/brand/LOGO_CROSS-CAR_Black_Red.svg', onDark: '/brand/LOGO_CROSS-CAR_White_Red.svg' } },
  cars: { id: 'cars', label: 'CARS', color: null, textOnColor: '#FFFFFF', googleCalendarColorId: '1' },
  mr: { id: 'mr', label: 'Modern Rally', parent: 'cars', color: '#2C4F9C', textOnColor: '#FFFFFF', googleCalendarColorId: '9',
    logo: { full: '/brand/LOGO_MODERN-RALLY_Blue.svg', onLight: '/brand/LOGO_MODERN-RALLY_Black_Blue.svg', onDark: '/brand/LOGO_MODERN-RALLY_White_Blue.svg' } },
  hrc: { id: 'hrc', label: 'Historic Racing', parent: 'cars', color: '#009540', textOnColor: '#FFFFFF', googleCalendarColorId: '10',
    logo: { full: '/brand/LOGO_HISTORIC-RACING_Green.svg', onLight: '/brand/LOGO_HISTORIC-RACING_Black_Green.svg', onDark: '/brand/LOGO_HISTORIC-RACING_White_Green.svg' } },
  hrl: { id: 'hrl', label: 'Historic Rally', parent: 'cars', color: '#F4BE00', textOnColor: '#2B2B2B', googleCalendarColorId: '5',
    logo: { full: '/brand/LOGO_HISTORIC-RALLY_Yellow.svg', onLight: '/brand/LOGO_HISTORIC-RALLY_Black_Yellow.svg', onDark: '/brand/LOGO_HISTORIC-RALLY_White_Yellow.svg' } },
};

/** Couleurs des trois pièces du symbole (haut, centre, bas). `ink` = couleur du texte courant. */
export function symbolColors(id: BuId, ink: string, dark = false): [string, string, string] {
  const mr = dark ? '#6F8FD6' : BUS.mr.color!;
  if (id === 'cars') return [mr, BUS.hrc.color!, BUS.hrl.color!];
  if (id === 'groupe') return [ink, '#8A8F95', ink];
  if (id === 'mr') return [ink, mr, ink];
  return [ink, BUS[id].color!, ink];
}

/** Filtre à deux niveaux : un élément est-il visible pour la sélection donnée ? */
export function matchesFilter(itemBu: BuId, selected: BuId | 'all'): boolean {
  if (selected === 'all' || itemBu === selected) return true;
  if (selected === 'cars') return BUS[itemBu].parent === 'cars';
  if (BUS[selected].parent === 'cars') return itemBu === 'cars'; // éléments communs CARS
  return false;
}
