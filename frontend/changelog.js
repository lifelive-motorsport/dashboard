// Journal des nouveautés affiché sur la page d'accueil (les plus récentes en premier). À compléter à chaque ajout important de section ou de fonctionnalité.
const CHANGELOG = [
  {date: 'Octobre 2026', title: 'Formulaires techniques : mesure d’embrayage, boîte et pont', tag: 'Consigner', items: [
    'Révisions de boîte de vitesses (M3, Z4 GT3, avec différentiel) et de pont arrière : chaque élément est OK ou NOK avec un commentaire, plus la demande de réglage ; validation par le chef d’atelier et feuille PDF.',
    'Dans un job d’atelier, bouton « Formulaires » : mesure d’embrayage 4 ou 6 patins (épaisseurs des disques, conicité des plateaux), saisie sur tablette ou téléphone.',
    'Calcul automatique de l’usure, de l’usure aux 1 000 km et du kilométrage restant estimé ; le chef d’atelier valide, puis le formulaire est verrouillé.',
    'Feuille imprimable aux couleurs de Lifelive, à enregistrer en PDF.',
    'Liée à l’embrayage du Garage : le contrôle s’y enregistre à la validation, avec une courbe d’usure (📉) ; « À remplacer » reste une proposition.',
  ]},
  {date: 'Octobre 2026', title: 'Accès clients', tag: 'Administrer', items: [
    'Administrer › Accès clients : on crée un client avec ses adresses e-mail et ses voitures du Garage ; il se connecte par un lien reçu par e-mail (valable 15 minutes, à usage unique).',
    'Accès clients : « 👁 Voir comme ce client » ouvre son espace en aperçu (2 h, lecture seule) ; dans Pointages, le chef d’atelier peut « Masquer pour le client » le texte d’une intervention.',
    'Le client consulte, en lecture seule, ses voitures, leurs documents et roulages, et les jobs avec leurs pointages validés (sans nom de mécanicien ni coût) ; journal des connexions pour le Super User.']},
  {date: 'Octobre 2026', title: 'Opérer : Garage, Magasin de pièces et Roulages', tag: 'Opérer', items: [
    'Garage : fiche de chaque voiture (photo, BU, compte Odoo, identité : châssis, moteur, boîte, livrée, n° de course), pièces avec compteurs calculés depuis les roulages et alertes aux seuils.',
    'Magasin de pièces : modèles d’architecture (11 ensembles fixes, sous-ensembles, composants) avec, pour chacun, contrôle, vidange, révisions 1 et 2 et remplacement ; modèle de départ Toyota GR Yaris Rally2 ; un modèle s’assigne à une voiture depuis sa fiche.',
    'Roulages : une sortie se crée une fois, puis on y associe les voitures avec leurs tours, spéciales ou kilomètres ; circuits enregistrés avec la longueur du tour.']},
  {date: 'Octobre 2026', title: 'Documents et validités des voitures', tag: 'Opérer', items: [
    'Certificat de conformité, assurance, contrôle technique, passeports FIA et ASN, réservoir, extincteur, harnais, siège, arceau, transpondeur : date limite, note et fichiers (PDF, photos) avec aperçu.',
    'Alerte sur la fiche et sur l’accueil (Super User et chef d’atelier de la BU) à quelques semaines de l’échéance, et e-mail la veille de l’expiration.']},
  {date: 'Octobre 2026', title: 'Cockpit : écran mural', tag: 'Piloter', items: [
    'Calendrier de 5 semaines des événements (couleur de la BU, jours fériés, absents du jour, immobilisation des véhicules) et vue Atelier (jobs ouverts, présence, indicateurs de la semaine), filtrable par BU, en plein écran.',
    'Un compte « Kiosque » ouvre directement cet écran.']},
  {date: 'Octobre 2026', title: 'Pointages, listes de contrôle et congés', tag: 'Consigner', items: [
    'Pointages par job (atelier, événement, tâche de fond) avec photos et mémos vocaux transcrits, listes de contrôle par modèle, validation par le chef d’atelier, rappels par e-mail ; sous-menu Jobs (jobs et modèles de jobs) à côté de Ma semaine et Équipe.',
    'Congés : demandes, justificatifs, validation par le chef d’atelier ou le Managing Director, création dans l’agenda Google et prise en compte dans les alertes de pointage.']},
  {date: 'Octobre 2026', title: 'Planning, événements et ressources', tag: 'Planifier', items: [
    'Planning par ressource ou en calendrier, semaine ou mois ; événements créés dans les agendas Google des BU (transport avec plage horaire, lieu et kilomètres) ; calendrier maison à semaine du lundi.',
    'Ressources : staff interne (BU de ressource indépendante de l’imputation des coûts), staff externe et véhicules.']},
  {date: 'Octobre 2026', title: 'Menu en 5 chapitres', tag: 'Application', items: [
    'Piloter (Tableaux de bord, Cockpit), Planifier (Planning, Événements, Ressources), Consigner (Pointages, Congés), Opérer (Garage, Magasin de pièces, Roulages, Consommables), Administrer (Équipage, Connexions).',
    'Bouton clair / sombre et indicateurs de chargement partout ; picto de l’en-tête pour suggérer une amélioration ou signaler un bug.']},
  {date: 'Octobre 2026', title: 'Filtre BU sur Vue d’ensemble et l’accueil', tag: 'Vue d’ensemble', items: [
    'Filtre à deux niveaux (ALL / XC / CARS, puis Modern Rally, Historic Racing, Historic Rally) sur l’accueil et sur les pages Vue d’ensemble ; le logo prend la couleur de la BU choisie.',
    'Créances et dettes par BU, avec rapprochement exact du total de la société ; jauges qui montrent aussi les marges négatives ; effectifs (ETP) par BU sur l’accueil.']},
  {date: 'Octobre 2026', title: 'Logbook : page d’accueil, nouvelle identité et nouveau menu', tag: 'Application', items: [
    'Nouvelle page d’accueil personnalisée, avec vos indicateurs clés selon vos accès.',
    'L’application devient « Logbook », avec sa charte graphique (couleurs, polices, logo), et le menu regroupe les anciens tableaux de bord sous « Tableaux de bord ».']},
  {date: 'Octobre 2026', title: 'Utilisateurs, catégories et droits d’accès', tag: 'Settings', items: [
    'Settings › Utilisateurs : le Super User crée les utilisateurs et choisit leur rôle (Standard, Administrateur ou catégorie).',
    'Catégories sur mesure : on nomme une catégorie et on coche les sections et sous-sections accessibles ; le serveur n’ouvre rien d’autre.']},
  {date: 'Octobre 2026', title: 'Projections annualisées', tag: 'Vue d’ensemble', items: [
    'Chiffre d’affaires : CA réalisé par mois (XC, CARS), CA espéré à encoder pour les mois à venir, comparaison avec l’année précédente.',
    'Marge brute et marge nette projetées à partir du CA espéré.']},
  {date: 'Octobre 2026', title: 'Contrôle des marges sur produits et sur devis TN11', tag: 'Détail XC', items: [
    'Contrôle des marges s/ produits : prix de vente, coût Odoo et coût réel estimé (achats et transport) des articles à code PIF.',
    'Contrôle des marges s/ TN11 : on dépose un devis PDF ; chaque ligne vendue est comparée à Odoo, avec le détail des nomenclatures et la main-d’œuvre.']},
  {date: 'Octobre 2026', title: 'Marge nette', tag: 'Vue d’ensemble', items: [
    'Nouvel onglet Marge nette (Vue d’ensemble, XC, CARS) avec personnel, véhicules, frais généraux, Shared Services, Management et marketing.',
    'Hypothèses d’imputation visibles et modifiables, avec simulation pour les utilisateurs qui ne sont pas propriétaires des valeurs de référence.']},
  {date: 'Septembre 2026', title: 'Service Vehicles, frais généraux et personnel', tag: 'Gestion', items: [
    'Imputation des frais de véhicules aux BU (carburant, agendas, rapprochement avec la comptabilité).',
    'Frais généraux et coûts de personnel par BU, avec fiches de paie.']},
];
