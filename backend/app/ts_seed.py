"""Modèle de départ des listes de contrôle (extrait de la feuille « Joblist » de JOB-CIRCUIT-2RM-ATMO-EVENT) : créé une seule fois, ensuite géré par le chef d'atelier."""

SEED_TEMPLATES = [
 {
  "name": "Révision Circuit",
  "bu": "CARS",
  "natures": [
   "pre_event",
   "post_event"
  ],
  "sections": [
   {
    "title": "Moteur",
    "lines": [
     {
      "text": "Vidange moteur",
      "note": ""
     },
     {
      "text": "Contrôle de l'étanchéité boite à air",
      "note": ""
     },
     {
      "text": "Nettoyage du filtre à air",
      "note": ""
     },
     {
      "text": "Niveau du circuit de refroidissement",
      "note": ""
     },
     {
      "text": "Contrôle du circuit de refroidissement (visuel + étanchéité)",
      "note": ""
     },
     {
      "text": "Nettoyage radiateur + check visuel",
      "note": ""
     },
     {
      "text": "Contrôle du collecteur (décoiffe + inspection : traces de suie?)",
      "note": ""
     },
     {
      "text": "Vérifier le support moteur : état, serrage, crack",
      "note": ""
     },
     {
      "text": "Vérifier le support de boite : état, serrage, crack",
      "note": ""
     },
     {
      "text": "Vérifier l'anti-couple : état, serrage, crack",
      "note": ""
     },
     {
      "text": "Contrôle de la courroie d'accessoire",
      "note": "Changement si besoin"
     },
     {
      "text": "Contrôle de l'alternateur : fixation, état, faisceau",
      "note": ""
     },
     {
      "text": "Contrôle du démarreur : fixation, état, faisceau",
      "note": ""
     },
     {
      "text": "Contrôle de la pompe à eau : fixation, état",
      "note": ""
     }
    ]
   },
   {
    "title": "Transmission",
    "lines": [
     {
      "text": "Contrôle des précharges:",
      "note": ""
     },
     {
      "text": "Vidange BV, nettoyage des filtre et des aimants + contrôle des butées d'embrayage, vider le pot de dégazage",
      "note": ""
     },
     {
      "text": "Vidange du pont, nettoyage des filtre et des aimants, vider le pot de dégazage",
      "note": ""
     },
     {
      "text": "Embrayage : mesurer l'embrayage => OK pour prochain event?",
      "note": ""
     },
     {
      "text": "Purge de l'embrayage",
      "note": ""
     },
     {
      "text": "Contrôle de l'arbre longi + pallier central",
      "note": ""
     },
     {
      "text": "Contrôle des trans latérales : Jeu, soufflet, point dur, serrage des clames, état ressort",
      "note": ""
     },
     {
      "text": "Contrôler le contact bol de trans sur moyeu et contrôler le serrage des vis de trans",
      "note": ""
     }
    ]
   },
   {
    "title": "Suspension / Direction / Freins",
    "lines": [
     {
      "text": "Faire un setdown : compléter les valeurs HdC HsC Pince Carro clics",
      "note": ""
     },
     {
      "text": "Contrôler le jeu aux roues",
      "note": ""
     },
     {
      "text": "Contrôle des serrages",
      "note": ""
     },
     {
      "text": "Contrôle des trains roulants (état, crack)",
      "note": ""
     },
     {
      "text": "Contrôle de la colonne de direction : état, jeu",
      "note": ""
     },
     {
      "text": "Contrôler le système de direction (étanchéité, fixation, état visuel) + vidange du circuit",
      "note": ""
     },
     {
      "text": "Placer des nouveaux thermax sur les étriers",
      "note": ""
     },
     {
      "text": "Sabler les disques pour inspection + appairage disques plaquettes",
      "note": ""
     },
     {
      "text": "Purger les freins",
      "note": ""
     },
     {
      "text": "Géométrie + contrôle de tous les points du setup + Poids par roue",
      "note": ""
     },
     {
      "text": "Compléter la feuille de setup avec les valeurs finales, les cales, les valeurs de ref",
      "note": ""
     }
    ]
   },
   {
    "title": "Habitacle",
    "lines": [
     {
      "text": "Nettoyage complet intérieur",
      "note": ""
     },
     {
      "text": "Contrôle du pédalier (serrages, fuites, crack)",
      "note": ""
     },
     {
      "text": "Contrôle du levier de vitesse (serrages, crack) + capteur de coupure",
      "note": ""
     }
    ]
   },
   {
    "title": "Châssis / Carrosserie",
    "lines": [
     {
      "text": "Nettoyage complet exterieur",
      "note": ""
     }
    ]
   },
   {
    "title": "Électricité / Accessoires",
    "lines": [
     {
      "text": "Vidange essence, mesure de la quantité retirée + conso à 0",
      "note": ""
     }
    ]
   },
   {
    "title": "Divers",
    "lines": [
     {
      "text": "Faire un démarrage sur chandelle (chauffe jusqu'au déclenchement des ventilos), passer toutes les vitesses",
      "note": ""
     }
    ]
   },
   {
    "title": "Camion",
    "lines": [
     {
      "text": "Vérifier le chargement du camion avant départ",
      "note": ""
     },
     {
      "text": "Vérifier les jantes",
      "note": ""
     },
     {
      "text": "Vérifier l'état des pneus",
      "note": ""
     }
    ]
   }
  ]
 }
]
